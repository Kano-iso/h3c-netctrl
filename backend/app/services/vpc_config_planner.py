"""VPCConfigPlanner — 把 SdnVpc / SdnPortBinding 转成有序双套 payload（v3.0 T3）

## 职责

- 输入: SdnVpc + SdnTenant (或 SdnPortBinding + SdnVpc)
- 输出: List[TemplateUnit]（v3.0 T3: 双套 payload，每 unit 含 cli + xml + undo）
- 序列化: 把 List[TemplateUnit] 转成 JSON 存到 SdnDeployment.planned_config

## ADR

- ADR-105: dry_run=True 不写 SdnDeployment (开发 / 排错工具)
- ADR-105: dry_run=False 由调用方决定是否写 DB (planner 本身只返回结果)
- ADR-110: render() 返回 List[TemplateUnit]（v3.0 T3）
- ADR-112: VPCConfigTemplate ABC render() 改 List[TemplateUnit]

## split 容器兼容

纯计算, 无 I/O, 可在 core / config 容器运行。
"""

from typing import List

from app.services.sdn_device_adapter import (
    SdnDeviceAdapter,
    TemplateUnit,
    deserialize_template_units,
    serialize_template_units,
)


class VPCConfigPlanner:
    """配置计划生成器（v3.0 T3: 适配 TemplateUnit 双套 payload）

    Args:
        adapter: SdnDeviceAdapter (决定命令拼装规则)
    """

    def __init__(self, adapter: SdnDeviceAdapter):
        self.adapter = adapter

    # ---- VPC 生命周期 ----

    def plan_vpc_create(
        self, vpc, tenant, dry_run: bool = True
    ) -> List[TemplateUnit]:
        """生成 VPC 创建双套 payload

        Args:
            vpc: SdnVpc (id, vni, cidr, gateway_ip, gateway_mac, vsi_interface)
            tenant: SdnTenant (l3_vni)
            dry_run: True (默认) = 不写 SdnDeployment, 仅返回 units

        Returns:
            List[TemplateUnit], 5 unit (H3C V7: vsi-l2/evpn/l3vpn/vsi-l3/global)

        Note:
            dry_run=False 时**不**自动写 SdnDeployment — 由调用方 router 处理
            (planner 保持纯计算, 易测试)
        """
        template = self.adapter.get_template("vpc_create")
        return template.render({"vpc": vpc, "tenant": tenant})

    def plan_vpc_delete(
        self, vpc, dry_run: bool = True
    ) -> List[TemplateUnit]:
        """生成 VPC 删除双套 payload (反向 create, 共享 l3vpn 保留)

        Returns:
            List[TemplateUnit], 3 unit (H3C V7: vsi-l2/evpn/vsi-l3, 共享 l3vpn/global 保留)
        """
        template = self.adapter.get_template("vpc_delete")
        return template.render({"vpc": vpc})

    # ---- 端口绑定 ----

    def plan_port_bind(
        self, binding, vpc, mode: str = "auto", dry_run: bool = True
    ) -> List[TemplateUnit]:
        """生成端口绑定双套 payload

        Args:
            binding: SdnPortBinding (interface_name, service_instance, access_vlan)
            vpc: SdnVpc (id)
            mode: auto | service_instance | access_vlan
            dry_run: 见 plan_vpc_create

        Returns:
            List[TemplateUnit], 1 unit (port-bind, 模式自适应)
        """
        template = self.adapter.get_template("port_bind")
        return template.render({"binding": binding, "vpc": vpc, "mode": mode})

    def plan_port_unbind(
        self, binding, vpc, dry_run: bool = True
    ) -> List[TemplateUnit]:
        """生成端口解绑双套 payload

        Returns:
            List[TemplateUnit], 1 unit (port-unbind)
        """
        template = self.adapter.get_template("port_unbind")
        return template.render({"binding": binding, "vpc": vpc})

    # ---- 序列化（v3.0 T3: 适配 TemplateUnit） ----

    @staticmethod
    def serialize(units: List[TemplateUnit]) -> str:
        """List[TemplateUnit] → JSON 字符串 (用于 SdnDeployment.planned_config)

        内部委托给 sdn_device_adapter.serialize_template_units
        """
        return serialize_template_units(units)

    @staticmethod
    def deserialize(json_str: str) -> List[TemplateUnit]:
        """JSON 字符串 → List[TemplateUnit] (用于 executor 解析 planned_config)

        内部委托给 sdn_device_adapter.deserialize_template_units
        """
        return deserialize_template_units(json_str)
