"""S1-021/S1-022 runner 对抗测试（不触真机、不读真实凭据、不启动生产网络）。

用 stub/fake 命令验证 `qa/run_s1_019_real_lifecycle.sh` 宿主机安全 runner 的守卫行为：

  1. 缺任一门禁 / 目标非 .5 → 在任何设备 I/O 前失败。
  2. 基线已有共享对象（sdn_l3vpn / vxlan global）→ 拒绝执行且不发出 undo。
  3. pytest 成功与失败两条路径都进入 cleanup + final readback。
  4. Ctrl-C/TERM 中断路径触发 trap（可控子进程模拟，killpg）。
  5. pytest 失败且 cleanup 成功 → 保留 pytest 非零；pytest 成功但 cleanup/readback
     失败 → runner 非零并指示人工。
  6. cleanup 只含两条精确共享 undo + 必要上下文，无 save / 越界命令。
  7. 本机锁防并发（第二个 runner 在设备 I/O 前退出 2；真实断言 loser 无新增调用/undo）。

S1-022 新增（审计目录失效时仍必须安全清理）：
  8. 审计目录启动不可创建/不可写 → 设备 I/O 调用 0、pytest 未调用、非零退出。
  9. baseline 持久化失败 → 不进入 pytest/可写阶段（仅基线只读一次，无 undo）。
  10. pytest 期间删除/破坏审计目录 → cleanup 两条精确 undo 仍实际调用、
      final readback 仍实际调用、runner 非零 + MANUAL-NEEDED（审计写失败不替代 cleanup/readback）。
  11. cleanup 设备命令失败 + 审计目录失败 → 仍执行 final readback。

运行前提：runner 与 stub 位于 openspec/changes/next-s1-backend/qa/。
  - QA 容器：compose 已挂载 qa 目录到 /opt/s1-qa 并设 S1_021_QA_DIR。
  - 宿主机：相对路径兜底（backend 位于 worktree 根时）。
找不到时整模块 skip。
"""
import os
import signal
import subprocess
import sys
import time

import pytest

QA_DIR_ENV = os.environ.get("S1_021_QA_DIR", "")


def _find_qa_dir():
    if QA_DIR_ENV and os.path.isfile(os.path.join(QA_DIR_ENV, "run_s1_019_real_lifecycle.sh")):
        return QA_DIR_ENV
    rel = os.path.abspath(os.path.join(
        os.path.dirname(__file__), "..", "..", "openspec",
        "changes", "next-s1-backend", "qa"))
    if os.path.isfile(os.path.join(rel, "run_s1_019_real_lifecycle.sh")):
        return rel
    return None


QA_DIR = _find_qa_dir()
if QA_DIR is None:
    pytest.skip(
        "S1-021 runner 未找到：需可访问 openspec/changes/next-s1-backend/qa/"
        "run_s1_019_real_lifecycle.sh（容器内设 S1_021_QA_DIR，或 backend 位于 worktree 根）",
        allow_module_level=True,
    )

RUNNER = os.path.join(QA_DIR, "run_s1_019_real_lifecycle.sh")
STUB_OPS = os.path.join(QA_DIR, "test_stubs", "stub_ops.sh")
STUB_PYTEST = os.path.join(QA_DIR, "test_stubs", "stub_pytest.sh")

FULL_ARGS = ("--integration", "--cleanup-shared")


def _base_env(tmp_path, read_seq="clean_baseline", pytest_rc=0, write_rc=0):
    env = os.environ.copy()
    env.update({
        "S1_019_REAL": "1",
        "S1_019_REAL_HOST": "192.168.100.5",
        "RUNNER_OPS_CMD": STUB_OPS,
        "RUNNER_PYTEST_CMD": STUB_PYTEST,
        "STUB_OPS_LOG": str(tmp_path / "ops.log"),
        "STUB_OPS_COUNTER_FILE": str(tmp_path / "ops.count"),
        "STUB_OPS_READ_SEQ": read_seq,
        "STUB_OPS_WRITE_RC": str(write_rc),
        "STUB_PYTEST_LOG": str(tmp_path / "pytest.log"),
        "STUB_PYTEST_RC": str(pytest_rc),
        "RUNNER_LOCK_FILE": str(tmp_path / "runner.lock"),
        "RUNNER_ARTIFACT_DIR": str(tmp_path / "artifacts"),
    })
    return env


def _run_runner(env, args=FULL_ARGS, timeout=60):
    return subprocess.run([RUNNER, *args], env=env, capture_output=True,
                          text=True, timeout=timeout)


