#!/usr/bin/env bash
# stub_pytest.sh — 模拟 S1-019 真机 pytest（不触真机、不读凭据）。
#
# 供 S1-021/S1-022 runner 对抗测试注入（RUNNER_PYTEST_CMD）。
#   STUB_PYTEST_LOG      调用日志文件（每行: CALL <argv...>），供断言
#   STUB_PYTEST_RC       pytest 返回码（默认 0）
#   STUB_PYTEST_SLEEP    =1 时 exec sleep（模拟长跑 pytest，供中断/并发锁测试）
#   STUB_PYTEST_SLEEP_SECS   sleep 秒数（默认 300）
#   STUB_PYTEST_HOOK     pytest 执行前运行的 shell 命令（S1-022：模拟 pytest 期间
#                        删除/破坏审计目录；经 bash -c 执行，值由测试注入）
set -uo pipefail

if [ -n "${STUB_PYTEST_LOG:-}" ]; then
    printf 'CALL %s\n' "$*" >> "$STUB_PYTEST_LOG"
fi

if [ -n "${STUB_PYTEST_HOOK:-}" ]; then
    bash -c "$STUB_PYTEST_HOOK" || true
fi

if [ "${STUB_PYTEST_SLEEP:-0}" = "1" ]; then
    exec sleep "${STUB_PYTEST_SLEEP_SECS:-300}"
fi
exit "${STUB_PYTEST_RC:-0}"
