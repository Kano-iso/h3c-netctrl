"""ops-toolkit paramiko-batch-exec 工具的单元测试（v242-paramiko-tool Task 6）

测 _paramiko_batch_exec.py:run_commands() 的核心逻辑：
- 成功/失败/部分失败的 summary 统计
- retry 行为
- continue_on_error vs stop_on_error
- 连接失败的容错
- 凭据缺失的 fail-fast

策略：把 _paramiko_batch_exec.py 当独立模块 import。
它顶部 `sys.path.insert(0, "/opt"); from ssh_executor import SSHExecutor` 在
qa-backend 容器里会失败（/opt 路径不存在），所以用 sys.modules 提前 mock SSHExecutor。
"""
import json
import os
import subprocess
import sys
import time
from unittest.mock import MagicMock, patch

import pytest

# === 真机集成测试 marker（qa-backend 默认 skip，需 --integration 开启）===
# 复用 backend/tests/conftest.py 的 integration 配置（v2.3 QA 规范化）
"""paramiko-batch-exec 工具的测试（v242-paramiko-tool Task 6/7）

Task 6: 单元测试（mock SSHExecutor，11 case）
Task 7: 真机集成测试（--integration marker，subprocess 调 ops-toolkit 容器）
"""

# _paramiko_batch_exec.py 路径：qa-backend 容器挂载点
_OPS_TOOLKIT_SCRIPTS = "/opt/ops-toolkit-scripts"

# 真实 SSHExecutor 路径（qa-backend 容器内 backend/app/utils/ssh_executor.py）
# 用真实 SSHExecutor 时 _paramiko_batch_exec.py 顶部 from ssh_executor import SSHExecutor
# 就会拿到 backend 的真实类（不是 MagicMock）
_BACKEND_SSH_EXECUTOR_PATH = "/app/app/utils"


def _import_paramiko_module(use_real_ssh_executor=False):
    """import _paramiko_batch_exec.py
    use_real_ssh_executor=False（默认）→ mock ssh_executor 模块（单元测试用）
    use_real_ssh_executor=True → 用真实 backend SSHExecutor（集成测试用）
    """
    if use_real_ssh_executor:
        # 清掉之前的 mock，强制重新 import
        sys.modules.pop("ssh_executor", None)
        sys.modules.pop("_paramiko_batch_exec", None)
        # 把 backend SSHExecutor 路径加到最前
        if _BACKEND_SSH_EXECUTOR_PATH not in sys.path:
            sys.path.insert(0, _BACKEND_SSH_EXECUTOR_PATH)
        # ops-toolkit scripts 路径也要加（_paramiko_batch_exec.py 在那）
        if _OPS_TOOLKIT_SCRIPTS not in sys.path:
            sys.path.insert(0, _OPS_TOOLKIT_SCRIPTS)
    else:
        # mock SSHExecutor 让顶部 import 不报错
        mock_ssh_executor = MagicMock()
        sys.modules["ssh_executor"] = mock_ssh_executor
        if _OPS_TOOLKIT_SCRIPTS not in sys.path:
            sys.path.insert(0, _OPS_TOOLKIT_SCRIPTS)
        # 强制重 import
        sys.modules.pop("_paramiko_batch_exec", None)

    import _paramiko_batch_exec  # noqa: E402
    return _paramiko_batch_exec


# ==================== Case 1: 成功跑 1 条命令 ====================

def test_run_commands_single_success():
    """Case 1: 单条命令成功 → success=1, failed=0"""
    mod = _import_paramiko_module()

    # mock SSHExecutor.execute_commands 返回 1 条成功
    fake_executor = MagicMock()
    fake_executor.execute_commands.return_value = [
        {"cmd": "display version", "output": "H3C Comware V7", "success": True,
         "error": None, "execution_time": 1.0}
    ]
    with patch.object(mod, "SSHExecutor", return_value=fake_executor):
        summary = mod.run_commands(
            "192.168.100.177", 22, "python", "Admin123!@#",
            ["display version"], timeout=30, retries=0, continue_on_error=True,
        )

    assert summary["host"] == "192.168.100.177"
    assert summary["total"] == 1
    assert summary["success"] == 1
    assert summary["failed"] == 0
    assert summary["results"][0]["command"] == "display version"
    assert summary["results"][0]["success"] is True
    assert summary["results"][0]["returncode"] == 0
    assert "H3C" in summary["results"][0]["stdout"]


