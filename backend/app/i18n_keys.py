# v2.6.0 i18n：错误码集中表
#
# 设计目标：
# 1. 集中管理所有后端返回的 i18n key，便于：
#    - 前端 locale 文件同步新增条目
#    - 单测验证 key 完整性（schema 与 i18n 字典对齐）
#    - 文档归类
# 2. 提供 error_response() helper，统一返回 success=False + error + error_key + error_params
# 3. 提供 is_valid_key()，防止拼写错误（运行时防御）
#
# 命名规范：<domain>.<semantic>
# - device.* / interface.* / vlan.* / asset.* / backup.* / batch.* / execute.* / log.* / dashboard.*
# - common.* 通用（参数错误 / 未找到 / 内部错误）
# - auth.* 认证（未来扩展）
#
# 使用：
#   from app.i18n_keys import err, error_response
#   return error_response(err.DEVICE_NOT_FOUND, params={"id": device_id})
#   # 等价于 APIResponse(success=False, error="设备不存在: id=42", error_key="device.not_found", error_params={"id": 42})

from typing import Optional
from types import SimpleNamespace

from app.schemas import APIResponse


class I18nKey:
    """i18n key 字符串类（仅作类型标识，运行时等价 str）"""
    __slots__ = ("value",)

    def __init__(self, value: str):
        self.value = value

    def __str__(self):
        return self.value

    def __repr__(self):
        return f"I18nKey({self.value!r})"

    def __eq__(self, other):
        if isinstance(other, I18nKey):
            return self.value == other.value
        if isinstance(other, str):
            return self.value == other
        return False

    def __hash__(self):
        return hash(self.value)


# ===== 通用（common）=====
class Common:
    MISSING_FIELD = I18nKey("common.missing_field")           # 缺少必填字段: {field}
    INVALID_PARAM = I18nKey("common.invalid_param")            # 参数不合法: {param}
    NOT_FOUND = I18nKey("common.not_found")                    # 资源不存在: {resource}
    INTERNAL_ERROR = I18nKey("common.internal_error")          # 内部错误: {message}
    OPERATION_FAILED = I18nKey("common.operation_failed")      # 操作失败: {error}
    INVALID_PORT = I18nKey("common.invalid_port")              # 端口不合法: {port}
    CRYPTO_FAILED = I18nKey("common.crypto_failed")            # 密码加解密失败


# ===== 设备（device）=====
class Device:
    NOT_FOUND = I18nKey("device.not_found")                    # 设备不存在: id={id}
    MISSING_HOST = I18nKey("device.missing_host")              # 缺少必填字段: host
    MISSING_USERNAME = I18nKey("device.missing_username")      # 缺少必填字段: username
    MISSING_PASSWORD = I18nKey("device.missing_password")      # 缺少必填字段: password
    EXISTS_V1_COMPAT = I18nKey("device.exists_v1_compat")      # V1.0 仅支持单设备
    NOT_CONFIGURED = I18nKey("device.not_configured")          # 未配置设备
    CONNECT_FAILED = I18nKey("device.connect_failed")          # 设备连接失败: {error}
    CONNECT_AUTH_FAILED = I18nKey("device.connect_auth_failed")  # 认证失败
    CONNECT_TIMEOUT = I18nKey("device.connect_timeout")        # 连接超时
    CONNECT_REFUSED = I18nKey("device.connect_refused")        # 连接被拒绝
    CONNECT_UNKNOWN_HOST = I18nKey("device.connect_unknown_host")  # 主机不可达
    CRYPTO_DECRYPT_FAILED = I18nKey("device.crypto_decrypt_failed")  # 密码解密失败
    SPLIT_CLEANUP_FAILED = I18nKey("device.split_cleanup_failed")    # 关联数据清理失败: {error}


