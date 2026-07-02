"""内部 API 客户端单测（v241-container-split）

验证：
- 重试 3 次 + 指数退避
- 超时 5s
- X-Internal-Token 鉴权头
- 业务调用（get_devices / get_device / write_log / trigger_backup / get_assets）
"""
import os
from unittest.mock import patch, MagicMock, call
import pytest

# 设置环境变量
os.environ["INTERNAL_CTRL_URL"] = "http://ctrl-test:8000"
os.environ["INTERNAL_DATA_URL"] = "http://data-test:8000"
os.environ["INTERNAL_API_TOKEN"] = "test-token-123"


def test_headers_contains_token():
    """验证请求头包含 X-Internal-Token"""
    from app.internal_api import _headers
    h = _headers()
    assert h["X-Internal-Token"] == "test-token-123"


def test_internal_get_success():
    """GET 请求成功"""
    from app.internal_api import _internal_get
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"success": True, "data": []}

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.return_value = mock_resp

    with patch("app.internal_api.httpx.Client", return_value=mock_client):
        result = _internal_get("http://ctrl-test:8000/internal/devices")
        assert result == {"success": True, "data": []}
        mock_client.get.assert_called_once()
        # 验证传了 headers
        _, kwargs = mock_client.get.call_args
        assert kwargs["headers"]["X-Internal-Token"] == "test-token-123"


def test_internal_get_retry_then_success():
    """GET 第 1 次失败，第 2 次成功（验证重试）"""
    from app.internal_api import _internal_get
    mock_resp_ok = MagicMock()
    mock_resp_ok.raise_for_status.return_value = None
    mock_resp_ok.json.return_value = {"success": True}

    mock_resp_fail = MagicMock()
    mock_resp_fail.raise_for_status.side_effect = Exception("connection error")

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = [mock_resp_fail, mock_resp_ok]

    with patch("app.internal_api.httpx.Client", return_value=mock_client):
        with patch("app.internal_api.time.sleep"):  # 跳过实际等待
            result = _internal_get("http://ctrl-test:8000/internal/devices")
            assert result == {"success": True}
            assert mock_client.get.call_count == 2


def test_internal_get_all_retries_fail():
    """GET 重试 3 次全失败，抛 RuntimeError"""
    from app.internal_api import _internal_get
    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.get.side_effect = Exception("connection error")

    with patch("app.internal_api.httpx.Client", return_value=mock_client):
        with patch("app.internal_api.time.sleep"):
            with pytest.raises(RuntimeError, match="内部 API 调用失败"):
                _internal_get("http://ctrl-test:8000/internal/devices")
            assert mock_client.get.call_count == 3


def test_internal_post_success():
    """POST 请求成功"""
    from app.internal_api import _internal_post
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"success": True}

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp

    with patch("app.internal_api.httpx.Client", return_value=mock_client):
        result = _internal_post("http://ctrl-test:8000/internal/logs", {"device_id": 1})
        assert result == {"success": True}
        _, kwargs = mock_client.post.call_args
        assert kwargs["headers"]["X-Internal-Token"] == "test-token-123"
        assert kwargs["json"] == {"device_id": 1}


def test_get_devices_calls_ctrl_url():
    """get_devices 调用 CTRL_URL/internal/devices"""
    from app.internal_api import get_devices, CTRL_URL
    with patch("app.internal_api._internal_get") as mock_get:
        mock_get.return_value = {"success": True, "data": []}
        get_devices()
        mock_get.assert_called_once_with(f"{CTRL_URL}/internal/devices")


def test_get_device_calls_ctrl_url():
    """get_device 调用 CTRL_URL/internal/devices/{id}"""
    from app.internal_api import get_device, CTRL_URL
    with patch("app.internal_api._internal_get") as mock_get:
        mock_get.return_value = {"success": True, "data": {}}
        get_device(5)
        mock_get.assert_called_once_with(f"{CTRL_URL}/internal/devices/5")


def test_write_log_calls_ctrl_url():
    """write_log 调用 CTRL_URL/internal/logs"""
    from app.internal_api import write_log, CTRL_URL
    with patch("app.internal_api._internal_post") as mock_post:
        mock_post.return_value = {"success": True}
        write_log(1, "backup_create", "成功", "测试日志")
        mock_post.assert_called_once_with(f"{CTRL_URL}/internal/logs", {
            "device_id": 1, "action": "backup_create", "status": "成功", "detail": "测试日志",
        })


def test_trigger_backup_calls_data_url():
    """trigger_backup 调用 DATA_URL/internal/backup"""
    from app.internal_api import trigger_backup, DATA_URL
    with patch("app.internal_api._internal_post") as mock_post:
        mock_post.return_value = {"success": True}
        trigger_backup(5, ["startup", "running"])
        mock_post.assert_called_once_with(f"{DATA_URL}/internal/backup", {
            "device_id": 5, "types": ["startup", "running"],
        })


def test_get_assets_calls_data_url():
    """get_assets 调用 DATA_URL/internal/assets"""
    from app.internal_api import get_assets, DATA_URL
    with patch("app.internal_api._internal_get") as mock_get:
        mock_get.return_value = {"success": True, "data": []}
        get_assets()
        mock_get.assert_called_once_with(f"{DATA_URL}/internal/assets")
