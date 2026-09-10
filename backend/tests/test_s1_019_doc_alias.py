"""S1-019 文档/工具别名一致性最小测试（无真机 I/O）。

对齐目标（docs/ops-toolkit.md §设备命名约定 ↔ ops-toolkit/scripts/_lib.sh `_resolve_alias`）：
- `leaf-04` 别名 → 192.168.100.5（真机 SWC）
- 不实现 `leaf-05` 别名（192.168.100.6 实为 SWD/Spine，非 Leaf-05，禁止误映射）
- `test` / `spine-01` 别名仍按表解析
"""
import os
import subprocess

import pytest

_LIB_SH_CANDIDATES = [
    os.environ.get("OPS_TOOLKIT_SCRIPTS", ""),
    "/opt/ops-toolkit-scripts/_lib.sh",
    os.path.join(os.path.dirname(__file__), "..", "..", "ops-toolkit", "scripts", "_lib.sh"),
]


def _lib_sh() -> str:
    for cand in _LIB_SH_CANDIDATES:
        if cand and os.path.isfile(cand):
            return cand
    pytest.skip("_lib.sh 不在可访问路径（OPS_TOOLKIT_SCRIPTS / /opt/ops-toolkit-scripts / repo）")


def _resolve_alias(alias: str) -> str:
    script = (
        "set +euo pipefail; source \"$1\" >/dev/null 2>&1; "
        "_resolve_alias \"$2\""
    )
    out = subprocess.run(
        ["bash", "-c", script, "_lib_sh", _lib_sh(), alias],
        capture_output=True, text=True, timeout=10,
    )
    return out.stdout.strip()


def test_alias_leaf04_maps_to_dot5():
    assert _resolve_alias("leaf-04") == "192.168.100.5"
    assert _resolve_alias("leaf04") == "192.168.100.5"


def test_alias_leaf05_is_not_implemented():
    # 无 leaf-05 别名 → 透传原串，绝不得解析成 .5 或 .6（.6 是 Spine）
    resolved = _resolve_alias("leaf-05")
    assert resolved not in ("192.168.100.5", "192.168.100.6"), resolved
    assert resolved == "leaf-05"


def test_alias_test_and_spine01_still_resolve():
    assert _resolve_alias("test") == "192.168.100.177"
    assert _resolve_alias("spine-01") == "192.168.100.100"
