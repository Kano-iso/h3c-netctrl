"""v3.0 SDN 设备型号适配层

## 背景

v3.0 SDN 仅支持 H3C Comware V7 系列交换机（型号 S6850 / S6850-56HF 等）。
其他型号（H3C V5 / Cisco NXOS / Huawei CE）在 v3.0 P0 暂不支持。

## 职责

`SdnDeviceAdapter` 抽象基类只做几件事：
1. 型号识别（`supports_model`）：决定一个 device.asset.model 是否能用本适配器
2. 模板路由（`get_template`）：根据动作（vpc_create / vpc_delete / port_bind / port_unbind）返回对应模板
3. **platform 识别**（`get_platform` / `get_platform_for_model`）：根据 device.model 映射到 LSTN / RSTN

实际命令拼装由 `H3cV7VpcCreateTemplate` / `H3cV7VpcDeleteTemplate` /
`H3cV7PortBindTemplate` / `H3cV7PortUnbindTemplate` 完成（双套 payload）。

## 设备 Platform（v3.0 sdn-vpc-netconf-schema-xml T1.13d + T1.13e 探针结论）

| Platform | 芯片 | 设备型号 | L2VPN NETCONF 通道 |
|---|---|---|---|
| **LSTN** | 老芯片 | S6850 / S6850-56HF / S6850-54HF / S6805 / S6825 / S5560X / S6520X | **CLI 文本**走 NETCONF `<Configuration>` 通道 |
| **RSTN** | 新芯片 | V9850 / S9820 / S12500R / S6890 | **schema 化 NETCONF XML** |

**真根因**（3 维证据链）：
- T1.13a：H3C V7 不接受 `<Configuration>{cli}</Configuration>` 文本子节点（**已被 T1.13f 推翻**）
- T1.13d：.26 V9850 (RSTN) schema 化 NETCONF L2VPN **完整可写**
- T1.13e：.177 S6850 (LSTN) schema 化 NETCONF L2VPN **不可达**（与 .5 R6555 行为相同）
- **device platform (LSTN vs RSTN)** 决定 L2VPN NETCONF 可达性，与软件版本无关

业务下发按 **device.platform 路由**：LSTN 走 CLI、RSTN 走 schema XML。

## 未来扩展

- v3.0.1+ 增加 H3cV5Adapter / CiscoAdapter / HuaweiAdapter
- 每个 adapter 独立 class，零侵入
"""

import json
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from typing import List, Optional

from app.i18n_keys import err, error_response
from app.schemas import APIResponse


# v3.0 P0 唯一支持的设备型号（基于现有设备清单）
# ADR-101: 硬编码白名单, 不连数据库查
H3C_V7_SUPPORTED_MODELS: List[str] = [
    "S6850",
    "S6850-56HF",
    "S6850-54HF",
]


# v3.0 sdn-vpc-netconf-schema-xml T3: device model → platform 映射
# 真根因：H3C V7 L2VPN/EVPN/VXLAN 业务 NETCONF 实现走芯片驱动
# - LSTN 老芯片：L2VPN schema 化 NETCONF 不可达
# - RSTN 新芯片：L2VPN schema 化 NETCONF 完整可写
#
# 映射规则：子串匹配（任一关键字出现在 model 中）
H3C_V7_PLATFORM_BY_MODEL = {
    # LSTN 老芯片平台
    "S6850": "LSTN",
    "S6850-56HF": "LSTN",
    "S6850-54HF": "LSTN",
    "S6805": "LSTN",
    "S6825": "LSTN",
    "S5560X": "LSTN",
    "S6520X": "LSTN",
    # RSTN 新芯片平台
    "V9850": "RSTN",
    "S9820": "RSTN",
    "S12500R": "RSTN",
    "S6890": "RSTN",
}


