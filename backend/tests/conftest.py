import os
import pytest
from unittest.mock import MagicMock, patch
from fastapi.testclient import TestClient

# 设置测试环境变量
os.environ["ENCRYPTION_KEY"] = "BRPOu1O4FIvcdwijI1yf0quviQjeSr0V1Zfw2CRwgRQ="
os.environ["DB_PATH"] = "/tmp/test_h3c.db"

# v2.6 i18n: 必须在 from app.main import app 之前 import app.models。
# `import app.models` 会把当前 namespace 的 `app` 重新绑定到 `app` package module，
# 覆盖 `app.main.app` 的 FastAPI 实例。testclient 会拿到 module 报 'module is not callable'。
# 顺序：先 import app.models（顺便注册 Task 等 Base 子类到 metadata），
# 然后 from app.main import app 重新把 app 绑回 FastAPI 实例。
import app.models  # noqa: F401
from app.main import app
from app.database import Base, engine, SessionLocal


# ======================== integration marker（v2.3 QA 规范化） ========================

def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: 真实设备集成测试，默认 skip，需 --integration 显式开启"
    )


def pytest_addoption(parser):
    parser.addoption(
        "--integration", action="store_true", default=False,
        help="跑真实设备集成测试（需 SSH 通 192.168.100.177 测试用交换机）"
    )


def pytest_collection_modifyitems(config, items):
    if not config.getoption("--integration"):
        skip_integration = pytest.mark.skip(reason="需 --integration 才跑")
        for item in items:
            if "integration" in item.keywords:
                item.add_marker(skip_integration)


@pytest.fixture(autouse=True)
def setup_db():
    """每个测试前重建数据库表 + 清 internal_api 缓存

    清缓存（v2.5）：避免上一个 test 写入的 GET 缓存污染下一个 test，
    例如 test_internal_get_success 和 test_internal_get_retry_then_success 用同 URL。
    """
    from app.internal_api import clear_cache
    clear_cache()
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)
    clear_cache()


@pytest.fixture
def client():
    """FastAPI 测试客户端"""
    return TestClient(app)


