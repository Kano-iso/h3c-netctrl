#!/usr/bin/env bash
# stub_ops.sh — 模拟 ops-toolkit paramiko-batch-exec.sh（不触真机、不读真实凭据）。
#
# 供 S1-021 runner 对抗测试注入（RUNNER_OPS_CMD）。argv 契约与真实入口一致：
#   --device <d> --commands <c...> --output-format text
#
# 行为由环境变量控制（测试注入）：
#   STUB_OPS_LOG          调用日志文件（每行: CALL <argv...>），供断言
#   STUB_OPS_COUNTER_FILE 只读调用计数器文件（区分基线 readback 与最终 readback）
#   STUB_OPS_READ_SEQ     逗号分隔的只读场景序列（第 N 次只读调用取第 N 个，超出取末位）
#                           clean_baseline | dirty_baseline_shared | dirty_baseline_vsi
#                           | dirty_baseline_ac | residue_after | readback_fail
#   STUB_OPS_WRITE_RC     写（undo 兜底清理）调用返回码（默认 0）
set -uo pipefail

LOG="${STUB_OPS_LOG:-/tmp/stub_ops.log}"
COUNTER="${STUB_OPS_COUNTER_FILE:-/tmp/stub_ops.count}"
SEQUENCE="${STUB_OPS_READ_SEQ:-clean_baseline}"
WRITE_RC="${STUB_OPS_WRITE_RC:-0}"

# 记录完整 argv（含命令，逐参数一行，避免含空格命令被截断），供断言
{
    printf 'CALL\n'
    for a in "$@"; do
        printf 'ARG <%s>\n' "$a"
    done
} >> "$LOG"

# ── 写调用（兜底清理：两条精确 undo + 上下文）──
if printf '%s' "$*" | grep -q 'undo ip vpn-instance sdn_l3vpn'; then
    if [ "$WRITE_RC" != "0" ]; then
        echo "stub write failure (rc=${WRITE_RC})" >&2
        exit "$WRITE_RC"
    fi
    printf '[1/4] system-view (500ms, rc=0, ok)\nsystem-view\n<SWC>\n'
    printf '[2/4] undo ip vpn-instance sdn_l3vpn (500ms, rc=0, ok)\nundo ip vpn-instance sdn_l3vpn\n<SWC>\n'
    printf '[3/4] undo vxlan tunnel mac-learning disable (500ms, rc=0, ok)\nundo vxlan tunnel mac-learning disable\n<SWC>\n'
    printf '[4/4] return (500ms, rc=0, ok)\nreturn\n<SWC>\n'
    exit 0
fi

# ── 只读调用：按计数器取场景 ──
n=0
if [ -f "$COUNTER" ]; then
    n=$(cat "$COUNTER" 2>/dev/null || echo 0)
fi
n=$((n + 1))
printf '%s\n' "$n" > "$COUNTER"
IFS=',' read -r -a SCENES <<< "$SEQUENCE"
if [ "$n" -le "${#SCENES[@]}" ]; then
    SCEN="${SCENES[$((n - 1))]}"
else
    SCEN="${SCENES[${#SCENES[@]} - 1]}"
fi

emit() { # $1 = 场景
    local s="$1"
    echo '[1/7] display bgp peer l2vpn evpn (500ms, rc=0, ok)'
    echo 'display bgp peer l2vpn evpn'
    echo ' Local Router ID: 1.1.1.4'
    echo ' Peer 192.168.100.1: State: Established'
    echo '<SWC>'
    echo '[2/7] display version (500ms, rc=0, ok)'
    echo 'display version'
    echo 'H3C Comware Software, Version 7.1.075, Ess 6850'
    echo 'S6850'
    echo '<SWC>'
    echo '[3/7] display l2vpn vsi (500ms, rc=0, ok)'
    echo 'display l2vpn vsi'
    case "$s" in dirty_baseline_vsi) echo 'VSI Name: vpc0001' ;; esac
    echo '<SWC>'
    echo '[4/7] display bgp l2vpn evpn (500ms, rc=0, ok)'
    echo 'display bgp l2vpn evpn'
    echo ''
    echo ' Total number of routes: 0'
    echo '<SWC>'
    echo '[5/7] display current-configuration | include sdn_l3vpn (500ms, rc=0, ok)'
    echo 'display current-configuration | include sdn_l3vpn'
    case "$s" in dirty_baseline_shared|residue_after) echo 'ip vpn-instance sdn_l3vpn' ;; esac
    echo '<SWC>'
    echo '[6/7] display current-configuration | include vxlan (500ms, rc=0, ok)'
    echo 'display current-configuration | include vxlan'
    case "$s" in dirty_baseline_shared|residue_after) echo ' vxlan tunnel mac-learning disable' ;; esac
    echo '<SWC>'
    echo '[7/7] display current-configuration interface GigabitEthernet1/0/10 (500ms, rc=0, ok)'
    echo 'display current-configuration interface GigabitEthernet1/0/10'
    echo '#'
    echo 'interface GigabitEthernet1/0/10'
    echo ' port link-mode bridge'
    echo ' combo enable fiber'
    case "$s" in dirty_baseline_ac) echo ' service-instance 3200' ;; esac
    echo '#'
    echo 'return'
    echo '<SWC>'
}

case "$SCEN" in
    clean_baseline|dirty_baseline_shared|dirty_baseline_vsi|dirty_baseline_ac|residue_after)
        emit "$SCEN"
        exit 0
        ;;
    readback_fail)
        echo 'stub read failure' >&2
        exit 1
        ;;
    *)
        echo "stub unknown scenario: $SCEN" >&2
        exit 2
        ;;
esac
