"""NETCONF 错误分类函数单测"""
import socket
from unittest.mock import MagicMock
from ncclient.transport.errors import AuthenticationError, SSHError
from ncclient.operations.rpc import RPCError
from paramiko.ssh_exception import AuthenticationException

from app.netconf_client import (
    classify_connection_error,
    classify_netconf_error,
    DeviceUnreachableError,
    NetconfPortClosedError,
    NetconfConnectionError,
)


def test_classify_device_unreachable():
    """network 错误：设备不可达"""
    err = DeviceUnreachableError("设备 192.168.1.1 ping 不通")
    msg = classify_connection_error(err)
    assert "不可达" in msg or "ping" in msg


def test_classify_port_closed():
    """port 错误：端口未开放"""
    err = NetconfPortClosedError("NETCONF 端口 830 未开放")
    msg = classify_connection_error(err)
    assert "端口" in msg
    assert "830" in msg


def test_classify_auth_error_ncclient():
    """auth 错误：ncclient 认证异常"""
    err = AuthenticationError("auth fail")
    msg = classify_connection_error(err)
    assert "认证" in msg


def test_classify_auth_error_paramiko():
    """auth 错误：paramiko 认证异常"""
    err = AuthenticationException("Authentication failed")
    msg = classify_connection_error(err)
    assert "认证" in msg


def test_classify_connection_refused():
    """port 错误：连接被拒绝"""
    err = ConnectionRefusedError("Connection refused")
    msg = classify_connection_error(err)
    assert "端口" in msg or "NETCONF" in msg


def test_classify_timeout():
    """network 错误：连接超时"""
    err = socket.timeout("timed out")
    msg = classify_connection_error(err)
    assert "不可达" in msg or "网络" in msg


def test_classify_dns_failure():
    """network 错误：DNS 解析失败"""
    err = socket.gaierror(-2, "Name or service not known")
    msg = classify_connection_error(err)
    assert "不可达" in msg or "IP" in msg


def test_classify_no_route():
    """network 错误：无路由"""
    err = OSError("No route to host")
    msg = classify_connection_error(err)
    assert "不可达" in msg


def test_classify_ssh_port_not_open():
    """port 错误：SSH 端口未开放"""
    err = SSHError("channel is not open")
    msg = classify_connection_error(err)
    assert "端口" in msg or "NETCONF" in msg


def test_classify_netconf_hello():
    """protocol 错误：NETCONF hello 失败"""
    err = Exception("capability exchange failed")
    msg = classify_connection_error(err)
    assert "NETCONF" in msg


def test_classify_netconf_error_rpc_not_exist():
    """NETCONF RPC 业务错误：资源不存在"""
    err = MagicMock(spec=RPCError)
    err.message = "VLAN does not exist"
    msg = classify_netconf_error(err)
    assert "不存在" in msg


def test_classify_netconf_error_rpc_already_exists():
    """NETCONF RPC 业务错误：资源已存在"""
    err = MagicMock(spec=RPCError)
    err.message = "VLAN already exists"
    msg = classify_netconf_error(err)
    assert "已存在" in msg


def test_classify_netconf_error_rpc_wrong():
    """NETCONF RPC 业务错误：参数错误"""
    err = MagicMock(spec=RPCError)
    err.message = "Wrong parameter value"
    msg = classify_netconf_error(err)
    assert "参数" in msg or "错误" in msg


def test_classify_netconf_error_rpc_vlan():
    """NETCONF RPC 业务错误：VLAN 相关"""
    err = MagicMock(spec=RPCError)
    err.message = "VLAN 100 not allowed on trunk port"
    msg = classify_netconf_error(err)
    assert "VLAN" in msg


def test_classify_netconf_error_with_category():
    """自定义 NetconfConnectionError 带 category"""
    err = NetconfConnectionError("认证失败", category="auth")
    msg = classify_connection_error(err)
    assert "认证" in msg


def test_classify_unexpected_error():
    """未知错误：返回原始信息"""
    err = Exception("Some weird thing happened")
    msg = classify_connection_error(err)
    assert "连接失败" in msg