def _ops_calls(log_path):
    """返回调用列表，每个调用 = [argv...]（stub 逐参数一行记录，保留含空格命令）"""
    if not os.path.exists(log_path):
        return []
    calls = []
    cur = None
    with open(log_path, encoding="utf-8") as fh:
        for ln in fh.read().splitlines():
            if ln == "CALL":
                cur = []
                calls.append(cur)
            elif cur is not None and ln.startswith("ARG <") and ln.endswith(">"):
                cur.append(ln[5:-1])
    return calls


def _has_undo(log_path):
    return any("undo ip vpn-instance sdn_l3vpn" in call for call in _ops_calls(log_path))


def _cleanup_call(log_path):
    for call in _ops_calls(log_path):
        if "undo ip vpn-instance sdn_l3vpn" in call:
            return call
    return None


def _extract_commands(call):
    # [--device, <d>, --commands, c1, c2, ..., --output-format, text]
    if "--commands" not in call:
        return []
    i = call.index("--commands")
    j = call.index("--output-format") if "--output-format" in call else len(call)
    return call[i + 1:j]


def _read_count(tmp_path):
    counter = tmp_path / "ops.count"
    if not counter.exists():
        return 0
    try:
        return int(counter.read_text().strip())
    except ValueError:
        return -1


def _pytest_called(tmp_path):
    log = tmp_path / "pytest.log"
    return log.exists() and "CALL" in log.read_text()


def _wait_for(pred, timeout=20, interval=0.1):
    deadline = time.time() + timeout
    while time.time() < deadline:
        if pred():
            return True
        time.sleep(interval)
    return False


# ── 1. 门禁：缺任一项 / 目标非 .5 → 设备 I/O 前失败 ──

def test_missing_integration_gate_refuses_before_io(tmp_path):
    env = _base_env(tmp_path)
    r = _run_runner(env, args=("--cleanup-shared",))
    assert r.returncode == 3
    assert "GATE-FAIL" in r.stderr
    assert _ops_calls(tmp_path / "ops.log") == []  # 无任何设备 I/O
    assert not _pytest_called(tmp_path)


def test_missing_real_env_refuses_before_io(tmp_path):
    env = _base_env(tmp_path)
    env["S1_019_REAL"] = "0"
    r = _run_runner(env)
    assert r.returncode == 3
    assert _ops_calls(tmp_path / "ops.log") == []


def test_wrong_target_refuses_before_io(tmp_path):
    env = _base_env(tmp_path)
    env["S1_019_REAL_HOST"] = "192.168.100.6"
    r = _run_runner(env)
    assert r.returncode == 3
    assert "192.168.100.5" in r.stderr
    assert _ops_calls(tmp_path / "ops.log") == []


def test_missing_cleanup_shared_gate_refuses_before_io(tmp_path):
    env = _base_env(tmp_path)
    r = _run_runner(env, args=("--integration",))
    assert r.returncode == 3
    assert "--cleanup-shared" in r.stderr
    assert _ops_calls(tmp_path / "ops.log") == []


# ── 2. 基线已有共享对象 → 拒绝执行且不发出 undo ──

def test_baseline_shared_present_refuses_no_undo(tmp_path):
    env = _base_env(tmp_path, read_seq="dirty_baseline_shared")
    r = _run_runner(env)
    assert r.returncode == 5
    assert "BASELINE-REFUSE" in r.stderr
    assert _ops_calls(tmp_path / "ops.log")  # 基线只读确实发生
    assert not _has_undo(tmp_path / "ops.log")  # 绝无 undo
    assert not _pytest_called(tmp_path)


def test_baseline_vsi_present_refuses(tmp_path):
    env = _base_env(tmp_path, read_seq="dirty_baseline_vsi")
    r = _run_runner(env)
    assert r.returncode == 4
    assert "BASELINE-FAIL" in r.stderr
    assert not _has_undo(tmp_path / "ops.log")
    assert not _pytest_called(tmp_path)


def test_baseline_ac_present_refuses(tmp_path):
    env = _base_env(tmp_path, read_seq="dirty_baseline_ac")
    r = _run_runner(env)
    assert r.returncode == 4
    assert "BASELINE-FAIL" in r.stderr
    assert not _has_undo(tmp_path / "ops.log")


# ── 3. pytest 成功/失败都进入 cleanup + final readback ──

def test_pytest_success_enters_cleanup_and_readback(tmp_path):
    env = _base_env(tmp_path, pytest_rc=0)
    r = _run_runner(env)
    assert r.returncode == 0, r.stdout + r.stderr
    assert _pytest_called(tmp_path)
    assert _has_undo(tmp_path / "ops.log")       # cleanup（undo）发出
    assert _read_count(tmp_path) == 2             # 基线 read + 最终 readback
    assert "FINAL-READBACK-OK" in r.stdout