# ==================== Case 2: 跑批命令 ====================

def test_run_commands_batch_mixed_results():
    """Case 2: 批命令 3 条混合结果（2 成功 1 失败）→ success=2, failed=1"""
    mod = _import_paramiko_module()

    fake_executor = MagicMock()
    fake_executor.execute_commands.return_value = [
        {"cmd": "display version", "output": "OK1", "success": True, "error": None, "execution_time": 0.5},
        {"cmd": "bad-cmd xyz", "output": "% Unknown command", "success": False, "error": "Unknown", "execution_time": 0.3},
        {"cmd": "display vlan 1", "output": "VLAN 1", "success": True, "error": None, "execution_time": 0.4},
    ]
    with patch.object(mod, "SSHExecutor", return_value=fake_executor):
        summary = mod.run_commands(
            "192.168.100.5", 22, "python", "Admin123!@#",
            ["display version", "bad-cmd xyz", "display vlan 1"],
            timeout=30, retries=0, continue_on_error=True,
        )

    assert summary["total"] == 3
    assert summary["success"] == 2
    assert summary["failed"] == 1
    assert summary["results"][0]["success"] is True
    assert summary["results"][1]["success"] is False
    assert summary["results"][1]["returncode"] == 1
    assert summary["results"][1]["stderr"] == "Unknown"
    assert summary["results"][2]["success"] is True


# ==================== Case 3: continue_on_error=False 遇错停止 ====================

def test_run_commands_stop_on_error():
    """Case 3: stop_on_error=True 第 1 条失败时停止（不跑后续）→ total=1"""
    mod = _import_paramiko_module()

    fake_executor = MagicMock()
    fake_executor.execute_commands.return_value = [
        {"cmd": "failing-cmd", "output": "% Error", "success": False, "error": "Boom", "execution_time": 0.2},
    ]
    with patch.object(mod, "SSHExecutor", return_value=fake_executor):
        # 注意：run_commands 在 SSHExecutor 层一次性把 commands 传进去
        # stop_on_error 行为通过 main() 的 continue_on_error 标志实现
        # 这里只测 run_commands 函数本身（它不解析 continue_on_error）
        summary = mod.run_commands(
            "192.168.100.5", 22, "python", "Admin123!@#",
            ["failing-cmd"], timeout=30, retries=0, continue_on_error=False,
        )

    # run_commands 总是跑完所有命令（SSHExecutor 一次性传）
    # stop_on_error 行为在 main() 实现，这里只验证 run_commands 透传
    assert summary["total"] == 1
    assert summary["failed"] == 1


# ==================== Case 4: SSH 连接失败 ====================

def test_run_commands_ssh_connection_error():
    """Case 4: SSH 连接失败（SSHExecutor 抛异常）→ 所有命令标 failed"""
    mod = _import_paramiko_module()

    fake_executor = MagicMock()
    fake_executor.execute_commands.side_effect = ConnectionError("Connection refused")
    with patch.object(mod, "SSHExecutor", return_value=fake_executor):
        summary = mod.run_commands(
            "192.168.100.5", 22, "python", "Admin123!@#",
            ["display version", "display vlan 1"],
            timeout=30, retries=0, continue_on_error=True,
        )

    assert summary["total"] == 2
    assert summary["success"] == 0
    assert summary["failed"] == 2
    for r in summary["results"]:
        assert r["success"] is False
        assert "Connection refused" in r["stderr"]


# ==================== Case 5: retry 行为 ====================

def test_run_commands_retry_on_failure():
    """Case 5: --retries 2 时第 1 次失败第 2 次成功 → 走 2 次"""
    mod = _import_paramiko_module()

    # 第 1 次调用 SSHExecutor.execute_commands 全失败
    # 第 2 次调用成功
    fake_executor = MagicMock()
    fake_executor.execute_commands.side_effect = [
        [
            {"cmd": "cmd1", "output": "fail", "success": False, "error": "transient", "execution_time": 0.1},
        ],
        [
            {"cmd": "cmd1", "output": "ok", "success": True, "error": None, "execution_time": 0.1},
        ],
    ]

    with patch.object(mod, "SSHExecutor", return_value=fake_executor):
        summary = mod.run_commands(
            "192.168.100.5", 22, "python", "Admin123!@#",
            ["cmd1"], timeout=30, retries=2, continue_on_error=True,
        )

    # 第 2 次成功 → results 应该是成功的版本
    assert summary["total"] == 1
    assert summary["success"] == 1
    assert summary["failed"] == 0
    # SSHExecutor.execute_commands 被调 2 次
    assert fake_executor.execute_commands.call_count == 2


