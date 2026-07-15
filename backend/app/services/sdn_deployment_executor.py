"""SdnDeploymentExecutor — 业务配置下发的 NETCONF 执行器（v3.0 T3 双套 payload 路由版）

## 职责

读 SdnDeployment.planned_config → 解析为 List[TemplateUnit] → 按 device.platform 选
cli_commands 或 xml_payloads → NETCONF edit-config → 写回 status

## 架构定位

- 业务下发**只走 backend**：frontend → config 容器 → SdnDeploymentExecutor → NetconfClient → 设备
- ops-toolkit 容器**不参与**业务下发（仅供排错）
- 单 deployment 串行下发（H3C V7 SSH max-session 限制）

## 业务下发通道（按 device.platform 路由，ADR-109）

| Platform | 通道 | 适用设备 |
|---|---|---|
| LSTN（老芯片）| CLI 文本走 `<Configuration>` 包裹 | S6850 / S6805 / S6825 / S5560X / S6520X |
| RSTN（新芯片）| schema 化 NETCONF XML 直接下发 | V9850 / S9820 / S12500R / S6890 |

**真根因**（design.md T1.13d + T1.13e 3 维证据链）：
H3C Comware V7 L2VPN/EVPN/VXLAN 业务 NETCONF 实现走**芯片驱动**，
LSTN 老芯片不实现 schema 化 L2VPN（任何软件版本都不实现）。

## 设备白名单

仅 Leaf-04（192.168.100.5）和 Leaf-05（192.168.100.6）允许下发：
- .2 / .3 是 SDN 参考机器，仅读
- .177 是 test 设备，但下发目标限定 .5/.6

## 失败处理

- 失败立即停（不重试、不自动回滚）
- error 字段记录：失败 unit + payload 索引 + 原始 NETCONF 错误
- 人工决定是否手动 undo（VPC 创建无 transaction 概念）

## split 容器兼容

- 设备查询走 get_device_with_password（monolith 走本地，split 走 internal API）
- executor 本身在 config 容器
"""
import json
import logging
from typing import List, Optional

from sqlalchemy.orm import Session

from app.models import SdnDeployment
from app.netconf_client import NetconfClient, classify_netconf_error
from app.services.sdn_device_adapter import (
    H3C_V7_CONFIG_NS,
    H3C_V7_XC_NS,
    PLATFORM_LSTN,
    PLATFORM_RSTN,
    PLATFORM_UNKNOWN,
    TemplateUnit,
    deserialize_template_units,
    get_platform_for_model,
)
from app.utils.device_access import get_device_with_password

logger = logging.getLogger("app")


# 设备白名单：仅 Leaf-04 / Leaf-05（.5 / .6）允许下发
WRITABLE_HOST_SUFFIXES = (".5", ".6")


class SdnDeploymentError(Exception):
    """executor 内部错误（业务可处理的异常）"""
    def __init__(self, error_key, params: Optional[dict] = None, status_code: int = 422):
        super().__init__(error_key)
        self.error_key = error_key
        self.params = params or {}
        self.status_code = status_code