# v3.0 sdn-vpc-netconf-schema-xml T3: H3C V7 NETCONF 命名空间 + 操作常量
# 供模板层 + executor 共享（避免各处硬编码字符串）
H3C_V7_CONFIG_NS = "http://www.h3c.com/netconf/config:1.0"  # 业务配置 namespace
H3C_V7_XC_NS = "urn:ietf:params:xml:ns:netconf:base:1.0"    # NETCONF base xc: namespace
H3C_V7_OP_CREATE = "create"   # xc:operation="create"
H3C_V7_OP_DELETE = "delete"   # xc:operation="delete"
H3C_V7_OP_MERGE = "merge"     # xc:operation="merge"
H3C_V7_OP_REPLACE = "replace" # xc:operation="replace"


# 平台常量（与 H3C_V7_PLATFORM_BY_MODEL values 对应）
PLATFORM_LSTN = "LSTN"  # L2VPN 业务走 CLI 文本
PLATFORM_RSTN = "RSTN"  # L2VPN 业务走 schema 化 NETCONF XML
PLATFORM_UNKNOWN = "UNKNOWN"  # model 不在白名单（executor 拒绝下发）


@dataclass
class TemplateUnit:
    """v3.0 sdn-vpc-netconf-schema-xml T3: VPC 配置命令的"5 unit 之一"。

    同一业务在 LSTN / RSTN 设备上的"配置语言"完全不同，因此每个 unit
    同时输出 cli_commands（CLI 文本）+ xml_payloads（schema 化 NETCONF XML）
    两套 payload，executor 按 device.platform 选一套下发。

    Attributes:
        name: Unit 标识（"vsi-l2" | "evpn" | "l3vpn" | "vsi-l3" | "port-bind" | "global"）
        description: Unit 描述（中文，给前端/排错用）
        cli_commands: LSTN 走 CLI 文本（List[str]，每条 system-view 下的命令）
        xml_payloads: RSTN 走 schema 化 NETCONF XML（List[str]，每条完整 <config> XML）
        undo_cli: LSTN 走 CLI 文本反向（VPC 删除/回滚用）
        undo_xml: RSTN 走 schema 化 NETCONF XML 反向（VPC 删除/回滚用）
    """
    name: str
    description: str
    cli_commands: List[str]
    xml_payloads: List[str]
    undo_cli: List[str] = field(default_factory=list)
    undo_xml: List[str] = field(default_factory=list)


# v3.0 业务 unit 标识常量（用于 SdnDeployment.unit 字段）
UNIT_VSI_L2 = "vsi-l2"
UNIT_EVPN = "evpn"
UNIT_L3VPN = "l3vpn"
UNIT_VSI_L3 = "vsi-l3"
UNIT_PORT_BIND = "port-bind"
UNIT_GLOBAL = "global"
UNIT_PORT_UNBIND = "port-unbind"
UNIT_VPC_CREATE_ALL = "vpc-create-all"  # 老数据兼容（全量下发）


# ─────────── TemplateUnit 序列化 helper（v3.0 T3） ───────────

def template_units_to_dicts(units: List["TemplateUnit"]) -> List[dict]:
    """List[TemplateUnit] → List[dict]（用于 SdnDeployment.planned_config JSON 序列化）

    放在 adapter 层（不放在具体模板类）避免循环引用；planner / executor / router 共享。
    """
    return [
        {
            "name": u.name,
            "description": u.description,
            "cli_commands": u.cli_commands,
            "xml_payloads": u.xml_payloads,
            "undo_cli": u.undo_cli,
            "undo_xml": u.undo_xml,
        }
        for u in units
    ]


def dicts_to_template_units(data: List[dict]) -> List["TemplateUnit"]:
    """List[dict] → List[TemplateUnit]（用于 executor 解析 planned_config）

    Raises:
        ValueError: 任一 unit 缺 name / cli_commands / xml_payloads（任一为空视为非法结构）
    """
    if not data:
        raise ValueError("planned_config unit 列表为空")
    units = []
    for idx, d in enumerate(data):
        if not isinstance(d, dict):
            raise ValueError(f"unit[{idx}] 不是 dict: {type(d).__name__}")
        if "name" not in d or not d["name"]:
            raise ValueError(f"unit[{idx}] 缺 name 字段")
        cli = d.get("cli_commands", [])
        xml = d.get("xml_payloads", [])
        if not isinstance(cli, list) or not isinstance(xml, list):
            raise ValueError(f"unit[{idx}] cli_commands/xml_payloads 必须是 list")
        # 至少有一个 payload（否则该 unit 实际无法下发任何配置）
        if not cli and not xml:
            raise ValueError(
                f"unit[{idx}] name={d['name']} cli_commands 和 xml_payloads 同时为空"
            )
        units.append(TemplateUnit(
            name=d["name"],
            description=d.get("description", ""),
            cli_commands=cli,
            xml_payloads=xml,
            undo_cli=d.get("undo_cli", []),
            undo_xml=d.get("undo_xml", []),
        ))
    return units