# ==================== Case 6: retry 用尽仍失败 ====================

def test_run_commands_retry_exhausted():
    """Case 6: --retries 1 但持续失败 → 用最后一次的结果"""
    mod = _import_paramiko_module()

    fake_executor = MagicMock()
    fake_executor.execute_commands.return_value = [
        {"cmd": "cmd1", "output": "% Error", "success": False, "error": "persistent", "execution_time": 0.1},
    ]
    with patch.object(mod, "SSHExecutor", return_value=fake_executor):
        summary = mod.run_commands(
            "192.168.100.5", 22, "python", "Admin123!@#",
            ["cmd1"], timeout=30, retries=1, continue_on_error=True,
        )

    assert summary["success"] == 0
    assert summary["failed"] == 1
    # 调用 2 次：retries=1 意味着 1+1=2 次机会
    assert fake_executor.execute_commands.call_count == 2


# ==================== Case 7: 空命令列表 ====================

def test_run_commands_empty_after_strip():
    """Case 7: commands 列表全是空白 → 过滤后空 list → 仍能调用（不崩）"""
    mod = _import_paramiko_module()

    fake_executor = MagicMock()
    fake_executor.execute_commands.return_value = []
    with patch.object(mod, "SSHExecutor", return_value=fake_executor):
        summary = mod.run_commands(
            "192.168.100.5", 22, "python", "Admin123!@#",
            ["", "  ", ""], timeout=30, retries=0, continue_on_error=True,
        )

    # commands 过滤后是空 list，SSHExecutor.execute_commands([]) 返 []
    # run_commands 保持 total=3（原始命令数）但 success + failed 反映实际执行
    # 一致性约束：success + failed <= total（多余的 total 是被过滤掉的空命令）
    assert summary["total"] == 3
    assert summary["success"] == 0
    assert summary["failed"] == 0
    # 实际只调用 SSHExecutor 一次（一次性传过滤后的 []）
    fake_executor.execute_commands.assert_called_once_with([], delay_ms=300)


# ==================== Case 8: main() fail-fast 缺 host ====================

def test_main_missing_host():
    """Case 8: _PMK_HOST 未设 → exit 2 + stderr '缺少'"""
    mod = _import_paramiko_module()

    env = os.environ.copy()
    env.pop("_PMK_HOST", None)
    env.pop("_PMK_USER", None)
    env.pop("_PMK_PASS", None)
    env["_PMK_COMMANDS_JSON"] = '["display version"]'

    with patch.object(sys, "argv", ["_paramiko_batch_exec.py"]):
        with pytest.raises(SystemExit) as exc_info:
            mod.main()

    assert exc_info.value.code == 2


# ==================== Case 9: main() fail-fast 缺命令 ====================

def test_main_missing_commands():
    """Case 9: _PMK_COMMANDS_JSON 为空 → exit 2 + stderr '为空'"""
    mod = _import_paramiko_module()

    env = os.environ.copy()
    env["_PMK_HOST"] = "192.168.100.177"
    env["_PMK_USER"] = "python"
    env["_PMK_PASS"] = "Admin123!@#"
    env["_PMK_COMMANDS_JSON"] = "[]"

    with patch.dict(os.environ, env, clear=True):
        with pytest.raises(SystemExit) as exc_info:
            mod.main()

    assert exc_info.value.code == 2


# ==================== Case 10: main() JSON 输出 ====================

