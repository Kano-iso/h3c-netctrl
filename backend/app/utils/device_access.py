"""统一设备访问工具（v241-container-split Task 4.4）

让所有 router 在 monolith / split 模式下都能查询 device：
- monolith 模式：直接查本地 Device 表（性能最优）
- 3 容器模式（config/data 容器无 devices 表）：本地查失败 → 走 internal_api 调 ctrl 容器

设计要点：
- device_obj 在 split 模式用 SimpleNamespace 包装 dict，保留属性访问兼容
- internal_api 返回的 password 已解密，直接用
- 不需要 device 缓存表，每次按需查询（调用频次低，可接受）
"""
import logging
from types import SimpleNamespace
from typing import Optional, Tuple, List

from sqlalchemy.orm import Session

from app.models import Device
from app.utils.crypto import decrypt_password
from app.schemas import APIResponse
from app.i18n_keys import err, error_response

logger = logging.getLogger("app")


def _wrap_device_dict(d: dict) -> SimpleNamespace:
    """把 internal_api 返回的 dict 包装成兼容 Device ORM 的对象

    internal_api.get_device() 返回字段：
        id / name / host / port / username / password（已解密）/ protected_interfaces
    """
    return SimpleNamespace(
        id=d["id"],
        name=d["name"],
        host=d["host"],
        port=d["port"],
        username=d["username"],
        # password_encrypted 兼容字段：内部 API 已解密，直接存放
        password_encrypted=d.get("password", ""),
        protected_interfaces=d.get("protected_interfaces", "[]"),
        # 内部 API 已解密的密码（部分代码可能直接访问 _password_decrypted）
        _password_decrypted=d.get("password", ""),
        # v3.0 SDN: platform 字段（split 模式内部 API 透传）
        platform=d.get("platform"),
    )


def get_device_with_password(
    db: Session, device_id: int
) -> Tuple[Optional[object], Optional[str], Optional[APIResponse]]:
    """获取设备 + 解密密码

    Returns:
        (device_obj, password, error_resp)
        - 成功: (device_obj, password, None)
        - 失败: (None, None, APIResponse(success=False, error=...))
    """
    # 1. 先尝试本地查（monolith 模式）
    table_unavailable = False
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
    except Exception as e:
        # split 模式：config/data 容器无 devices 表
        logger.warning(f"本地 Device 表不可用，走内部 API: {e}")
        device = None
        table_unavailable = True

    # 本地表查询成功（monolith 模式）
    if not table_unavailable:
        if device:
            try:
                password = decrypt_password(device.password_encrypted)
                return device, password, None
            except Exception as e:
                logger.error(f"密码解密失败: {e}")
                return None, None, error_response(err.DEVICE_CRYPTO_DECRYPT_FAILED)
        else:
            # 设备真不存在（本地查到了但返回 None）
            return None, None, error_response(
                err.DEVICE_NOT_FOUND, params={"id": device_id}
            )

    # 2. 走内部 API（split 模式）
    try:
        from app.internal_api import get_device
        resp = get_device(device_id)
        if not resp.get("success"):
            err_msg = resp.get("error", f"设备不存在: id={device_id}")
            return None, None, error_response(
                err.DEVICE_NOT_FOUND, params={"id": device_id}, fallback=err_msg
            )
        d = resp["data"]
        device_obj = _wrap_device_dict(d)
        # 内部 API 已解密密码
        return device_obj, d.get("password", ""), None
    except Exception as e:
        logger.error(f"内部 API 查设备失败: {e}")
        return None, None, error_response(
            err.DEVICE_NOT_FOUND, params={"id": device_id}, fallback=f"设备查询失败: {e}"
        )


def get_device_or_error(
    db: Session, device_id: int
) -> Tuple[Optional[object], Optional[APIResponse]]:
    """获取设备（不需要密码的场景，如 asset 查询）

    Returns:
        (device_obj, error_resp)
        - 成功: (device_obj, None)
        - 失败: (None, APIResponse(success=False, error=...))
    """
    device, _, error = get_device_with_password(db, device_id)
    if error:
        return None, error
    return device, None


def get_devices_batch(db: Session, device_ids: List[int]) -> List[object]:
    """批量获取设备（batch 用）

    monolith 模式：本地批量查
    split 模式：调 internal_api.get_devices() 拉所有再过滤
    """
    if not device_ids:
        return []

    # 1. 本地批量查
    try:
        devices = db.query(Device).filter(Device.id.in_(device_ids)).all()
        return devices  # 本地查询成功（无论是否为空都直接返回）
    except Exception as e:
        logger.warning(f"本地 Device 表不可用，走内部 API: {e}")

    # 2. 走内部 API
    try:
        from app.internal_api import get_devices
        resp = get_devices()
        if not resp.get("success"):
            return []
        devices_data = resp["data"]
        id_set = set(device_ids)
        return [
            _wrap_device_dict(d)
            for d in devices_data
            if d["id"] in id_set
        ]
    except Exception as e:
        logger.error(f"内部 API 批量查设备失败: {e}")
        return []
