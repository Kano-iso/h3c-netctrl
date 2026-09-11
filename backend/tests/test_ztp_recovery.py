"""v3.1.3 / S1-023 ZTP recovery override QA（含凭据卫生边界）.
"""
import json
import os
import stat

from app.schemas import ZtpOnboardRequest, ZtpRecoveryOverrideRequest

# 明显 synthetic test password（非真实设备口令）
TEST_PASS = "SyntheticTestPass!1"


def _post(client, monkeypatch, tmp_path, payload):
    monkeypatch.setattr("app.services.ztp_recovery.settings.ZTP_STATE_DIR", str(tmp_path))
    return client.post("/api/ztp/recovery-override", json=payload)


def test_ztp_recovery_override_write_read_clear(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.ztp_recovery.settings.ZTP_STATE_DIR", str(tmp_path))

    initial = client.get("/api/ztp/recovery-override")
    assert initial.status_code == 200
    assert initial.json()["data"]["active"] is False

    resp = _post(client, monkeypatch, tmp_path, {
        "host": "192.168.100.2",
        "name": "Leaf-01",
        "platform": "lstn",
        "hcl_t7064p15": True,
        "username": "python",
        "password": TEST_PASS,
        "netconf_port": 830,
        "collect_asset": True,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is True
    data = body["data"]
    assert data["active"] is True
    ov = data["override"]
    assert ov["host"] == "192.168.100.2"
    assert ov["sysname"] == "Leaf-01"
    assert ov["platform"] == "lstn"
    assert ov["hcl_t7064p15"] is True
    # S1-023: API 响应不回显明文密码，只给 password_set 布尔
    assert "password" not in ov
    assert ov["password_set"] is True

    state_file = tmp_path / "recovery_override.json"
    assert state_file.exists()
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["mgmt_ip"] == "192.168.100.2"
    assert state["mode"] == "recovery"
    assert state["collect_asset"] is False
    # S1-023: 明文密码仅落盘 state（渲染需要），但权限收紧为 0600
    assert state["password"] == TEST_PASS
    mode = stat.S_IMODE(state_file.stat().st_mode)
    assert mode == 0o600, f"recovery state 权限应 0600，实际 {oct(mode)}"

    current = client.get("/api/ztp/recovery-override").json()["data"]
    assert current["active"] is True
    assert current["override"]["host"] == "192.168.100.2"
    # S1-023: GET 同样脱敏
    assert "password" not in current["override"]
    assert current["override"]["password_set"] is True

    cleared = client.delete("/api/ztp/recovery-override")
    assert cleared.status_code == 200
    assert cleared.json()["data"]["active"] is False
    assert not state_file.exists()


def test_ztp_recovery_override_rejects_invalid_ip(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.ztp_recovery.settings.ZTP_STATE_DIR", str(tmp_path))

    resp = _post(client, monkeypatch, tmp_path, {
        "host": "192.168.100.999",
        "platform": "lstn",
        "username": "python",
        "password": TEST_PASS,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert not (tmp_path / "recovery_override.json").exists()


def test_ztp_recovery_missing_password_without_env_fails_clearly(client, monkeypatch, tmp_path):
    """缺密码 + 无既有 override + 无 ZTP_ADMIN_PASS → 明确失败（不回退代码内口令）。"""
    monkeypatch.delenv("ZTP_ADMIN_PASS", raising=False)
    resp = _post(client, monkeypatch, tmp_path, {
        "host": "192.168.100.3",
        "platform": "lstn",
        "username": "python",
        "password": None,
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["success"] is False
    assert "ZTP_ADMIN_PASS" in body.get("error", "")
    assert "不回退" in body.get("error", "")
    assert not (tmp_path / "recovery_override.json").exists()


def test_ztp_recovery_missing_password_injects_env(client, monkeypatch, tmp_path):
    """缺密码 + 无既有 override + ZTP_ADMIN_PASS 已设置 → 从环境注入。"""
    monkeypatch.setenv("ZTP_ADMIN_PASS", "EnvInjectedPass!1")
    resp = _post(client, monkeypatch, tmp_path, {
        "host": "192.168.100.4",
        "platform": "lstn",
        "username": "python",
        "password": None,
    })
    assert resp.status_code == 200
    assert resp.json()["success"] is True
    state = json.loads((tmp_path / "recovery_override.json").read_text(encoding="utf-8"))
    assert state["password"] == "EnvInjectedPass!1"


def test_ztp_recovery_blank_password_keeps_existing(client, monkeypatch, tmp_path):
    """已有 override 时留空密码 → 沿用已有密码，不清空。"""
    monkeypatch.setattr("app.services.ztp_recovery.settings.ZTP_STATE_DIR", str(tmp_path))
    first = _post(client, monkeypatch, tmp_path, {
        "host": "192.168.100.5",
        "platform": "lstn",
        "username": "python",
        "password": TEST_PASS,
    })
    assert first.json()["success"] is True

    # 第二次提交不带密码（前端留空 → null）
    second = _post(client, monkeypatch, tmp_path, {
        "host": "192.168.100.5",
        "platform": "lstn",
        "username": "python",
        "password": None,
    })
    assert second.json()["success"] is True
    state = json.loads((tmp_path / "recovery_override.json").read_text(encoding="utf-8"))
    assert state["password"] == TEST_PASS


def test_ztp_recovery_schema_has_no_password_default():
    """S1-023: ZTP schema 不得带代码内默认口令；password 字段语义符合新契约。"""
    onboard_pwd = ZtpOnboardRequest.model_fields["password"]
    assert onboard_pwd.is_required() is True
    assert not isinstance(onboard_pwd.default, str)  # 无字符串默认（不允许字面量口令）
    recovery_pwd = ZtpRecoveryOverrideRequest.model_fields["password"]
    assert recovery_pwd.is_required() is False
    assert recovery_pwd.default is None  # 留空 → 沿用已有 / 环境注入
