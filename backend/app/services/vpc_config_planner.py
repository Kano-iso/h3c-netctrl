"""VPCConfigPlanner — 把 SdnVpc / SdnPortBinding 转成有序命令序列

## 职责

- 输入: SdnVpc + SdnTenant (或 SdnPortBinding + SdnVpc)
- 输出: List[ConfigCommand] = List[{mode, command}]
- 序列化: 把 List 转成 JSON 存到 SdnDeployment.planned_config

## ADR

- ADR-105: dry_run=True 不写 SdnDeployment (开发 / 排错工具)
- ADR-105: dry_run=False 由调用方决定是否写 DB (planner 本身只返回结果)

## split 容器兼容

纯计算, 无 I/O, 可在 core / config 容器运行。
"""

import json
from typing import List, Optional

from app.services.sdn_device_adapter import SdnDeviceAdapter


# ConfigCommand 类型契约: {mode: "configure", command: str}
# mode 预留给未来扩展 (system-view / interface view)
ConfigCommand = dict


class VPCConfigPlanner:
    """配置计划生成器

    Args:
        adapter: SdnDeviceAdapter (决定命令拼装规则)
    """

    def __init__(self, adapter: SdnDeviceAdapter):
        self.adapter = adapter

    # ---- VPC 生命周期 ----

    def plan_vpc_create(
        self, vpc, tenant, dry_run: bool = True
    ) -> List[ConfigCommand]:
        """生成 VPC 创建命令序列

        Args:
            vpc: SdnVpc (id, vni, cidr, gateway_ip, gateway_mac, vsi_interface)
            tenant: SdnTenant (l3_vni)
            dry_run: True (默认) = 不写 SdnDeployment, 仅返回命令

        Returns:
            List[ConfigCommand], 14 条 (H3C V7)

        Note:
            dry_run=False 时**不**自动写 SdnDeployment — 由调用方 router 处理
            (planner 保持纯计算, 易测试)
        """
        template = self.adapter.get_template("vpc_create")
        return template.render({"vpc": vpc, "tenant": tenant})

    def plan_vpc_delete(
        self, vpc, dry_run: bool = True
    ) -> List[ConfigCommand]:
        """生成 VPC 删除命令序列 (反向 create, 共享 l3vpn 保留)"""
        template = self.adapter.get_template("vpc_delete")
        return template.render({"vpc": vpc})

    # ---- 端口绑定 ----

    def plan_port_bind(
        self, binding, vpc, mode: str = "auto", dry_run: bool = True
    ) -> List[ConfigCommand]:
        """生成端口绑定命令序列

        Args:
            binding: SdnPortBinding (interface_name, service_instance, access_vlan)
            vpc: SdnVpc (id)
            mode: auto | service_instance | access_vlan
            dry_run: 见 plan_vpc_create
        """
        template = self.adapter.get_template("port_bind")
        return template.render({"binding": binding, "vpc": vpc, "mode": mode})

    def plan_port_unbind(
        self, binding, vpc, dry_run: bool = True
    ) -> List[ConfigCommand]:
        """生成端口解绑命令序列"""
        template = self.adapter.get_template("port_unbind")
        return template.render({"binding": binding, "vpc": vpc})

    # ---- 序列化 ----

    @staticmethod
    def serialize(commands: List[ConfigCommand]) -> str:
        """List[ConfigCommand] → JSON 字符串 (用于 SdnDeployment.planned_config)"""
        return json.dumps(commands, ensure_ascii=False)

    @staticmethod
    def deserialize(json_str: str) -> List[ConfigCommand]:
        """JSON 字符串 → List[ConfigCommand] (用于 ops-toolkit 读取)"""
        return json.loads(json_str)
