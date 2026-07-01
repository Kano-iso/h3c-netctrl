#!/usr/bin/env python3
"""v2.4-bugfix-100: 真机实测 namespace + get 影响 (data NS vs config NS + get vs get_config)"""
import time
import sys
from ncclient import manager
from lxml import etree

DEV = sys.argv[1] if len(sys.argv) > 1 else "192.168.100.100"
PASS = "Admin123!@#"
USER = "python"
DATA_NS = "http://www.h3c.com/netconf/data:1.0"
CONFIG_NS = "http://www.h3c.com/netconf/config:1.0"

FILT_DATA = (
    f'<top xmlns="{DATA_NS}">'
    '<Ifmgr><Interfaces/></Ifmgr>'
    '<IPV4ADDRESS></IPV4ADDRESS>'
    '<L3vpn></L3vpn>'
    '</top>'
)
FILT_CONFIG = (
    f'<top xmlns="{CONFIG_NS}">'
    '<Ifmgr><Interfaces/></Ifmgr>'
    '<IPV4ADDRESS></IPV4ADDRESS>'
    '<L3vpn></L3vpn>'
    '</top>'
)

def query(use_get: bool, filt: str, label: str) -> tuple[int, int, float]:
    t0 = time.time()
    with manager.connect(
        host=DEV, port=830,
        username=USER, password=PASS,
        hostkey_verify=False, timeout=10,
        device_params={"name": "h3c"},
    ) as m:
        if use_get:
            r = m.get(("subtree", filt))
        else:
            r = m.get_config("running", ("subtree", filt))
        xml_bytes = r.data.xml.encode() if isinstance(r.data.xml, str) else etree.tostring(r.data)
        ifaces = r.data.findall(f".//{{{DATA_NS}}}Interface")
        elapsed = time.time() - t0
        print(f"   {label:50s}  XML={len(xml_bytes):>7d}B  IfMgr={len(ifaces):>3d}  t={elapsed:5.1f}s")
        return len(xml_bytes), len(ifaces), elapsed

print(f"=== {DEV} namespace + op 对比 ===")
# 1. data NS + GET (应该拿全)
try:
    query(True, FILT_DATA, "data NS + GET (我们想要的)")
except Exception as e:
    print(f"   ❌ {e}")
# 2. config NS + GET_CONFIG (修复前: 不全)
try:
    query(False, FILT_CONFIG, "config NS + GET_CONFIG (修复前: 不全)")
except Exception as e:
    print(f"   ❌ {e}")
# 3. config NS + GET (错用: 拿空)
try:
    query(True, FILT_CONFIG, "config NS + GET (错用: 拿空)")
except Exception as e:
    print(f"   ❌ {e}")