# ===== 接口（interface）=====
class Interface:
    NOT_FOUND = I18nKey("interface.not_found")                # 接口不存在: device={device_id} if_index={if_index}
    PROTECTED_BLOCKED = I18nKey("interface.protected_blocked")  # 接口是受保护口，禁止配置
    LINK_TYPE_INVALID = I18nKey("interface.link_type_invalid")   # link type 不合法: {type}
    IP_INVALID = I18nKey("interface.ip_invalid")                # IP 格式不合法: {ip}
    MASK_INVALID = I18nKey("interface.mask_invalid")            # mask 格式不合法: {mask}
    APPLY_FAILED = I18nKey("interface.apply_failed")            # 接口配置下发失败
    IPV4_CLEAR_FAILED = I18nKey("interface.ipv4_clear_failed")  # 清空 IP 失败
    IPV4_SET_FAILED = I18nKey("interface.ipv4_set_failed")      # 配 IP 失败
    L3_OPERATION_FAILED = I18nKey("interface.l3_op_failed")     # 三层操作失败: {error}


# ===== VLAN =====
class VLAN:
    CREATE_FAILED = I18nKey("vlan.create_failed")              # VLAN 创建失败: {error}
    DELETE_FAILED = I18nKey("vlan.delete_failed")              # VLAN 删除失败: {error}
    NOT_FOUND = I18nKey("vlan.not_found")                      # VLAN 不存在: {vlan_id}
    DUPLICATE = I18nKey("vlan.duplicate")                      # VLAN 已存在: {vlan_id}


# ===== 资产（asset）/ CMDB =====
class Asset:
    NOT_FOUND = I18nKey("asset.not_found")                    # 资产记录不存在
    COLLECT_FAILED = I18nKey("asset.collect_failed")          # 资产采集失败: {error}
    UPDATE_FAILED = I18nKey("asset.update_failed")            # 资产更新失败
    # v2.6.1 fix-asset-collect-failure: 路由层错误（用于 routers/asset.py 错误响应）
    ROUTE_REFRESH_FAILED = I18nKey("asset.route.refresh_failed")     # 采集失败：{error}
    ROUTE_UPDATE_FAILED = I18nKey("asset.route.update_failed")       # 资产更新失败：{error}
    ROUTE_DEVICE_NOT_FOUND = I18nKey("asset.route.device_not_found") # 设备 {id} 不存在


# ===== 备份（backup）=====
class Backup:
    NOT_FOUND = I18nKey("backup.not_found")                    # 备份不存在: id={id}
    CREATE_FAILED = I18nKey("backup.create_failed")            # 备份创建失败: {error}
    RESTORE_FAILED = I18nKey("backup.restore_failed")          # 备份回滚失败: {error}
    RESTORE_REBOOT_FAILED = I18nKey("backup.restore_reboot_failed")  # 回滚后设备未恢复 SSH
    DELETE_FAILED = I18nKey("backup.delete_failed")            # 备份删除失败
    LOCK_FAILED = I18nKey("backup.lock_failed")                # 锁定失败: {error}
    UNLOCK_FAILED = I18nKey("backup.unlock_failed")            # 解锁失败: {error}
    LOCKED_NO_DELETE = I18nKey("backup.locked_no_delete")      # 已锁定，禁止删除
    DOWNLOAD_FAILED = I18nKey("backup.download_failed")        # 备份下载失败
    ASYNC_SUBMIT_FAILED = I18nKey("backup.async_submit_failed")  # 提交异步备份任务失败
    ASYNC_RESTORE_SUBMIT_FAILED = I18nKey("backup.async_restore_submit_failed")  # 提交异步回滚任务失败
    FILE_NOT_FOUND = I18nKey("backup.file_not_found")          # 备份文件不存在
    INVALID_ID = I18nKey("backup.invalid_id")                  # 备份 ID 不合法
    # v2.6.1 fix-asset-backup-state-sync Task 1.5: 资产离线错误
    DEVICE_OFFLINE = I18nKey("error.backup.device_offline")    # 设备 {device_id} 资产未采集/离线，请先采集后再备份


