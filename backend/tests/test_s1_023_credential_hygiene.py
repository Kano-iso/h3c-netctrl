"""S1-023 仓库凭据卫生对抗测试（不连设备、不读真实凭据、不跑真机）.

覆盖：
  1. 活动生产路径无真实密码字面量（schemas / ztp-stack 三脚本 / 模板 / 前端 / 活动文档）。
  2. ZTP 密码只来自环境注入，缺失 → 明确失败（fail closed，不回退代码内口令）：
     ztp_runtime_render.default_context / load_override、ztp_onboard_callback.current_payload。
  3. ZTP onboard API 缺密码 → 422（无默认口令兜底）。
  4. ops-toolkit debug-v24-* 临时脚本已移除。
  5. 测试代码（backend/tests）不再携带真实口令字面量。
"""
import json
import os
import stat
import sys
import types
from pathlib import Path

import pytest

# 仓库根（QA 容器经 compose 只读挂载 /opt/s1-repo；宿主机走相对兜底）
_REPO_ROOT = Path(os.getenv("S1_023_REPO_DIR", "")) if os.getenv("S1_023_REPO_DIR") else Path(__file__).resolve().parents[2]
if not (_REPO_ROOT / "backend").is_dir():
    _REPO_ROOT = Path("/opt/s1-repo")

# 真实默认口令的公共前缀（含截断变体）；拼装以避开“测试代码自身携带字面量”的自指
_REAL_PASSWORD_SUBSTR = "".join(["Admin", "123"])

# 活动生产路径（真实口令字面量不得出现）
PRODUCTION_PATHS = [
    "backend/app/schemas.py",
    "backend/app/services/ztp_recovery.py",
    "docker/ztp-stack/entrypoint.sh",
    "docker/ztp-stack/ztp_runtime_render.py",
    "docker/ztp-stack/ztp_onboard_callback.py",
    "docker/ztp-stack/tftp/autocfg.cfg.j2",
    "frontend/src/views/ZtpRecovery.vue",
    "frontend/src/i18n/zh-CN.js",
    "frontend/src/i18n/en-US.js",
    "docs/ztp-stack.md",
    "openspec/specs/device-crud-ui/spec.md",
]

DEBUG_SCRIPTS = [
    "debug-v24-177-full.py",
    "debug-v24-bugfix-ns.py",
    "debug-v24-filter-test.py",
    "debug-v24-filter-wrap.py",
    "debug-v24-iface-100.py",
]


# ── 1. 活动生产路径无真实密码字面量 ──

def test_active_production_paths_have_no_real_password_literal():
    for rel in PRODUCTION_PATHS:
        path = _REPO_ROOT / rel
        assert path.exists(), f"缺少预期生产文件: {rel}"
        text = path.read_text(encoding="utf-8", errors="replace")
        assert _REAL_PASSWORD_SUBSTR not in text, (
            f"生产路径仍含真实口令字面量: {rel}"
        )


def test_active_test_files_have_no_real_password_literal():
    tests_dir = _REPO_ROOT / "backend" / "tests"
    offenders = []
    for path in tests_dir.rglob("*.py"):
        if _REAL_PASSWORD_SUBSTR in path.read_text(encoding="utf-8", errors="replace"):
            offenders.append(str(path.relative_to(_REPO_ROOT)))
    assert offenders == [], f"测试文件仍含真实口令字面量: {offenders}"


def test_debug_v24_temporary_scripts_removed():
    scripts_dir = _REPO_ROOT / "ops-toolkit" / "scripts"
    for name in DEBUG_SCRIPTS:
        assert not (scripts_dir / name).exists(), (
            f"debug-v24 临时脚本（裸 ncclient + 硬编码凭据）应已移除: {name}"
        )


# ── 2. ZTP 密码只来自环境注入；缺失 → 明确失败 ──

