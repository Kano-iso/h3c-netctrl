#!/usr/bin/env python3
# _paramiko_batch_exec.py — paramiko 批命令核心（v242-paramiko-tool Task 1）
#
# 功能：连接 SSH 设备，串行跑 N 条命令，输出文本 / JSON。
# 边界：单设备（不支持多设备）
#
# 环境变量（由 bash 入口注入）：
#   _PMK_HOST          设备 IP（必填）
#   _PMK_PORT          SSH 端口（默认 22）
#   _PMK_USER          用户名（必填）
#   _PMK_PASS          密码（必填）
#   _PMK_COMMANDS_JSON 命令 JSON 数组（必填，Task 1 传 1 条）
#   _PMK_TIMEOUT       单命令 timeout 秒（默认 30）
#   _PMK_OUTPUT_FORMAT text / json（默认 text）
#   _PMK_RETRIES       失败重试次数（默认 0，Task 5 实现）
#   _PMK_CONTINUE_ON_ERROR true/false（默认 true）
import json
import os
import sys
import time

import paramiko


def run_one_command(host, port, user, password, command, timeout):
    """单条命令，返回 (returncode, stdout, stderr, elapsed_ms, error)
    H3C V7 设备 SSH 走交互式 shell (invoke_shell)。
    兼容 H3C V7 旧设备的关键配置：
    - 放宽 kex 包含 diffie-hellman-group14-sha1
    - host key 算法加 ssh-rsa
    - look_for_keys=False, allow_agent=False（避免本地 ssh key 干扰）
    """
    from paramiko import Transport
    # 兼容 H3C V7 旧设备 SHA1 密钥交换
    Transport._preferred_kex = [
        'diffie-hellman-group14-sha1',
        'diffie-hellman-group-exchange-sha256',
        'diffie-hellman-group14-sha256',
        'ecdh-sha2-nistp256',
        'ecdh-sha2-nistp384',
        'ecdh-sha2-nistp521',
    ]
    # H3C V7 server host key 算法只支持 ssh-rsa（OpenSSH 8+ 默认禁用）
    Transport._preferred_server_host_key_algorithms = (
        'ssh-rsa', 'rsa-sha2-512', 'rsa-sha2-256',
        'ecdsa-sha2-nistp256', 'ecdsa-sha2-nistp384', 'ecdsa-sha2-nistp521',
        'ssh-ed25519',
    )
    start = time.time()
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    try:
        client.connect(
            host, port=port, username=user, password=password,
            timeout=10, banner_timeout=10, auth_timeout=10,
            look_for_keys=False, allow_agent=False,
        )
        # H3C V7 走 invoke_shell（交互式 CLI 模式）
        shell = client.invoke_shell(term='vt100', width=512, height=512)
        shell.settimeout(timeout)
        time.sleep(1.0)
        initial = b""
        if shell.recv_ready():
            initial = shell.recv(65535)
        shell.send(command + "\r\n")
        # 读回显（含分页自动翻页 + prompt 检测）
        output = b""
        deadline = time.time() + timeout
        idle_count = 0
        import re
        while time.time() < deadline:
            if shell.recv_ready():
                idle_count = 0
                chunk = shell.recv(4096)
                output += chunk
                chunk_str = chunk.decode('utf-8', errors='replace')
                # H3C 分页提示：自动按空格翻页
                if '---- More ----' in chunk_str or '--More--' in chunk_str or '----More----' in chunk_str:
                    time.sleep(0.2)
                    shell.send(' ')
                    continue
                # prompt 结束符（<SW-Name> 或 [SW-Name]）
                full = (initial + output).decode('utf-8', errors='replace').strip()
                if full and re.search(r'[<\[]\S+[>\]]\s*$', full.split('\n')[-1]):
                    break
            else:
                idle_count += 1
                if idle_count > 10:  # 1 秒无数据认为结束
                    break
                time.sleep(0.1)
        try:
            shell.close()
        except Exception:
            pass
        # 清理 ANSI + 分页 + 回车
        full = (initial + output).decode('utf-8', errors='replace')
        full = re.sub(r'\x1b\[[^m]*m', '', full)
        full = re.sub(r'\x1b\[K', '', full)
        full = re.sub(r'----\s*More\s*----', '', full)
        full = re.sub(r'--More--', '', full)
        full = full.replace('\r\n', '\n').replace('\r', '')
        returncode = 0
        elapsed_ms = int((time.time() - start) * 1000)
        return returncode, full, "", elapsed_ms, None
    except paramiko.AuthenticationException:
        elapsed_ms = int((time.time() - start) * 1000)
        return 1, "", "认证失败：用户名或密码错误", elapsed_ms, "auth_error"
    except paramiko.SSHException as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return 1, "", f"SSH 错误: {e}", elapsed_ms, "ssh_error"
    except (OSError, ConnectionError, TimeoutError) as e:
        elapsed_ms = int((time.time() - start) * 1000)
        return 1, "", f"连接失败: {e}", elapsed_ms, "conn_error"
    finally:
        try:
            client.close()
        except Exception:
            pass