@pytest.fixture
def db():
    """数据库 session"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# === NETCONF 模拟 ===

# 默认 fixture 的 NETCONF XML 响应
DEFAULT_NETCONF_INTERFACE_XML = """<?xml version="1.0" encoding="UTF-8"?>
<data>
<top xmlns="http://www.h3c.com/netconf/config:1.0">
<Ifmgr>
<Interfaces>
<Interface><IfIndex>100</IfIndex><Name>GigabitEthernet1/0/1</Name><PVID>1</PVID></Interface>
<Interface><IfIndex>101</IfIndex><Name>GigabitEthernet1/0/2</Name><PVID>1</PVID></Interface>
</Interfaces>
</Ifmgr>
</top>
</data>"""

DEFAULT_NETCONF_VLAN_XML = """<?xml version="1.0" encoding="UTF-8"?>
<data>
<top xmlns="http://www.h3c.com/netconf/config:1.0">
<VLAN>
<VLANs>
<VLANID><ID>1</ID></VLANID>
<VLANID><ID>100</ID></VLANID>
</VLANs>
</VLAN>
</top>
</data>"""


def _make_mock_netconf(ifmgr_xml: str = None, vlan_xml: str = None):
    """构造一个 mock NetconfClient，get / get_config 都返回 XML 字符串

    关键：fixture 直接给 mock instance 的 .get / .get_config / .edit_config 设 side_effect，
    返回 str（不走真 NetconfClient method 的 `return result.xml` 链——str 没 .xml 属性）。
    """
    mgr = MagicMock()
    if ifmgr_xml is None:
        ifmgr_xml = DEFAULT_NETCONF_INTERFACE_XML
    if vlan_xml is None:
        vlan_xml = DEFAULT_NETCONF_VLAN_XML
    # get_config / get 共用的 filter → XML 字符串逻辑
    def filter_to_xml(filter_tuple):
        filter_xml = filter_tuple[1] if isinstance(filter_tuple, tuple) else filter_tuple
        if "Ifmgr" in filter_xml or "Interface" in filter_xml:
            return ifmgr_xml
        if "VLAN" in filter_xml:
            return vlan_xml
        # 默认返回空 data
        return "<data/>"
    # get_config 直接返回 XML 字符串
    mgr.get_config.side_effect = filter_to_xml
    # v2.4-bugfix-interface-display-100：get_interfaces 改用 client.get()，mock 也直接返回 str
    mgr.get.side_effect = filter_to_xml
    mgr.edit_config.return_value = "<ok/>"
    mgr.close_session.return_value = None
    # v2.3.0 新增方法 mock：按 if_index 推 name，< 4096 → 物理口，>= 4096 → LoopBack
    # （真实设备上 5123-5125 实际是 LoopBack0/1/2，这里只保证 _detect_layer 不报 TypeError）
    def fake_get_interface_name_by_index(if_index: int):
        if if_index < 4096:
            return f"GigabitEthernet1/0/{max(if_index - 1, 0)}"
        return f"LoopBack{if_index - 5123}"
    mgr.get_interface_name_by_index.side_effect = fake_get_interface_name_by_index
    return mgr


@pytest.fixture
def mock_netconf():
    """自动 patch NetconfClient，使其走 mock 实现（不连真实设备）"""
    # 必须 patch 所有引用 NetconfClient 的位置（路由模块）
    with patch("app.routers.interface.NetconfClient") as mock_cls, \
         patch("app.routers.vlan.NetconfClient") as mock_cls_v, \
         patch("app.routers.device.NetconfClient") as mock_cls_d:
        mock_instance = MagicMock()
        mock_instance.__enter__ = MagicMock(return_value=mock_instance)
        mock_instance.__exit__ = MagicMock(return_value=False)
        for mc in (mock_cls, mock_cls_v, mock_cls_d):
            mc.return_value = mock_instance
        yield mock_instance


# === 真实 H3C Ifmgr 响应样本（来自 192.168.100.100 真实探测） ===

H3C_IFMGR_REAL_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="1">
<data>
<top xmlns="http://www.h3c.com/netconf/config:1.0">
<Ifmgr>
<Interfaces>
<Interface><IfIndex>2</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>3</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>4</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>5</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>6</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>7</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>8</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>9</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>10</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>11</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>12</IfIndex><PVID>200</PVID></Interface>
<Interface><IfIndex>13</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>14</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>15</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>16</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>17</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>18</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>19</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>20</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>21</IfIndex><PVID>100</PVID></Interface>
<Interface><IfIndex>5123</IfIndex><MAC>00-00-00-00-00-00</MAC></Interface>
<Interface><IfIndex>5124</IfIndex><MAC>00-00-00-00-00-01</MAC></Interface>
<Interface><IfIndex>5125</IfIndex><MAC>00-00-00-00-00-02</MAC></Interface>
</Interfaces>
</Ifmgr>
</top>
</data>
</rpc-reply>"""

H3C_VLAN_REAL_RESPONSE = """<?xml version="1.0" encoding="UTF-8"?>
<rpc-reply xmlns="urn:ietf:params:xml:ns:netconf:base:1.0" message-id="1">
<data>
<top xmlns="http://www.h3c.com/netconf/config:1.0">
<VLAN>
<VLANs>
<VLANID><ID>1</ID></VLANID>
<VLANID><ID>100</ID></VLANID>
<VLANID><ID>200</ID></VLANID>
</VLANs>
</VLAN>
</top>
</data>
</rpc-reply>"""


@pytest.fixture
def real_device_netconf():
    """Mock NetconfClient 返回真实设备的 H3C 响应样本"""
    mock_instance = _make_mock_netconf(
        ifmgr_xml=H3C_IFMGR_REAL_RESPONSE,
        vlan_xml=H3C_VLAN_REAL_RESPONSE,
    )
    mock_instance.__enter__ = MagicMock(return_value=mock_instance)
    mock_instance.__exit__ = MagicMock(return_value=False)
    with patch("app.routers.interface.NetconfClient") as mock_cls, \
         patch("app.routers.vlan.NetconfClient") as mock_cls_v, \
         patch("app.routers.device.NetconfClient") as mock_cls_d:
        for mc in (mock_cls, mock_cls_v, mock_cls_d):
            mc.return_value = mock_instance
        yield mock_instance


@pytest.fixture
def created_device(client):
    """创建一个测试设备，返回 device dict"""
    resp = client.post("/api/devices", json={
        "name": "Test-Device",
        "host": "192.168.100.100",
        "port": 830,
        "username": "admin",
        "password": "TestPass123!",
        "protected_interfaces": [2],
    })
    assert resp.status_code == 200, resp.text
    return resp.json()["data"]
