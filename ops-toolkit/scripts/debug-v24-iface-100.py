#!/usr/bin/env python3
"""
v2.4-bugfix-interface-display-100 debug 脚本
对比 100.100（特例）vs 100.4（普通生产）的 NETCONF get-interfaces 原始返回
"""
import sys
import os
from ncclient import manager
from lxml import etree

DEVICES = [
    {"name": "100.100 (特例)", "host": "192.168.100.100", "user": "python", "pass": "Admin123!@#"},
    {"name": "100.4 (普通生产)", "host": "192.168.100.4", "user": "python", "pass": "Admin123!@#"},
    {"name": "100.5 (普通生产)", "host": "192.168.100.5", "user": "python", "pass": "Admin123!@#"},
]

# v2.4-bugfix-interface-display-100 探针
# 1. 用后端默认 filter 拉接口（Ifmgr 全部）
# 2. 看 XML 原始大小 / 节点数 / 字段分布
# 3. 单独查 AdminStatus 字段（看 down 接口是否被 server 过滤）

IFMGR_FILTER = """
<filter xmlns="urn:ietf:params:xml:ns:netconf:base:1.0">
  <top xmlns="http://www.h3c.com/netconf/data:1.0">
    <Ifmgr>
      <Interfaces>
        <Interface/>
      </Interfaces>
    </Ifmgr>
  </top>
</filter>
"""

def query_device(dev):
    print(f"\n{'='*70}")
    print(f"设备: {dev['name']} ({dev['host']})")
    print(f"{'='*70}")
    try:
        with manager.connect(
            host=dev["host"],
            port=830,
            username=dev["user"],
            password=dev["pass"],
            hostkey_verify=False,
            timeout=15,
            device_params={"name": "h3c"},
        ) as m:
            print(f"✅ NETCONF 连接成功")

            # 1. 拉 Ifmgr 全表
            result = m.get(IFMGR_FILTER)
            xml_str = etree.tostring(result.data, pretty_print=True).decode()
            xml_size = len(xml_str)
            xml_lines = xml_str.count("\n")

            # 2. 解析所有 <Interface> 节点
            ns = {"h3c": "http://www.h3c.com/netconf/data:1.0"}
            interfaces = result.data.findall(".//h3c:Interface", ns)
            print(f"\n📊 NETCONF 原始返回:")
            print(f"   XML 大小: {xml_size} 字节")
            print(f"   XML 行数: {xml_lines}")
            print(f"   <Interface> 节点数: {len(interfaces)}")

            # 3. 统计 AdminStatus 分布
            admin_status_dist = {}
            if_oper_status_dist = {}
            for iface in interfaces:
                admin = iface.find(".//h3c:AdminStatus", ns)
                oper = iface.find(".//h3c:OperStatus", ns)
                a_val = admin.text if admin is not None and admin.text else "(缺省)"
                o_val = oper.text if oper is not None and oper.text else "(缺省)"
                admin_status_dist[a_val] = admin_status_dist.get(a_val, 0) + 1
                if_oper_status_dist[o_val] = if_oper_status_dist.get(o_val, 0) + 1

            print(f"\n📊 AdminStatus 分布:")
            for k, v in admin_status_dist.items():
                print(f"   {k}: {v}")
            print(f"\n📊 OperStatus 分布:")
            for k, v in if_oper_status_dist.items():
                print(f"   {k}: {v}")

            # 4. 抽 3 个 down 接口的 Name/Description
            down_samples = []
            for iface in interfaces:
                admin = iface.find(".//h3c:AdminStatus", ns)
                if admin is not None and admin.text == "2":  # down
                    name = iface.find(".//h3c:Name", ns)
                    desc = iface.find(".//h3c:Description", ns)
                    if_index = iface.find(".//h3c:IfIndex", ns)
                    down_samples.append({
                        "IfIndex": if_index.text if if_index is not None else "?",
                        "Name": name.text if name is not None and name.text else "(无 Name)",
                        "Description": desc.text if desc is not None and desc.text else "(无 Description)",
                    })
                    if len(down_samples) >= 3:
                        break
            if down_samples:
                print(f"\n📊 前 3 个 down 接口详情:")
                for s in down_samples:
                    print(f"   IfIndex={s['IfIndex']} Name={s['Name']} Desc={s['Description']}")
            else:
                print(f"\n📊 没有 AdminStatus=down 的接口（可能 server 端 filter 了）")

            # 5. 保存 XML 到 captures
            os.makedirs("/captures", exist_ok=True)
            safe_name = dev["host"].replace(".", "_")
            cap_path = f"/captures/debug-v24-bugfix-iface-{safe_name}.xml"
            with open(cap_path, "w") as f:
                f.write(xml_str)
            print(f"\n💾 XML 已保存: {cap_path}")

    except Exception as e:
        print(f"❌ 连接失败: {e}")
        return False
    return True

if __name__ == "__main__":
    print("🚀 v2.4-bugfix-interface-display-100 debug")
    print(f"   设备列表: {[d['host'] for d in DEVICES]}")

    if len(sys.argv) > 1:
        target = sys.argv[1]
        dev = next((d for d in DEVICES if d["host"] == target), None)
        if not dev:
            print(f"❌ 未找到设备: {target}")
            sys.exit(1)
        DEVICES = [dev]

    success_count = 0
    for dev in DEVICES:
        if query_device(dev):
            success_count += 1

    print(f"\n{'='*70}")
    print(f"📊 总览: {success_count}/{len(DEVICES)} 设备成功")
    print(f"{'='*70}")