def test_pytest_failure_preserves_code_but_cleans(tmp_path):
    env = _base_env(tmp_path, pytest_rc=5)
    r = _run_runner(env)
    assert r.returncode == 5                       # 保留 pytest 原始退出码
    assert _has_undo(tmp_path / "ops.log")         # 仍进入 cleanup
    assert _read_count(tmp_path) == 2              # 仍 final readback
    assert "FINAL-READBACK-OK" in r.stdout


# ── 5. pytest 成功但 cleanup/readback 失败 → runner 非零 + 指示人工 ──

def test_cleanup_write_failure_runner_fails(tmp_path):
    env = _base_env(tmp_path, pytest_rc=0, write_rc=1)
    r = _run_runner(env)
    assert r.returncode != 0
    assert "MANUAL-NEEDED" in r.stderr


def test_cleanup_rc0_but_readback_residue_runner_fails(tmp_path):
    # 命令返回码 0 ≠ 清理成功：final readback 仍见共享残留 → runner 失败
    env = _base_env(tmp_path, read_seq="clean_baseline,residue_after", pytest_rc=0, write_rc=0)
    r = _run_runner(env)
    assert r.returncode != 0
    assert "MANUAL-NEEDED" in r.stderr
    assert "残留" in r.stderr


def test_final_readback_failure_runner_fails(tmp_path):
    env = _base_env(tmp_path, read_seq="clean_baseline,readback_fail", pytest_rc=0)
    r = _run_runner(env)
    assert r.returncode != 0
    assert "最终 readback" in r.stderr


# ── 6. cleanup 命令精确：两条共享 undo + 上下文，无 save / 越界 ──

def test_cleanup_commands_exact_no_save(tmp_path):
    env = _base_env(tmp_path, pytest_rc=0)
    r = _run_runner(env)
    assert r.returncode == 0, r.stdout + r.stderr
    cleanup = _cleanup_call(tmp_path / "ops.log")
    assert cleanup is not None
    cmds = _extract_commands(cleanup)
    assert cmds == [
        "system-view",
        "undo ip vpn-instance sdn_l3vpn",
        "undo vxlan tunnel mac-learning disable",
        "return",
    ]
    joined = " ".join(cleanup)
    assert all("save" not in c.lower() and "startup" not in c.lower() for c in cmds)
    assert not any(k in joined for k in (".6", "MGE0/0/0", "GigabitEthernet1/0/1"))


# ── 4. 中断路径触发 trap（可控子进程模拟，killpg）──

def test_interrupt_triggers_trap_cleanup(tmp_path):
    env = _base_env(tmp_path, pytest_rc=0)
    env["STUB_PYTEST_SLEEP"] = "1"
    env["STUB_PYTEST_SLEEP_SECS"] = "300"
    proc = subprocess.Popen([RUNNER, *FULL_ARGS], env=env, start_new_session=True)
    assert _wait_for(lambda: bool(_ops_calls(env["STUB_OPS_LOG"]))), "runner 未进入写阶段"
    time.sleep(0.5)
    os.killpg(proc.pid, signal.SIGINT)
    rc = proc.wait(timeout=30)
    assert rc == 130
    assert _has_undo(env["STUB_OPS_LOG"])          # trap 触发 cleanup
    assert _read_count(tmp_path) == 2              # 中断后仍 final readback


def test_sigterm_triggers_trap_cleanup(tmp_path):
    env = _base_env(tmp_path, pytest_rc=0)
    env["STUB_PYTEST_SLEEP"] = "1"
    env["STUB_PYTEST_SLEEP_SECS"] = "300"
    proc = subprocess.Popen([RUNNER, *FULL_ARGS], env=env, start_new_session=True)
    assert _wait_for(lambda: bool(_ops_calls(env["STUB_OPS_LOG"])))
    time.sleep(0.5)
    os.killpg(proc.pid, signal.SIGTERM)
    rc = proc.wait(timeout=30)
    assert rc == 130
    assert _has_undo(env["STUB_OPS_LOG"])
    assert _read_count(tmp_path) == 2


# ── 7. 本机锁：并发第二个 runner 在设备 I/O 前退出 2 ──