# ===== 批量（batch）=====
class Batch:
    NO_DEVICES = I18nKey("batch.no_devices")                  # 未选择设备
    EMPTY_COMMAND = I18nKey("batch.empty_command")             # 命令不能为空
    EXECUTE_FAILED = I18nKey("batch.execute_failed")          # 批量执行失败: {error}
    TASK_NOT_FOUND = I18nKey("batch.task_not_found")          # 任务不存在: {task_id}


# ===== 命令执行（execute）=====
class Execute:
    EMPTY_COMMAND = I18nKey("execute.empty_command")          # 命令不能为空
    DEVICE_NOT_FOUND = I18nKey("execute.device_not_found")    # 设备不存在: id={id}
    SEND_FAILED = I18nKey("execute.send_failed")              # 命令下发失败: {error}
    TIMEOUT = I18nKey("execute.timeout")                       # 命令执行超时
    OUTPUT_PARSE_FAILED = I18nKey("execute.output_parse_failed")  # 输出解析失败


# ===== 日志（log）=====
class Log:
    NOT_FOUND = I18nKey("log.not_found")                      # 日志记录不存在: id={id}
    QUERY_FAILED = I18nKey("log.query_failed")                # 日志查询失败


# ===== Dashboard =====
class Dashboard:
    QUERY_FAILED = I18nKey("dashboard.query_failed")          # 仪表盘数据查询失败
    DEVICE_QUERY_FAILED = I18nKey("dashboard.device_query_failed")  # 设备概览查询失败
    RECENT_OPS_FAILED = I18nKey("dashboard.recent_ops_failed")      # 最近操作查询失败


