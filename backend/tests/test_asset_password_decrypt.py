"""v2.6.1 fix-asset-split-password-decrypt — split 模式密码二次解密单测

覆盖：
- monolith 模式：Device ORM + 密文 password_encrypted → refresh 成功（明文解密一次）
- split 模式：internal_api.get_device 返回明文 password → refresh 成功（不二次 decrypt）
- split 模式 + 错误凭据：internal_api.get_device 返 None / success=false → DEVICE_NOT_FOUND 错误

修复前（旧 refresh_asset）：
  password = decrypt_password(device.password_encrypted)  # split 模式下把明文当密文解 → InvalidToken

修复后（新 refresh_asset）：
  device, password, error = get_device_with_password(db, device_id)  # 统一封装，内部已解
  # password 已是明文，直接用
"""
from unittest.mock import MagicMock, patch

from sqlalchemy.exc import NoSuchTableError

from app.models import Device


# 工具 helper：mock SSHExecutor 返 valid 硬件信息 + 跳过真 SSH
def _patch_ssh_executor_with_valid_info():
    """mock app.utils.ssh_executor.SSHExecutor → 返 valid 硬件信息（不连真设备）

    注意：refresh_asset 用 `from app.utils.ssh_executor import SSHExecutor` 局部 import，
    所以必须 patch `app.utils.ssh_executor.SSHExecutor`（模块内的类），不能 patch `app.routers.asset.SSHExecutor`。
    """
    fake_executor = MagicMock()
    fake_executor.collect_hardware_info.return_value = {
        "model": "H3C S6850-56HF",
        "serial_number": "CNEXXXXXXXXX",
        "firmware_version": "Version 7.1.070",
        "software_package": "S6850-56HF-CMW710-R6329",
    }
    return patch("app.utils.ssh_executor.SSHExecutor", return_value=fake_executor)


# ===== Case 1: monolith 模式 =====

def test_refresh_asset_monolith_mode_uses_plaintext_password(client, created_device):
    """monolith 模式：Device ORM + 密文 password_encrypted → refresh 成功

    验证：device.password_encrypted 是真密文 → get_device_with_password 内部 decrypt → 用明文连 SSH
    行为：status=online + 硬件信息写入 asset
    """
    device_id = created_device["id"]
    with _patch_ssh_executor_with_valid_info():
        resp = client.post(f"/api/assets/device/{device_id}/refresh")

    assert resp.status_code == 200, f"refresh 失败 status={resp.status_code} body={resp.text}"
    data = resp.json()
    assert data["success"] is True, f"monolith 模式 refresh 应 success，实际 {data}"
    assert "硬件信息已刷新" in data["data"]["message"]


# ===== Case 2: split 模式 =====

def test_refresh_asset_split_mode_uses_plaintext_from_internal_api(client, created_device, db, monkeypatch):
    """split 模式：internal_api.get_device 返明文 → refresh 成功（不二次 decrypt）

    关键验证（修复目标）：
    - 模拟 split 模式：db.query(Device) 抛 NoSuchTableError
    - mock internal_api.get_device 返 {password: "明文"}（不加密）
    - 旧代码会调 decrypt_password("明文") → InvalidToken 失败
    - 新代码直接用 internal_api 已解密的明文 → 成功

    复现链路（pre-fix bug）：
      device.password_encrypted = "明文"（来自 _wrap_device_dict）
      ↓
      decrypt_password("明文") → Fernet InvalidToken
    """
    device_id = created_device["id"]

    # 1. 模拟 split 模式：data 容器无 devices 表 → db.query(Device) 抛 NoSuchTableError
    real_db_query = db.query

    def fake_query(*args, **kwargs):
        if args and args[0] is Device:
            raise NoSuchTableError("simulated: data 容器无 devices 表（split 模式）")
        return real_db_query(*args, **kwargs)

    monkeypatch.setattr(db, "query", fake_query)

    # 2. mock internal_api.get_device → 返明文 password（ctrl 容器已内部解密）
    def fake_internal_get_device(dev_id):
        return {
            "success": True,
            "data": {
                "id": dev_id,
                "name": "Test-Device",
                "host": "192.168.100.100",
                "port": 22,
                "username": "admin",
                # 关键：password 是明文（ctrl 容器已 decrypt）
                "password": "TestPass123!",
                "protected_interfaces": "[]",
            },
        }

    import app.internal_api as internal_api_mod
    monkeypatch.setattr(internal_api_mod, "get_device", fake_internal_get_device)

    # 3. mock SSHExecutor → 返 valid 硬件信息
    with _patch_ssh_executor_with_valid_info():
        resp = client.post(f"/api/assets/device/{device_id}/refresh")

    assert resp.status_code == 200, f"split 模式 refresh 失败 status={resp.status_code} body={resp.text}"
    data = resp.json()
    # 关键断言：success=True（修复后，明文不再二次 decrypt）
    assert data["success"] is True, (
        f"split 模式 refresh 应 success（密码已由 ctrl 内部解密）"
        f"，实际 {data}"
    )
    assert "硬件信息已刷新" in data["data"]["message"]


# ===== Case 3: split 模式 + 错误凭据（设备不存在）=====

def test_refresh_asset_split_mode_device_not_found_returns_clear_error(client, db, monkeypatch):
    """split 模式：internal_api.get_device 返 success=false（设备不存在） → DEVICE_NOT_FOUND 错误

    验证：错误场景下返明确中文错误（DEVICE_NOT_FOUND），不暴露技术异常
    """
    # 1. 模拟 split 模式：data 容器无 devices 表
    real_db_query = db.query

    def fake_query(*args, **kwargs):
        if args and args[0] is Device:
            raise NoSuchTableError("simulated: data 容器无 devices 表（split 模式）")
        return real_db_query(*args, **kwargs)

    monkeypatch.setattr(db, "query", fake_query)

    # 2. mock internal_api.get_device → 返 success=False（设备不存在）
    def fake_internal_get_device(dev_id):
        return {
            "success": False,
            "error": f"设备不存在: id={dev_id}",
        }

    import app.internal_api as internal_api_mod
    monkeypatch.setattr(internal_api_mod, "get_device", fake_internal_get_device)

    # 3. 调用 refresh（设备 id=99999 不存在）
    resp = client.post("/api/assets/device/99999/refresh")

    assert resp.status_code == 200, f"应返 200 (APIResponse wrap)，实际 {resp.status_code}"
    data = resp.json()
    assert data["success"] is False, f"设备不存在应返 success=False，实际 {data}"
    err = data.get("error", "")
    # 关键断言：错误信息是中文 + 含"设备"和"不存在"关键字
    assert "设备" in err and "不存在" in err, (
        f"应返明确中文错误，实际 error={err!r}"
    )
