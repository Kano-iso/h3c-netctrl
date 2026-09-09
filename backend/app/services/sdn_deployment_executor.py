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

- 支持 create / delete / port_bind / port_unbind / gateway_delete
- 失败立即停（不重试、不自动回滚）
- error 字段记录：失败 unit + payload 索引 + 原始 NETCONF 错误
- 人工决定是否手动 undo（VPC 创建无 transaction 概念）

## split 容器兼容

- 设备查询走 get_device_with_password（monolith 走本地，split 走 internal API）
- executor 本身在 config 容器
"""
import json
import logging
from datetime import datetime
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
# v3.0 sdn-vpc-netconf-schema-xml T6: 跨平台对比 .26 (V9850 RSTN) 也加入白名单
# - .5 / .6 = S6850 LSTN（生产业务下发目标）
# - .26 = V9850 RSTN（跨平台对比验证，A 方案走 schema 化 NETCONF XML）
# - .2 / .3 是 SDN 参考机器，仅读
# - .177 是 test 设备，但下发目标限定 .5/.6/.26
WRITABLE_HOST_SUFFIXES = (".5", ".6", ".26")


class SdnDeploymentError(Exception):
    """executor 内部错误（业务可处理的异常）

    definitive=True 表示设备已给出确定性失败回读（failed_known）；
    definitive=False 表示传输超时/无响应（unknown），需 reconcile 对账。
    """
    def __init__(self, error_key, params: Optional[dict] = None, status_code: int = 422, definitive: bool = False):
        super().__init__(error_key)
        self.error_key = error_key
        self.params = params or {}
        self.status_code = status_code
        self.definitive = definitive


class SdnDeploymentExecutor:
    """业务配置下发执行器（v3.0 T3：按 device.platform 路由双套 payload）

    Usage:
        executor = SdnDeploymentExecutor()
        deployment = executor.execute(db, deployment_id=1)
    """

    def __init__(self):
        pass

    def execute(self, db: Session, deployment_id: int, *, unit_hooks=None) -> SdnDeployment:
        """执行 deployment 下发（v3.0 T3 路由版 + S1-006 短事务/逐单元证据）。

        流程（S1-006 CR1/CR2 修正）：
        1. 只读加载 deployment + 静态校验（action/device/白名单/解析/平台），
           此阶段不写 DB、不碰设备 I/O。
        2. 静态校验全过后，CAS pending->running 并 commit（短事务，claim 持久可见）。
        3. 才进入设备 I/O；逐单元经 unit_hooks 先落 started 再 I/O、I/O 后落终态。
        4. 终态（success/failed/unknown）由单元证据推导并 commit。

        unit_hooks: 可选对象，含 before_unit(index,name)/after_unit_success(index,name)/
                    after_unit_failure(index,name,definitive,error)。index 0-based，与
                    sdn_attempt_units.unit_index 对齐。
        """
        # 1. 只读加载
        deployment = db.query(SdnDeployment).filter(SdnDeployment.id == deployment_id).first()
        if not deployment:
            raise SdnDeploymentError("SDN_DEPLOYMENT_NOT_FOUND", params={"id": deployment_id}, status_code=404)

        # 2. 静态校验（无写、无 I/O）
        if deployment.action not in {"create", "delete", "port_bind", "port_unbind", "gateway_delete"}:
            raise SdnDeploymentError("SDN_DEPLOYMENT_ACTION_NOT_SUPPORTED", params={"action": deployment.action}, status_code=422)
        # 快速失败：非 pending 直接拒绝（不解析配置/不碰设备），CAS 在下方仍原子兜底
        if deployment.status != "pending":
            raise SdnDeploymentError("SDN_DEPLOYMENT_NOT_PENDING", params={"id": deployment_id, "status": deployment.status}, status_code=409)
        device, password, device_err = get_device_with_password(db, deployment.device_id)
        if device_err is not None:
            raise SdnDeploymentError(device_err.error_key or "SDN_DEVICE_NOT_FOUND", params={"id": deployment.device_id}, status_code=404)
        if not password:
            raise SdnDeploymentError("SDN_DEVICE_NOT_WRITABLE", params={"name": device.name, "host": device.host}, status_code=422)
        if not self._is_writable_host(device.host):
            raise SdnDeploymentError("SDN_DEVICE_NOT_WRITABLE", params={"name": device.name, "host": device.host}, status_code=422)
        try:
            units = self._parse_planned_config(deployment.planned_config)
        except (json.JSONDecodeError, ValueError, KeyError) as e:
            deployment.status = "failed"
            deployment.error = f"planned_config 格式错误: {e}"
            db.commit()
            db.refresh(deployment)
            raise SdnDeploymentError("SDN_PLANNED_CONFIG_INVALID", params={"id": deployment_id, "error": str(e)}, status_code=500)
        platform = self._resolve_platform(device)
        if platform == PLATFORM_UNKNOWN:
            asset_model = device.asset.model if device.asset is not None else None
            raise SdnDeploymentError("SDN_DEVICE_PLATFORM_UNKNOWN", params={"model": asset_model or "<empty>", "name": device.name, "host": device.host}, status_code=422)

        # 3. CAS 认领（短事务：claim 持久可见后才开始 I/O；单一 CAS 来源 = claim_deployment）
        try:
            from app.services.sdn_operation_service import claim_deployment, SdnOperationError as _SdnOpErr
            claim_deployment(db, deployment_id, attempt_id=getattr(unit_hooks, "attempt_id", None) or 0, operation_id=getattr(unit_hooks, "operation_id", None))
        except _SdnOpErr as e:
            db.expire_all()
            dep = db.query(SdnDeployment).filter(SdnDeployment.id == deployment_id).first()
            raise SdnDeploymentError("SDN_DEPLOYMENT_NOT_PENDING", params={"id": deployment_id, "status": dep.status if dep else "missing"}, status_code=409)
        db.commit()  # CR1: 短事务提交，第二个 Session 立即可见 running 且无法再认领
        db.refresh(deployment)

        # 4. 设备 I/O（逐单元证据经 unit_hooks 落库）
        try:
            self._apply_units(units=units, platform=platform, device=device, password=password, unit_hooks=unit_hooks)
        except SdnDeploymentError as e:
            ui = e.params.get("unit_index")
            definitive = e.definitive
            if ui is not None and unit_hooks is not None:
                # CR14: after_unit_failure 零行更新不得静默忽略——证据无法持久化时降级 unknown
                if not unit_hooks.after_unit_failure(ui, e.params.get("unit", "?"), e.definitive, e.params.get("error", "?")):
                    definitive = False
            deployment.status = "failed" if definitive else "unknown"
            deployment.error = f"配置下发失败: {e.error_key}: {e.params.get('error', '?')}"
            if definitive:
                deployment.config_completed_at = datetime.utcnow()
            db.commit()
            db.refresh(deployment)
            logger.error(f"sdn deploy: deployment {deployment_id} {deployment.status} ({platform})")
            return deployment
        except Exception as e:
            error_msg = classify_netconf_error(e)
            deployment.status = "unknown"
            deployment.error = f"配置下发结果未知: {error_msg}"
            db.commit()
            db.refresh(deployment)
            logger.error(f"sdn deploy: deployment {deployment_id} unknown ({platform}): {error_msg}")
            return deployment

        # 5. 成功
        deployment.status = "success"
        deployment.error = None
        deployment.config_completed_at = datetime.utcnow()
        self._mark_resource_success(deployment)
        db.commit()
        db.refresh(deployment)
        logger.info(f"sdn deploy: deployment {deployment_id} 成功下发 {len(units)} 个 unit (platform={platform})")
        return deployment

    @staticmethod
    def _mark_resource_success(deployment: SdnDeployment) -> None:
        """deployment 成功后回写资源状态。

        资源状态是前端用户视角入口；deployment 仍保留完整审计。
        """
        if deployment.action == "create" and deployment.vpc is not None:
            deployment.vpc.status = "active"
        elif deployment.action == "delete" and deployment.vpc is not None:
            deployment.vpc.status = "withdrawn"
        elif deployment.action == "gateway_delete" and deployment.vpc is not None:
            deployment.vpc.status = "degraded"
        elif deployment.action == "port_bind" and deployment.port_binding is not None:
            deployment.port_binding.status = "active"
        elif deployment.action == "port_unbind" and deployment.port_binding is not None:
            deployment.port_binding.status = "unbound"

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
        device,
        password: str,
        unit_hooks=None,
    ) -> None:
        """按 device.platform 路由业务下发，逐单元经 unit_hooks 落证据（S1-006 CR2）。"""
        if platform == PLATFORM_LSTN:
            host, port, username = device.host, 22, device.username
            SdnDeploymentExecutor._apply_units_via_ssh(units, host, port, username, password, unit_hooks)
        elif platform == PLATFORM_RSTN:
            host, port, username = device.host, device.port, device.username
            SdnDeploymentExecutor._apply_units_via_netconf(units, host, port, username, password, unit_hooks)
        else:
            raise SdnDeploymentError("SDN_DEVICE_PLATFORM_UNKNOWN", params={"platform": platform}, status_code=422)

    @staticmethod
    def _hook(unit_hooks, method, *args):
        """调用 hook 并返回其返回值；无 hook 视为允许（True）。"""
        if unit_hooks is not None and hasattr(unit_hooks, method):
            return getattr(unit_hooks, method)(*args)
        return True

    @staticmethod
    def _apply_units_via_ssh(units, host, port, username, password, unit_hooks=None) -> None:
        """LSTN 老芯片走 SSH 22 跑 system-view CLI（v3.0 T6 A 方案）

        每个 unit 独立一次 SSH 连接；失败立即停并抛 SdnDeploymentError。
        连接失败/超时 definitive=False（unknown），设备回读命令失败 definitive=True（failed_known）。
        """
        from app.utils.ssh_executor import SSHExecutor
        for unit_index, unit in enumerate(units):
            # CR14: before_unit CAS 失败（单元已非 not_started）必须阻止 I/O
            if not SdnDeploymentExecutor._hook(unit_hooks, "before_unit", unit_index, unit.name):
                raise SdnDeploymentError(
                    "SDN_UNIT_NOT_STARTABLE",
                    params={"unit": unit.name, "unit_index": unit_index, "error": "unit already started or terminal"},
                    status_code=409, definitive=False,
                )
            if not unit.cli_commands:
                logger.warning(f"ssh deploy: unit[{unit_index}] {unit.name} cli_commands 为空，跳过")
                if not SdnDeploymentExecutor._hook(unit_hooks, "after_unit_success", unit_index, unit.name):
                    raise SdnDeploymentError(
                        "SDN_UNIT_EVIDENCE_LOST",
                        params={"unit": unit.name, "unit_index": unit_index, "error": "unit terminal CAS failed"},
                        status_code=500, definitive=False,
                    )
                continue
            commands = ["system-view"] + list(unit.cli_commands) + ["return"]
            try:
                ssh = SSHExecutor(host, port, username, password, timeout=30)
                results = ssh.execute_commands(commands, delay_ms=300)
            except Exception as ssh_conn_err:
                raise SdnDeploymentError(
                    "SDN_DEPLOYMENT_SSH_FAILED",
                    params={"unit": unit.name, "unit_index": unit_index, "unit_idx": unit_index + 1,
                            "stage": "ssh_connect",
                            "error": f"SSH 连接失败: {type(ssh_conn_err).__name__}: {ssh_conn_err}"[:300]},
                    status_code=502, definitive=False,
                )
            failed = [r for r in results if not r.get("success", False)]
            if failed:
                failed_cmd = failed[0]
                raise SdnDeploymentError(
                    "SDN_DEPLOYMENT_SSH_FAILED",
                    params={"unit": unit.name, "unit_index": unit_index, "unit_idx": unit_index + 1,
                            "stage": "cmd_failed", "cmd": failed_cmd.get("cmd", ""),
                            "error": (failed_cmd.get("error") or failed_cmd.get("output", ""))[:200]},
                    status_code=502, definitive=True,
                )
            # CR14: after_unit_success 零行更新不得静默忽略
            if not SdnDeploymentExecutor._hook(unit_hooks, "after_unit_success", unit_index, unit.name):
                raise SdnDeploymentError(
                    "SDN_UNIT_EVIDENCE_LOST",
                    params={"unit": unit.name, "unit_index": unit_index, "error": "unit terminal CAS failed"},
                    status_code=500, definitive=False,
                )

    @staticmethod
    def _apply_units_via_netconf(units, host, port, username, password, unit_hooks=None) -> None:
        """RSTN 新芯片走 NETCONF 830 schema 化 XML edit-config。"""
        with NetconfClient(host, port, username, password) as client:
            for unit_index, unit in enumerate(units):
                # CR14: before_unit CAS 失败必须阻止 I/O
                if not SdnDeploymentExecutor._hook(unit_hooks, "before_unit", unit_index, unit.name):
                    raise SdnDeploymentError(
                        "SDN_UNIT_NOT_STARTABLE",
                        params={"unit": unit.name, "unit_index": unit_index, "error": "unit already started or terminal"},
                        status_code=409, definitive=False,
                    )
                if not unit.xml_payloads:
                    logger.warning(f"netconf deploy: unit[{unit_index}] {unit.name} xml_payloads 为空，跳过")
                    if not SdnDeploymentExecutor._hook(unit_hooks, "after_unit_success", unit_index, unit.name):
                        raise SdnDeploymentError(
                            "SDN_UNIT_EVIDENCE_LOST",
                            params={"unit": unit.name, "unit_index": unit_index, "error": "unit terminal CAS failed"},
                            status_code=500, definitive=False,
                        )
                    continue
                for payload_idx, payload in enumerate(unit.xml_payloads, 1):
                    try:
                        client.edit_config(payload)
                    except Exception as e:
                        definitive = "timeout" not in str(e).lower() and "no response" not in str(e).lower()
                        raise SdnDeploymentError(
                            "SDN_DEPLOYMENT_NETCONF_FAILED",
                            params={"unit": unit.name, "unit_index": unit_index, "unit_idx": unit_index + 1,
                                    "payload_idx": payload_idx, "error": str(e)[:200]},
                            status_code=502, definitive=definitive,
                        )
                # CR14: after_unit_success 零行更新不得静默忽略
                if not SdnDeploymentExecutor._hook(unit_hooks, "after_unit_success", unit_index, unit.name):
                    raise SdnDeploymentError(
                        "SDN_UNIT_EVIDENCE_LOST",
                        params={"unit": unit.name, "unit_index": unit_index, "error": "unit terminal CAS failed"},
                        status_code=500, definitive=False,
                    )
