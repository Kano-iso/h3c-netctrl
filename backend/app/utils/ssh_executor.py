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

    def execute(self, command: str) -> dict:
        """执行单条命令，返回输出和执行时间"""
        start_time = time.time()
        client = None
        try:
            client = self._connect()
            stdin, stdout, stderr = client.exec_command(command, timeout=self.timeout)
            output = stdout.read().decode('utf-8', errors='replace')
            error_output = stderr.read().decode('utf-8', errors='replace')
            execution_time = round(time.time() - start_time, 2)

            if error_output and not output:
                return {"success": False, "output": error_output, "execution_time": execution_time}

            return {"success": True, "output": output, "execution_time": execution_time}
        except Exception as e:
            execution_time = round(time.time() - start_time, 2)
            return {"success": False, "output": str(e), "execution_time": execution_time}
        finally:
            if client:
                client.close()

    def collect_hardware_info(self) -> dict:
        """采集设备硬件信息"""
        info = {}

        # display device → 型号、SN
        result = self.execute("display device")
        if result["success"]:
            output = result["output"]
            # 解析型号
            model_match = re.search(r'(\S+)\s+\d+\s+(?:Normal|Master)', output)
            if model_match:
                info["model"] = model_match.group(1)
            # 解析 SN
            sn_match = re.search(r'(CNE|CN[A-Z]*)\w+', output)
            if sn_match:
                info["serial_number"] = sn_match.group(0)

        # display version → 固件版本
        result = self.execute("display version")
        if result["success"]:
            output = result["output"]
            version_match = re.search(r'Release\s+(\S+)', output)
            if version_match:
                info["firmware_version"] = f"Release {version_match.group(1)}"

        # display cpu-usage
        result = self.execute("display cpu-usage")
        if result["success"]:
            output = result["output"]
            cpu_match = re.search(r'(\d+)%', output)
            if cpu_match:
                info["cpu_usage"] = f"{cpu_match.group(1)}%"

        # display memory
        result = self.execute("display memory")
        if result["success"]:
            output = result["output"]
            mem_match = re.search(r'(\d+)(?:\.\d+)?%', output)
            if mem_match:
                info["memory_usage"] = f"{mem_match.group(1)}%"

        return info
