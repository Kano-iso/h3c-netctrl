"""内部 API 客户端：跨容器通信（v241-container-split）

设计：
- 寻址：环境变量注入（12-factor），不硬编码 IP/端口
- 鉴权：X-Internal-Token 头
- 重试：3 次指数退避（1s / 2s / 4s）
- 超时：5s
- 错误：返回中文错误信息，不暴露技术异常
- 缓存（v2.5）：GET 请求 5s TTL 本地缓存，命中跳过 HTTP
"""
import os
import time
import logging
from typing import Optional

import httpx

logger = logging.getLogger("app.internal_api")

# 容器寻址（环境变量注入，默认 Docker 内部 DNS 容器名）
CTRL_URL = os.getenv("INTERNAL_CTRL_URL", "http://ctrl:8000")
CONFIG_URL = os.getenv("INTERNAL_CONFIG_URL", "http://config:8000")
DATA_URL = os.getenv("INTERNAL_DATA_URL", "http://data:8000")
INTERNAL_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")

# 请求配置
_TIMEOUT = 5.0
_MAX_RETRIES = 3

# 缓存配置（v2.5：GET 请求 5s TTL 本地缓存）
_CACHE_TTL = 5.0  # 秒
_cache: dict = {}  # key: (url, params_tuple, headers_tuple) → value: (timestamp, data)


def _headers() -> dict:
    """构造内部 API 请求头"""
    return {"X-Internal-Token": INTERNAL_TOKEN}


def _cache_key(url: str, params: Optional[dict] = None) -> tuple:
    """构造缓存 key

    key = (url, params_tuple, headers_tuple)
    - params: dict 转 sorted tuple 保证可哈希
    - headers: _headers() 转 sorted tuple（X-Internal-Token 参与 key）
    """
    params_t = tuple(sorted(params.items())) if params else ()
    headers_t = tuple(sorted(_headers().items()))
    return (url, params_t, headers_t)


def clear_cache() -> None:
    """清除全部缓存

    用途：
    - 测试间隔离（pytest fixture 调用）
    - 业务代码手动失效
    """
    _cache.clear()


def _internal_get(url: str, timeout: float = _TIMEOUT) -> dict:
    """GET 请求，带重试 + 超时 + 鉴权 + 5s TTL 缓存

    缓存策略：
    - 命中跳过 HTTP，5s TTL
    - 仅成功响应缓存（raise_for_status 不抛异常后写）
    - POST/PUT/DELETE 不缓存（见 _internal_post/_internal_delete）
    - 写操作不主动失效缓存（接受短暂陈旧，TTL 自然过期）
    """
    key = _cache_key(url)
    cached_entry = _cache.get(key)
    if cached_entry is not None:
        timestamp, data = cached_entry
        if time.time() - timestamp <= _CACHE_TTL:
            logger.debug(f"内部 GET {url} 缓存命中")
            return data

    last_err: Optional[Exception] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url, headers=_headers())
                resp.raise_for_status()
                data = resp.json()
                _cache[key] = (time.time(), data)  # 仅成功响应缓存
                return data
        except Exception as e:
            last_err = e
            if attempt < _MAX_RETRIES:
                wait = 2 ** (attempt - 1)  # 1s / 2s / 4s
                logger.warning(f"内部 GET {url} 第 {attempt} 次失败: {e}，{wait}s 后重试")
                time.sleep(wait)
    logger.error(f"内部 GET {url} 重试 {_MAX_RETRIES} 次仍失败: {last_err}")
    raise RuntimeError(f"内部 API 调用失败: {last_err}")


def _internal_post(url: str, json_data: dict, timeout: float = _TIMEOUT) -> dict:
    """POST 请求，带重试 + 超时 + 鉴权"""
    last_err: Optional[Exception] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.post(url, json=json_data, headers=_headers())
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            last_err = e
            if attempt < _MAX_RETRIES:
                wait = 2 ** (attempt - 1)
                logger.warning(f"内部 POST {url} 第 {attempt} 次失败: {e}，{wait}s 后重试")
                time.sleep(wait)
    logger.error(f"内部 POST {url} 重试 {_MAX_RETRIES} 次仍失败: {last_err}")
    raise RuntimeError(f"内部 API 调用失败: {last_err}")


def _internal_delete(url: str, timeout: float = _TIMEOUT) -> dict:
    """DELETE 请求，带重试 + 超时 + 鉴权"""
    last_err: Optional[Exception] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.delete(url, headers=_headers())
                resp.raise_for_status()
                return resp.json()
        except Exception as e:
            last_err = e
            if attempt < _MAX_RETRIES:
                wait = 2 ** (attempt - 1)
                logger.warning(f"内部 DELETE {url} 第 {attempt} 次失败: {e}，{wait}s 后重试")
                time.sleep(wait)
    logger.error(f"内部 DELETE {url} 重试 {_MAX_RETRIES} 次仍失败: {last_err}")
    raise RuntimeError(f"内部 API 调用失败: {last_err}")


# ── 业务调用 ─────────────────────────────────


def get_devices() -> dict:
    """从 ctrl 容器拉所有设备列表（config/data 启动时缓存用）"""
    return _internal_get(f"{CTRL_URL}/internal/devices")


def get_device(device_id: int) -> dict:
    """从 ctrl 容器查单个设备（NETCONF 连接前查 IP/凭据）"""
    return _internal_get(f"{CTRL_URL}/internal/devices/{device_id}")


def write_log(device_id: int, action: str, status: str, detail: str) -> dict:
    """写操作日志到 ctrl 容器"""
    return _internal_post(f"{CTRL_URL}/internal/logs", {
        "device_id": device_id,
        "action": action,
        "status": status,
        "detail": detail,
    })


def trigger_backup(device_id: int, types: list) -> dict:
    """触发 data 容器执行备份"""
    return _internal_post(f"{DATA_URL}/internal/backup", {
        "device_id": device_id,
        "types": types,
    })


def get_assets() -> dict:
    """从 data 容器拉所有资产数据（dashboard 聚合用）"""
    return _internal_get(f"{DATA_URL}/internal/assets")


def upsert_asset(device_id: int, status: str, info: dict) -> dict:
    """让 ctrl 容器在 split 模式下写 data 容器 asset。"""
    payload = {"status": status, **(info or {})}
    return _internal_post(f"{DATA_URL}/internal/assets/device/{device_id}/upsert", payload)


def cleanup_device(device_id: int) -> dict:
    """调 data 容器清理设备的 asset / backup 数据 + 本地备份文件

    触发场景：split 模式下 ctrl 容器 `DELETE /api/devices/{id}` 成功后调。
    monolith 模式不调（SQLAlchemy cascade 已自动级联清理）。
    """
    return _internal_delete(f"{DATA_URL}/internal/devices/{device_id}/cleanup")
