"""v3.1.2 ZTP onboard mock QA.

不连真实设备：虚构管理 IP，mock SSHExecutor / NetconfClient。
覆盖 onboard → device/asset 可见 → 幂等更新 → 删除闭环。
"""
from unittest.mock import MagicMock, patch

from app.models import Asset, Device


class FakeNetconfClient:
    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def _patch_successful_device_probe():
    fake_executor = MagicMock()
    fake_executor.execute.return_value = {
        "success": True,
        "output": "H3C Comware Software, Version 7.1.070",
    }
    fake_executor.collect_hardware_info.return_value = {
        "model": "H3C S6850-56HF",
        "serial_number": "CNEZTPTST001",
        "firmware_version": "Version 7.1.070",
        "software_package": "s6850-cmw710-boot-t7064p15.bin",
    }
    return patch("app.services.ztp_onboarding.SSHExecutor", return_value=fake_executor), \
        patch("app.services.ztp_onboarding.NetconfClient", FakeNetconfClient)


def test_ztp_onboard_creates_device_and_asset(client, db):
    ssh_patch, netconf_patch = _patch_successful_device_probe()
    with ssh_patch, netconf_patch:
        resp = client.post("/api/ztp/onboard", json={
            "host": "192.0.2.101",
            "username": "python",
            "password": "Admin123!@#",
            "platform": "lstn",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["status"] == "success"
    assert data["created"] is True
    assert data["device"]["name"] == "ztp-switch-101"
    assert data["device"]["host"] == "192.0.2.101"
    assert data["asset"]["status"] == "online"
    assert data["asset"]["model"] == "H3C S6850-56HF"

    device_id = data["device"]["id"]
    with patch("app.routers.device._get_restore_support_cached", return_value=None):
        list_resp = client.get("/api/devices")
        assert list_resp.status_code == 200
        assert any(d["id"] == device_id for d in list_resp.json()["data"])

    asset_resp = client.get(f"/api/assets/device/{device_id}")
    assert asset_resp.status_code == 200
    asset = asset_resp.json()["data"]
    assert asset["status"] == "online"
    assert asset["serial_number"] == "CNEZTPTST001"


def test_ztp_onboard_same_host_is_idempotent_update(client, db):
    ssh_patch, netconf_patch = _patch_successful_device_probe()
    payload = {
        "host": "192.0.2.102",
        "name": "ztp-old-name",
        "username": "python",
        "password": "Admin123!@#",
        "platform": "lstn",
    }
    with ssh_patch, netconf_patch:
        first = client.post("/api/ztp/onboard", json=payload).json()["data"]

    payload["name"] = "ztp-new-name"
    payload["platform"] = "rstn"
    ssh_patch, netconf_patch = _patch_successful_device_probe()
    with ssh_patch, netconf_patch:
        second = client.post("/api/ztp/onboard", json=payload).json()["data"]

    assert first["device"]["id"] == second["device"]["id"]
    assert second["created"] is False
    assert second["device"]["name"] == "ztp-new-name"
    assert second["device"]["platform"] == "rstn"
    assert db.query(Device).filter(Device.host == "192.0.2.102").count() == 1


def test_ztp_onboard_asset_collect_failure_returns_partial(client, db):
    fake_executor = MagicMock()
    fake_executor.execute.return_value = {"success": True, "output": "Version 7.1.070"}
    fake_executor.collect_hardware_info.side_effect = RuntimeError("mock asset collect failed")

    with patch("app.services.ztp_onboarding.SSHExecutor", return_value=fake_executor), \
         patch("app.services.ztp_onboarding.NetconfClient", FakeNetconfClient):
        resp = client.post("/api/ztp/onboard", json={
            "host": "192.0.2.103",
            "username": "python",
            "password": "Admin123!@#",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["status"] == "partial"
    assert "mock asset collect failed" in data["asset_error"]

    asset = db.query(Asset).filter(Asset.device_id == data["device"]["id"]).first()
    assert asset is not None
    assert asset.status == "offline"


def test_ztp_onboard_probe_failure_does_not_create_device(client, db):
    fake_executor = MagicMock()
    fake_executor.execute.return_value = {"success": False, "error": "refused"}

    with patch("app.services.ztp_onboarding.SSHExecutor", return_value=fake_executor):
        resp = client.post("/api/ztp/onboard", json={
            "host": "192.0.2.104",
            "username": "python",
            "password": "Admin123!@#",
        })

    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "SSH 22 探测失败" in body["error"]
    assert db.query(Device).filter(Device.host == "192.0.2.104").count() == 0


def test_ztp_onboard_crud_cleanup(client, db):
    ssh_patch, netconf_patch = _patch_successful_device_probe()
    with ssh_patch, netconf_patch:
        onboard = client.post("/api/ztp/onboard", json={
            "host": "192.0.2.105",
            "username": "python",
            "password": "Admin123!@#",
        }).json()["data"]

    device_id = onboard["device"]["id"]
    assert client.get(f"/api/devices/{device_id}").json()["success"] is True
    assert client.get(f"/api/assets/device/{device_id}").json()["success"] is True

    deleted = client.delete(f"/api/devices/{device_id}")
    assert deleted.status_code == 200
    assert deleted.json()["success"] is True
    assert db.query(Device).filter(Device.id == device_id).first() is None
    assert db.query(Asset).filter(Asset.device_id == device_id).first() is None