# ===== 集中导出（便于 import，支持 err.X 点访问） =====
err = SimpleNamespace(
    # common
    MISSING_FIELD=Common.MISSING_FIELD,
    INVALID_PARAM=Common.INVALID_PARAM,
    NOT_FOUND=Common.NOT_FOUND,
    INTERNAL_ERROR=Common.INTERNAL_ERROR,
    OPERATION_FAILED=Common.OPERATION_FAILED,
    INVALID_PORT=Common.INVALID_PORT,
    CRYPTO_FAILED=Common.CRYPTO_FAILED,
    # device
    DEVICE_NOT_FOUND=Device.NOT_FOUND,
    DEVICE_MISSING_HOST=Device.MISSING_HOST,
    DEVICE_MISSING_USERNAME=Device.MISSING_USERNAME,
    DEVICE_MISSING_PASSWORD=Device.MISSING_PASSWORD,
    DEVICE_EXISTS_V1_COMPAT=Device.EXISTS_V1_COMPAT,
    DEVICE_NOT_CONFIGURED=Device.NOT_CONFIGURED,
    DEVICE_CONNECT_FAILED=Device.CONNECT_FAILED,
    DEVICE_CONNECT_AUTH_FAILED=Device.CONNECT_AUTH_FAILED,
    DEVICE_CONNECT_TIMEOUT=Device.CONNECT_TIMEOUT,
    DEVICE_CONNECT_REFUSED=Device.CONNECT_REFUSED,
    DEVICE_CONNECT_UNKNOWN_HOST=Device.CONNECT_UNKNOWN_HOST,
    DEVICE_CRYPTO_DECRYPT_FAILED=Device.CRYPTO_DECRYPT_FAILED,
    DEVICE_SPLIT_CLEANUP_FAILED=Device.SPLIT_CLEANUP_FAILED,
    # interface
    INTERFACE_NOT_FOUND=Interface.NOT_FOUND,
    INTERFACE_PROTECTED_BLOCKED=Interface.PROTECTED_BLOCKED,
    INTERFACE_LINK_TYPE_INVALID=Interface.LINK_TYPE_INVALID,
    INTERFACE_IP_INVALID=Interface.IP_INVALID,
    INTERFACE_MASK_INVALID=Interface.MASK_INVALID,
    INTERFACE_APPLY_FAILED=Interface.APPLY_FAILED,
    INTERFACE_IPV4_CLEAR_FAILED=Interface.IPV4_CLEAR_FAILED,
    INTERFACE_IPV4_SET_FAILED=Interface.IPV4_SET_FAILED,
    INTERFACE_L3_OP_FAILED=Interface.L3_OPERATION_FAILED,
    # vlan
    VLAN_CREATE_FAILED=VLAN.CREATE_FAILED,
    VLAN_DELETE_FAILED=VLAN.DELETE_FAILED,
    VLAN_NOT_FOUND=VLAN.NOT_FOUND,
    VLAN_DUPLICATE=VLAN.DUPLICATE,
    # asset
    ASSET_NOT_FOUND=Asset.NOT_FOUND,
    ASSET_COLLECT_FAILED=Asset.COLLECT_FAILED,
    ASSET_UPDATE_FAILED=Asset.UPDATE_FAILED,
    ASSET_ROUTE_REFRESH_FAILED=Asset.ROUTE_REFRESH_FAILED,
    ASSET_ROUTE_UPDATE_FAILED=Asset.ROUTE_UPDATE_FAILED,
    ASSET_ROUTE_DEVICE_NOT_FOUND=Asset.ROUTE_DEVICE_NOT_FOUND,
    # backup
    BACKUP_NOT_FOUND=Backup.NOT_FOUND,
    BACKUP_CREATE_FAILED=Backup.CREATE_FAILED,
    BACKUP_RESTORE_FAILED=Backup.RESTORE_FAILED,
    BACKUP_RESTORE_REBOOT_FAILED=Backup.RESTORE_REBOOT_FAILED,
    BACKUP_DELETE_FAILED=Backup.DELETE_FAILED,
    BACKUP_LOCK_FAILED=Backup.LOCK_FAILED,
    BACKUP_UNLOCK_FAILED=Backup.UNLOCK_FAILED,
    BACKUP_LOCKED_NO_DELETE=Backup.LOCKED_NO_DELETE,
    BACKUP_DOWNLOAD_FAILED=Backup.DOWNLOAD_FAILED,
    BACKUP_ASYNC_SUBMIT_FAILED=Backup.ASYNC_SUBMIT_FAILED,
    BACKUP_ASYNC_RESTORE_SUBMIT_FAILED=Backup.ASYNC_RESTORE_SUBMIT_FAILED,
    BACKUP_FILE_NOT_FOUND=Backup.FILE_NOT_FOUND,
    BACKUP_INVALID_ID=Backup.INVALID_ID,
    BACKUP_DEVICE_OFFLINE=Backup.DEVICE_OFFLINE,  # v2.6.1 fix-asset-backup-state-sync Task 1.5
    # batch
    BATCH_NO_DEVICES=Batch.NO_DEVICES,
    BATCH_EMPTY_COMMAND=Batch.EMPTY_COMMAND,
    BATCH_EXECUTE_FAILED=Batch.EXECUTE_FAILED,
    BATCH_TASK_NOT_FOUND=Batch.TASK_NOT_FOUND,
    # execute
    EXECUTE_EMPTY_COMMAND=Execute.EMPTY_COMMAND,
    EXECUTE_DEVICE_NOT_FOUND=Execute.DEVICE_NOT_FOUND,
    EXECUTE_SEND_FAILED=Execute.SEND_FAILED,
    EXECUTE_TIMEOUT=Execute.TIMEOUT,
    EXECUTE_OUTPUT_PARSE_FAILED=Execute.OUTPUT_PARSE_FAILED,
    # log
    LOG_NOT_FOUND=Log.NOT_FOUND,
    LOG_QUERY_FAILED=Log.QUERY_FAILED,
    # dashboard
    DASHBOARD_QUERY_FAILED=Dashboard.QUERY_FAILED,
    DASHBOARD_DEVICE_QUERY_FAILED=Dashboard.DEVICE_QUERY_FAILED,
    DASHBOARD_RECENT_OPS_FAILED=Dashboard.RECENT_OPS_FAILED,
)


# 保持向后兼容：暴露 err.values() / err.keys() / 包含关系检查
def _err_values():
    return err.__dict__.values()


def _err_contains(key: str) -> bool:
    return key in err.__dict__