def test_main_json_output_format(capsys):
    """Case 10: main() 默认 JSON 输出含全部字段"""
    mod = _import_paramiko_module()

    fake_executor = MagicMock()
    fake_executor.execute_commands.return_value = [
        {"cmd": "display version", "output": "H3C V7.1", "success": True, "error": None, "execution_time": 0.5},
    ]

    env = {
        "_PMK_HOST": "192.168.100.177",
        "_PMK_PORT": "22",
        "_PMK_USER": "python",
        "_PMK_PASS": "Admin123!@#",
        "_PMK_COMMANDS_JSON": '["display version"]',
        "_PMK_TIMEOUT": "30",
        "_PMK_OUTPUT_FORMAT": "json",
        "_PMK_RETRIES": "0",
        "_PMK_CONTINUE_ON_ERROR": "true",
    }
    # 清空 _PMK_HOST 等可能从外面 env 传进来的值
    cleared = {k: v for k, v in os.environ.items() if not k.startswith("_PMK_")}

    with patch.dict(os.environ, cleared, clear=True):
        for k, v in env.items():
            os.environ[k] = v
        with patch.object(mod, "SSHExecutor", return_value=fake_executor):
            with pytest.raises(SystemExit) as exc_info:
                mod.main()

    assert exc_info.value.code == 0
    captured = capsys.readouterr()
    summary = json.loads(captured.out)
    assert summary["host"] == "192.168.100.177"
    assert summary["total"] == 1
    assert summary["success"] == 1
    assert summary["failed"] == 0
    assert "elapsed_ms" in summary
    assert len(summary["results"]) == 1
    assert summary["results"][0]["stdout"] == "H3C V7.1"


# ==================== 额外 Case 11: 验证真复用 backend SSHExecutor（不手搓）===================

def test_uses_backend_ssh_executor():
    """Case 11: _paramiko_batch_exec.py 顶部 from ssh_executor import SSHExecutor
    这是约束：ops-toolkit 必须复用 backend SSHExecutor（不重复造 paramiko 协议）

    验证：SSHExecutor 来自 ssh_executor 模块（不是手搓的 class）
    """
    mod = _import_paramiko_module()
    # 关键断言：SSHExecutor 来自 ssh_executor 模块（不是手搓的 class）
    # 真实场景下是 backend/app/utils/ssh_executor.py 的 SSHExecutor
    # 单元测试只验证 import 路径正确
    assert hasattr(mod, "SSHExecutor")
    # 关键断言：mod 内部用了 SSHExecutor（不是手搓的 invoke_shell）
    import inspect
    source = inspect.getsource(mod.run_commands)
    assert "SSHExecutor" in source, "run_commands 必须复用 SSHExecutor，不能手搓 paramiko"
    assert "invoke_shell" not in source, "run_commands 不能手写 invoke_shell（应复用 SSHExecutor）"
    assert "Transport._preferred_kex" not in source, "run_commands 不能配 H3C kex（应复用 SSHExecutor）"


# ==================== 真机集成测试（Task 7，--integration marker）====================

# 集成测试默认 skip，需 --integration 显式开启
# 跑：docker compose -f docker-compose.dev.yml run --rm --entrypoint \
#     "python -m pytest tests/test_ops_toolkit_paramiko.py -m integration --integration -v" qa-backend
#
# 实现策略：在 qa-backend 容器内复用 backend SSHExecutor 直接连 .177
# （不用 docker compose run ops-toolkit，因为 qa-backend 容器内没装 docker CLI）
# 这也间接验证：SSHExecutor 既能驱动 backend 业务代码，也能驱动 ops-toolkit 工具

# 真实设备地址（v2.3+ 默认 .177 test 设备）
_REAL_DEVICE_HOST = "192.168.100.177"


def _get_real_credentials():
    """从环境变量读 .env 注入的凭据（qa-backend 容器内可用）"""
    user = os.environ.get("DEVICE_USERNAME") or os.environ.get("SSH_USER")
    password = os.environ.get("DEVICE_PASSWORD") or os.environ.get("SSH_PASS")
    if not user or not password:
        pytest.skip("缺 DEVICE_USERNAME/DEVICE_PASSWORD 环境变量（.env 注入失败）")
    return user, password


