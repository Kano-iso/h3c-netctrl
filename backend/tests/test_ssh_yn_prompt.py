"""v24-bugfix-ui-feedback-and-loopback / 4.2b 真机回归单测

覆盖：H3C V7 SSH CLI `port link-mode bridge→route` 弹 [Y/N] 二次确认时，
SSHExecutor.execute_commands 必须自动应答 Y，否则命令被设备丢弃但 executor
返回 success=True（无 Error 关键字），导致 API 静默假成功。

bug 场景（修前）：
- 输入: commands=["system-view", "interface GE1/0/5", "port link-mode route"]
- 设备响应: "...Continue? [Y/N]:"
- 原实现: 读完 prompt 后判 success=True（无 Error 关键字），未应答 Y
- 结果: 命令被设备丢弃，但 API 返 success，设备配置没改

修复后：
- executor 检测 [Y/N] 提示，自动发送 Y
- 设备正常执行
"""
from unittest.mock import MagicMock, patch

from app.utils.ssh_executor import SSHExecutor


def _make_channel_with_outputs(outputs):
    """构造 mock channel，按 recv_ready 顺序吐出 outputs 列表

    outputs: List[str]，每次 recv 返回一个 chunk
    注：execute_commands 启动时调 1 次 channel.recv(65535) 清欢迎，所以
    第 1 个 output 是欢迎信息，第 2 个开始才是命令响应
    """
    ch = MagicMock()
    recv_iter = iter(outputs)
    recv_count = [0]

    def recv_ready_side():
        return recv_count[0] < len(outputs)

    def recv_side(n):
        if recv_count[0] < len(outputs):
            chunk = outputs[recv_count[0]]
            recv_count[0] += 1
            return chunk.encode('utf-8') if isinstance(chunk, str) else chunk
        return b''

    def recv_large(_):
        # 清欢迎的那次（大 buffer），跟普通 recv 共用队列
        return recv_side(_)

    ch.recv_ready.side_effect = recv_ready_side
    # recv(65535) 清欢迎 + recv(4096) 读输出 都用同一个队列
    ch.recv.side_effect = recv_large
    sent = []

    def send_side(data):
        sent.append(data)

    ch.send.side_effect = send_side
    return ch, sent


def test_execute_commands_handles_yn_prompt_h3c_v7():
    """H3C V7 link-mode bridge→route 弹 [Y/N] 提示，executor 必须自动应答 Y

    场景：commands=["port link-mode route"]，设备返回 "...Continue? [Y/N]:" + 答 Y 后提示符
    修复后：executor 发送 "Y\\n"，最终 success=True，且 output 含设备最终提示符（无 Error）
    """
    outputs = [
        # 0) 欢迎信息（被 execute_commands 启动时 recv(65535) 清空）
        "*********************************************************\n* Copyright (c) ...\n* without owner's prior written consent...\n*********************************************************\n<MGT>",
        # 1) 命令回显 + Y/N 提示（H3C V7）
        "port link-mode route\r\nThe configuration of the interface will be restored to the default. Continue? [Y/N]:",
        # 2) 答 Y 后设备返回的提示符（无更多输出）
        " [MGT-GigabitEthernet1/0/5]",
    ]
    ch, sent = _make_channel_with_outputs(outputs)

    fake_client = MagicMock()
    fake_client.invoke_shell.return_value = ch

    with patch.object(SSHExecutor, '_connect', return_value=fake_client):
        ssh = SSHExecutor(host='1.2.3.4', port=22, username='u', password='p', timeout=10)
        results = ssh.execute_commands(["port link-mode route"], delay_ms=200)

    # 验证：检测到 [Y/N] 后必须发 'Y\n'
    assert any('Y' in s for s in sent), f"必须应答 Y，实际 send: {sent}"
    # 验证：success=True（不是 Error）
    assert len(results) == 1
    assert results[0]["success"] is True, f"link-mode 应 success，实际: {results[0]}"
    assert "Error" not in results[0]["output"]


def test_execute_commands_handles_cisco_yes_no_prompt():
    """Cisco 'continue? [yes/no]:' 提示也能被识别"""
    outputs = [
        # 0) 欢迎信息
        "*********************************************************\n* Cisco IOS ...\n*********************************************************\nRouter>",
        # 1) Cisco 'continue? [yes/no]:' 提示
        "Router(config-if)#ip address 1.1.1.1 255.255.255.0\n% Please confirm 'yes/no': [yes/no]:",
        # 2) 答 Y 后
        " [Router(config-if)#]",
    ]
    ch, sent = _make_channel_with_outputs(outputs)

    fake_client = MagicMock()
    fake_client.invoke_shell.return_value = ch

    with patch.object(SSHExecutor, '_connect', return_value=fake_client):
        ssh = SSHExecutor(host='1.2.3.4', port=22, username='u', password='p', timeout=10)
        results = ssh.execute_commands(["ip address 1.1.1.1 255.255.255.0"], delay_ms=200)

    assert any('Y' in s for s in sent), f"Cisco 提示也应被识别应答 Y，实际: {sent}"
    assert results[0]["success"] is True


