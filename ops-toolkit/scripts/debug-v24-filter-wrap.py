#!/usr/bin/env python3
"""
v2.4-bugfix-interface-display-100: 验证 filter 加 <filter> 包裹的影响
"""
from ncclient import manager
from lxml import etree

DEV = {"host": "192.168.100.100", "user": "python", "pass": "Admin123!@#"}
NS = "http://www.h3c.com/netconf/data:1.0"

# 后端组合 filter（3 模块，无 <filter> 包裹）
INNER = f'''<top xmlns="{NS}">
  <Ifmgr><Interfaces><Interface/></Interfaces></Ifmgr>
  <IPV4ADDRESS></IPV4ADDRESS>
  <L3vpn></L3vpn>
</top>'''

# 方式 A：filter=("subtree", INNER) - 后端当前做法
# 方式 B：filter=("subtree", "<filter>" + INNER + "</filter>") - 加外层
# 方式 C：直接传位置参数（无 subtree tuple）
WRAPPED = "<filter>" + INNER + "</filter>"

def query(filter_arg, label):
    with manager.connect(
        host=DEV["host"], port=830,
        username=DEV["user"], password=DEV["pass"],
        hostkey_verify=False, timeout=15,
        device_params={"name": "h3c"},
    ) as m:
        if isinstance(filter_arg, tuple):
            result = m.get(filter=filter_arg)
        else:
            result = m.get(filter_arg)
        xml_str = etree.tostring(result.data, pretty_print=True).decode()
        interfaces = result.data.findall(f".//{{{NS}}}Interface")
        print(f"\n=== {label} ===")
        print(f"   XML 大小: {len(xml_str)} 字节")
        print(f"   <Interface> 节点数: {len(interfaces)}")
        return len(xml_str), len(interfaces)


if __name__ == "__main__":
    print("🚀 v2.4-bugfix-interface-display-100 filter 包裹测试")
    for arg, label in [
        (("subtree", INNER), "A. m.get(filter=('subtree', INNER))  ← 后端当前"),
        (("subtree", WRAPPED), "B. m.get(filter=('subtree', '<filter>INNER</filter>'))"),
        (INNER, "C. m.get(INNER) - 直接传 XML（无 tuple）"),
        (WRAPPED, "D. m.get(WRAPPED) - 直接传带 <filter> 包裹的 XML"),
    ]:
        try:
            query(arg, label)
        except Exception as e:
            print(f"\n=== {label} ===")
            print(f"   ❌ 失败: {e}")
