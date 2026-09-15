"""S1-027 设备 I/O 边界 fake（仅由 stack_backend_wrapper 注入；生产入口从不加载）。

三个 fake 覆盖本通道故事涉及的全部设备 I/O 入口：
- FakeNetconfClient   → 接口读取（app.routers.interface.NetconfClient）
- FakeExecutor        → 配置下发（app.routers.sdn_access.SdnDeploymentExecutor）
- FakeValidationCollector → 验证采集（app.routers.sdn_access.SdnValidationCollector）

每个 fake 把调用记录到 STACK_QA_DIR/device-io.log（launcher 事后断言：全部 fake、
无真实设备 I/O、目标 host 必须是 TEST-NET 合成地址）。FakeValidationCollector 的
行为由 STACK_QA_DIR/collector-mode 控制（fresh=回读成功 / insufficient=证据不足）。
"""

import json
import os
import time
from datetime import datetime, timedelta

from app.services.sdn_validation_collector import SdnValidationCollector

STACK_QA_DIR = os.environ.get("STACK_QA_DIR", "/tmp/stack-qa")
LOG_PATH = os.path.join(STACK_QA_DIR, "device-io.log")
MODE_PATH = os.path.join(STACK_QA_DIR, "collector-mode")


def _log(kind: str, **kw) -> None:
    os.makedirs(STACK_QA_DIR, exist_ok=True)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(json.dumps({"kind": kind, "at": round(time.time(), 3), **kw}, ensure_ascii=False) + "\n")


def _collector_mode() -> str:
    try:
        with open(MODE_PATH, encoding="utf-8") as f:
            return f.read().strip() or "fresh"
    except OSError:
        return "fresh"


# 合成接口回读（data namespace，与 tests/conftest 同构；解析逻辑走真实 _parse_interface_response）
IFMGR_XML = """<?xml version="1.0" encoding="UTF-8"?>
<data>
<top xmlns="http://www.h3c.com/netconf/config:1.0">
<Ifmgr>
<Interfaces>
<Interface><IfIndex>10</IfIndex><Name>GigabitEthernet1/0/10</Name><PVID>100</PVID></Interface>
<Interface><IfIndex>11</IfIndex><Name>GigabitEthernet1/0/11</Name><PVID>100</PVID></Interface>
</Interfaces>
</Ifmgr>
</top>
</data>"""


class FakeNetconfClient:
    """替代 app.netconf_client.NetconfClient：get/get_config 返回合成 XML，绝不连真机。"""

    def __init__(self, host, port, username, password, timeout=30, max_retries=2):
        _log("netconf_constructed", host=host, port=port, username=username)
        self.host = host
        self.port = port

    def __enter__(self):
        _log("netconf_enter")
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        _log("netconf_exit")
        return False

    def get(self, filter_xml: str) -> str:
        _log("netconf_get")
        return IFMGR_XML

    def get_config(self, filter_xml: str) -> str:
        _log("netconf_get_config")
        return IFMGR_XML

    def get_interface_name_by_index(self, if_index: int):
        if if_index < 4096:
            return f"GigabitEthernet1/0/{max(if_index, 1)}"
        return f"LoopBack{if_index - 5123}"

    def close(self):
        pass


class FakeExecutor:
    """替代 sdn_access.SdnDeploymentExecutor：按 attempt units 走 hooks 落库，绝不连真机。"""

    def execute(self, db, deployment_id, *, unit_hooks=None):
        from app.models import SdnAttemptUnit, SdnDeployment

        deployment = db.query(SdnDeployment).filter(SdnDeployment.id == deployment_id).first()
        _log("executor_execute", deployment_id=deployment_id,
             action=getattr(deployment, "action", None),
             vpc_id=getattr(deployment, "vpc_id", None),
             device_id=getattr(deployment, "device_id", None))
        if unit_hooks is not None:
            units = (
                db.query(SdnAttemptUnit)
                .filter(SdnAttemptUnit.attempt_id == unit_hooks.attempt_id)
                .order_by(SdnAttemptUnit.unit_index)
                .all()
            )
            for u in units:
                started = unit_hooks.before_unit(u.unit_index, u.unit_name)
                if started:
                    unit_hooks.after_unit_success(u.unit_index, u.unit_name)
                else:
                    unit_hooks.after_unit_failure(
                        u.unit_index, u.unit_name, definitive=True,
                        error="fake: dependency unit not started",
                    )
        deployment.status = "success"
        deployment.config_completed_at = datetime.utcnow()
        db.commit()
        _log("executor_success", deployment_id=deployment_id, action=getattr(deployment, "action", None))
        return deployment


class FakeValidationCollector(SdnValidationCollector):
    """替代 sdn_access.SdnValidationCollector：按 collector-mode 控制，绝不连真机。

    继承真实类以保留静态解析辅助（如 _has_display_error 被 _l2_ready_status
    直接以类名调用），只覆写 sync() 设备采集入口。
    """

    def sync(self, db, vpc_id, device_id, *, force=False, min_interval_seconds=600, scope_bindings=None):
        from app.models import SdnValidationSnapshot, SdnVpc

        mode = _collector_mode()
        _log("collector_sync", vpc_id=vpc_id, device_id=device_id, force=force, mode=mode)
        if mode == "insufficient":
            return None, {"key": "sdn.collection_failed", "detail": "fake collector: insufficient"}, False

        vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
        now = datetime.utcnow()
        snap = SdnValidationSnapshot(
            vpc_id=vpc_id,
            device_id=device_id,
            validation_result="active",
            collection_started_at=now - timedelta(seconds=1),
            collection_completed_at=now,
            snapshot_data=json.dumps({
                "commands": {
                    "display bgp peer l2vpn evpn": {"success": True, "output": "Peer: State: Established", "error": None},
                    ("display l2vpn vsi name %s verbose" % vpc.vsi_name) if vpc else "x": {"success": True, "output": "VSI State: Up", "error": None},
                    "display bgp l2vpn evpn": {"success": True, "output": "Route Type: [3]", "error": None},
                }
            }, ensure_ascii=False),
            validation_details=json.dumps({
                "vsi_exists": {"ok": True}, "vsi_up": {"ok": True}, "type3_present": {"ok": True},
                "raw_has_error": {"ok": True}, "bgp_peer_established": {"ok": True},
                "vsi_interface_exists": {"ok": True}, "l3_vni_present": {"ok": True},
            }, ensure_ascii=False),
        )
        db.add(snap)
        db.commit()
        _log("collector_snapshot", snapshot_id=snap.id, result=snap.validation_result)
        return snap, None, False
