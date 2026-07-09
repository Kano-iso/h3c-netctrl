"""SdnPreflight 单元测试（v3.0 sdn-vpc-device-templates Task 7）

6 用例覆盖 (spec.md Requirement: SdnPreflight 6 项预检):
1. 设备型号不支持 → SDN_DEVICE_MODEL_UNSUPPORTED
2. 设备 offline → SDN_PREFLIGHT_FAILED
3-6. 设备侧占位 (L2 阶段无 SSH, 由 vpc-apply.sh L3 真机执行)
"""

from types import SimpleNamespace

import pytest

from app.i18n_keys import err
from app.services.sdn_device_adapter import H3cV7Adapter
from app.services.sdn_preflight import SdnPreflight, PreflightResult


@pytest.fixture
def adapter():
    return H3cV7Adapter()


@pytest.fixture
def preflight(adapter):
    return SdnPreflight(adapter, db=None)  # db=None (本地检查不需要)


@pytest.fixture
def dev_online_s6850():
    return SimpleNamespace(
        id=1,
        status="online",
        asset=SimpleNamespace(model="S6850-56HF"),
    )


@pytest.fixture
def vpc():
    return SimpleNamespace(
        id=1, vni=20000, vlan_id=2, cidr="10.0.1.0/24",
        gateway_ip="10.0.1.1", gateway_mac="00-00-00-00-4e20-01",
        vsi_interface=1,
    )


# ======================== 1. 设备型号 ========================

def test_preflight_fails_on_unsupported_model(preflight, vpc):
    """设备型号不支持 → 预检失败, error_key=SDN_DEVICE_MODEL_UNSUPPORTED"""
    dev = SimpleNamespace(
        id=1, status="online",
        asset=SimpleNamespace(model="Cisco Catalyst 9300"),
    )
    r = preflight.preflight_vpc_deploy(vpc, dev)
    assert r.success is False
    assert r.error_key == err.SDN_DEVICE_MODEL_UNSUPPORTED
    assert "[device_model]" in r.reason
    assert "Catalyst 9300" in r.reason


# ======================== 2. 设备 offline ========================

def test_preflight_fails_when_device_offline(preflight, vpc):
    """设备 offline → 预检失败, error_key=SDN_PREFLIGHT_FAILED"""
    dev = SimpleNamespace(
        id=1, status="offline",
        asset=SimpleNamespace(model="S6850-56HF"),
    )
    r = preflight.preflight_vpc_deploy(vpc, dev)
    assert r.success is False
    assert r.error_key == err.SDN_PREFLIGHT_FAILED
    assert "[device_online]" in r.reason
    assert "offline" in r.reason


# ======================== 3. 全部通过 ========================

def test_preflight_passes_when_all_local_checks_ok(preflight, vpc, dev_online_s6850):
    """设备型号 OK + online → 6 项全通过 (3-6 占位)"""
    r = preflight.preflight_vpc_deploy(vpc, dev_online_s6850)
    assert r.success is True
    assert r.error_key is None
    assert r.reason is None


# ======================== 4. 型号优先短路 (model fail < online check) ========================

def test_preflight_short_circuits_on_model_check(preflight, vpc):
    """型号失败优先于其他检查 (短路)"""
    dev = SimpleNamespace(
        id=1, status="offline",  # 同时 offline, 但 model check 先
        asset=SimpleNamespace(model="Catalyst 9300"),
    )
    r = preflight.preflight_vpc_deploy(vpc, dev)
    assert r.success is False
    assert "[device_model]" in r.reason  # 不是 device_online
    assert "[device_online]" not in r.reason


# ======================== 5. 单 check 方法 ========================

def test_check_device_model_passes_for_s6850(preflight, dev_online_s6850):
    """check_device_model 单元: S6850-56HF → success"""
    r = preflight.check_device_model(dev_online_s6850)
    assert r.success is True


def test_check_device_online_passes_when_online(preflight, dev_online_s6850):
    """check_device_online 单元: status=online → success"""
    r = preflight.check_device_online(dev_online_s6850)
    assert r.success is True