# ===== 默认中文降级消息（当 error_key 在前端找不到时 fallback 用）=====
FALLBACK_MESSAGES = {
    # common
    Common.MISSING_FIELD: "缺少必填字段: {field}",
    Common.INVALID_PARAM: "参数不合法: {param}",
    Common.NOT_FOUND: "资源不存在: {resource}",
    Common.INTERNAL_ERROR: "内部错误: {message}",
    Common.OPERATION_FAILED: "操作失败: {error}",
    Common.INVALID_PORT: "端口不合法: {port}",
    Common.CRYPTO_FAILED: "密码加解密失败",
    # device
    Device.NOT_FOUND: "设备不存在: id={id}",
    Device.MISSING_HOST: "缺少必填字段: host",
    Device.MISSING_USERNAME: "缺少必填字段: username",
    Device.MISSING_PASSWORD: "缺少必填字段: password",
    Device.EXISTS_V1_COMPAT: "已存在设备配置，V1.0仅支持单设备，请使用PUT更新",
    Device.NOT_CONFIGURED: "未配置设备，请先添加设备信息",
    Device.CONNECT_FAILED: "设备连接失败: {error}",
    Device.CONNECT_AUTH_FAILED: "认证失败，请检查用户名密码",
    Device.CONNECT_TIMEOUT: "连接超时",
    Device.CONNECT_REFUSED: "连接被拒绝",
    Device.CONNECT_UNKNOWN_HOST: "主机不可达",
    Device.CRYPTO_DECRYPT_FAILED: "密码解密失败，请检查ENCRYPTION_KEY配置",
    Device.SPLIT_CLEANUP_FAILED: "关联数据清理失败: {error}",
    # interface
    Interface.NOT_FOUND: "接口不存在: device={device_id} if_index={if_index}",
    Interface.PROTECTED_BLOCKED: "该接口已被标记为受保护口，禁止配置",
    Interface.LINK_TYPE_INVALID: "link type 不合法: {type}",
    Interface.IP_INVALID: "IP 格式不合法: {ip}",
    Interface.MASK_INVALID: "mask 格式不合法: {mask}",
    Interface.APPLY_FAILED: "接口配置下发失败",
    Interface.IPV4_CLEAR_FAILED: "清空 IP 失败: {error}",
    Interface.IPV4_SET_FAILED: "配 IP 失败: {error}",
    Interface.L3_OPERATION_FAILED: "三层操作失败: {error}",
    # vlan
    VLAN.CREATE_FAILED: "VLAN 创建失败: {error}",
    VLAN.DELETE_FAILED: "VLAN 删除失败: {error}",
    VLAN.NOT_FOUND: "VLAN 不存在: vlan_id={vlan_id}",
    VLAN.DUPLICATE: "VLAN 已存在: vlan_id={vlan_id}",
    # asset
    Asset.NOT_FOUND: "资产记录不存在",
    Asset.COLLECT_FAILED: "资产采集失败: {error}",
    Asset.UPDATE_FAILED: "资产更新失败: {error}",
    # v2.6.1 fix-asset-collect-failure 路由层错误
    Asset.ROUTE_REFRESH_FAILED: "采集失败：{error}",
    Asset.ROUTE_UPDATE_FAILED: "资产更新失败：{error}",
    Asset.ROUTE_DEVICE_NOT_FOUND: "设备 {id} 不存在",
    # backup
    Backup.NOT_FOUND: "备份不存在: id={id}",
    Backup.CREATE_FAILED: "备份创建失败: {error}",
    Backup.RESTORE_FAILED: "备份回滚失败: {error}",
    Backup.RESTORE_REBOOT_FAILED: "回滚完成但设备 SSH 未恢复",
    Backup.DELETE_FAILED: "备份删除失败: {error}",
    Backup.LOCK_FAILED: "锁定失败: {error}",
    Backup.UNLOCK_FAILED: "解锁失败: {error}",
    Backup.LOCKED_NO_DELETE: "已锁定，禁止删除",
    Backup.DOWNLOAD_FAILED: "备份下载失败: {error}",
    Backup.ASYNC_SUBMIT_FAILED: "提交异步备份任务失败: {error}",
    Backup.ASYNC_RESTORE_SUBMIT_FAILED: "提交异步回滚任务失败: {error}",
    Backup.FILE_NOT_FOUND: "备份文件不存在",
    Backup.INVALID_ID: "备份 ID 不合法: {id}",
    # v2.6.1 fix-asset-backup-state-sync Task 1.5: 资产离线错误兜底
    Backup.DEVICE_OFFLINE: "设备 {device_id} 资产未采集/离线，请先采集后再备份",
    # batch
    Batch.NO_DEVICES: "未选择设备",
    Batch.EMPTY_COMMAND: "命令不能为空",
    Batch.EXECUTE_FAILED: "批量执行失败: {error}",
    Batch.TASK_NOT_FOUND: "任务不存在: task_id={task_id}",
    # execute
    Execute.EMPTY_COMMAND: "命令不能为空",
    Execute.DEVICE_NOT_FOUND: "设备不存在: id={id}",
    Execute.SEND_FAILED: "命令下发失败: {error}",
    Execute.TIMEOUT: "命令执行超时",
    Execute.OUTPUT_PARSE_FAILED: "命令输出解析失败",
    # log
    Log.NOT_FOUND: "日志记录不存在: id={id}",
    Log.QUERY_FAILED: "日志查询失败: {error}",
    # dashboard
    Dashboard.QUERY_FAILED: "仪表盘数据查询失败: {error}",
    Dashboard.DEVICE_QUERY_FAILED: "设备概览查询失败: {error}",
    Dashboard.RECENT_OPS_FAILED: "最近操作查询失败: {error}",
}