def test_execute_commands_no_yn_no_extra_send():
    """无 Y/N 提示的正常命令不应触发 Y 发送（防误答）"""
    outputs = [
        # 0) 欢迎信息
        "*********************************************************\n<MGT>",
        # 1) 正常 system-view 命令
        "system-view\r\nSystem View: return to User View with Ctrl+Z.\r\n[MGT]",
    ]
    ch, sent = _make_channel_with_outputs(outputs)

    fake_client = MagicMock()
    fake_client.invoke_shell.return_value = ch

    with patch.object(SSHExecutor, '_connect', return_value=fake_client):
        ssh = SSHExecutor(host='1.2.3.4', port=22, username='u', password='p', timeout=10)
        results = ssh.execute_commands(["system-view"], delay_ms=200)

    # 只有命令本身被发送（1 次），不应额外发 Y
    assert len(sent) == 1, f"正常命令不应触发额外 send，实际 sent: {sent}"
    assert 'system-view' in sent[0]
    assert results[0]["success"] is True


def test_execute_commands_yn_with_real_error_still_fails():
    """Y/N 提示后命令仍报 Error（如 Y/N 答完但命令实际失败），executor 必须判 failure"""
    outputs = [
        # 0) 欢迎信息
        "*********************************************************\n<MGT>",
        # 1) 命令回显 + Y/N 提示
        "port link-mode route\r\nThe configuration will be restored. Continue? [Y/N]:",
        # 2) 答 Y 后设备报错
        "Y\r\nError: Interface not found.\r\n[MGT]",
    ]
    ch, sent = _make_channel_with_outputs(outputs)

    fake_client = MagicMock()
    fake_client.invoke_shell.return_value = ch

    with patch.object(SSHExecutor, '_connect', return_value=fake_client):
        ssh = SSHExecutor(host='1.2.3.4', port=22, username='u', password='p', timeout=10)
        results = ssh.execute_commands(["port link-mode route"], delay_ms=200)

    # 验证：答了 Y，但设备后续报 Error → success=False
    assert any('Y' in s for s in sent)
    assert results[0]["success"] is False, f"设备报 Error 时必须判 failure，实际: {results[0]}"
    # 错误信息在 output 全文里（error 字段只截第一行 → 命令回显）
    assert "Error" in results[0]["output"], f"output 必须含 Error 关键字，实际: {results[0]}"


def test_execute_commands_multiple_yn_prompts_max_3():
    """设备连续弹 Y/N 提示（最多 3 次），防止无限循环"""
    outputs = [
        # 0) 欢迎信息
        "*********************************************************\n<MGT>",
        # 1) 第一次 Y/N
        "cmd1\r\nContinue? [Y/N]:",
        "Y\r\nContinue? [Y/N]:",  # 第二次
        "Y\r\nContinue? [Y/N]:",  # 第三次
        "Y\r\n[MGT]",  # 第四次
    ]
    ch, sent = _make_channel_with_outputs(outputs)

    fake_client = MagicMock()
    fake_client.invoke_shell.return_value = ch

    with patch.object(SSHExecutor, '_connect', return_value=fake_client):
        ssh = SSHExecutor(host='1.2.3.4', port=22, username='u', password='p', timeout=10)
        results = ssh.execute_commands(["cmd1"], delay_ms=200)

    # 最多答 3 次 Y（防死循环）
    y_count = sum(1 for s in sent if s.strip() == 'Y')
    assert y_count <= 3, f"Y 回答必须封顶 3 次防死循环，实际 {y_count} 次: {sent}"
    assert results[0]["success"] is True


def test_execute_commands_yn_does_not_loop_on_stale_prompt():
    """回归 bug：累计 output 里仍含首次 [Y/N]:，不能反复触发 Y 发送

    修前 bug 场景：
    - 设备首次返回 "...Continue? [Y/N]:" + Y echo + "[MGT-...]" 提示
    - 修前 while 用累计 output 判 [Y/N]，老 [Y/N]: 仍匹配 → 连发 Y
    - 设备在 [MGT-...] 提示符下收到 Y 当命令 → "% Unrecognized command" 假失败
    修复后：只在最新 extra 里查 [Y/N]，答 1 次 Y 后即使累计 output 含 [Y/N]: 也不再发
    """
    outputs = [
        # 0) 欢迎信息
        "*********************************************************\n<MGT>",
        # 1) 第一次 [Y/N]
        "cmd1\r\nContinue? [Y/N]:",
        # 2) Y echo + 设备回到 [MGT] 提示符（无新 [Y/N]）
        "Y\r\n[MGT-GigabitEthernet1/0/5]",
    ]
    ch, sent = _make_channel_with_outputs(outputs)

    fake_client = MagicMock()
    fake_client.invoke_shell.return_value = ch

    with patch.object(SSHExecutor, '_connect', return_value=fake_client):
        ssh = SSHExecutor(host='1.2.3.4', port=22, username='u', password='p', timeout=10)
        results = ssh.execute_commands(["cmd1"], delay_ms=200)

    # 关键断言：只发 1 次 Y（修前会发 3 次）
    y_count = sum(1 for s in sent if s.strip() == 'Y')
    assert y_count == 1, f"修后应只发 1 次 Y，实际 {y_count} 次: {sent}"
    # 验证无 Unrecognized command（无假失败）
    assert "Unrecognized" not in results[0]["output"], f"不应有假 Unrecognized 报错: {results[0]}"
    assert results[0]["success"] is True, f"link-mode 应 success，实际: {results[0]}"
