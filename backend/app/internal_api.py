"""内部 API 客户端：跨容器通信（v241-container-split）

设计：
- 寻址：环境变量注入（12-factor），不硬编码 IP/端口
- 鉴权：X-Internal-Token 头
- 重试：3 次指数退避（1s / 2s / 4s）
- 超时：5s
- 错误：返回中文错误信息，不暴露技术异常
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


def _headers() -> dict:
    """构造内部 API 请求头"""
    return {"X-Internal-Token": INTERNAL_TOKEN}


def _internal_get(url: str, timeout: float = _TIMEOUT) -> dict:
    """GET 请求，带重试 + 超时 + 鉴权"""
    last_err: Optional[Exception] = None
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            with httpx.Client(timeout=timeout) as client:
                resp = client.get(url, headers=_headers())
                resp.raise_for_status()
                return resp.json()
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