# ===== 工具函数 =====

def is_valid_key(key) -> bool:
    """校验是否为已注册的 i18n key（防御拼写错误）

    FALLBACK_MESSAGES 的 key 是 I18nKey 实例，所以直接查字典 key 即可
    """
    if isinstance(key, I18nKey):
        return key in FALLBACK_MESSAGES
    if not isinstance(key, str):
        return False
    # 字符串形式：检查是否匹配任何已注册 key 的 .value
    for k in FALLBACK_MESSAGES.keys():
        if k.value == key:
            return True
    return False


def _format_fallback(key, params: Optional[dict] = None) -> str:
    """根据 FALLBACK_MESSAGES 格式化中文降级消息"""
    if isinstance(key, I18nKey):
        template = FALLBACK_MESSAGES.get(key, key.value)
    else:
        template = FALLBACK_MESSAGES.get(key, key)
    if params:
        try:
            return template.format(**params)
        except (KeyError, IndexError):
            return template
    return template


def error_response(key, params: Optional[dict] = None, fallback: Optional[str] = None):
    """
    构造一个带 i18n 信息的错误响应（APIResponse）。

    参数:
        key: I18nKey 实例或字符串（必须已注册到 FALLBACK_MESSAGES）
        params: i18n 插值参数（如 {"id": 42}）
        fallback: 可选，覆盖默认中文降级消息（一般不用）

    返回:
        APIResponse(success=False, error=..., error_key=..., error_params=...)

    使用:
        from app.i18n_keys import err, error_response
        return error_response(err.DEVICE_NOT_FOUND, params={"id": 42})
    """
    if not is_valid_key(key):
        # 防御：未注册的 key 直接用 key 字符串作为 error
        if isinstance(key, I18nKey):
            key_str = key.value
        else:
            key_str = str(key)
        return APIResponse(
            success=False,
            error=fallback or f"Unknown i18n key: {key_str}",
            error_key=key_str,
            error_params=params,
        )
    if isinstance(key, I18nKey):
        key_str = key.value
    else:
        key_str = str(key)
    error_msg = fallback or _format_fallback(key, params)
    return APIResponse(
        success=False,
        error=error_msg,
        error_key=key_str,
        error_params=params,
    )
