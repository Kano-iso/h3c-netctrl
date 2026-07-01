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

    def execute_commands(self, commands: list, delay_ms: int = 1000) -> list:
        """执行多条配置命令（如 system-view → interface → 配置），逐条发送，遇错继续

        v24-bugfix-ui-feedback-and-loopback / 4.2b 真机回归发现：
        H3C V7 `port link-mode bridge→route` 弹 `[Y/N]` 二次确认，必须回 Y 才生效。
        原实现只读不答 Y，命令被设备丢弃但 executor 判 success（无 Error 关键字）→ API 静默返 success。
        修复：检测 Y/N / yes/no 提示并自动应答 Y（v2.3 已知只 link-mode 这类破坏性命令会弹，安全）。

        Args:
            commands: 命令列表
            delay_ms: 每条命令之间的间隔毫秒数（默认 1000）

        Returns:
            list[dict]: 每条命令的执行结果
                [{cmd, output, success, error, execution_time}, ...]
        """
        # H3C V7 / Cisco 等设备会弹的二次确认提示（H3C V7 形式为 [Y/N]:，Cisco 形式为 [yes/no]:）
        CONFIRM_PROMPT_PATTERNS = [
            r'\[Y/N\]',         # H3C V7 "Continue? [Y/N]:"
            r'\[yes/no\]',      # Cisco "continue? [yes/no]:"
            r'continue\?\s*\(yes/no\)',  # Cisco alt
            r'Continue\?\s*\(Y/N\)',     # 大小写变体
        ]

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

            results = []
            delay_sec = max(0, delay_ms) / 1000.0

            for cmd in commands:
                cmd_strip = cmd.strip()
                if not cmd_strip:
                    continue
                cmd_start = time.time()
                try:
                    channel.send(cmd_strip + '\n')
                    time.sleep(max(delay_sec, 0.5))
                    output = self._read_with_pagination(channel, max_wait=10)

                    # v24-bugfix 4.2b: 检测二次确认 Y/N 提示，自动应答 Y
                    # 一次不只弹一次：H3C V7 偶发连续弹 2 次（route 模式 + 默认配置重置）
                    # ⚠️ 只在最新 extra 里查 [Y/N]，不要在累计 output 里查（避免老 [Y/N]: 反复触发）
                    # 修前 bug：累计 output 仍含首次 [Y/N]:，导致循环 3 次连发 Y → 设备在 [MGT] 提示符
                    #    收到 Y 当命令报 "% Unrecognized command found at '^' position." → 假失败
                    confirm_loops = 0
                    while confirm_loops < 3:
                        if not any(re.search(p, output) for p in CONFIRM_PROMPT_PATTERNS):
                            break
                        logger.info(f"SSH 检测到二次确认提示，自动应答 Y（cmd={cmd_strip}）")
                        channel.send('Y\n')
                        time.sleep(1.0)
                        extra = self._read_with_pagination(channel, max_wait=10)
                        output = output + '\n' + extra
                        # 只用最新 extra 判定是否还有 Y/N
                        if not any(re.search(p, extra) for p in CONFIRM_PROMPT_PATTERNS):
                            break
                        confirm_loops += 1

                    # 清理 ANSI 和分页
                    output_clean = re.sub(r'\x1b\[[^m]*m', '', output)
                    output_clean = re.sub(r'\x1b\[K', '', output_clean)
                    output_clean = re.sub(r'\x1b\[24;1H', '', output_clean)
                    output_clean = re.sub(r'----\s*More\s*----', '', output_clean)
                    output_clean = re.sub(r'--More--', '', output_clean)
                    output_clean = output_clean.replace('\r\n', '\n').replace('\r', '').strip()

                    # 错误指示符检测
                    error_indicators = ['Error:', 'Error :', 'Incomplete command', 'Unrecognized command',
                                        'Wrong parameter', 'Too many parameters', '% Unknown command',
                                        'Invalid input detected', 'Command rejected']
                    has_error = any(ind in output_clean for ind in error_indicators)

                    results.append({
                        "cmd": cmd_strip,
                        "output": output_clean,
                        "success": not has_error,
                        "error": (output_clean.split('\n')[0] if has_error else None),
                        "execution_time": round(time.time() - cmd_start, 2),
                    })
                except Exception as e:
                    logger.error(f"SSH 单命令执行失败: cmd={cmd_strip}, err={e}", exc_info=True)
                    results.append({
                        "cmd": cmd_strip,
                        "output": "",
                        "success": False,
                        "error": str(e),
                        "execution_time": round(time.time() - cmd_start, 2),
                    })

            return results
        except Exception as e:
            logger.error(f"SSH 多命令执行失败: {e}", exc_info=True)
            # SSH 连接失败时所有命令标为失败
            return [
                {
                    "cmd": c.strip(),
                    "output": "",
                    "success": False,
                    "error": str(e),
                    "execution_time": 0,
                }
                for c in commands if c and c.strip()
            ]
        finally:
            if client:
                client.close()

    def collect_hardware_info(self) -> dict:
        """采集设备硬件信息（型号、SN、固件版本、软件包版本）

        当 SSH 连接失败（第一条 execute 返回 success=false）时主动抛 ConnectionError，
        让调用方（如 asset.py::refresh_asset）能进入 except 分支正确设置 status='offline'。
        之前是静默返回空 dict，导致 status 被错误设为 'online'。
        """
        info = {}

        # display device → 型号、SN
        result = self.execute("display device")
        if not result["success"]:
            # SSH 连接失败 / 认证失败 / 命令无输出 → 主动抛异常
            raise ConnectionError(
                f"SSH 连接失败或命令无输出: {self.host}（第一条命令 'display device' 失败，"
                f"output={result.get('output', '')[:100]!r}）"
            )
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