def test_lock_prevents_concurrent_runners(tmp_path):
    env = _base_env(tmp_path, pytest_rc=0)
    env["STUB_PYTEST_SLEEP"] = "1"
    env["STUB_PYTEST_SLEEP_SECS"] = "300"
    proc_a = subprocess.Popen([RUNNER, *FULL_ARGS], env=env, start_new_session=True)
    assert _wait_for(lambda: bool(_ops_calls(env["STUB_OPS_LOG"]))), "runner A 未取得锁"
    r_b = _run_runner(env, timeout=30)
    assert r_b.returncode == 2
    assert "LOCK-FAIL" in r_b.stderr
    # B 在设备 I/O 前退出：日志里只有 A 的基线只读（1 次），无 undo、无 pytest
    calls_before_kill = _ops_calls(env["STUB_OPS_LOG"])
    assert len(calls_before_kill) == 1, f"B 增加了设备调用: {calls_before_kill}"
    assert not _has_undo(env["STUB_OPS_LOG"]), "并发 loser 不应发出 undo"
    assert _read_count(tmp_path) == 1  # 只有 A 的基线 read（B 未增加 read）
    os.killpg(proc_a.pid, signal.SIGTERM)
    assert proc_a.wait(timeout=30) == 130


# ── S1-022：审计目录失效时仍必须安全清理 ──

def test_artifact_dir_uncreatable_fails_before_io(tmp_path):
    # 审计目录父级是普通文件 → mkdir -p 失败 → 任何设备 I/O 前退出
    blocker = tmp_path / "afile"
    blocker.write_text("x")
    env = _base_env(tmp_path)
    env["RUNNER_ARTIFACT_DIR"] = str(blocker / "sub")
    r = _run_runner(env)
    assert r.returncode != 0
    assert "ARTIFACT-FAIL" in r.stderr
    assert _ops_calls(tmp_path / "ops.log") == []   # 0 次设备 I/O
    assert not _pytest_called(tmp_path)


def test_artifact_dir_is_a_file_fails_before_io(tmp_path):
    # 审计目录本身是普通文件（不可创建/不可写）→ 任何设备 I/O 前退出
    blocker = tmp_path / "adir"
    blocker.write_text("x")
    env = _base_env(tmp_path)
    env["RUNNER_ARTIFACT_DIR"] = str(blocker)
    r = _run_runner(env)
    assert r.returncode != 0
    assert "ARTIFACT-FAIL" in r.stderr
    assert _ops_calls(tmp_path / "ops.log") == []
    assert not _pytest_called(tmp_path)


def test_baseline_persist_failure_stops_before_pytest(tmp_path):
    # 审计目录可创建，但 baseline.txt 已存在为目录 → baseline 写失败，
    # 必须在 pytest/可写阶段前终止（只发生 1 次基线只读，无 undo、无 pytest）
    env = _base_env(tmp_path)
    artifacts = tmp_path / "artifacts"
    artifacts.mkdir(parents=True, exist_ok=True)
    (artifacts / "baseline.txt").mkdir(exist_ok=True)   # 让 baseline 写入失败
    r = _run_runner(env)
    assert r.returncode == 4
    assert "基线持久化失败" in r.stderr
    assert _read_count(tmp_path) == 1       # 仅基线只读
    assert not _has_undo(tmp_path / "ops.log")
    assert not _pytest_called(tmp_path)


def test_artifact_dir_removed_during_pytest_cleanup_still_runs(tmp_path):
    # pytest 期间删除审计目录：cleanup 两条精确 undo 仍实际调用、final readback 仍实际调用、
    # runner 非零（审计写失败）+ MANUAL-NEEDED，但 cleanup/readback 不被审计失败替代/跳过
    import shlex
    env = _base_env(tmp_path, pytest_rc=0)
    env["STUB_PYTEST_HOOK"] = "rm -rf " + shlex.quote(env["RUNNER_ARTIFACT_DIR"])
    r = _run_runner(env)
    assert r.returncode != 0
    assert "MANUAL-NEEDED" in r.stderr
    assert _has_undo(tmp_path / "ops.log")            # cleanup 实际执行（undo 已发出）
    assert _read_count(tmp_path) == 2                 # 基线 + 最终 readback 仍执行
    cleanup = _cleanup_call(tmp_path / "ops.log")
    assert _extract_commands(cleanup) == [
        "system-view",
        "undo ip vpn-instance sdn_l3vpn",
        "undo vxlan tunnel mac-learning disable",
        "return",
    ]


def test_cleanup_device_failure_and_audit_failure_still_readback(tmp_path):
    # cleanup 设备命令失败（写 rc=1）+ 审计目录被破坏：仍执行 final readback，
    # undo 已实际尝试（被记录），runner 非零 + MANUAL-NEEDED
    import shlex
    env = _base_env(tmp_path, pytest_rc=0, write_rc=1)
    env["STUB_PYTEST_HOOK"] = "rm -rf " + shlex.quote(env["RUNNER_ARTIFACT_DIR"])
    r = _run_runner(env)
    assert r.returncode != 0
    assert "MANUAL-NEEDED" in r.stderr
    assert _has_undo(tmp_path / "ops.log")            # cleanup 确实被尝试（调用被记录）
    assert _read_count(tmp_path) == 2                 # final readback 未被 cleanup 失败跳过


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
