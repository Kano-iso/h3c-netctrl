#!/usr/bin/env bash
# S1-022: 唯一、可复用的宿主机安全 Runner —— 包装 S1-019/S1-020 真机生命周期 pytest。
#
# 职责：
#   1) 默认拒绝真机；四重门禁全部满足才继续（否则在任何设备 I/O 前退出）：
#        --integration 参数、S1_019_REAL=1、S1_019_REAL_HOST 精确 = 192.168.100.5、
#        --cleanup-shared 显式共享清理确认门。
#   2) 任何设备 I/O 前可靠创建并验证审计目录可写（umask 077 + 临时探针文件后删除）；
#      失败直接退出，不采集基线、不跑 pytest。
#   3) pytest 前保存最小基线（设备身份 / VSI / EVPN / sdn_l3vpn / vxlan global / GE1/0/10）；
#      baseline 必须成功持久化后才进入可写阶段（写失败在 pytest 前终止）；
#      共享对象（sdn_l3vpn / vxlan tunnel mac-learning disable）基线已存在 → 拒绝承担其所有权，
#      绝不在 trap 中删除既有配置。
#   4) 进入可写阶段后安装 shell trap：无论 pytest 成功/失败/Ctrl-C/TERM，只要基线证明共享对象
#      原先不存在，就按恢复清单精确兜底清理；禁止 save / startup-config / .6 / 管理口 / GE1/0/1~3 /
#      underlay / OSPF / BGP 邻居。
#   5) cleanup / final readback 均「先真实执行并捕获返回码/输出，再尽力写审计文件」：审计目录
#      在 pytest 期间被删除/变只读/写失败，不得阻止清理命令或回读执行；审计写入失败本身让
#      runner 最终非零并明确 MANUAL-NEEDED，但不替代 cleanup/readback；cleanup 失败不跳过
#      final readback。
#   6) cleanup 之后始终最终 readback 确认 VSI/测试 VPC、测试 AC、共享对象回到基线；
#      命令返回码 0 不等于清理成功（以 readback 证据为准）。
#   7) 保留 pytest 原始退出码；但 cleanup / final readback / 审计写入失败时整体失败并指示人工处理。
#   8) 本机 flock 锁，避免两个 runner 并发操作 .5。
#
# 凭据：只从既有 .env / 环境注入（生产走 docker --env-file），不打印、不复制到文件。
# 额外设备读写：全部走 ops-toolkit 既有入口（paramiko-batch-exec.sh），不新增裸 SSH/paramiko；
# 业务生命周期仍由 backend API/executor 执行（测试内部）。
#
# 用法：
#   S1_019_REAL=1 S1_019_REAL_HOST=192.168.100.5 \
#   ./run_s1_019_real_lifecycle.sh --integration --cleanup-shared
#
# 测试注入点（对抗测试用 stub 覆盖，生产用默认 docker 命令）：
#   RUNNER_OPS_CMD        ops-toolkit 可执行（argv: --device <d> --commands <c...> --output-format text）
#   RUNNER_PYTEST_CMD     真机 pytest 可执行（无参）
#   RUNNER_ENV_FILE       .env 路径（默认 /root/workpace/h3c-netctrl/.env）
#   RUNNER_NETWORK        docker 网络（默认 h3c-netctrl_h3c-net）
#   RUNNER_OPS_IMAGE      ops-toolkit 镜像（默认 h3c-netctrl-ops-toolkit:latest）
#   RUNNER_QA_IMAGE       QA 镜像（默认 next-s1-qa-backend:local）
#   RUNNER_BACKEND_DIR    backend 目录（默认 worktree backend）
#   RUNNER_LOCK_FILE      锁文件（默认 /tmp/s1-019-runner-192.168.100.5.lock）
#   RUNNER_ARTIFACT_DIR   基线/readback 审计目录（默认 /tmp/s1-019-runner/artifacts）
set -uo pipefail
umask 077

TARGET="${S1_019_REAL_HOST:-}"
REAL="${S1_019_REAL:-0}"
INTEGRATION=0
CLEANUP_SHARED=0

