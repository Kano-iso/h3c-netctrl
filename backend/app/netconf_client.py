import logging
import re
import socket
import subprocess
import time
from typing import Optional

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


class DeviceUnreachableError(Exception):
    """设备不可达（ping 不通）"""
    pass


class NetconfPortClosedError(Exception):
    """NETCONF 端口未开放"""
    pass


class NetconfConnectionError(Exception):
    """NETCONF 连接失败（认证/协议/其他）"""
    def __init__(self, message: str, category: str = "protocol"):
        super().__init__(message)
        self.category = category  # network/port/auth/protocol


def diagnose_device(host: str, port: int, timeout: int = 3) -> None:
    """渐进式设备诊断：ping → nc 端口 → 抛具体异常

    成功无返回；失败抛 DeviceUnreachableError 或 NetconfPortClosedError
    """
    # 1. ping 检测
    logger.debug(f"[诊断] ping {host} ...")
    try:
        result = subprocess.run(
            ["ping", "-c", "1", "-W", "2", host],
            capture_output=True, timeout=timeout, text=True
        )
        if result.returncode != 0:
            raise DeviceUnreachableError(f"设备 {host} ping 不通")
        logger.debug(f"[诊断] ping {host} 成功")
    except subprocess.TimeoutExpired:
        raise DeviceUnreachableError(f"设备 {host} ping 超时")
    except FileNotFoundError:
        # ping 命令不存在（Windows 等），跳过
        logger.debug(f"[诊断] ping 命令不可用，跳过")

    # 2. TCP 端口检测
    logger.debug(f"[诊断] nc {host}:{port} ...")
    try:
        with socket.create_connection((host, port), timeout=timeout):
            logger.debug(f"[诊断] 端口 {host}:{port} 开放")
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        raise NetconfPortClosedError(f"NETCONF 端口 {port} 未开放（请在设备上执行 netconf service enable）") from e


def connect_with_retry(host: str, port: int, username: str, password: str,
                        timeout: int = 30, max_retries: int = 2) -> manager:
    """带重试的 NETCONF 连接

    流程：先诊断设备，诊断通过后连接 NETCONF。
    失败时指数退避重试最多 max_retries 次（间隔 1s, 2s）。
    """
    # 先做渐进式诊断
    try:
        diagnose_device(host, port, timeout=3)
    except DeviceUnreachableError as e:
        raise NetconfConnectionError(str(e), category="network") from e
    except NetconfPortClosedError as e:
        raise NetconfConnectionError(str(e), category="port") from e

    # 诊断通过，连接 NETCONF（带重试）
    last_error = None
    for attempt in range(max_retries + 1):
        try:
            logger.debug(f"[NETCONF] 连接尝试 {attempt + 1}/{max_retries + 1}: {host}:{port}")
            mgr = manager.connect(
                host=host, port=port,
                username=username, password=password,
                timeout=timeout,
                device_params={"name": "h3c"},
                hostkey_verify=False,
                look_for_keys=False,
                allow_agent=False,
            )
            if attempt > 0:
                logger.info(f"[NETCONF] 第 {attempt + 1} 次重试连接成功: {host}:{port}")
            else:
                logger.info(f"[NETCONF] 连接成功: {host}:{port}")
            return mgr
        except AuthenticationError as e:
            # 认证错误不重试
            raise NetconfConnectionError(f"认证失败: 请检查用户名密码", category="auth") from e
        except Exception as e:
            last_error = e
            if attempt < max_retries:
                wait = 2 ** attempt  # 1, 2
                logger.warning(f"[NETCONF] 连接失败，{wait}s 后重试: {e}")
                time.sleep(wait)
            else:
                logger.error(f"[NETCONF] 重试 {max_retries} 次后仍失败: {e}")

    # 重试耗尽
    raise NetconfConnectionError(f"连接失败（重试 {max_retries} 次）: {last_error}", category="protocol") from last_error