@pytest.fixture()
def ztp_stack():
    """导入 docker/ztp-stack 模块（jinja2 用最小 stub 注入）。"""
    stack_dir = Path(os.getenv("S1_023_ZTP_STACK_DIR", str(_REPO_ROOT / "docker" / "ztp-stack")))
    if not stack_dir.is_dir():
        stack_dir = _REPO_ROOT / "docker" / "ztp-stack"
    assert stack_dir.is_dir(), f"ztp-stack 目录不可达: {stack_dir}"

    # jinja2 在 qa-backend 镜像不可用；ztp_runtime_render 顶层 import → 注入最小 stub
    if "jinja2" not in sys.modules:
        fake_jinja = types.ModuleType("jinja2")

        class _FakeTemplate:
            def __init__(self, source):
                self._source = source

            def render(self, **ctx):
                return self._source

        fake_jinja.Template = _FakeTemplate
        sys.modules["jinja2"] = fake_jinja

    sys.path.insert(0, str(stack_dir))
    try:
        import ztp_runtime_render
        import ztp_onboard_callback
    finally:
        sys.path.pop(0)
    return ztp_runtime_render, ztp_onboard_callback


def test_runtime_render_default_context_fails_without_admin_pass(ztp_stack, monkeypatch):
    rt, _ = ztp_stack
    monkeypatch.delenv("ZTP_ADMIN_PASS", raising=False)
    with pytest.raises(RuntimeError) as ei:
        rt.default_context()
    assert "ZTP_ADMIN_PASS" in str(ei.value)


def test_runtime_render_default_context_uses_env_when_set(ztp_stack, monkeypatch):
    rt, _ = ztp_stack
    monkeypatch.setenv("ZTP_ADMIN_PASS", "EnvAdminPass!1")
    ctx = rt.default_context()
    assert ctx["admin_pass"] == "EnvAdminPass!1"


def test_runtime_render_load_override_fails_without_password_and_env(ztp_stack, monkeypatch, tmp_path):
    rt, _ = ztp_stack
    monkeypatch.delenv("ZTP_ADMIN_PASS", raising=False)
    override_path = tmp_path / "recovery_override.json"
    monkeypatch.setattr(rt, "OVERRIDE_PATH", override_path)
    override_path.write_text(json.dumps(
        {"host": "192.168.100.2", "username": "python", "password": None}), encoding="utf-8")
    with pytest.raises(RuntimeError) as ei:
        rt.load_override()
    assert "ZTP_ADMIN_PASS" in str(ei.value)


def test_onboard_callback_payload_fails_without_password_and_env(ztp_stack, monkeypatch, tmp_path):
    _, cb = ztp_stack
    monkeypatch.delenv("ZTP_ADMIN_PASS", raising=False)
    override_path = tmp_path / "recovery_override.json"
    monkeypatch.setattr(cb, "OVERRIDE_PATH", override_path)
    override_path.write_text(json.dumps(
        {"host": "192.168.100.2", "password": None}), encoding="utf-8")
    with pytest.raises(RuntimeError) as ei:
        cb.current_payload(830)
    assert "ZTP_ADMIN_PASS" in str(ei.value)


def test_onboard_callback_payload_uses_env_when_override_password_missing(ztp_stack, monkeypatch, tmp_path):
    _, cb = ztp_stack
    monkeypatch.setenv("ZTP_ADMIN_PASS", "EnvAdminPass!1")
    override_path = tmp_path / "recovery_override.json"
    monkeypatch.setattr(cb, "OVERRIDE_PATH", override_path)
    override_path.write_text(json.dumps(
        {"host": "192.168.100.2", "password": None}), encoding="utf-8")
    payload = cb.current_payload(830)
    assert payload["password"] == "EnvAdminPass!1"


# ── 3. ZTP onboard API 缺密码 → 422（无默认口令兜底） ──

def test_ztp_onboard_missing_password_is_rejected(client):
    resp = client.post("/api/ztp/onboard", json={
        "host": "192.0.2.201",
        "username": "python",
    })
    assert resp.status_code == 422  # password 必填，绝无代码内默认口令


# ── 4. recovery state 权限与脱敏（服务层） ──

def test_recovery_state_file_permissions(client, monkeypatch, tmp_path):
    monkeypatch.setattr("app.services.ztp_recovery.settings.ZTP_STATE_DIR", str(tmp_path))
    resp = client.post("/api/ztp/recovery-override", json={
        "host": "192.168.100.9",
        "username": "python",
        "password": "SyntheticTestPass!1",
    })
    assert resp.json()["success"] is True
    state_file = tmp_path / "recovery_override.json"
    assert stat.S_IMODE(state_file.stat().st_mode) == 0o600
    # API 响应脱敏（POST 与 GET 都不含 password 字段）
    assert "password" not in resp.json()["data"]["override"]
    got = client.get("/api/ztp/recovery-override").json()["data"]
    assert "password" not in got["override"]