def main():
    # 读环境变量
    host = os.environ.get('_PMK_HOST', '').strip()
    port = int(os.environ.get('_PMK_PORT', '22'))
    user = os.environ.get('_PMK_USER', '').strip()
    password = os.environ.get('_PMK_PASS', '')
    commands_json = os.environ.get('_PMK_COMMANDS_JSON', '[]')
    timeout = int(os.environ.get('_PMK_TIMEOUT', '30'))
    output_format = os.environ.get('_PMK_OUTPUT_FORMAT', 'text')
    retries = int(os.environ.get('_PMK_RETRIES', '0'))
    continue_on_error = os.environ.get('_PMK_CONTINUE_ON_ERROR', 'true').lower() == 'true'

    if not host or not user or not password:
        print('❌ 缺少 _PMK_HOST / _PMK_USER / _PMK_PASS 环境变量', file=sys.stderr)
        sys.exit(2)

    try:
        commands = json.loads(commands_json)
    except json.JSONDecodeError as e:
        print(f'❌ _PMK_COMMANDS_JSON 解析失败: {e}', file=sys.stderr)
        sys.exit(2)

    if not commands:
        print('❌ _PMK_COMMANDS_JSON 为空（至少 1 条命令）', file=sys.stderr)
        sys.exit(2)

    # 跑批命令
    results = []
    success_count = 0
    for idx, command in enumerate(commands, start=1):
        attempt = 0
        last_result = None
        while attempt <= retries:
            rc, out, err, elapsed_ms, error = run_one_command(
                host, port, user, password, command, timeout,
            )
            last_result = {
                'command': command,
                'returncode': rc,
                'stdout': out,
                'stderr': err,
                'elapsed_ms': elapsed_ms,
                'success': rc == 0,
            }
            if error:
                last_result['error'] = error
            if rc == 0:
                break  # 成功，跳出重试
            attempt += 1
            if attempt <= retries:
                time.sleep(5)  # retry backoff

        results.append(last_result)
        if last_result['success']:
            success_count += 1
        elif not continue_on_error:
            # 遇错停止
            break

    # 输出
    summary = {
        'host': host,
        'total': len(commands),
        'success': success_count,
        'failed': len(commands) - success_count,
        'results': results,
    }

    if output_format == 'json':
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        for idx, r in enumerate(results, start=1):
            status = '✓' if r['success'] else '✗'
            print(f"[{idx}/{len(results)}] {r['command']} ({r['elapsed_ms']}ms, rc={r['returncode']}, {status})")
            if r['stdout']:
                print(r['stdout'], end='' if r['stdout'].endswith('\n') else '\n')
            if r['stderr']:
                print(f"STDERR: {r['stderr']}", file=sys.stderr)
        if summary['failed'] == 0:
            print(f"✅ {summary['success']}/{summary['total']} 成功")
        else:
            print(f"❌ {summary['success']}/{summary['total']} 成功, {summary['failed']} 失败")

    sys.exit(0 if summary['failed'] == 0 else 1)


if __name__ == '__main__':
    main()
