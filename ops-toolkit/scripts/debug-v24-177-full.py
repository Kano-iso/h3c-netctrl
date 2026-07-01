#!/usr/bin/env python3
"""v2.4-bugfix: 抓 100.177 完整 3 模块 XML + 分析"""
import sys
from ncclient import manager
from lxml import etree

NS = "http://www.h3c.com/netconf/data:1.0"

with manager.connect(
    host="192.168.100.177", port=830,
    username="python", password="Admin123!@#",
    hostkey_verify=False, timeout=10,
    device_params={"name": "h3c"},
) as m:
    filt = (
        f'<top xmlns="{NS}">'
        f'<Ifmgr><Interfaces/></Ifmgr>'
        f'<IPV4ADDRESS></IPV4ADDRESS>'
        f'<L3vpn></L3vpn>'
        f'</top>'
    )
    r = m.get(("subtree", filt))
    xml = r.data.xml
    ifaces = r.data.findall(f".//{{{NS}}}Interface")
    no_name = []
    for iface in ifaces:
        idx = iface.findtext(f"{{{NS}}}IfIndex")
        name = iface.findtext(f"{{{NS}}}Name")
        if not name:
            no_name.append(idx)
    print(f"XML={len(xml)}B  IfMgr={len(ifaces)}  no_name={len(no_name)}: {no_name[:20]}")
    ipv4s = r.data.findall(f".//{{{NS}}}Ipv4Address")
    print(f"IPv4Address={len(ipv4s)}")
    binds = r.data.findall(f".//{{{NS}}}Bind")
    print(f"L3vpn Bind={len(binds)}")
    # 写 capture
    with open("/captures/debug-v24-bugfix-177-full.xml", "w") as f:
        f.write(xml)
    print("✅ saved to /captures/debug-v24-bugfix-177-full.xml")
