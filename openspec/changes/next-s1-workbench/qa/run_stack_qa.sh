#!/usr/bin/env bash
# S1-027 真实应用栈隔离联调 launcher（在 qa-stack 容器内执行）
#
# 流程：端口检查 → seed 合成数据 → 起真实 FastAPI（uvicorn，进程内边界 fake）→
#       起 vite dev（core 模式，代理到真实后端）→ Playwright 真实栈 spec →
#       断言 device-io.log（全部 fake、无真实设备 I/O）→ 清理。
# 成功 / 失败 / Ctrl-C / TERM 均走 trap 清理进程与 /tmp/stack-qa，不污染宿主。
set -euo pipefail

BACKEND_PORT="${STACK_QA_BACKEND_PORT:-18000}"
VITE_PORT=5173
FRONTEND_DIR="${STACK_QA_FRONTEND:-/opt/stack/app/frontend}"
BACKEND_DIR="${STACK_QA_BACKEND:-/opt/stack/app/backend}"
QA_DIR="${STACK_QA_DIR:-/tmp/stack-qa}"
LOG="$QA_DIR/launcher.log"
UVICORN_PID=""
VITE_PID=""

# seed / wrapper 需要 import 后端 app 包
export PYTHONPATH="${BACKEND_DIR}:${PYTHONPATH:-}"

# 合成 Fernet 键（不打印、非生产凭据）：seed 加密 + 接口读取解密需要合法 32B url-safe base64
export ENCRYPTION_KEY="$(python3 -c 'import base64,os;print(base64.urlsafe_b64encode(os.urandom(32)).decode())')"

mkdir -p "$QA_DIR"
: > "$LOG"

cleanup() {
  set +e
  [ -n "$VITE_PID" ] && kill "$VITE_PID" 2>/dev/null
  [ -n "$UVICORN_PID" ] && kill "$UVICORN_PID" 2>/dev/null
  sleep 1
  [ -n "$VITE_PID" ] && kill -9 "$VITE_PID" 2>/dev/null
  [ -n "$UVICORN_PID" ] && kill -9 "$UVICORN_PID" 2>/dev/null
  rm -rf "$QA_DIR"
}
trap cleanup EXIT INT TERM

port_free() {
  python3 - "$1" <<'EOF'
import socket, sys
port = int(sys.argv[1])
s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
try:
    s.bind(("127.0.0.1", port))
    s.close()
    sys.exit(0)
except OSError:
    sys.exit(1)
EOF
}

# 端口占用 → 明确失败（绝不误连 5174 演示环境）
if ! port_free "$BACKEND_PORT"; then
  echo "FATAL: stack backend port $BACKEND_PORT already in use" >&2
  exit 9
fi
if ! port_free "$VITE_PORT"; then
  echo "FATAL: stack vite port $VITE_PORT already in use (5174 演示环境不受影响)" >&2
  exit 9
fi

echo "[stack-qa] start real FastAPI backend on 127.0.0.1:${BACKEND_PORT} (boundary fakes injected)"
rm -f "$QA_DIR/device-io.log"
# cwd=backend：app.main 以相对路径加载 alembic.ini（与 qa-backend 容器 WORKDIR /app 同理）
(
  cd "$BACKEND_DIR"
  DB_PATH="$QA_DIR/db.sqlite" STACK_QA_DIR="$QA_DIR" STACK_QA_BACKEND_PORT="$BACKEND_PORT" \
    exec python3 /opt/stack/qa/stack/stack_backend_wrapper.py
) >>"$LOG" 2>&1 &
UVICORN_PID=$!
backend_ready=0
for _ in $(seq 1 60); do
  if curl -sf "http://127.0.0.1:${BACKEND_PORT}/health" >/dev/null 2>&1; then backend_ready=1; break; fi
  if ! kill -0 "$UVICORN_PID" 2>/dev/null; then
    echo "FATAL: uvicorn died during startup" >&2
    tail -30 "$LOG" >&2
    exit 4
  fi
  sleep 0.5
