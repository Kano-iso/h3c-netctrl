import logging
import re
import time

import paramiko

logger = logging.getLogger("app")


class SSHExecutor:
    """SSH 命令执行器，用于命令派发和硬件信息采集"""

    def __init__(self, host: str, port: int, username: str, password: str, timeout: int = 30):
        self.host = host
        self.port = port
        self.username = username
        self.password = password
        self.timeout = timeout

    def _connect(self):
        """建立 SSH 连接"""
        # 兼容 H3C 旧设备的 SHA1 密钥交换
        if not hasattr(paramiko.Transport, '_orig_preferred_kex'):
            paramiko.Transport._orig_preferred_kex = paramiko.Transport._preferred_kex
        paramiko.Transport._preferred_kex = [
            'diffie-hellman-group14-sha1',
            'diffie-hellman-group-exchange-sha256',
            'diffie-hellman-group14-sha256',
        ]

        client = paramiko.SSHClient()
        client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        client.connect(
            hostname=self.host,
            port=self.port,
            username=self.username,
            password=self.password,
            timeout=self.timeout,
            look_for_keys=False,
            allow_agent=False,
        )
        return client

    def _read_with_pagination(self, channel, max_wait: int = 15) -> str:
        """通过交互式 shell 读取输出，自动处理 H3C 分页提示"""
        output = ""
        start = time.time()
        idle_count = 0

        while time.time() - start < max_wait:
            if channel.recv_ready():
                idle_count = 0
                chunk = channel.recv(4096).decode('utf-8', errors='replace')
                output += chunk

                # 检测分页提示，发送空格继续
                if '---- More ----' in chunk or '--More--' in chunk or '----More----' in chunk:
                    # 清除分页标记
                    time.sleep(0.2)
                    channel.send(' ')
                    continue

                # 检测命令提示符（如 <SW-Name> 或 [SW-Name]），表示输出结束
                if re.search(r'[<\[]\S+[>\]]\s*$', output.strip().split('\n')[-1] if output.strip() else ''):
                    break
            else:
                idle_count += 1
                if idle_count > 10:  # 连续 1 秒无数据，认为输出结束
                    break
                time.sleep(0.1)

        # 清理 ANSI 转义序列和分页标记
        output = re.sub(r'\x1b\[[^m]*m', '', output)
        output = re.sub(r'\x1b\[K', '', output)
        output = re.sub(r'\x1b\[24;1H', '', output)
        output = re.sub(r'----\s*More\s*----', '', output)
        output = re.sub(r'--More--', '', output)
        # 清理回车符（保留换行）
        output = output.replace('\r\n', '\n').replace('\r', '')

        return output.strip()

    def execute(self, command: str) -> dict:
        """执行命令，使用交互式 shell 处理 H3C 分页"""
        start_time = time.time()
        client = None
        try:
            client = self._connect()
            channel = client.invoke_shell(width=200, height=1000)
            time.sleep(0.5)

            # 清空欢迎信息
            if channel.recv_ready():
                channel.recv(65535)
                time.sleep(0.3)

            # 发送命令
            channel.send(command.strip() + '\n')
            time.sleep(1)

            # 读取输出（含分页处理）
            output = self._read_with_pagination(channel, max_wait=self.timeout)
            execution_time = round(time.time() - start_time, 2)

            # 去掉命令回显（第一行通常是命令本身）
            lines = output.split('\n')
            if lines and command.strip() in lines[0]:
                lines = lines[1:]
            output = '\n'.join(lines).strip()

            return {"success": True, "output": output, "execution_time": execution_time}
        except Exception as e:
            execution_time = round(time.time() - start_time, 2)
            logger.error(f"SSH 执行失败: {e}", exc_info=True)
            return {"success": False, "output": str(e), "execution_time": execution_time}
        finally:
            if client:
                client.close()

    def execute_commands(self, commands: list) -> dict:
        """执行多条配置命令（如 system-view → interface → 配置），逐条发送"""
        start_time = time.time()
        client = None
        try:
            client = self._connect()
            channel = client.invoke_shell(width=200, height=1000)
            time.sleep(0.5)

            # 清空欢迎信息
            if channel.recv_ready():
                channel.recv(65535)
                time.sleep(0.3)

            full_output = ""
            for cmd in commands:
                channel.send(cmd.strip() + '\n')
                time.sleep(0.8)
                output = self._read_with_pagination(channel, max_wait=10)
                full_output += output + '\n'

            execution_time = round(time.time() - start_time, 2)

            # 清理 ANSI 和分页
            full_output = re.sub(r'\x1b\[[^m]*m', '', full_output)
            full_output = re.sub(r'\x1b\[K', '', full_output)
            full_output = full_output.replace('\r\n', '\n').replace('\r', '')

            # 检查是否有错误提示
            error_indicators = ['Error:', 'Error :', 'Incomplete command', 'Unrecognized command',
                                'Wrong parameter', 'Too many parameters']
            has_error = any(indicator in full_output for indicator in error_indicators)

            return {"success": not has_error, "output": full_output.strip(), "execution_time": execution_time}
        except Exception as e:
            execution_time = round(time.time() - start_time, 2)
            logger.error(f"SSH 多命令执行失败: {e}", exc_info=True)
            return {"success": False, "output": str(e), "execution_time": execution_time}
        finally:
            if client:
                client.close()

    def collect_hardware_info(self) -> dict:
        """采集设备硬件信息（型号、SN、固件版本、软件包版本）"""
        info = {}

        # display device → 型号、SN
        result = self.execute("display device")
        if result["success"]:
            output = result["output"]
            # 解析型号: H3C S6850 等
            model_match = re.search(r'(H3C\s+\S+)', output)
            if model_match:
                info["model"] = model_match.group(1)
            # 解析 SN
            sn_match = re.search(r'(CNE\w+)', output)
            if sn_match:
                info["serial_number"] = sn_match.group(1)

        # display version → 固件版本、软件包版本
        result = self.execute("display version")
        if result["success"]:
            output = result["output"]
            # 解析版本号: Version 7.1.070, Alpha 7170
            version_match = re.search(r'Version\s+([\d.]+[^\n,]*)', output)
            if version_match:
                info["firmware_version"] = version_match.group(1).strip()
            # 解析软件包: flash:/s6850-cmw710-boot-t7064p15.bin
            boot_match = re.search(r'flash:/(\S+\.bin)', output)
            if boot_match:
                info["software_package"] = boot_match.group(1)
            # 解析设备型号（从 version 中补充）
            if "model" not in info:
                model_match = re.search(r'(H3C\s+\S+)', output)
                if model_match:
                    info["model"] = model_match.group(1)

        return info
