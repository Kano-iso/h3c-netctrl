"""SDN/VPC display 状态采集与校验（v3.3）。

最小闭环：
- 手动同步或 10 分钟级别缓存复用；
- 通过 SSH display 命令采集 BGP EVPN / VSI / AC / MAC / ARP / Type-2/3；
- 写入 sdn_validation_snapshots，供前端展示直观状态。
"""

import json
import re
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.models import SdnPortBinding, SdnValidationSnapshot, SdnVpc
from app.utils.device_access import get_device_with_password


class SdnValidationCollector:
    """围绕一个 {vpc_id, device_id} 采集 SDN/VPC 状态。"""

    DEFAULT_MIN_INTERVAL_SECONDS = 600

    def sync(
        self,
        db: Session,
        vpc_id: int,
        device_id: int,
        *,
        force: bool = False,
        min_interval_seconds: int = DEFAULT_MIN_INTERVAL_SECONDS,
        scope_bindings: Optional[list[SdnPortBinding]] = None,
    ) -> tuple[Optional[SdnValidationSnapshot], Optional[dict], bool]:
        """同步状态快照。

        CR24: scope_bindings 为显式采集 scope（如 reconcile 的待对账绑定），
        无论其 status（planned/unbound 等）都追加目标接口回读命令；
        普通周期采集不传该参数，保持只采 active|expanding 的边界。

        Returns:
            (snapshot, error, cached)
        """
        vpc = db.query(SdnVpc).filter(SdnVpc.id == vpc_id).first()
        if not vpc:
            return None, {"key": "sdn.vpc_not_found", "params": {"id": vpc_id}}, False

        latest = self.latest(db, vpc_id, device_id)
        if latest and not force and self._is_fresh(latest, min_interval_seconds):
            return latest, None, True

        device, password, device_err = get_device_with_password(db, device_id)
        if device_err is not None:
            return None, {"key": device_err.error_key or "device.not_found", "params": {"id": device_id}}, False
        if not password:
            return None, {"key": "sdn.device_not_writable", "params": {"id": device_id}}, False

        bindings = (
            db.query(SdnPortBinding)
            .filter(
                SdnPortBinding.vpc_id == vpc_id,
                SdnPortBinding.device_id == device_id,
                SdnPortBinding.status.in_(("active", "expanding")),
            )
            .all()
        )

        commands = self._commands(vpc, bindings, scope_bindings=scope_bindings)
        started = datetime.utcnow()
        raw_results = self._collect(device, password, commands)
        completed = datetime.utcnow()
        snapshot_data = self._snapshot_data(commands, raw_results)
        validation_details = self._validate(vpc, bindings, snapshot_data)
        validation_result = self._overall(validation_details)

        snapshot = SdnValidationSnapshot(
            vpc_id=vpc_id,
            device_id=device_id,
            snapshot_data=json.dumps(snapshot_data, ensure_ascii=False),
            validation_result=validation_result,
            validation_details=json.dumps(validation_details, ensure_ascii=False),
            # CR8: 新快照落采集起止时间（真实采集窗口，不是 created_at）
            collection_started_at=started,
            collection_completed_at=completed,
        )
        db.add(snapshot)
        db.commit()
        db.refresh(snapshot)
        return snapshot, None, False

    @staticmethod
    def latest(db: Session, vpc_id: int, device_id: int) -> Optional[SdnValidationSnapshot]:
        return (
            db.query(SdnValidationSnapshot)
            .filter(
                SdnValidationSnapshot.vpc_id == vpc_id,
                SdnValidationSnapshot.device_id == device_id,
            )
            .order_by(SdnValidationSnapshot.id.desc())
            .first()
        )

    @staticmethod
    def to_response(snapshot: SdnValidationSnapshot, *, cached: bool = False) -> dict:
        return {
            "id": snapshot.id,
            "vpc_id": snapshot.vpc_id,
            "device_id": snapshot.device_id,
            "snapshot_data": json.loads(snapshot.snapshot_data or "{}"),
            "validation_result": snapshot.validation_result,
            "validation_details": json.loads(snapshot.validation_details or "{}"),
            "created_at": snapshot.created_at,
            "cached": cached,
        }

    @staticmethod
    def _is_fresh(snapshot: SdnValidationSnapshot, min_interval_seconds: int) -> bool:
        if min_interval_seconds <= 0:
            return False
        return snapshot.created_at >= datetime.now() - timedelta(seconds=min_interval_seconds)

    @staticmethod
    def _commands(vpc: SdnVpc, bindings: list[SdnPortBinding], scope_bindings: Optional[list[SdnPortBinding]] = None) -> list[str]:
        commands = [
            "display bgp peer l2vpn evpn",
            f"display current-configuration interface Vsi-interface{vpc.vsi_interface}",
            f"display l2vpn vsi name {vpc.vsi_name} verbose",
            "display l2vpn mac-address",
            "display evpn route arp",
            "display bgp l2vpn evpn",
        ]
        scoped = list(scope_bindings or [])
        if bindings or scoped:
            commands.append(f"display arp vpn-instance {SdnValidationCollector._sdn_l3vpn_name()}")
            seen: set[str] = set()
            for binding in list(bindings) + scoped:
                cmd = f"display current-configuration interface {binding.interface_name}"
                if cmd not in seen:
                    commands.append(cmd)
                    seen.add(cmd)
        return commands

    @staticmethod
    def _collect(device, password: str, commands: list[str]) -> list[dict]:
        from app.utils.ssh_executor import SSHExecutor

        ssh = SSHExecutor(device.host, 22, device.username, password, timeout=30)
        return ssh.execute_commands(commands, delay_ms=300)

    @staticmethod
    def _snapshot_data(commands: list[str], results: list[dict]) -> dict:
        by_command = {}
        for command, result in zip(commands, results):
            by_command[command] = {
                "success": bool(result.get("success")),
                "output": result.get("output", ""),
                "error": result.get("error"),
            }
        return {"commands": by_command}

    @staticmethod
    def _validate(vpc: SdnVpc, bindings: list[SdnPortBinding], snapshot_data: dict) -> dict:
        outputs = {
            cmd: data.get("output", "")
            for cmd, data in snapshot_data.get("commands", {}).items()
        }
        all_text = "\n".join(outputs.values())
        vsi_text = outputs.get(f"display l2vpn vsi name {vpc.vsi_name} verbose", "")
        vsi_if_text = outputs.get(
            f"display current-configuration interface Vsi-interface{vpc.vsi_interface}", ""
        )
        bgp_peer_text = outputs.get("display bgp peer l2vpn evpn", "")
        bgp_evpn_text = outputs.get("display bgp l2vpn evpn", "")
        arp_text = outputs.get(f"display arp vpn-instance {SdnValidationCollector._sdn_l3vpn_name()}", "")
        mac_text = outputs.get("display l2vpn mac-address", "")
        evpn_arp_text = outputs.get("display evpn route arp", "")

        details = {
            "bgp_peer_established": {
                "ok": "Established" in bgp_peer_text,
                "required": True,
            },
            "vsi_exists": {
                "ok": f"VSI Name: {vpc.vsi_name}" in vsi_text,
                "required": True,
            },
            "vsi_up": {
                "ok": "VSI State               : Up" in vsi_text,
                "required": bool(bindings),
            },
            "vsi_interface_exists": {
                "ok": f"interface Vsi-interface{vpc.vsi_interface}" in vsi_if_text,
                "required": True,
            },
            "l3_vni_present": {
                "ok": f"l3-vni {vpc.tenant.l3_vni}" in vsi_if_text if vpc.tenant else False,
                "required": True,
            },
            "type3_present": {
                "ok": SdnValidationCollector._type3_scoped(bgp_evpn_text, vpc.vni),
                "required": True,
            },
            "active_binding_count": {
                "value": len(bindings),
                "required": False,
            },
            "mac_present": {
                "ok": vpc.vsi_name in mac_text,
                "required": bool(bindings),
            },
            "arp_present": {
                "ok": any(self_ip in arp_text for self_ip in SdnValidationCollector._candidate_host_ips(arp_text)),
                "required": bool(bindings),
            },
            "type2_present": {
                "ok": "[2]" in bgp_evpn_text or "DL" in evpn_arp_text,
                "required": bool(bindings),
            },
            "raw_has_error": {
                "ok": not SdnValidationCollector._has_display_error(all_text),
                "required": True,
            },
        }
        return details

    @staticmethod
    def _overall(details: dict) -> str:
        required = [d for d in details.values() if isinstance(d, dict) and d.get("required")]
        if required and all(d.get("ok") is True for d in required):
            return "active"
        if any(d.get("ok") is True for d in required):
            return "degraded"
        return "failed"

    @staticmethod
    def _has_display_error(text: str) -> bool:
        return any(
            marker in text
            for marker in (
                "Incomplete command",
                "Unrecognized command",
                "Wrong parameter",
                "Too many parameters",
                "VPN-Instance does not exist",
            )
        )

    @staticmethod
    def _type3_scoped(text: str, vni: int) -> bool:
        """Type-3 按目标 VPC 的 Route distinguisher 归属判定（CR38）。

        只在目标 `Route distinguisher: 1:{vni}` 路由块中发现 `[3]` 才为真：
        - 输出按 `Route distinguisher:` 行分块（RD 与该关键字同行或紧随其后）；
        - 逐块精确提取 RD 并做等值比较（`1:2000` 与 `1:20000` 不串匹配）；
        - 其他 RD 块有 `[3]`、目标 RD 只有 `[2]`、或目标 RD 块缺失 → false（保守）。
        """
        target_rd = f"1:{vni}"
        blocks = re.split(r"(?im)^\s*Route distinguisher:\s*", text)
        for block in blocks[1:]:
            if not block.strip():
                continue
            m = re.match(r"([0-9]+:[0-9]+)\b", block.lstrip())
            if not m:
                continue
            if m.group(1) == target_rd:
                return "[3]" in block
        return False

    @staticmethod
    def _candidate_host_ips(text: str) -> list[str]:
        return re.findall(r"\b(?:\d{1,3}\.){3}\d{1,3}\b", text)

    @staticmethod
    def _sdn_l3vpn_name() -> str:
        from app.services.sdn_device_adapter import SDN_L3VPN_NAME

        return SDN_L3VPN_NAME
