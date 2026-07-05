"""v2.6.0 后端 i18n 单测

覆盖：
1. i18n_keys 模块：
   - is_valid_key() 正常 / 拒绝未知 key
   - error_response() 必填 4 字段填充（success/error/error_key/error_params）
   - _format_fallback() 模板格式化
2. APIResponse schema：
   - 4 字段可序列化 / 向后兼容（error_key 可选）
3. 关键 router 错误场景：
   - device/interface/vlan/backup 错误响应带 error_key
   - error 字段填中文降级
4. 集中表完整性：FALLBACK_MESSAGES 与 err 字典对齐
"""
import pytest
from pydantic import ValidationError

from app.schemas import APIResponse
from app.i18n_keys import (
    err,
    error_response,
    is_valid_key,
    FALLBACK_MESSAGES,
    I18nKey,
    Common,
    Device,
    Interface,
    VLAN,
    Asset,
    Backup,
    Batch,
    Execute,
    Log,
    Dashboard,
)


# ======================== i18n_keys 模块 ========================

class TestIsValidKey:
    def test_known_keys_are_valid(self):
        """所有 err.* 引用都应通过 is_valid_key"""
        for v in vars(err).values():
            assert is_valid_key(v), f"Known key {v} should be valid"

    def test_unknown_key_is_invalid(self):
        """未注册的 key 字符串应被拒绝"""
        assert not is_valid_key("nonexistent.key")
        assert not is_valid_key("device.unknown_error")

    def test_non_string_input(self):
        """非字符串 / 非 I18nKey 输入应返回 False"""
        assert not is_valid_key(None)
        assert not is_valid_key(123)
        assert not is_valid_key({})

    def test_i18n_key_instance_is_valid(self):
        """I18nKey 实例本身应能被验证"""
        assert is_valid_key(Device.NOT_FOUND)

    def test_dot_access_works(self):
        """err.X 点访问应返回 I18nKey 实例"""
        assert isinstance(err.DEVICE_NOT_FOUND, I18nKey)
        assert err.DEVICE_NOT_FOUND.value == "device.not_found"


class TestErrorResponse:
    def test_basic_fields_filled(self):
        """error_response 应填充 4 字段（success/error/error_key/error_params）"""
        resp = error_response(err.DEVICE_NOT_FOUND, params={"id": 42})
        assert resp.success is False
        assert resp.error_key == "device.not_found"
        assert resp.error_params == {"id": 42}
        assert "42" in resp.error  # 中文降级含 id

    def test_fallback_chinese(self):
        """FALLBACK_MESSAGES 模板应正确格式化"""
        resp = error_response(err.DEVICE_NOT_FOUND, params={"id": 99})
        assert resp.error == "设备不存在: id=99"

    def test_no_params_keeps_template(self):
        """无 params 时保留模板字符串"""
        resp = error_response(err.DEVICE_MISSING_HOST)
        assert resp.error == "缺少必填字段: host"
        assert resp.error_params is None

    def test_unknown_key_returns_defensive_error(self):
        """未注册的 key 应返回 'Unknown i18n key' 防御性错误"""
        resp = error_response("custom.unknown.key")
        assert resp.success is False
        assert resp.error_key == "custom.unknown.key"
        assert "Unknown i18n key" in resp.error

    def test_custom_fallback_overrides(self):
        """显式 fallback 应覆盖默认中文降级"""
        resp = error_response(err.DEVICE_NOT_FOUND, params={"id": 1}, fallback="自定义错误")
        assert resp.error == "自定义错误"
        assert resp.error_key == "device.not_found"
        assert resp.error_params == {"id": 1}


class TestFallbackMessagesConsistency:
    """FALLBACK_MESSAGES 集中表与 err 字典应对齐"""

    def test_all_err_keys_have_fallback(self):
        """err 字典中所有 key 都必须在 FALLBACK_MESSAGES 里有降级"""
        for name in vars(err):
            key = getattr(err, name)
            assert key in FALLBACK_MESSAGES, f"err.{name} ({key}) 缺少 FALLBACK_MESSAGES 条目"

    def test_fallback_messages_have_err(self):
        """FALLBACK_MESSAGES 中所有 key 都应在 err 字典里（避免孤儿 key）"""
        err_values = set(vars(err).values())
        for key in FALLBACK_MESSAGES:
            assert key in err_values, f"FALLBACK_MESSAGES 孤儿 key: {key}"


# ======================== APIResponse schema ========================

