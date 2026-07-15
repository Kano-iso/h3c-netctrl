"""H3C V7 端口绑定 / 解绑 双套 payload 模板（v3.0 sdn-vpc-netconf-schema-xml T3）

## 背景

端口绑定支持 2 种模式（spec.md Requirement: 端口绑定 2 种模式）：
  - Mode 1: service-instance + xconnect vsi（EVPN 标准）
  - Mode 2: port access vlan（传统 fallback）

模板输出 1 个 TemplateUnit（含 cli + xml + undo）。

## 业务下发通道（按 device.platform 路由）

| Platform | 通道 | 适用设备 |
|---|---|---|
| LSTN（老芯片）| CLI 文本走 `<Configuration>` 包裹 | S6850 / S6850-56HF |
| RSTN（新芯片）| schema 化 NETCONF XML 直接下发 | V9850 / S9820 |

## ADR

- ADR-104: service-instance 优先, access vlan fallback
- ADR-109: 按 device.platform 路由通道
- ADR-110: 1 unit × 4 字段（cli + xml + undo_cli + undo_xml）
"""

from typing import List

from app.services.sdn_device_adapter import (
    H3C_V7_CONFIG_NS,
    H3C_V7_OP_CREATE,
    H3C_V7_OP_DELETE,
    H3C_V7_XC_NS,
    TemplateUnit,
    UNIT_PORT_BIND,
    UNIT_PORT_UNBIND,
    VPCConfigTemplate,
)


def _vsi_name(vpc_id: int) -> str:
    """VSI 名称: vpc0001 ~ vpc9999（与 vpc_create 模板保持一致）"""
    return f"vpc{vpc_id:04d}"


# ─────────── XML 构造 helpers ───────────

def _wrap_rstn_xml(body_xml: str, operation: str = H3C_V7_OP_CREATE) -> str:
    """RSTN 平台 schema 化 NETCONF XML 完整 payload"""
    return (
        f'<config xmlns:xc="{H3C_V7_XC_NS}">'
        f'<top xmlns="{H3C_V7_CONFIG_NS}" xc:operation="{operation}">'
        f"{body_xml}"
        f"</top></config>"
    )


# ─────────── H3cV7PortBindTemplate ───────────

class H3cV7PortBindTemplate(VPCConfigTemplate):
    """H3C V7 端口绑定双套 payload 模板（v3.0 sdn-vpc-netconf-schema-xml T3）

    Args (context):
      - binding: SdnPortBinding (interface_name, service_instance, access_vlan)
      - vpc: SdnVpc (id) -- 用于 vsi_name
      - mode: "auto" | "service_instance" | "access_vlan"

    Auto 模式: service_instance 非空 → Mode 1, 否则 Mode 2

    Output:
      1 个 TemplateUnit（port-bind）：
      - Mode 1 (service_instance): service-instance + xconnect vsi access
      - Mode 2 (access_vlan):       port access vlan {vlan_id}
    """

    def render(self, context: dict) -> List[TemplateUnit]:
        binding = context["binding"]
        vpc = context["vpc"]
        mode = context.get("mode", "auto")

        vsi_name = _vsi_name(vpc.id)
        iface = binding.interface_name

        # 模式决策（ADR-104）
        if mode == "auto":
            use_service_instance = binding.service_instance is not None
        elif mode == "service_instance":
            use_service_instance = True
        elif mode == "access_vlan":
            use_service_instance = False
        else:
            raise ValueError(
                f"Unknown mode: {mode}, expected auto/service_instance/access_vlan"
            )

        if use_service_instance:
            return [self._port_bind_service_instance(iface, vsi_name, binding.service_instance)]
        else:
            return [self._port_bind_access_vlan(iface, binding.access_vlan)]

    def _port_bind_service_instance(
        self, iface: str, vsi_name: str, service_instance: int
    ) -> TemplateUnit:
        """Mode 1: service-instance + xconnect vsi（EVPN 标准）

        CLI (LSTN):
            interface GigabitEthernet1/0/14
              port link-mode bridge
              service-instance 1001
                xconnect vsi vpc0001 access

        XML (RSTN):
            <Interfaces><Interface>
              <Name>GigabitEthernet1/0/14</Name>
              <LinkMode>bridge</LinkMode>
              <ServiceInstances>
                <ServiceInstance>
                  <ID>1001</ID>
                  <XConnectVsi>
                    <VsiName>vpc0001</VsiName>
                    <AccessMode>access</AccessMode>
                  </XConnectVsi>
                </ServiceInstance>
              </ServiceInstances>
            </Interface></Interfaces>
        """
        cli = [
            f"interface {iface}",
            "  port link-mode bridge",
            f"  service-instance {service_instance}",
            f"    xconnect vsi {vsi_name} access",
        ]

        xml = [
            _wrap_rstn_xml(
                f"<Interfaces><Interface>"
                f"<Name>{iface}</Name>"
                f"<LinkMode>bridge</LinkMode>"
                f"<ServiceInstances>"
                f"<ServiceInstance>"
                f"<ID>{service_instance}</ID>"
                f"<XConnectVsi>"
                f"<VsiName>{vsi_name}</VsiName>"
                f"<AccessMode>access</AccessMode>"
                f"</XConnectVsi>"
                f"</ServiceInstance>"
                f"</ServiceInstances>"
                f"</Interface></Interfaces>"
            ),
        ]

        undo_cli = [
            f"interface {iface}",
            f"  undo service-instance {service_instance}",
        ]

        undo_xml = [
            _wrap_rstn_xml(
                f"<Interfaces><Interface>"
                f"<Name>{iface}</Name>"
                f"<ServiceInstances>"
                f"<ServiceInstance>"
                f"<ID>{service_instance}</ID>"
                f"</ServiceInstance>"
                f"</ServiceInstances>"
                f"</Interface></Interfaces>",
                operation=H3C_V7_OP_DELETE,
            ),
        ]

        return TemplateUnit(
            name=UNIT_PORT_BIND,
            description=f"端口绑定（Mode 1: service-instance + xconnect vsi {vsi_name}）",
            cli_commands=cli,
            xml_payloads=xml,
            undo_cli=undo_cli,
            undo_xml=undo_xml,
        )

    def _port_bind_access_vlan(self, iface: str, access_vlan: int) -> TemplateUnit:
        """Mode 2: port access vlan（传统 fallback）

        CLI (LSTN):
            interface GigabitEthernet1/0/14
              port link-mode bridge
              port access vlan 2

        XML (RSTN):
            <Interfaces><Interface>
              <Name>GigabitEthernet1/0/14</Name>
              <LinkMode>bridge</LinkMode>
              <AccessVlan>2</AccessVlan>
            </Interface></Interfaces>
        """
        cli = [
            f"interface {iface}",
            "  port link-mode bridge",
            f"  port access vlan {access_vlan}",
        ]

        xml = [
            _wrap_rstn_xml(
                f"<Interfaces><Interface>"
                f"<Name>{iface}</Name>"
                f"<LinkMode>bridge</LinkMode>"
                f"<AccessVlan>{access_vlan}</AccessVlan>"
                f"</Interface></Interfaces>"
            ),
        ]

        undo_cli = [
            f"interface {iface}",
            f"  undo port access vlan {access_vlan}",
        ]

        undo_xml = [
            _wrap_rstn_xml(
                f"<Interfaces><Interface>"
                f"<Name>{iface}</Name>"
                f"<AccessVlan>{access_vlan}</AccessVlan>"
                f"</Interface></Interfaces>",
                operation=H3C_V7_OP_DELETE,
            ),
        ]

        return TemplateUnit(
            name=UNIT_PORT_BIND,
            description=f"端口绑定（Mode 2: port access vlan {access_vlan}，fallback）",
            cli_commands=cli,
            xml_payloads=xml,
            undo_cli=undo_cli,
            undo_xml=undo_xml,
        )


