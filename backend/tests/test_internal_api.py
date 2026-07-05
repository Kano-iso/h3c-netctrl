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


# ============================================================================
# v2.5 缓存测试（8 场景，对应 specs/internal-api-cache/spec.md）
# ============================================================================


def _make_mock_client(resp_data=None, side_effect=None):
    """构造 mock httpx.Client，简化缓存测试样板"""
    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = resp_data or {"success": True, "data": []}

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    if side_effect is not None:
        mock_client.get.side_effect = side_effect
    else:
        mock_client.get.return_value = mock_resp
    return mock_client


def test_cache_hit_skips_http():
    """场景 1：缓存命中跳过 HTTP（5s 内第二次 GET 不发 HTTP）"""
    from app.internal_api import _internal_get, _cache, _cache_key
    url = "http://ctrl-test:8000/internal/devices"

    mock_client = _make_mock_client(resp_data={"success": True, "data": [{"id": 1}]})

    with patch("app.internal_api.httpx.Client", return_value=mock_client):
        # 第一次：发起 HTTP，写缓存
        r1 = _internal_get(url)
        assert r1 == {"success": True, "data": [{"id": 1}]}
        assert mock_client.get.call_count == 1

        # 第二次：5s 内同 URL，应命中缓存，不发起 HTTP
        r2 = _internal_get(url)
        assert r2 == {"success": True, "data": [{"id": 1}]}
        assert mock_client.get.call_count == 1  # 仍是 1，没增加

    # 验证缓存确实写入了
    assert _cache_key(url) in _cache


def test_cache_expired_refetches():
    """场景 2：缓存过期自动回源（>5s 后重新发 HTTP）"""
    from app.internal_api import _internal_get, _cache, _CACHE_TTL
    url = "http://ctrl-test:8000/internal/devices"

    mock_client = _make_mock_client(resp_data={"success": True, "data": []})

    # time.time() 调用顺序：
    # 1) 第一次 GET 成功后写缓存 → t=0.0
    # 2) 第二次 GET 缓存命中检查 → t=_CACHE_TTL+0.1（已过期）
    # 3) 第二次 GET 成功后写缓存 → t=_CACHE_TTL+0.1
    time_seq = [0.0, _CACHE_TTL + 0.1, _CACHE_TTL + 0.1]
    with patch("app.internal_api.httpx.Client", return_value=mock_client):
        with patch("app.internal_api.time.time", side_effect=time_seq):
            r1 = _internal_get(url)
            assert mock_client.get.call_count == 1

            # 过期后第二次 GET，应重新发 HTTP
            r2 = _internal_get(url)
            assert mock_client.get.call_count == 2
            assert r2 == {"success": True, "data": []}


def test_post_not_cached():
    """场景 3：写操作（POST）不缓存"""
    from app.internal_api import _internal_post, _cache, _cache_key
    url = "http://ctrl-test:8000/internal/logs"

    mock_resp = MagicMock()
    mock_resp.raise_for_status.return_value = None
    mock_resp.json.return_value = {"success": True}

    mock_client = MagicMock()
    mock_client.__enter__ = MagicMock(return_value=mock_client)
    mock_client.__exit__ = MagicMock(return_value=False)
    mock_client.post.return_value = mock_resp

    with patch("app.internal_api.httpx.Client", return_value=mock_client):
        _internal_post(url, {"device_id": 1})

    # POST 后缓存应为空（key 不存在）
    assert _cache_key(url) not in _cache
    assert len(_cache) == 0


def test_post_does_not_invalidate_get_cache():
    """场景 4：写操作不主动失效缓存（POST 后 GET 仍可能命中陈旧缓存）"""
    from app.internal_api import _internal_get, _internal_post, _cache
    get_url = "http://ctrl-test:8000/internal/devices"
    post_url = "http://ctrl-test:8000/internal/logs"

    # 先 GET 写缓存
    mock_get_client = _make_mock_client(resp_data={"success": True, "data": [{"id": 1, "v": "old"}]})
    with patch("app.internal_api.httpx.Client", return_value=mock_get_client):
        r1 = _internal_get(get_url)
        assert r1 == {"success": True, "data": [{"id": 1, "v": "old"}]}

    # POST 不影响缓存
    mock_post_resp = MagicMock()
    mock_post_resp.raise_for_status.return_value = None
    mock_post_resp.json.return_value = {"success": True}
    mock_post_client = MagicMock()
    mock_post_client.__enter__ = MagicMock(return_value=mock_post_client)
    mock_post_client.__exit__ = MagicMock(return_value=False)
    mock_post_client.post.return_value = mock_post_resp
    with patch("app.internal_api.httpx.Client", return_value=mock_post_client):
        _internal_post(post_url, {"device_id": 1})

    # 缓存仍在
    assert len(_cache) == 1

    # GET 仍命中陈旧缓存（5s 内）
    mock_get_client2 = _make_mock_client(resp_data={"success": True, "data": [{"id": 1, "v": "new"}]})
    with patch("app.internal_api.httpx.Client", return_value=mock_get_client2):
        r2 = _internal_get(get_url)
        # 返回陈旧数据，未发 HTTP
        assert r2 == {"success": True, "data": [{"id": 1, "v": "old"}]}
        assert mock_get_client2.get.call_count == 0


def test_different_params_cached_separately():
    """场景 5：不同 params 分别缓存（_cache_key 用 sorted tuple 区分）"""
    from app.internal_api import _cache_key

    key1 = _cache_key("http://ctrl-test:8000/internal/devices", None)
    key2 = _cache_key("http://ctrl-test:8000/internal/devices", {"status": "up"})
    key3 = _cache_key("http://ctrl-test:8000/internal/devices", {"status": "down"})

    assert key1 != key2
    assert key2 != key3
    assert key1 != key3


def test_same_params_shares_cache():
    """场景 6：同 params 共享缓存（_cache_key 同入参 → 同 key）"""
    from app.internal_api import _cache_key

    url = "http://ctrl-test:8000/internal/devices"
    params = {"status": "up", "vlan": 100}

    # dict 顺序不同但内容相同 → 同 key
    k1 = _cache_key(url, params)
    k2 = _cache_key(url, {"vlan": 100, "status": "up"})
    assert k1 == k2


def test_clear_cache_between_tests():
    """场景 7：测试间清缓存（autouse fixture 调 clear_cache 后 _cache 必空）"""
    from app.internal_api import _cache, clear_cache

    # 本 test 启动时 setup_db 已调 clear_cache，但内部可能写过——这里手动写一个再清
    _cache["fake_key"] = (0.0, {"fake": True})
    assert len(_cache) == 1

    clear_cache()
    assert len(_cache) == 0
    assert _cache == {}


def test_manual_clear_cache_invalidates():
    """场景 8：手动失效（业务代码调 clear_cache 后 GET 必发 HTTP）"""
    from app.internal_api import _internal_get, clear_cache, _cache
    url = "http://ctrl-test:8000/internal/devices"

    mock_client = _make_mock_client(resp_data={"success": True, "data": [{"id": 1}]})

    with patch("app.internal_api.httpx.Client", return_value=mock_client):
        # 第一次写缓存
        _internal_get(url)
        assert mock_client.get.call_count == 1
        assert len(_cache) == 1

        # 手动清缓存
        clear_cache()
        assert len(_cache) == 0

        # 第二次必发 HTTP（无缓存可命中）
        _internal_get(url)
        assert mock_client.get.call_count == 2
