"""S1-024 / CR43 ZTP 渲染凭据边界加固对抗测试（不连真机、无设备 I/O）.

覆盖：
  1. 特殊字符密码（单引号/反斜杠/换行/$()/反引号/通配符）原样渲染、不执行注入
     —— ztp_runtime_render 模块级 + entrypoint.sh 全量运行级（stub dnsmasq）。
  2. runtime 首次渲染与覆盖重渲染后 autocfg.cfg 均保持 0600（修复重渲染变 0644 的回归）。
  3. 失败路径不残留宽权限或含口令的临时文件（安全原子写 cleanup）。
  4. entrypoint.sh 的 python3 -c 渲染块只从 os.environ 读取、无 shell 变量拼进源码。
"""
import os
import shutil
import re
import stat
import subprocess
import sys
import types
from pathlib import Path

import pytest

_REPO_ROOT = Path(os.getenv("S1_023_REPO_DIR", "")) if os.getenv("S1_023_REPO_DIR") else Path(__file__).resolve().parents[2]
if not (_REPO_ROOT / "backend").is_dir():
    _REPO_ROOT = Path("/opt/s1-repo")

ZTP_STACK = _REPO_ROOT / "docker" / "ztp-stack"
ENTRYPOINT = ZTP_STACK / "entrypoint.sh"

INJECTION_MARKER = "/tmp/ztp-injected-ok"

# 特殊字符密码：单引号、反斜杠、换行、$()、反引号、通配符、管道、中文字符
SPECIAL_PASS = "p'w\\d\nline2 $() `id` *?;|&<>中"


def _ensure_jinja2():
    """qa 容器无 jinja2：pip 安装（网络可用时）；失败则 skip。"""
    try:
        import jinja2  # noqa: F401
        return
    except ImportError:
        pass
    r = subprocess.run(["python3", "-m", "pip", "install", "-q", "--no-input", "jinja2"],
                       capture_output=True, text=True)
    if r.returncode != 0:
        pytest.skip(f"jinja2 不可用: {r.stderr[-300:]}")


@pytest.fixture()
def ztp_renderer(monkeypatch, tmp_path):
    """隔离的 ztp_runtime_render 模块：TFTP/STATE 全指向 tmp_path。"""
    if "jinja2" not in sys.modules:
        fake = types.ModuleType("jinja2")

        class _StubTemplate:
            def __init__(self, source):
                self._source = source

            def render(self, **ctx):
                out = self._source
                for k, v in ctx.items():
                    out = out.replace("{{ %s }}" % k, str(v))
                return out

        fake.Template = _StubTemplate
        sys.modules["jinja2"] = fake

    sys.path.insert(0, str(ZTP_STACK))
    try:
        import ztp_runtime_render as rt
    finally:
        sys.path.pop(0)

    tftp = tmp_path / "tftp"
    state = tmp_path / "state"
    tftp.mkdir()
    state.mkdir()
    (tftp / "autocfg.cfg.j2").write_text(
        "# tmpl\nsysname {{ sysname }}\nmgmt_ip {{ mgmt_ip }}\npassword simple {{ admin_pass }}\n",
        encoding="utf-8")
    monkeypatch.setattr(rt, "TEMPLATE_PATH", tftp / "autocfg.cfg.j2")
    monkeypatch.setattr(rt, "OUTPUT_PATH", tftp / "autocfg.cfg")
    monkeypatch.setattr(rt, "STATE_DIR", state)
    monkeypatch.setattr(rt, "OVERRIDE_PATH", state / "recovery_override.json")
    return rt, tftp


# ── 1. 特殊字符密码原样渲染、不执行注入 ──

def test_renderer_special_char_password_verbatim_no_injection(ztp_renderer, monkeypatch):
    rt, tftp = ztp_renderer
    monkeypatch.setenv("ZTP_ADMIN_PASS", SPECIAL_PASS)
    monkeypatch.setenv("ZTP_PLATFORM", "lstn")
    monkeypatch.setenv("ZTP_MGMT_IP", "192.168.100.101")
    Path(INJECTION_MARKER).unlink(missing_ok=True)

    assert rt.render_once() == "default"
    text = (tftp / "autocfg.cfg").read_text(encoding="utf-8")
    assert f"password simple {SPECIAL_PASS}" in text  # 原样渲染
    assert not Path(INJECTION_MARKER).exists()          # 未执行注入
    assert stat.S_IMODE((tftp / "autocfg.cfg").stat().st_mode) == 0o600


