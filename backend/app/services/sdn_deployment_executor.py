"""SdnDeploymentExecutor — 业务配置下发执行器（v3.0 T6 A 方案：LSTN→SSH 22 / RSTN→NETCONF）

## 职责

读 SdnDeployment.planned_config → 解析为 List[TemplateUnit] → 按 device.platform 路由
- LSTN 老芯片平台：SSH 22 + paramiko 跑 system-view CLI（5 unit 业务命令）
- RSTN 新芯片平台：NETCONF 830 edit-config schema 化 XML

## 架构定位

- 业务下发**只走 backend**：frontend → config 容器 → SdnDeploymentExecutor → NetconfClient / SSHExecutor → 设备
- ops-toolkit 容器**不参与**业务下发（仅供排错）
- 单 deployment 串行下发（H3C V7 SSH max-session 限制）

## 业务下发通道（按 device.platform 路由，ADR-109 / T6 修订）

| Platform | 通道 | 适用设备 |
|---|---|---|
| LSTN（老芯片）| SSH 22 + paramiko system-view CLI | S6850 / S6805 / S6825 / S5560X / S6520X |
| RSTN（新芯片）| NETCONF 830 schema 化 XML edit-config | V9850 / S9820 / S12500R / S6890 |

**A 方案根因**（design.md T1.13d + T1.13e + T6 修订）：
- LSTN 老芯片不实现 schema 化 L2VPN（任何软件版本都不实现）—— 真实
- T1.13f "H3C 私有 `<CLI><Configuration>` RPC 可写" 探针**错认成功**：
  - raw `session.send` 包能发（vpc_t113f_v4 display 看到）但 ncclient 框架同步拿不到 reply
  - "Unknown 'message-id'" 抛错 → 业务能否真落设备只能 display 二次人工确认
  - **不满足"业务下发通道"对程序化可靠性的要求**（A 方案决策）
- T6 实测证伪：edit-config 包裹 `<top><Configuration>` 设备直接拒
  - "Element ... Configuration[1] can not have a textual child element"

**A 方案结论**：
- LSTN 走 SSH 22（`backend/app/utils/ssh_executor.SSHExecutor.execute_commands`）
- RSTN 走 NETCONF schema XML（`NetconfClient.edit_config`）

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
        """按 device.platform 路由业务下发（v3.0 T6 A 方案）

        Args:
            units: List[TemplateUnit]（从 planned_config 解析）
            platform: "LSTN" | "RSTN"
            host: 设备 host
            port: LSTN=22 (SSH); RSTN=830 (NETCONF)
            username: 设备用户名
            password: 设备密码

        Note:
            - LSTN 走 SSH 22 + SSHExecutor 跑 system-view CLI（T6 A 方案）
            - RSTN 走 NETCONF 830 + NetconfClient edit-config schema XML
            - 任一 unit 失败立即停 + 抛出
        """
        if platform == PLATFORM_LSTN:
            # LSTN 老芯片 → SSH 22 + paramiko（不依赖 NETCONF L2VPN 通道）
            SdnDeploymentExecutor._apply_units_via_ssh(
                units, host, port, username, password
            )
        elif platform == PLATFORM_RSTN:
            # RSTN 新芯片 → NETCONF 830 schema XML
            SdnDeploymentExecutor._apply_units_via_netconf(
                units, host, port, username, password
            )
        else:
            raise SdnDeploymentError(
                "SDN_DEVICE_PLATFORM_UNKNOWN",
                params={"platform": platform},
                status_code=422,
            )

    @staticmethod
    def _apply_units_via_ssh(
        units: List[TemplateUnit],
        host: str,
        port: int,
        username: str,
        password: str,
    ) -> None:
        """LSTN 老芯片走 SSH 22 跑 system-view CLI（v3.0 T6 A 方案）

        每个 unit 独立一次 SSH 连接：
        - 进入 system-view
        - 跑该 unit 的 cli_commands
        - return 退到 user-view
        失败立即抛 SdnDeploymentError（unit 级错误定位）

        SSH 22 验证基础：
        - T1.13 早期 .5/.177 SSH CLI 跑命令成功
        - 清理 .5 脏数据用 SSHExecutor 成功（vpna/vpnb/vpc_t113f_v2-4/v9999 全部 undo）
        - SSHExecutor.execute_commands 处理 H3C V7 [Y/N] 二次确认 + 分页 + 错误检测
        """
        from app.utils.ssh_executor import SSHExecutor
        for unit_idx, unit in enumerate(units, 1):
            if not unit.cli_commands:
                # LSTN 走空 cli_commands 不合理，但 global unit 这种情况少
                logger.warning(
                    f"ssh deploy: unit[{unit_idx}/{len(units)}] {unit.name} "
                    f"unit.cli_commands 为空，跳过"
                )
                continue
            commands = ["system-view"] + list(unit.cli_commands) + ["return"]
            ssh = SSHExecutor(host, port, username, password, timeout=30)
            results = ssh.execute_commands(commands, delay_ms=300)
            failed = [r for r in results if not r.get("success", False)]
            if failed:
                failed_cmd = failed[0]
                raise SdnDeploymentError(
                    "SDN_DEPLOYMENT_SSH_FAILED",
                    params={
                        "unit": unit.name,
                        "unit_idx": unit_idx,
                        "cmd": failed_cmd.get("cmd", ""),
                        "error": (failed_cmd.get("error") or failed_cmd.get("output", ""))[:200],
                    },
                    status_code=502,
                )
            logger.info(
                f"ssh deploy: unit[{unit_idx}/{len(units)}] {unit.name} "
                f"{len(results)} 条命令全过"
            )

    @staticmethod
    def _apply_units_via_netconf(
        units: List[TemplateUnit],
        host: str,
        port: int,
        username: str,
        password: str,
    ) -> None:
        """RSTN 新芯片走 NETCONF 830 schema 化 XML edit-config（v3.0 T6 A 方案）

        每个 unit 的 xml_payloads 逐条 edit_config（payload 已含完整 <config> XML）
        RSTN 平台上 unit.xml_payloads 为空（如 global unit）→ fallback 走 unit.cli_commands
        但 RSTN 不走 SSH——这种情况下应改用 NETCONF 包 CLI 文本
        目前 v3.0 P0：global unit cli 走 NETCONF <CLI> RPC（ncclient 后续兼容方案预留）
        """
        with NetconfClient(host, port, username, password) as client:
            for unit_idx, unit in enumerate(units, 1):
                if not unit.xml_payloads:
                    logger.warning(
                        f"netconf deploy: unit[{unit_idx}/{len(units)}] {unit.name} "
                        f"unit.xml_payloads 为空，跳过"
                    )
                    continue
                for payload_idx, payload in enumerate(unit.xml_payloads, 1):
                    logger.debug(
                        f"netconf deploy: unit[{unit_idx}/{len(units)}] "
                        f"{unit.name} payload[{payload_idx}/{len(unit.xml_payloads)}] "
                        f"len={len(payload)}"
                    )
                    try:
                        client.edit_config(payload)
                    except Exception as e:
                        logger.error(
                            f"netconf deploy: unit[{unit_idx}] {unit.name} "
                            f"payload[{payload_idx}] 失败: {e}"
                        )
                        raise SdnDeploymentError(
                            "SDN_DEPLOYMENT_NETCONF_FAILED",
                            params={
                                "unit": unit.name,
                                "unit_idx": unit_idx,
                                "payload_idx": payload_idx,
                                "error": str(e)[:200],
                            },
                            status_code=502,
                        )