# 顶层 JSON 序列化 / 反序列化 alias（test / planner 友好）
# 实际数据流：template_units_to_dicts → json.dumps → DB string → json.loads → dicts_to_template_units


def serialize_template_units(units: List["TemplateUnit"]) -> str:
    """List[TemplateUnit] → JSON 字符串（用于 DB 存储 / SdnDeployment.planned_config）"""
    return json.dumps(template_units_to_dicts(units), ensure_ascii=False)


def deserialize_template_units(json_str: str) -> List["TemplateUnit"]:
    """JSON 字符串 → List[TemplateUnit]（用于 executor / 测试回放）"""
    if not json_str:
        raise ValueError("planned_config 为空")
    data = json.loads(json_str)
    if not isinstance(data, list):
        raise ValueError("planned_config 不是 list")
    return dicts_to_template_units(data)


@lru_cache(maxsize=128)
def get_platform_for_model(model: Optional[str]) -> str:
    """根据 device model 推导 platform（v3.0 sdn-vpc-netconf-schema-xml T3）

    Args:
        model: device.model 字符串（如 "S6850-56HF" / "V9850-256H"）

    Returns:
        "LSTN" | "RSTN" | "UNKNOWN"
        - LSTN: 老芯片平台，L2VPN 业务走 CLI-over-NETCONF
        - RSTN: 新芯片平台，L2VPN 业务走 schema 化 NETCONF
        - UNKNOWN: model 不在白名单（executor 应拒绝下发）

    Note:
        - 大小写不敏感
        - 子串匹配（任一关键字出现在 model 中）
        - lru_cache 缓存结果（executor 每次下发都调用，避免重复匹配）
    """
    if not model:
        return PLATFORM_UNKNOWN
    model_upper = model.upper()
    # 优先精确匹配（处理 "S6850" 不匹配 "S68500" 的边界情况）
    for kw, platform in H3C_V7_PLATFORM_BY_MODEL.items():
        if model_upper == kw.upper():
            return platform
    # 回退到子串匹配
    for kw, platform in H3C_V7_PLATFORM_BY_MODEL.items():
        if kw.upper() in model_upper:
            return platform
    return PLATFORM_UNKNOWN


class VPCConfigTemplate(ABC):
    """VPC 配置命令模板抽象基类（v3.0 T3: render() 返回 List[TemplateUnit]）

    子类: H3cV7VpcCreateTemplate / H3cV7VpcDeleteTemplate
           H3cV7PortBindTemplate / H3cV7PortUnbindTemplate
    """

    @abstractmethod
    def render(self, context: dict) -> List[TemplateUnit]:
        """渲染模板, 返回 List[TemplateUnit]（v3.0 T3: 5 unit 双套 payload）

        Args:
            context: 模板变量字典（vpc / tenant / port_binding / device）
                     - vpc: SdnVpc (id, vni, cidr, gateway_ip, gateway_mac, vsi_interface, vsi_name)
                     - tenant: SdnTenant (rd, l3_vni)
                     - binding: SdnPortBinding (interface_name, service_instance, access_vlan)
                     - device: Device ORM（用于 platform 识别，可选）

        Returns:
            List[TemplateUnit], 每项含 cli_commands + xml_payloads + undo 双套
            - LSTN 设备下发时用 unit.cli_commands
            - RSTN 设备下发时用 unit.xml_payloads
        """
        raise NotImplementedError


