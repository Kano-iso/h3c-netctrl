"""H3C V7 端口绑定 / 解绑 CLI 模板

## 背景

端口绑定支持 2 种模式 (spec.md Requirement: 端口绑定 2 种模式):
  - Mode 1: service-instance + xconnect vsi (EVPN 标准)
  - Mode 2: port access vlan (传统 fallback)

## ADR

- ADR-104: service-instance 优先, access vlan fallback
"""

from typing import List

from app.services.sdn_device_adapter import VPCConfigTemplate


class H3cV7PortBindTemplate(VPCConfigTemplate):
    """H3C V7 端口绑定命令模板

    Args (context):
      - binding: SdnPortBinding (interface_name, service_instance, access_vlan)
      - vpc: SdnVpc (id)  -- 用于 vsi_name
      - mode: "auto" | "service_instance" | "access_vlan"

    Auto 模式: service_instance 非空 → Mode 1, 否则 Mode 2
    """

    def render(self, context: dict) -> List[dict]:
        binding = context["binding"]
        vpc = context["vpc"]
        mode = context.get("mode", "auto")

        vsi_name = f"vpc{vpc.id:04d}"
        iface = binding.interface_name

        # 模式决策 (ADR-104)
        if mode == "auto":
            use_service_instance = binding.service_instance is not None
        elif mode == "service_instance":
            use_service_instance = True
        elif mode == "access_vlan":
            use_service_instance = False
        else:
            raise ValueError(f"Unknown mode: {mode}, expected auto/service_instance/access_vlan")

        if use_service_instance:
            # Mode 1: service-instance + xconnect vsi (EVPN 标准)
            return [
                {"mode": "configure", "command": f"interface {iface}"},
                {"mode": "configure", "command": "  port link-mode bridge"},
                {"mode": "configure", "command": f"  service-instance {binding.service_instance}"},
                {"mode": "configure", "command": f"    xconnect vsi {vsi_name} access"},
            ]
        else:
            # Mode 2: port access vlan (传统 fallback)
            return [
                {"mode": "configure", "command": f"interface {iface}"},
                {"mode": "configure", "command": "  port link-mode bridge"},
                {"mode": "configure", "command": f"  port access vlan {binding.access_vlan}"},
            ]


class H3cV7PortUnbindTemplate(VPCConfigTemplate):
    """H3C V7 端口解绑命令模板（同时尝试 undo 2 种模式, 不会冲突）"""

    def render(self, context: dict) -> List[dict]:
        binding = context["binding"]
        vpc = context["vpc"]

        vsi_name = f"vpc{vpc.id:04d}"
        iface = binding.interface_name

        commands = [
            {"mode": "configure", "command": f"interface {iface}"},
        ]

        # 同时 undo service-instance 和 access vlan (任一未配置会被设备忽略)
        if binding.service_instance is not None:
            commands.append({"mode": "configure", "command": f"  undo service-instance {binding.service_instance}"})
        if binding.access_vlan is not None:
            commands.append({"mode": "configure", "command": f"  undo port access vlan {binding.access_vlan}"})

        return commands