class SdnDeploymentExecutor:
    """业务配置下发执行器（v3.0 T3：按 device.platform 路由双套 payload）

    Usage:
        executor = SdnDeploymentExecutor()
        deployment = executor.execute(db, deployment_id=1)
    """

    def __init__(self):
        pass

    def execute(self, db: Session, deployment_id: int) -> SdnDeployment:
        """执行 deployment 下发（v3.0 T3 路由版）

        流程：
        1. 查 deployment + 校验（status == 'pending'、action == 'create'）
        2. 查 device + 解密密码 + 校验 host 白名单
        3. 解析 planned_config 为 List[TemplateUnit]（用 deserialize_template_units）
        4. 解析 device.platform（device.platform 优先，fallback 调 get_platform_for_model）
        5. NetconfClient context manager 按 device.platform 串行 edit_config
           - LSTN: 每条 unit.cli_commands 走 `<Configuration>` 包裹
           - RSTN: 每条 unit.xml_payloads 直接 schema 化 NETCONF
        6. 写回 status（success / failed + error）

        Args:
            db: SQLAlchemy Session
            deployment_id: SdnDeployment.id

        Returns:
            SdnDeployment（已写回 status / error，commit 到 DB）

        Raises:
            SdnDeploymentError: 校验失败（status / action / device / JSON / platform）
            异常会冒泡到 router 层，router 转 APIResponse
        """
        # 1. 查 deployment
        deployment = db.query(SdnDeployment).filter(SdnDeployment.id == deployment_id).first()
        if not deployment:
            raise SdnDeploymentError(
                "SDN_DEPLOYMENT_NOT_FOUND",
                params={"id": deployment_id},
                status_code=404,
            )

        # 2. 校验 status
        if deployment.status != "pending":
            raise SdnDeploymentError(
                "SDN_DEPLOYMENT_NOT_PENDING",
                params={"id": deployment_id, "status": deployment.status},
                status_code=409,
            )

        # 3. 校验 action（本 change 仅支持 create）
        if deployment.action != "create":
            raise SdnDeploymentError(
                "SDN_DEPLOYMENT_ACTION_NOT_SUPPORTED",
                params={"action": deployment.action},
                status_code=422,
            )

        # 4. 查 device + 校验
        device, password, device_err = get_device_with_password(db, deployment.device_id)
        if device_err is not None:
            # 透传 device_err 的 error_key（可能是 device.not_found / device.crypto_decrypt_failed 等）
            raise SdnDeploymentError(
                device_err.error_key or "SDN_DEVICE_NOT_FOUND",
                params={"id": deployment.device_id},
                status_code=404,
            )
        if not password:
            raise SdnDeploymentError(
                "SDN_DEVICE_NOT_WRITABLE",
                params={"name": device.name, "host": device.host},
                status_code=422,
            )

        # 5. 校验 host 白名单
        if not self._is_writable_host(device.host):
            raise SdnDeploymentError(
                "SDN_DEVICE_NOT_WRITABLE",
                params={"name": device.name, "host": device.host},
                status_code=422,
            )

        # 6. 解析 planned_config 为 List[TemplateUnit]
        try:
            units = self._parse_planned_config(deployment.planned_config)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            # 标记 failed
            deployment.status = "failed"
            deployment.error = f"planned_config 格式错误: {e}"
            db.commit()
            db.refresh(deployment)
            logger.error(f"sdn deploy: deployment {deployment_id} planned_config 解析失败: {e}")
            raise SdnDeploymentError(
                "SDN_PLANNED_CONFIG_INVALID",
                params={"id": deployment_id, "error": str(e)},
                status_code=500,
            )

        # 7. 解析 device.platform
        platform = self._resolve_platform(device)
        if platform == PLATFORM_UNKNOWN:
            # device.model 不在白名单（既不是 LSTN 也不是 RSTN）→ 拒绝下发
            asset_model = device.asset.model if device.asset is not None else None
            raise SdnDeploymentError(
                "SDN_DEVICE_PLATFORM_UNKNOWN",
                params={"model": asset_model or "<empty>", "name": device.name, "host": device.host},
                status_code=422,
            )

        # 8. 按 device.platform 路由串行 NETCONF edit_config
        try:
            self._apply_units(
                units=units,
                platform=platform,
                host=device.host,
                port=device.port,
                username=device.username,
                password=password,
            )
        except Exception as e:
            # 失败：记录 error + status=failed
            error_msg = classify_netconf_error(e) if hasattr(e, '__class__') else str(e)
            deployment.status = "failed"
            deployment.error = f"配置下发失败: {error_msg}"
            db.commit()
            db.refresh(deployment)
            logger.error(f"sdn deploy: deployment {deployment_id} NETCONF 失败 ({platform}): {error_msg}")
            # 业务视为已尝试下发（不是校验错），返回 200 + status=failed 由 router 处理
            return deployment

        # 9. 成功
        deployment.status = "success"
        deployment.error = None
        db.commit()
        db.refresh(deployment)
        logger.info(f"sdn deploy: deployment {deployment_id} 成功下发 {len(units)} 个 unit (platform={platform})")
        return deployment

    @staticmethod
    def _is_writable_host(host: str) -> bool:
        """设备 host 后缀校验：仅 .5 / .6 允许下发"""
        if not host:
            return False
        return any(host.endswith(suffix) for suffix in WRITABLE_HOST_SUFFIXES)

    @staticmethod
    def _resolve_platform(device) -> str:
        """解析 device.platform（v3.0 T3: device.platform 优先，fallback 调 get_platform_for_model）

        Args:
            device: Device ORM（需要 .platform 字段 + 可选 .asset.model 关联）

        Returns:
            "LSTN" | "RSTN" | "UNKNOWN"
        """
        # 优先用 device.platform 字段（alembic 009 后已存在）
        if device.platform in (PLATFORM_LSTN, PLATFORM_RSTN):
            return device.platform
        # 老数据：platform 字段为 None → 调 get_platform_for_model 推算
        # model 存在 device.asset.model（关联表）—— 没有 asset 时 model=None
        asset_model = device.asset.model if device.asset is not None else None
        return get_platform_for_model(asset_model)

    @staticmethod
    def _parse_planned_config(planned_config: Optional[str]) -> List[TemplateUnit]:
        """解析 planned_config JSON 字符串 → List[TemplateUnit]

        内部委托给 deserialize_template_units（统一校验 unit 结构）

        Raises:
            json.JSONDecodeError: JSON 格式错
            ValueError: TemplateUnit 结构错
        """
        return deserialize_template_units(planned_config)

    @staticmethod
    def _apply_units(
        units: List[TemplateUnit],
        platform: str,
        host: str,
        port: int,
        username: str,
        password: str,
    ) -> None:
        """按 device.platform 路由串行 NETCONF edit_config（v3.0 T3）

        Args:
            units: List[TemplateUnit]（从 planned_config 解析）
            platform: "LSTN" | "RSTN"
            host: 设备 host
            port: NETCONF 端口
            username: 设备用户名
            password: 设备密码

        Note:
            - LSTN: 每个 unit.cli_commands 逐条走 <Configuration>{cli}</Configuration>
            - RSTN: 每个 unit.xml_payloads 逐条直接 edit_config（已是完整 <config> XML）
            - 任一 unit 失败立即停 + 抛出
            - payload 索引从 1 开始记入日志
        """
        with NetconfClient(host, port, username, password) as client:
            unit_idx = 0
            for unit in units:
                unit_idx += 1
                # 按 platform 选 payload
                if platform == PLATFORM_LSTN:
                    payloads = unit.cli_commands
                    payload_kind = "cli"
                elif platform == PLATFORM_RSTN:
                    payloads = unit.xml_payloads
                    payload_kind = "xml"
                else:
                    # 防御性检查（_resolve_platform 已过滤，此处兜底）
                    raise SdnDeploymentError(
                        "SDN_DEVICE_PLATFORM_UNKNOWN",
                        params={"platform": platform},
                        status_code=422,
                    )

                # 跳过空 payload（LSTN 设备走空 cli_commands 不合理；
                # RSTN 设备 unit.xml_payloads 为空时 fallback 到 cli_commands 兜底）
                if not payloads:
                    if platform == PLATFORM_RSTN and unit.cli_commands:
                        # RSTN 平台上 unit.xml_payloads 为空（如 global unit）
                        # fallback 走 unit.cli_commands（CLI 文本也走 LSTN 通道，因为 RSTN 兼容 <Configuration>）
                        logger.info(
                            f"sdn deploy: [{unit_idx}/{len(units)}] {unit.name} "
                            f"RSTN 平台无 schema XML，fallback 走 CLI 通道"
                        )
                        payloads = unit.cli_commands
                        payload_kind = "cli-fallback"
                    else:
                        logger.warning(
                            f"sdn deploy: [{unit_idx}/{len(units)}] {unit.name} "
                            f"unit.{payload_kind} 为空，跳过"
                        )
                        continue

                # 逐条 payload 下发
                for payload_idx, payload in enumerate(payloads, 1):
                    if platform == PLATFORM_LSTN or payload_kind == "cli-fallback":
                        # LSTN 设备 / RSTN 平台 CLI fallback：CLI 文本走 <Configuration> 包裹
                        config_xml = (
                            f'<config xmlns:xc="{H3C_V7_XC_NS}">'
                            f'<top xmlns="{H3C_V7_CONFIG_NS}" xc:operation="merge">'
                            f"<Configuration>{payload}</Configuration>"
                            f"</top></config>"
                        )
                    else:
                        # RSTN 设备：payload 已是完整 schema 化 NETCONF XML，直接下发
                        config_xml = payload

                    logger.debug(
                        f"sdn deploy: unit[{unit_idx}/{len(units)}] "
                        f"{unit.name} payload[{payload_idx}/{len(payloads)}] "
                        f"kind={payload_kind} len={len(payload)}"
                    )
                    try:
                        client.edit_config(config_xml)
                    except Exception as e:
                        logger.error(
                            f"sdn deploy: unit[{unit_idx}] {unit.name} "
                            f"payload[{payload_idx}] 失败: {e}"
                        )
                        raise
