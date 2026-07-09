"""SdnPreflight — VPC 下发前 6 项预检

## spec.md Requirement: SdnPreflight 6 项预检

| # | 检查项 | 失败时错误码 | 实现位置 |
|---|---|---|---|
| 1 | 设备型号在白名单 | SDN_DEVICE_MODEL_UNSUPPORTED | 本地 (adapter) |
| 2 | 设备 status == "online" | SDN_PREFLIGHT_FAILED | 本地 (DB) |
| 3 | VNI 在设备上未存在 | SDN_VPC_ALREADY_EXISTS | 设备侧 (L3) |
| 4 | VLAN 在设备上未占用 | SDN_VLAN_CONFLICT | 设备侧 (L3) |
| 5 | BGP peer 已 Established | SDN_BGP_PEER_NOT_ESTABLISHED | 设备侧 (L3) |
| 6 | l3vpn vpn-instance 已存在 | SDN_L3VPN_NOT_FOUND | 设备侧 (L3) |

## 设计

- 1 + 2: L2 阶段本地可检查, 由本模块实现
- 3 + 4 + 5 + 6: 设备侧状态需连 SSH/NETCONF, 不在 L2 范围
  - 本模块提供 check 方法签名 + 占位实现 (返 success=True 带 reason)
  - 真机检查由 vpc-apply.sh (L3 deploy) 在下发前执行
  - 避免 L2 模块做 I/O (split 容器兼容: core / config 容器无 SSH)
"""

from dataclasses import dataclass, field
from typing import List, Optional

from app.i18n_keys import err
from app.services.sdn_device_adapter import SdnDeviceAdapter


@dataclass
class PreflightResult:
    """预检结果

    success=True → 可下发
    success=False → 失败, error_key + reason 必填
    """
    success: bool
    error_key: Optional[object] = None  # I18nKey instance
    reason: Optional[str] = None
    commands: List[dict] = field(default_factory=list)  # 预留 (未来: 自动修复命令)

    def __bool__(self):
        return self.success


# 设备侧预检项目 — L2 阶段无 SSH 能力, 由 vpc-apply.sh 真机执行
DEVICE_SIDE_CHECKS = (
    "check_vpc_not_exists",
    "check_vlan_not_conflict",
    "check_bgp_peer_established",
    "check_l3vpn_exists",
)


class SdnPreflight:
    """VPC 下发前预检

    Args:
        adapter: SdnDeviceAdapter (型号白名单检查)
        db: SQLAlchemy Session (设备 status 检查)
    """

    def __init__(self, adapter: SdnDeviceAdapter, db):
        self.adapter = adapter
        self.db = db

    # ---- 1. 设备型号 ----

    def check_device_model(self, device) -> PreflightResult:
        """1. 设备型号在白名单 (本地检查, 0 I/O)"""
        model = getattr(device.asset, "model", None) if hasattr(device, "asset") and device.asset else None
        if not model:
            return PreflightResult(
                success=False,
                error_key=err.SDN_DEVICE_MODEL_UNSUPPORTED,
                reason=f"设备型号为空 (device.id={device.id}, asset 未采集)",
            )
        if not self.adapter.supports_model(model):
            return PreflightResult(
                success=False,
                error_key=err.SDN_DEVICE_MODEL_UNSUPPORTED,
                reason=f"设备型号不支持: model={model}",
            )
        return PreflightResult(success=True)

    # ---- 2. 设备 online ----

    def check_device_online(self, device) -> PreflightResult:
        """2. 设备 status == "online" (本地检查, DB)"""
        status = getattr(device, "status", None)
        if status != "online":
            return PreflightResult(
                success=False,
                error_key=err.SDN_PREFLIGHT_FAILED,
                reason=f"device offline (status={status})",
            )
        return PreflightResult(success=True)

    # ---- 3-6. 设备侧检查 (L2 阶段占位, 真机由 vpc-apply.sh 执行) ----

    def check_vpc_not_exists(self, device, vpc) -> PreflightResult:
        """3. VNI 在设备上未存在 — 设备侧, L2 占位

        真机: vpc-apply.sh 调 `display l2vpn vsi` 确认
        L2 占位: 返 success, 标注 deferred
        """
        return PreflightResult(
            success=True,
            reason="deferred: 设备侧检查由 vpc-apply.sh 执行",
        )

    def check_vlan_not_conflict(self, device, vpc) -> PreflightResult:
        """4. VLAN 在设备上未占用 — 设备侧, L2 占位"""
        return PreflightResult(
            success=True,
            reason="deferred: 设备侧检查由 vpc-apply.sh 执行",
        )

    def check_bgp_peer_established(self, device) -> PreflightResult:
        """5. BGP peer 已 Established — 设备侧, L2 占位"""
        return PreflightResult(
            success=True,
            reason="deferred: 设备侧检查由 vpc-apply.sh 执行",
        )

    def check_l3vpn_exists(self, device) -> PreflightResult:
        """6. l3vpn vpn-instance 已存在 — 设备侧, L2 占位"""
        return PreflightResult(
            success=True,
            reason="deferred: 设备侧检查由 vpc-apply.sh 执行",
        )

    # ---- 入口 ----

    def preflight_vpc_deploy(self, vpc, device) -> PreflightResult:
        """6 项预检顺序执行, 任一失败立即返回 (spec.md Requirement: SdnPreflight 6 项预检)

        Args:
            vpc: SdnVpc
            device: Device (ORM 模型)

        Returns:
            PreflightResult(success=..., error_key=..., reason=..., commands=[])
        """
        checks = [
            ("device_model", lambda: self.check_device_model(device)),
            ("device_online", lambda: self.check_device_online(device)),
            ("vpc_not_exists", lambda: self.check_vpc_not_exists(device, vpc)),
            ("vlan_not_conflict", lambda: self.check_vlan_not_conflict(device, vpc)),
            ("bgp_peer_established", lambda: self.check_bgp_peer_established(device)),
            ("l3vpn_exists", lambda: self.check_l3vpn_exists(device)),
        ]

        for name, check_fn in checks:
            result = check_fn()
            if not result.success:
                # 任一失败 → 立即返回
                return PreflightResult(
                    success=False,
                    error_key=result.error_key,
                    reason=f"[{name}] {result.reason}",
                )

        return PreflightResult(success=True, commands=[])
