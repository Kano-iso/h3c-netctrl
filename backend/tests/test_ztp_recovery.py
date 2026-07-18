"""v3.1.3 ZTP recovery override QA."""
import json


def test_ztp_recovery_override_write_read_clear(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.ztp_recovery.settings.ZTP_STATE_DIR", str(tmp_path))

    initial = client.get("/api/ztp/recovery-override")
    assert initial.status_code == 200
    assert initial.json()["data"]["active"] is False

    resp = client.post("/api/ztp/recovery-override", json={
        "host": "192.168.100.2",
        "name": "Leaf-01",
        "platform": "lstn",
        "hcl_t7064p15": True,
        "username": "python",
        "password": "Admin123!@#",
        "netconf_port": 830,
        "collect_asset": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["active"] is True
    assert data["override"]["host"] == "192.168.100.2"
    assert data["override"]["sysname"] == "Leaf-01"
    assert data["override"]["platform"] == "lstn"
    assert data["override"]["hcl_t7064p15"] is True

    state_file = tmp_path / "recovery_override.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["mgmt_ip"] == "192.168.100.2"
    assert state["mode"] == "recovery"
    assert state["collect_asset"] is False

    current = client.get("/api/ztp/recovery-override").json()["data"]
    assert current["active"] is True
    assert current["override"]["host"] == "192.168.100.2"

    cleared = client.delete("/api/ztp/recovery-override")
    assert cleared.status_code == 200
    assert cleared.json()["data"]["active"] is False
    assert not state_file.exists()


def test_ztp_recovery_override_rejects_invalid_ip(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.ztp_recovery.settings.ZTP_STATE_DIR", str(tmp_path))

    resp = client.post("/api/ztp/recovery-override", json={
        "host": "192.168.100.999",
        "platform": "lstn",
        "username": "python",
        "password": "Admin123!@#",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert not (tmp_path / "recovery_override.json").exists()
