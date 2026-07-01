#!/usr/bin/env python3
"""
v2.4-bugfix-interface-display-100: 验证 ncclient 用不同 filter 的返回大小
"""
from ncclient import manager
from lxml import etree

DEV = {"host": "192.168.100.100", "user": "python", "pass": "Admin123!@#"}
NS = "http://www.h3c.com/netconf/data:1.0"

# 后端 filter（3 模块）
FILTER_BACKEND = f'''<top xmlns="{NS}">
  <Ifmgr><Interfaces/></Ifmgr>
  <IPV4ADDRESS></IPV4ADDRESS>
  <L3vpn></L3vpn>
</top>'''

# 简单 filter（只查 Ifmgr）
FILTER_SIMPLE = f'''<top xmlns="{NS}">
  <Ifmgr><Interfaces><Interface/></Interfaces></Ifmgr>
</top>'''

# 简单 filter v2（自闭合 Interfaces，但用 Interface 提示）
FILTER_SIMPLE2 = f'''<top xmlns="{NS}">
  <Ifmgr><Interfaces/></Ifmgr>
</top>'''

# 3 模块 v2（带 <Interface/> 提示）
FILTER_BACKEND2 = f'''<top xmlns="{NS}">
  <Ifmgr><Interfaces><Interface/></Interfaces></Ifmgr>
  <IPV4ADDRESS></IPV4ADDRESS>
  <L3vpn></L3vpn>
</top>'''


def query(filter_xml, label, use_get=False):
    with manager.connect(
        host=DEV["host"], port=830,
        username=DEV["user"], password=DEV["pass"],
        hostkey_verify=False, timeout=15,
        device_params={"name": "h3c"},
    ) as m:
        if use_get:
            result = m.get(("subtree", filter_xml))
        else:
            result = m.get_config("running", ("subtree", filter_xml))
        xml_str = etree.tostring(result.data, pretty_print=True).decode()
        interfaces = result.data.findall(f".//{{{NS}}}Interface")
        print(f"\n=== {label} ===")
        print(f"   XML 大小: {len(xml_str)} 字节")
        print(f"   <Interface> 节点数: {len(interfaces)}")
        return len(xml_str), len(interfaces)


if __name__ == "__main__":
    print("🚀 v2.4-bugfix-interface-display-100 filter 对比")
    for filt, label in [
        (FILTER_BACKEND, "后端 filter（3 模块 + Interfaces/ 自闭合）"),
        (FILTER_BACKEND2, "3 模块 + <Interface/> 提示"),
        (FILTER_SIMPLE, "只 Ifmgr + <Interface/> 提示"),
        (FILTER_SIMPLE2, "只 Ifmgr + Interfaces/ 自闭合"),
    ]:
        try:
            query(filt, label, use_get=True)
        except Exception as e:
            print(f"\n=== {label} ===")
            print(f"   ❌ 失败: {e}")