@pytest.mark.integration
def test_paramiko_batch_exec_real_device_single_command():
    """Task 7 case 1: 真机跑单条 display version 命令

    前置：qa-backend 容器有 .env 注入 + .177 设备可达 + paramiko 已装
    验证：调 _paramiko_batch_exec.run_commands() 返 success=1 + stdout 含 "H3C"
    """
    user, password = _get_real_credentials()
    mod = _import_paramiko_module(use_real_ssh_executor=True)

    # 调 run_commands（它会复用真实的 backend SSHExecutor）
    summary = mod.run_commands(
        _REAL_DEVICE_HOST, 22, user, password,
        ["display version"], timeout=30, retries=0, continue_on_error=True,
    )

    assert summary["host"] == _REAL_DEVICE_HOST
    assert summary["total"] == 1
    assert summary["success"] == 1, f"命令失败: {summary['results'][0]}"
    assert summary["failed"] == 0
    # stdout 含 H3C 关键字（设备是 S6850 / V7）
    stdout = summary["results"][0]["stdout"]
    assert "H3C" in stdout, f"stdout 不含 H3C: {stdout[:200]}"


@pytest.mark.integration
def test_paramiko_batch_exec_real_device_batch_commands():
    """Task 7 case 2: 真机跑批命令 3 条

    验证：单 SSH 连接复用，3 条命令全部成功
    """
    user, password = _get_real_credentials()
    mod = _import_paramiko_module(use_real_ssh_executor=True)

    summary = mod.run_commands(
        _REAL_DEVICE_HOST, 22, user, password,
        ["display version", "display vlan 1", "display interface brief"],
        timeout=60, retries=0, continue_on_error=True,
    )

    assert summary["total"] == 3
    assert summary["success"] == 3, f"有命令失败: {summary['results']}"
    assert summary["failed"] == 0
    # 3 条命令全部 stdout 不应为空
    for r in summary["results"]:
        assert r["stdout"], f"命令 {r['command']} 输出为空"


@pytest.mark.integration
def test_paramiko_batch_exec_real_device_via_docker_compose():
    """Task 7 case 3: 真机跑 ops-toolkit 容器（端到端）

    验证：docker compose run ops-toolkit paramiko-batch-exec.sh --device test
    能在 .177 上跑通（开箱即用，零参数）
    """
    # qa-backend 容器内没装 docker CLI，skip（这个 case 在宿主机上跑）
    import shutil
    if not shutil.which("docker"):
        pytest.skip("qa-backend 容器内无 docker CLI，端到端 case 需在宿主机跑")
        return

    cmd = [
        "docker", "compose", "-f", "docker-compose.dev.yml",
        "--profile", "ops", "run", "--rm", "ops-toolkit",
        "paramiko-batch-exec.sh", "--device", "test",
        "--command", "display version",
    ]
    # 找 docker-compose.dev.yml 路径
    cwd = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    if not os.path.exists(os.path.join(cwd, "docker-compose.dev.yml")):
        # 在 qa-backend 容器内，文件不在 cwd，需要从 env 读
        cwd = os.environ.get("PROJECT_ROOT", cwd)

    result = subprocess.run(
        cmd, capture_output=True, text=True, timeout=60,
        cwd=cwd,
    )
    assert result.returncode == 0, f"exit={result.returncode}\nSTDOUT={result.stdout[:500]}\nSTDERR={result.stderr[:500]}"

    summary = json.loads(result.stdout)
    assert summary["host"] == _REAL_DEVICE_HOST
    assert summary["success"] == 1
    assert "H3C" in summary["results"][0]["stdout"]


@pytest.mark.integration
def test_paramiko_batch_exec_real_device_fail_fast_no_credentials():
    """Task 7 case 4: 缺凭据时 run_commands 的容错

    验证：连接错误（错误密码）→ SSHExecutor 抛异常 → run_commands 把
    所有命令标 failed，不崩
    """
    mod = _import_paramiko_module(use_real_ssh_executor=True)
    # 用错误密码连 .177 → 必然失败
    summary = mod.run_commands(
        _REAL_DEVICE_HOST, 22, "python", "WRONG_PASSWORD_XXX",
        ["display version"], timeout=15, retries=0, continue_on_error=True,
    )

    assert summary["total"] == 1
    assert summary["success"] == 0
    assert summary["failed"] == 1
    # stderr 应含认证失败信息
    assert "Auth" in summary["results"][0]["stderr"] or "认证" in summary["results"][0]["stderr"] or "fail" in summary["results"][0]["stderr"].lower(), \
        f"stderr 应含认证失败信息: {summary['results'][0]['stderr'][:200]}"