class TestAPIResponseSchema:
    def test_minimal_response_no_i18n(self):
        """向后兼容：error_key 可选，缺省时为 None"""
        resp = APIResponse(success=True, data={"foo": "bar"})
        assert resp.error is None
        assert resp.error_key is None
        assert resp.error_params is None
        assert resp.success is True

    def test_full_i18n_response(self):
        """完整 i18n 响应：4 字段都有"""
        resp = APIResponse(
            success=False,
            error="设备不存在: id=42",
            error_key="device.not_found",
            error_params={"id": 42},
        )
        assert resp.error_key == "device.not_found"
        assert resp.error_params == {"id": 42}
        assert resp.error == "设备不存在: id=42"

    def test_serialization_roundtrip(self):
        """JSON 序列化 / 反序列化保持字段一致"""
        resp = APIResponse(
            success=False,
            error="X",
            error_key="test.key",
            error_params={"a": 1},
        )
        j = resp.model_dump()
        assert j["error_key"] == "test.key"
        assert j["error_params"] == {"a": 1}
        # 反序列化
        resp2 = APIResponse(**j)
        assert resp2.error_key == resp.error_key
        assert resp2.error_params == resp.error_params


# ======================== 关键 router 错误场景 ========================

class TestDeviceRouterI18n:
    """device router 错误响应带 error_key"""

    def test_get_device_not_found_has_key(self, client):
        resp = client.get("/api/devices/9999")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["error_key"] == "device.not_found"
        assert body["error_params"] == {"id": 9999}

    def test_create_device_missing_host(self, client):
        resp = client.post("/api/devices", json={
            "name": "Test",
            "host": "",
            "port": 830,
            "username": "admin",
            "password": "x",
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is False
        assert body["error_key"] == "device.missing_host"
        assert body["error"] == "缺少必填字段: host"

    def test_create_device_missing_username(self, client):
        resp = client.post("/api/devices", json={
            "name": "Test",
            "host": "1.2.3.4",
            "port": 830,
            "username": "",
            "password": "x",
        })
        body = resp.json()
        assert body["error_key"] == "device.missing_username"

    def test_create_device_missing_password(self, client):
        resp = client.post("/api/devices", json={
            "name": "Test",
            "host": "1.2.3.4",
            "port": 830,
            "username": "admin",
            "password": "",
        })
        body = resp.json()
        assert body["error_key"] == "device.missing_password"


class TestVlanRouterI18n:
    """vlan router 错误响应带 error_key"""

    def test_create_vlan_missing_name(self, client):
        resp = client.post("/api/devices/1/vlans", json={"vlan_id": 100, "name": ""})
        body = resp.json()
        assert body["success"] is False
        assert body["error_key"] == "common.missing_field"
        assert body["error_params"] == {"field": "name"}


class TestBatchRouterI18n:
    """batch router 错误响应带 error_key"""

    def test_batch_no_devices(self, client):
        resp = client.post("/api/batch/execute", json={"device_ids": [], "command": "show version"})
        body = resp.json()
        assert body["success"] is False
        assert body["error_key"] == "batch.no_devices"

    def test_batch_empty_command(self, client):
        resp = client.post("/api/batch/execute", json={"device_ids": [1], "command": "  "})
        body = resp.json()
        assert body["success"] is False
        assert body["error_key"] == "batch.empty_command"


class TestExecuteRouterI18n:
    """execute router 错误响应带 error_key"""

    def test_execute_device_not_found(self, client):
        """执行到不存在的设备 → device_not_found key"""
        resp = client.post("/api/devices/9999/execute", json={"command": "show version"})
        # 设备不存在返回 error_resp
        body = resp.json()
        assert body["success"] is False
        # 设备访问层可能返 DEVICE_NOT_FOUND 或 EXECUTE_DEVICE_NOT_FOUND
        assert body["error_key"] in ("device.not_found", "execute.device_not_found")


class TestBackupRouterI18n:
    """backup router 错误响应带 error_key"""

    def test_backup_invalid_types(self, client):
        """不支持的备份类型 → invalid_param key"""
        resp = client.post("/api/devices/1/backup", json={"types": ["invalid"]})
        body = resp.json()
        # 设备不存在时可能先返 device_not_found
        assert body["success"] is False
        assert body["error_key"] in ("common.invalid_param", "device.not_found")

    def test_task_not_found(self, client):
        """任务不存在 → batch.task_not_found key"""
        resp = client.get("/api/tasks/9999")
        body = resp.json()
        assert body["success"] is False
        assert body["error_key"] == "batch.task_not_found"
        assert body["error_params"] == {"task_id": 9999}


# ======================== 关键 key 集中覆盖 ========================

class TestKeyCoverage:
    """确保所有 i18n 域名都有 key 注册（防止遗漏 domain）"""

    def test_all_domains_have_keys(self):
        """每个域至少 1 个 key"""
        domains = [Common, Device, Interface, VLAN, Asset, Backup, Batch, Execute, Log, Dashboard]
        for d in domains:
            attrs = [v for k, v in vars(d).items() if isinstance(v, I18nKey)]
            assert len(attrs) > 0, f"{d.__name__} 域无 key"
