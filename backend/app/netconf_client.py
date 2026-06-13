import logging
import re
import socket

import paramiko
from ncclient import manager
from ncclient.transport.errors import AuthenticationError, SSHError
from ncclient.operations.rpc import RPCError

logger = logging.getLogger("app")

# 放宽 SSH 密钥算法支持，兼容 H3C 旧设备
paramiko.Transport._preferred_kex = (
    "diffie-hellman-group14-sha1",
    "diffie-hellman-group14-sha256",
    "diffie-hellman-group16-sha512",
    "diffie-hellman-group-exchange-sha256",
    "ecdh-sha2-nistp256",
    "ecdh-sha2-nistp384",
    "ecdh-sha2-nistp521",
)


class NetconfClient:
    """NETCONF 连接管理器，使用 context manager 模式管理连接生命周期"""

    def __init__(self, host: str, port: int, username: str, password: str, timeout: int = 30):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self._manager = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        """建立 NETCONF SSH 连接"""
        logger.debug(f"正在连接设备 {self.host}:{self.port} (用户: {self.username})")
        # 密码脱敏日志
        debug_password = re.sub(r'.', '*', self.password) if self.password else '***'
        logger.debug(f"连接参数: host={self.host}, port={self.port}, username={self.username}, password={debug_password}")

        self._manager = manager.connect(
            host=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=self.timeout,
            device_params={"name": "h3c"},
            hostkey_verify=False,
            look_for_keys=False,
            allow_agent=False,
        )
        logger.info(f"NETCONF连接成功: {self.host}:{self.port}")

    def disconnect(self):
        """断开 NETCONF 连接"""
        if self._manager:
            try:
                self._manager.close_session()
            except Exception:
                pass
            self._manager = None
            logger.debug(f"NETCONF连接已关闭: {self.host}:{self.port}")

    def get_config(self, filter_xml: str) -> str:
        """执行 get-config 操作"""
        if not self._manager:
            raise RuntimeError("NETCONF未连接")

        logger.debug(f"get-config 请求 XML:\n{filter_xml}")
        result = self._manager.get_config(source="running", filter=("subtree", filter_xml))
        logger.debug(f"get-config 响应 XML:\n{result.xml}")
        return result.xml

    def edit_config(self, config_xml: str) -> str:
        """执行 edit-config 操作"""
        if not self._manager:
            raise RuntimeError("NETCONF未连接")

        logger.debug(f"edit-config 请求 XML:\n{config_xml}")
        result = self._manager.edit_config(target="running", config=config_xml)
        logger.debug(f"edit-config 响应 XML:\n{result.xml}")
        return result.xml


def classify_connection_error(error: Exception) -> str:
    """将连接异常分类为可读的中文错误信息"""
    error_str = str(error)

    # 设备不可达
    if isinstance(error, socket.gaierror) or "Name or service not known" in error_str:
        return "设备不可达，请检查IP地址和网络连通性"

    # 连接超时
    if isinstance(error, socket.timeout) or "timed out" in error_str.lower():
        return "设备不可达，请检查IP地址和网络连通性"

    # 连接被拒绝（端口未开放）
    if "Connection refused" in error_str or "refused" in error_str.lower():
        return "连接被拒绝，请检查设备NETCONF服务是否开启（端口830）"

    # 认证失败
    if isinstance(error, AuthenticationError) or "Authentication" in error_str:
        return "认证失败，请检查用户名或密码"

    # SSH 密钥交换失败
    if isinstance(error, SSHError):
        if "not open" in error_str.lower():
            return "连接被拒绝，请检查设备NETCONF服务是否开启（端口830）"
        return f"SSH连接失败: {error_str}"

    # paramiko 特定错误
    if isinstance(error, paramiko.ssh_exception.AuthenticationException):
        return "认证失败，请检查用户名或密码"

    # NETCONF 会话创建失败
    if "hello" in error_str.lower() or "capability" in error_str.lower():
        return "NETCONF会话创建失败，请确认设备已启用NETCONF over SSH"

    # 通用网络错误
    if "No route to host" in error_str or "Network is unreachable" in error_str:
        return "设备不可达，请检查IP地址和网络连通性"

    return f"连接失败: {error_str}"