ENV_FILE="${RUNNER_ENV_FILE:-/root/workpace/h3c-netctrl/.env}"
NETWORK="${RUNNER_NETWORK:-h3c-netctrl_h3c-net}"
OPS_IMAGE="${RUNNER_OPS_IMAGE:-h3c-netctrl-ops-toolkit:latest}"
QA_IMAGE="${RUNNER_QA_IMAGE:-next-s1-qa-backend:local}"
BACKEND_DIR="${RUNNER_BACKEND_DIR:-/root/workpace/h3c-netctrl/.agent-worktrees/next-s1-backend/backend}"
TEST_FILE="tests/test_s1_019_reallife.py"
LOCK_FILE="${RUNNER_LOCK_FILE:-/tmp/s1-019-runner-192.168.100.5.lock}"
ARTIFACT_DIR="${RUNNER_ARTIFACT_DIR:-/tmp/s1-019-runner/artifacts}"

# ── 可写阶段 / 基线共享对象证明（供 EXIT trap 判定是否授权兜底清理）──
WRITE_PHASE=0
BASELINE_SHARED_ABSENT=0
CLEANUP_RAN=0

usage() {
    cat <<'EOF'
用法:
  S1_019_REAL=1 S1_019_REAL_HOST=192.168.100.5 \
  ./run_s1_019_real_lifecycle.sh --integration --cleanup-shared

门禁（全部满足才继续，否则在任何设备 I/O 前退出）:
  --integration        显式确认是真机集成运行
  S1_019_REAL=1        显式真机开关
  S1_019_REAL_HOST     必须精确等于 192.168.100.5（.5，仅此一台）
  --cleanup-shared     显式确认允许按恢复清单对共享对象做精确兜底清理

安全:
  - 凭据只从 .env / 环境注入，不打印、不落盘
  - 额外设备读写走 ops-toolkit（paramiko-batch-exec.sh），不新增裸 SSH/paramiko
  - 禁 save / startup-config / .6 / 管理口 / GE1/0/1~3 / underlay / OSPF / BGP 邻居
  - 基线已有共享对象 → 拒绝承担其所有权，绝不删除既有配置
  - 进入可写阶段装 trap：成功/失败/Ctrl-C/TERM 都按恢复清单精确兜底清理 + 最终 readback
  - 本机 flock 锁，避免并发操作 .5
EOF
}

# ── 命令注入点（对抗测试用 stub 覆盖）──
run_ops() {  # $@ = commands
    if [ -n "${RUNNER_OPS_CMD:-}" ]; then
        "$RUNNER_OPS_CMD" --device "$TARGET" --commands "$@" --output-format text
    else
        docker run --rm --env-file "$ENV_FILE" --network "$NETWORK" \
            "$OPS_IMAGE" paramiko-batch-exec.sh --device "$TARGET" \
            --commands "$@" --output-format text
    fi
}

run_pytest() {
    if [ -n "${RUNNER_PYTEST_CMD:-}" ]; then
        "$RUNNER_PYTEST_CMD"
    else
        docker run --rm --env-file "$ENV_FILE" --network "$NETWORK" \
            -e S1_019_REAL=1 -e S1_019_REAL_HOST="$TARGET" \
            -v "$BACKEND_DIR:/app" \
            "$QA_IMAGE" python -m pytest "$TEST_FILE" -m integration --integration -v -s
    fi
}

# ── 命令集（恢复清单契约）──
BASELINE_COMMANDS=(
    "display bgp peer l2vpn evpn"
    "display version"
    "display l2vpn vsi"
    "display bgp l2vpn evpn"
    "display current-configuration | include sdn_l3vpn"
    "display current-configuration | include vxlan"
    "display current-configuration interface GigabitEthernet1/0/10"
)
# 兜底清理只含两条精确共享 undo + 必要上下文（无 save / 无越界命令）
CLEANUP_COMMANDS=(
    "system-view"
    "undo ip vpn-instance sdn_l3vpn"
    "undo vxlan tunnel mac-learning disable"
    "return"
)

# ── 解析参数 ──
while [ $# -gt 0 ]; do
    case "$1" in
        --integration) INTEGRATION=1 ;;
        --cleanup-shared) CLEANUP_SHARED=1 ;;
        -h|--help) usage; exit 0 ;;
        *) echo "run_s1_019_real_lifecycle.sh: 未知参数: $1" >&2; usage >&2; exit 3 ;;
    esac
    shift
done

# ── 门禁（任何设备 I/O 之前）──
if [ "$INTEGRATION" != "1" ]; then
    echo "GATE-FAIL: 缺少 --integration（拒绝真机）" >&2
    exit 3