done
[ "$backend_ready" = 1 ] || { echo "FATAL: backend not ready" >&2; tail -30 "$LOG" >&2; exit 4; }
echo "[stack-qa] backend ready (alembic migrated empty DB)"

echo "[stack-qa] seed synthetic data (isolated sqlite, tables already migrated)"
if ! DB_PATH="$QA_DIR/db.sqlite" STACK_QA_DIR="$QA_DIR" python3 /opt/stack/qa/stack/stack_seed.py; then
  echo "FATAL: seed failed" >&2
  exit 3
fi

echo "[stack-qa] start vite dev (core mode -> real backend)"
(
  cd "$FRONTEND_DIR"
  VITE_API_MODE=core VITE_API_BACKEND_TARGET="http://127.0.0.1:${BACKEND_PORT}" \
    npm run dev -- --host 127.0.0.1 --port "$VITE_PORT"
) >>"$LOG" 2>&1 &
VITE_PID=$!
vite_ready=0
for _ in $(seq 1 90); do
  if curl -sf "http://127.0.0.1:${VITE_PORT}/" >/dev/null 2>&1; then vite_ready=1; break; fi
  if ! kill -0 "$VITE_PID" 2>/dev/null; then
    echo "FATAL: vite died during startup" >&2
    tail -30 "$LOG" >&2
    exit 5
  fi
  sleep 0.5
done
[ "$vite_ready" = 1 ] || { echo "FATAL: vite not ready" >&2; tail -30 "$LOG" >&2; exit 5; }
echo "[stack-qa] vite ready"

echo "[stack-qa] run real-stack playwright spec"
(
  cd "$FRONTEND_DIR"
  STACK_QA_DIR="$QA_DIR" npx playwright test --config=playwright.stack.config.js --reporter=line
) || {
  echo "FATAL: stack playwright failed" >&2
  echo "--- preview API diagnostic (real backend, synthetic payload) ---" >&2
  curl -s -X POST "http://127.0.0.1:${BACKEND_PORT}/api/sdn/vpcs/1/access-preview" \
    -H 'Content-Type: application/json' \
    -d '{"device_id":1,"if_index":10,"interface_name":"GigabitEthernet1/0/10","access_vlan":null,"service_instance":3200,"expected_host_ip":"10.1.0.2","mode":"l2"}' >&2 || echo "(preview diagnostic curl failed)" >&2
  echo "" >&2
  echo "--- device-io.log ---" >&2
  cat "$QA_DIR/device-io.log" 2>/dev/null >&2 || true
  echo "--- launcher.log (uvicorn/vite stderr, last 80) ---" >&2
  tail -80 "$LOG" 2>/dev/null >&2 || true
  exit 6
}

echo "[stack-qa] assert device-I/O boundary (all fakes, no real device I/O)"
python3 - "$QA_DIR" <<'EOF'
import json, os, sys
qa = sys.argv[1]
log = os.path.join(qa, "device-io.log")
if not os.path.exists(log):
    print("FATAL: device-io.log missing - no fake boundary recorded")
    sys.exit(7)
lines = [json.loads(l) for l in open(log, encoding="utf-8") if l.strip()]
kinds = [l["kind"] for l in lines]
required = {"executor_execute", "executor_success", "netconf_enter", "collector_sync"}
missing = required - set(kinds)
if missing:
    print(f"FATAL: fake boundary events missing: {sorted(missing)}")
    sys.exit(7)
for l in lines:
    if l["kind"] == "netconf_constructed":
        host = l.get("host", "")
        if not host.startswith("192.0.2."):
            print(f"FATAL: unexpected netconf target {host} (must be TEST-NET synthetic)")
            sys.exit(7)
print(f"BOUNDARY_OK events={len(lines)} kinds={sorted(set(kinds))}")
EOF

echo "STACK_QA_OK"