# ─────────── H3cV7PortUnbindTemplate ───────────

class H3cV7PortUnbindTemplate(VPCConfigTemplate):
    """H3C V7 端口解绑双套 payload 模板（v3.0 sdn-vpc-netconf-schema-xml T3）

    同时 undo 2 种模式（任一未配置会被设备忽略，幂等）。

    Output:
      1 个 TemplateUnit（port-unbind）：
      - undo service-instance {id}（如果 binding 有）
      - undo port access vlan {vlan}（如果 binding 有）
    """

    def render(self, context: dict) -> List[TemplateUnit]:
        binding = context["binding"]
        vpc = context["vpc"]

        vsi_name = _vsi_name(vpc.id)
        iface = binding.interface_name

        # 至少要有一个非空（否则该 binding 实际不存在）
        if binding.service_instance is None and binding.access_vlan is None:
            raise ValueError(
                f"PortUnbind: binding (interface={iface}) 至少要有 service_instance 或 access_vlan"
            )

        # CLI (LSTN) — 同时 undo 2 种模式
        cli = [f"interface {iface}"]
        if binding.service_instance is not None:
            cli.append(f"  undo service-instance {binding.service_instance}")
        if binding.access_vlan is not None:
            cli.append(f"  undo port access vlan {binding.access_vlan}")

        # XML (RSTN) — 1 条 payload 即可（同时清 service-instance 子树和 AccessVlan）
        # 用 merge 操作可重复执行，幂等
        xml_body_parts = [f"<Name>{iface}</Name>"]
        if binding.service_instance is not None:
            xml_body_parts.append(
                f"<ServiceInstances>"
                f"<ServiceInstance>"
                f"<ID>{binding.service_instance}</ID>"
                f"</ServiceInstance>"
                f"</ServiceInstances>"
            )
        if binding.access_vlan is not None:
            xml_body_parts.append(f"<AccessVlan>{binding.access_vlan}</AccessVlan>")

        xml = [
            _wrap_rstn_xml(
                f"<Interfaces><Interface>{''.join(xml_body_parts)}</Interface></Interfaces>",
                operation=H3C_V7_OP_DELETE,
            ),
        ]

        # undo: 本身是 delete 操作，不需要再 undo
        undo_cli: List[str] = []
        undo_xml: List[str] = []

        # 描述
        parts = [f"端口解绑（interface={iface}"]
        if binding.service_instance is not None:
            parts.append(f"service-instance={binding.service_instance}")
        if binding.access_vlan is not None:
            parts.append(f"access_vlan={binding.access_vlan}")
        parts.append("）")
        description = ", ".join(parts).replace("（", "（").replace("）", "）")

        return [
            TemplateUnit(
                name=UNIT_PORT_UNBIND,
                description=description,
                cli_commands=cli,
                xml_payloads=xml,
                undo_cli=undo_cli,
                undo_xml=undo_xml,
            )
        ]