fi
if [ "$REAL" != "1" ]; then
    echo "GATE-FAIL: S1_019_REAL != 1（拒绝真机）" >&2
    exit 3
fi
if [ "$TARGET" != "192.168.100.5" ]; then
    echo "GATE-FAIL: S1_019_REAL_HOST 必须精确等于 192.168.100.5（当前 '$TARGET'）——在任何设备 I/O 前退出" >&2
    exit 3
fi
if [ "$CLEANUP_SHARED" != "1" ]; then
    echo "GATE-FAIL: 缺少 --cleanup-shared（未显式确认共享兜底清理）" >&2
    exit 3
fi

# ── 审计目录（任何设备 I/O 前：可靠创建 + 验证可写；失败直接退出）──
setup_artifact_dir() {
    if ! mkdir -p "$ARTIFACT_DIR" 2>/dev/null; then
        echo "ARTIFACT-FAIL: 审计目录不可创建：$ARTIFACT_DIR（在任何设备 I/O 前退出）" >&2
        return 1
    fi
    local probe="$ARTIFACT_DIR/.probe.$$"
    if ! : > "$probe" 2>/dev/null; then
        echo "ARTIFACT-FAIL: 审计目录不可写：$ARTIFACT_DIR（在任何设备 I/O 前退出）" >&2
        return 1
    fi
    rm -f "$probe" 2>/dev/null
    return 0
}
setup_artifact_dir || exit 6

# ── 本机锁（防并发操作 .5）──
exec 9>"$LOCK_FILE"
if ! flock -n 9; then
    echo "LOCK-FAIL: 另一个 runner 正在操作 .5（$LOCK_FILE）" >&2
    exit 2
fi

# ── 基线核对（只读）──
BASELINE_TEXT="$(run_ops "${BASELINE_COMMANDS[@]}")" || {
    echo "MANUAL-NEEDED: 基线采集失败（设备不可达？）——未做任何写入" >&2
    exit 4
}
if ! printf '%s\n' "$BASELINE_TEXT" > "$ARTIFACT_DIR/baseline.txt" 2>/dev/null; then
    echo "MANUAL-NEEDED: 基线持久化失败（$ARTIFACT_DIR/baseline.txt）——在 pytest/可写阶段前终止" >&2
    exit 4
fi

verify_identity() {
    local text="$1"
    case "$text" in
        *"1.1.1.4"*) : ;;
        *) echo "BASELINE-FAIL: 设备身份不符（缺 Router ID 1.1.1.4）" >&2; return 1 ;;
    esac
    case "$text" in
        *"S6850"*) : ;;
        *) echo "BASELINE-FAIL: 设备身份不符（缺 S6850）" >&2; return 1 ;;
    esac
    return 0
}

verify_clean_state() {  # VSI/EVPN/共享/GE1/0/10 是否回到基线
    local text="$1" reason=""
    case "$text" in
        *"VSI Name:"*) reason="VSI 残留" ;;
    esac
    case "$text" in
        *"Total number of routes: 0"*) : ;;
        *) reason="$reason; EVPN routes != 0" ;;
    esac
    case "$text" in
        *"ip vpn-instance sdn_l3vpn"*) reason="$reason; sdn_l3vpn 残留" ;;
    esac
    case "$text" in
        *"vxlan tunnel mac-learning disable"*) reason="$reason; vxlan global 残留" ;;
    esac
    case "$text" in
        *"service-instance"*) reason="$reason; service-instance/AC 残留" ;;
    esac
    case "$text" in
        *"port link-mode bridge"*) : ;;
        *) reason="$reason; GE1/0/10 非 bridge" ;;
    esac
    case "$text" in
        *"combo enable fiber"*) : ;;
        *) reason="$reason; GE1/0/10 combo 非 fiber" ;;
    esac
    if [ -n "$reason" ]; then
        echo "BASELINE-FAIL: 未回到基线：$reason" >&2
        return 1
    fi
    return 0
}

verify_identity "$BASELINE_TEXT" || exit 4
# 共享对象基线已存在 → 拒绝承担所有权（绝不删除既有配置）
if printf '%s' "$BASELINE_TEXT" | grep -q 'ip vpn-instance sdn_l3vpn'; then
    echo "BASELINE-REFUSE: 基线已存在 sdn_l3vpn —— 拒绝承担其所有权，不发出任何 undo" >&2
    exit 5