class NetconfClient:
    """NETCONF 连接管理器，使用 context manager 模式管理连接生命周期

    特性：
    - 连接前先做 ping/端口诊断，失败时给出具体错误
    - 连接失败时自动重试（指数退避）
    - 错误按四级分类：network/port/auth/protocol
    """

    def __init__(self, host: str, port: int, username: str, password: str,
                 timeout: int = 30, max_retries: int = 2):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout
        self.max_retries = max_retries
        self._manager = None

    def __enter__(self):
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.disconnect()

    def connect(self):
        """建立 NETCONF SSH 连接（带诊断和重试）"""
        debug_password = re.sub(r'.', '*', self.password) if self.password else '***'
        logger.debug(f"连接参数: host={self.host}, port={self.port}, username={self.username}, password={debug_password}")
        self._manager = connect_with_retry(
            host=self.host, port=self.port,
            username=self.username, password=self.password,
            timeout=self.timeout, max_retries=self.max_retries,
        )

    def get_interface_name_by_index(self, if_index: int) -> Optional[str]:
        """根据 if_index 查询接口的 name（如 GigabitEthernet1/0/3）

        v2.3 新增：link-mode 走 SSH CLI 需要真实接口名（if_index 数字不能解析出 name）
        """
        if not self._manager:
            raise RuntimeError("NETCONF未连接")
        xml = f'''<filter>
  <top xmlns="http://www.h3c.com/netconf/data:1.0">
    <Ifmgr>
      <Interfaces>
        <Interface>
          <IfIndex>{if_index}</IfIndex>
        </Interface>
      </Interfaces>
    </Ifmgr>
  </top>
</filter>'''
        try:
            r = self._manager.get(xml)
            # 解析 <Name> 字段
            import xml.etree.ElementTree as ET
            root = ET.fromstring(str(r))
            NS = '{http://www.h3c.com/netconf/data:1.0}'
            for iface in root.iter(NS + 'Interface'):
                if iface.findtext(NS + 'IfIndex') == str(if_index):
                    return iface.findtext(NS + 'Name')
            return None
        except Exception as e:
            logger.error(f"get_interface_name_by_index 失败 if_index={if_index}: {e}")
            return None

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
    """将连接异常分类为可读的中文错误信息

    错误分类（每类对应不同的修复建议）：
    - network: 设备不可达，请检查 IP 和网络
    - port: NETCONF 端口未开放
    - auth: 认证失败
    - protocol: 协议/其他错误
    """
    # 自定义异常优先
    if isinstance(error, NetconfConnectionError):
        return error.args[0]
    if isinstance(error, DeviceUnreachableError):
        return f"设备不可达: {error}"
    if isinstance(error, NetconfPortClosedError):
        return str(error)

    error_str = str(error)

    # 设备不可达（DNS 解析失败）
    if isinstance(error, socket.gaierror) or "Name or service not known" in error_str:
        return "设备不可达，请检查IP地址和网络连通性"

    # 连接超时
    if isinstance(error, socket.timeout) or "timed out" in error_str.lower():
        return "设备不可达，请检查IP地址和网络连通性"

    # 连接被拒绝（端口未开放）
    if "Connection refused" in error_str or "refused" in error_str.lower():
        return "NETCONF 端口 830 未开放，请检查设备 NETCONF 服务"

    # 认证失败
    if isinstance(error, AuthenticationError) or "Authentication" in error_str:
        return "认证失败，请检查用户名或密码"

    # paramiko 认证
    if isinstance(error, paramiko.ssh_exception.AuthenticationException):
        return "认证失败，请检查用户名或密码"

    # SSH 错误
    if isinstance(error, SSHError):
        if "not open" in error_str.lower():
            return "NETCONF 端口 830 未开放，请检查设备 NETCONF 服务"
        return f"SSH连接失败: {error_str}"

    # NETCONF 会话创建失败
    if "hello" in error_str.lower() or "capability" in error_str.lower():
        return "NETCONF会话创建失败，请确认设备已启用NETCONF over SSH"

    # 网络不通
    if "No route to host" in error_str or "Network is unreachable" in error_str:
        return "设备不可达，请检查IP地址和网络连通性"

    return f"连接失败: {error_str}"


def classify_netconf_error(error: Exception) -> str:
    """将 NETCONF 异常分类为用户可读的中文错误信息

    包含 RPC 错误（业务错误）的处理
    """
    # 已知连接错误标识（含其中之一即为连接类错误）
    connection_indicators = [
        "重试",       # 重试 N 次后仍失败
        "不可达",     # 设备不可达
        "认证失败",   # 认证失败
        "端口 830",   # 端口未开放
        "NETCONF会话创建失败",
        "SSH连接失败",
    ]
    # 先用连接错误分类器
    conn_msg = classify_connection_error(error)
    is_connection_error = any(ind in conn_msg for ind in connection_indicators)
    if is_connection_error:
        return conn_msg

    # RPC 业务错误（连接错误标识没有命中，往下走 RPCError 分支）
    if isinstance(error, RPCError):
        msg = str(error.message) if hasattr(error, "message") else str(error)
        # 常见错误模式
        if "does not exist" in msg.lower() or "not exist" in msg.lower():
            return f"资源不存在: {msg}"
        if "already exists" in msg.lower():
            return f"资源已存在: {msg}"
        if "not support" in msg.lower():
            return f"设备不支持此操作: {msg}"
        if "denied" in msg.lower():
            return f"操作被拒绝: {msg}"
        if "wrong" in msg.lower() or "invalid" in msg.lower():
            return f"参数错误: {msg}"
        if "vlan" in msg.lower():
            return f"VLAN 错误: {msg}"
        return f"设备返回错误: {msg}"

    # 超时
    error_str = str(error)
    if "timeout" in error_str.lower():
        return "设备响应超时，请检查网络连接或设备状态"

    return conn_msg