class SdnDeviceAdapter(ABC):
    """SDN 设备型号适配层抽象基类

    v3.0 唯一实现: H3cV7Adapter
    """

    @property
    @abstractmethod
    def supported_models(self) -> List[str]:
        """本适配器支持的设备型号关键字列表"""
        raise NotImplementedError

    @abstractmethod
    def supports_model(self, model: str) -> bool:
        """判断 device.asset.model 是否能用本适配器

        匹配规则: 大小写不敏感, 子串匹配（任一关键字出现在 model 中）
        """
        raise NotImplementedError

    @abstractmethod
    def get_template(self, action: str) -> VPCConfigTemplate:
        """根据动作返回对应模板

        Args:
            action: vpc_create | vpc_delete | port_bind | port_unbind
        """
        raise NotImplementedError

    @abstractmethod
    def get_platform(self, model: str) -> str:
        """根据 device model 返回 device platform（v3.0 T3）

        Returns:
            "LSTN" | "RSTN" | "UNKNOWN"
        """
        raise NotImplementedError


class H3cV7Adapter(SdnDeviceAdapter):
    """H3C Comware V7 适配器（型号 S6850 等）

    ADR-101: 型号白名单硬编码
    ADR-102: 第 1 轮省略 import-rt / export-rt
    ADR-109: 按 device.platform 路由通道（LSTN 走 CLI / RSTN 走 schema XML）
    """

    @property
    def supported_models(self) -> List[str]:
        return list(H3C_V7_SUPPORTED_MODELS)

    def supports_model(self, model: str) -> bool:
        """大小写不敏感, 任一关键字出现在 model 中即可"""
        if not model:
            return False
        model_upper = model.upper()
        return any(kw.upper() in model_upper for kw in self.supported_models)

    def get_template(self, action: str) -> VPCConfigTemplate:
        """路由到对应模板

        Task 2 阶段: 仅注册路由表, 模板类在 Task 3 引入
        """
        # 先检查 action 合法性 (避免被 Task 3 模板未实现掩盖)
        valid_actions = ("vpc_create", "vpc_delete", "port_bind", "port_unbind")
        if action not in valid_actions:
            raise ValueError(f"Unknown action: {action}, expected one of {list(valid_actions)}")

        # 延迟 import, 避免循环引用 & Task 3 模板未实现时报清晰错误
        try:
            from app.services.templates.h3c_v7_vpc_create import (
                H3cV7VpcCreateTemplate,
                H3cV7VpcDeleteTemplate,
            )
            from app.services.templates.h3c_v7_port_bind import (
                H3cV7PortBindTemplate,
                H3cV7PortUnbindTemplate,
            )
        except ImportError as e:
            raise NotImplementedError(
                f"H3C V7 模板未实现 (Task 3 待补): {e}. "
                f"action={action} 需要先实现对应的 Template 类"
            ) from e

        mapping = {
            "vpc_create": H3cV7VpcCreateTemplate,
            "vpc_delete": H3cV7VpcDeleteTemplate,
            "port_bind": H3cV7PortBindTemplate,
            "port_unbind": H3cV7PortUnbindTemplate,
        }
        return mapping[action]()

    def get_platform(self, model: str) -> str:
        """根据 device model 返回 platform（v3.0 T3）

        LSTN: L2VPN 业务走 CLI-over-NETCONF
        RSTN: L2VPN 业务走 schema 化 NETCONF
        """
        return get_platform_for_model(model)


def get_adapter_for_model(model: str) -> SdnDeviceAdapter:
    """工厂函数: 根据 device model 返回对应 adapter

    型号不支持时返回带 i18n 错误信息的 APIResponse-like dict
    (调用方判断 isinstance 决定如何处理)

    v3.0: 仅支持 H3C V7, 其他型号明确报错
    """
    adapter = H3cV7Adapter()
    if adapter.supports_model(model):
        return adapter
    # 型号不支持 → 返 i18n 错误 (调用方用 error_response() 包装)
    return error_response(
        err.SDN_DEVICE_MODEL_UNSUPPORTED,
        params={"model": model or "<empty>", "supported": ", ".join(H3C_V7_SUPPORTED_MODELS)},
    )