def test_entrypoint_full_run_special_char_password_verbatim_no_injection():
    """全量运行 entrypoint.sh（stub dnsmasq + 真实 jinja2）：env 注入无注入、0600、无中间文件。"""
    if os.geteuid() != 0:
        pytest.skip("需要 root 在容器内创建 /dnsmasq.conf.template 与 /var/tftp")
    _ensure_jinja2()

    Path("/dnsmasq.conf.template").write_text(
        "dhcp-range=${ZTP_DHCP_RANGE_START},${ZTP_DHCP_RANGE_END}\n", encoding="utf-8")
    Path("/var/tftp").mkdir(exist_ok=True)
    shutil.copy2(ZTP_STACK / "tftp" / "autocfg.cfg.j2", Path("/var/tftp") / "autocfg.cfg.j2")
    # dnsmasq stub（容器根文件系统；/tmp 为 tmpfs 且默认 noexec 不可放可执行文件）
    Path("/opt/ztp-bin").mkdir(exist_ok=True)
    stub = Path("/opt/ztp-bin/dnsmasq")
    stub.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    stub.chmod(0o755)
    # entrypoint 末尾会拉起 runtime renderer 后台任务：给一个无害 stub，避免噪音
    Path("/ztp_runtime_render.py").write_text("#!/usr/bin/env python3\n", encoding="utf-8")
    Path(INJECTION_MARKER).unlink(missing_ok=True)
    Path("/tmp/ztp-state").mkdir(exist_ok=True)

    env = dict(os.environ)
    env["PATH"] = "/opt/ztp-bin:" + env.get("PATH", "")
    env["ZTP_ADMIN_PASS"] = SPECIAL_PASS
    env["ZTP_ADMIN_USER"] = "python"
    env["ZTP_PLATFORM"] = "lstn"
    env["ZTP_HCL_T7064P15"] = "false"
    env["ZTP_MGMT_IP"] = "192.168.100.101"
    env["ZTP_STATE_DIR"] = "/tmp/ztp-state"
    env["ZTP_ONBOARD_ENABLED"] = "false"

    r = subprocess.run(["sh", str(ENTRYPOINT)], env=env, capture_output=True, text=True, timeout=90)
    assert r.returncode == 0, f"entrypoint 失败: {r.stderr[-500:]}"

    out = Path("/var/tftp/autocfg.cfg")
    assert out.exists()
    text = out.read_text(encoding="utf-8")
    assert f"password simple {SPECIAL_PASS}" in text  # 特殊字符原样
    assert not Path(INJECTION_MARKER).exists()          # 未执行注入
    assert stat.S_IMODE(out.stat().st_mode) == 0o600    # 最终 0600
    # 无含口令中间文件残留（mktemp 前缀 autocfg.cfg.XXXXXX；模板 .j2 与最终输出 autocfg.cfg 除外）
    leftovers = [p for p in Path("/var/tftp").iterdir()
                 if p.name.startswith("autocfg.cfg.") and not p.name.endswith(".j2")]
    assert leftovers == [], f"残留中间文件: {leftovers}"


# ── 2. runtime 首次与覆盖重渲染均保持 0600 ──

def test_renderer_first_and_rerender_keep_0600(ztp_renderer, monkeypatch):
    rt, tftp = ztp_renderer
    monkeypatch.setenv("ZTP_ADMIN_PASS", "SyntheticTestPass!1")
    monkeypatch.setenv("ZTP_MGMT_IP", "192.168.100.101")
    out = tftp / "autocfg.cfg"

    rt.render_once()  # 首次
    assert stat.S_IMODE(out.stat().st_mode) == 0o600

    monkeypatch.setenv("ZTP_MGMT_IP", "192.168.100.102")  # 覆盖重渲染（内容变化）
    rt.render_once()
    assert stat.S_IMODE(out.stat().st_mode) == 0o600, "重渲染后权限被放宽（回归：旧实现变 0644）"
    assert "192.168.100.102" in out.read_text(encoding="utf-8")


# ── 3. 失败路径不残留宽权限/含口令临时文件 ──

def test_renderer_failure_leaves_no_wide_secret_temp(ztp_renderer, monkeypatch):
    rt, tftp = ztp_renderer
    monkeypatch.setenv("ZTP_ADMIN_PASS", "SyntheticTestPass!1")
    # 让 os.replace 失败：OUTPUT_PATH 位置已是目录
    outdir = tftp / "autocfg.cfg"
    outdir.mkdir()

    with pytest.raises(OSError):
        rt.render_once()

    # 安全原子写清理：无 .tmp 残留
    assert list(tftp.glob(".autocfg.cfg.tmp.*")) == []
    # 无任何含口令的中间文件落盘
    for p in tftp.iterdir():
        assert p.is_dir() or p.name == "autocfg.cfg.j2", f"意外落盘文件: {p}"


def test_renderer_missing_env_fails_before_any_write(ztp_renderer, monkeypatch):
    rt, tftp = ztp_renderer
    monkeypatch.delenv("ZTP_ADMIN_PASS", raising=False)
    with pytest.raises(RuntimeError):
        rt.render_once()
    assert not (tftp / "autocfg.cfg").exists()
    assert list(tftp.glob(".autocfg.cfg.tmp.*")) == []


# ── 4. entrypoint.sh 渲染块只从 os.environ 读取 ──

def test_entrypoint_render_snippet_is_env_only_no_shell_interpolation():
    src = ENTRYPOINT.read_text(encoding="utf-8")
    m = re.search(r"python3 -c '(.*?)'\s*>", src, re.S)
    assert m, "未找到 python3 -c 渲染块"
    block = m.group(1)
    assert "$" not in block, "渲染块内含 shell 变量拼入源码（注入风险）"
    assert 'admin_pass=os.environ["ZTP_ADMIN_PASS"]' in block
    assert 'admin_user=os.environ["ZTP_ADMIN_USER"]' in block
    assert 'platform=os.environ["ZTP_PLATFORM"]' in block
    # 安全临时文件 + 原子替换 + 显式 0600 + trap 清理
    assert "mktemp" in src
    assert 'chmod 600 "$AUTOCFG_TMP"' in src
    assert 'mv -f "$AUTOCFG_TMP" "$AUTOCFG_OUT"' in src
    assert "trap 'rm -f \"$AUTOCFG_TMP\"' EXIT" in src