fi
if printf '%s' "$BASELINE_TEXT" | grep -q 'vxlan tunnel mac-learning disable'; then
    echo "BASELINE-REFUSE: 基线已存在 vxlan tunnel mac-learning disable —— 拒绝承担其所有权，不发出任何 undo" >&2
    exit 5
fi
if ! verify_clean_state "$BASELINE_TEXT"; then
    echo "BASELINE-FAIL: 基线不干净，先人工核对 .5 再跑" >&2
    exit 4
fi
BASELINE_SHARED_ABSENT=1
echo "BASELINE-OK: .5 基线干净（身份 1.1.1.4/S6850、VSI 空、routes 0、无 sdn_l3vpn、无 vxlan global、GE1/0/10 原始）"

# ── 清理 + 最终 readback（EXIT trap 统一收尾；INT/TERM 先转 130 再走同一路径）──
# S1-022：cleanup / readback 一律「先真实执行并捕获返回码/输出，再尽力写审计文件」；
# 审计目录在 pytest 期间被删除/变只读/写失败不得阻止设备命令执行；审计写失败只提升退出码。
AUDIT_FAIL=0
write_audit() {  # $1=文件名 $2=内容（尽力写；失败置 AUDIT_FAIL=1 并提示人工）
    if ! printf '%s\n' "$2" > "$ARTIFACT_DIR/$1" 2>/dev/null; then
        echo "MANUAL-NEEDED: 审计文件写入失败（$ARTIFACT_DIR/$1）——设备清理/回读结果无法落盘" >&2
        AUDIT_FAIL=1
    fi
}

do_exit_handler() {
    local base=$?
    [ "$CLEANUP_RAN" = "1" ] && exit "$base"
    CLEANUP_RAN=1
    if [ "$WRITE_PHASE" = "1" ] && [ "$BASELINE_SHARED_ABSENT" = "1" ]; then
        # 先真实执行 cleanup（不经由审计文件重定向），捕获返回码/输出
        CLEANUP_OUT="$(run_ops "${CLEANUP_COMMANDS[@]}" 2>&1)"
        cleanup_rc=$?
        write_audit "cleanup.txt" "$CLEANUP_OUT"
        if [ "$cleanup_rc" -eq 0 ]; then
            echo "CLEANUP: 共享对象精确兜底清理已发出（system-view/undo sdn_l3vpn/undo vxlan/return）"
        else
            echo "MANUAL-NEEDED: 共享兜底清理执行失败（rc=$cleanup_rc，.5 可能有残留，请人工核对）" >&2
            [ "$base" -eq 0 ] && base=6
        fi
    fi
    if [ "$WRITE_PHASE" = "1" ]; then
        # 先真实执行 final readback（cleanup 失败也不跳过），捕获返回码/输出
        READBACK_TEXT="$(run_ops "${BASELINE_COMMANDS[@]}" 2>&1)"
        readback_rc=$?
        write_audit "final-readback.txt" "$READBACK_TEXT"
        if [ "$readback_rc" -ne 0 ]; then
            echo "MANUAL-NEEDED: 最终 readback 执行失败（rc=$readback_rc，.5 不可达？）——需人工核对" >&2
            [ "$base" -eq 0 ] && base=6
        elif verify_clean_state "$READBACK_TEXT"; then
            echo "FINAL-READBACK-OK: .5 已回到基线（VSI 空/routes 0/无 sdn_l3vpn/无 vxlan global/无 AC/GE1/0/10 原始）"
        else
            echo "MANUAL-NEEDED: 最终 readback 显示残留——需人工核对 .5（命令返回码 0 不代表清理成功）" >&2
            [ "$base" -eq 0 ] && base=6
        fi
    fi
    [ "$AUDIT_FAIL" = "1" ] && [ "$base" -eq 0 ] && base=6
    exit "$base"
}
trap do_exit_handler EXIT
trap 'exit 130' INT TERM

# ── 进入可写阶段：运行真机 pytest（业务生命周期走 backend API/executor）──
WRITE_PHASE=1
run_pytest
pytest_rc=$?
echo "PYTEST-EXIT: $pytest_rc"
exit "$pytest_rc"
