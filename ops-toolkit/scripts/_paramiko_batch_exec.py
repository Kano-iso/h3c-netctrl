#!/usr/bin/env python3
# _paramiko_batch_exec.py — paramiko 批命令薄壳（v242-paramiko-tool）
#
# 设计：复用 backend SSHExecutor，不重复造轮子
#   - H3C V7 设备的 kex/host key 兼容：SSHExecutor._connect() 已处理
#   - H3C V7 设备的分页（---- More ----）：SSHExecutor._read_with_pagination() 已处理
#   - H3C V7 设备的 [Y/N] 二次确认：SSHExecutor.execute_commands() 已处理
#   - ops-toolkit 工具只负责：环境变量收参 → 调 SSHExecutor → 包装 JSON 输出
#
# 边界：单设备（明确不做 5 设备批量配置）
#
# 环境变量（由 bash 入口注入）：
#   _PMK_HOST          设备 IP（必填）
#   _PMK_PORT          SSH 端口（默认 22）
#   _PMK_USER          用户名（必填）
#   _PMK_PASS          密码（必填）
#   _PMK_COMMANDS_JSON 命令 JSON 数组（必填）
#   _PMK_TIMEOUT       单命令 timeout 秒（默认 30）
#   _PMK_OUTPUT_FORMAT text / json（默认 json）
#   _PMK_RETRIES       失败重试次数（默认 0，整体重试整 batch）
#   _PMK_CONTINUE_ON_ERROR true/false（默认 true）
import json
import os
import sys
import time

# 把 /opt 加到 path，import backend 单文件 ssh_executor.py
sys.path.insert(0, "/opt")
from ssh_executor import SSHExecutor  # noqa: E402


def run_commands(host, port, user, password, commands, timeout, retries, continue_on_error):
    """调 SSHExecutor 跑批命令，单连接复用，H3C 兼容由 SSHExecutor 内部处理

    Returns:
        dict: {host, total, success, failed, elapsed_ms, results: [{command, returncode, stdout, stderr, elapsed_ms, success}, ...]}
    """
    summary = {
        "host": host,
        "total": len(commands),
        "success": 0,
        "failed": 0,
        "elapsed_ms": 0,
        "results": [],
    }

    # 整体 retry：连接失败 / batch 中有命令失败时整 batch 重跑
    for attempt in range(retries + 1):
        start = time.time()
        client = SSHExecutor(host, port, user, password, timeout=timeout)
        try:
            # delay_ms=300：H3C 设备处理命令需要时间
            raw_results = client.execute_commands([c.strip() for c in commands if c.strip()], delay_ms=300)
        except Exception as e:
            elapsed_ms = int((time.time() - start) * 1000)
            summary["elapsed_ms"] = elapsed_ms
            if attempt < retries:
                time.sleep(5)
                continue
            # 最后一次也失败 → 把整 batch 标为失败
            for cmd in commands:
                summary["results"].append({
                    "command": cmd.strip(),
                    "returncode": 1,
                    "stdout": "",
                    "stderr": f"SSH 连接/执行失败: {e}",
                    "elapsed_ms": elapsed_ms,
                    "success": False,
                })
            summary["failed"] = len(commands)
            return summary

        # 把 SSHExecutor 返回的 [{cmd, output, success, error, execution_time}, ...]
        # 转换成 ops-toolkit 工具的 JSON 格式
        elapsed_ms = int((time.time() - start) * 1000)
        results = []
        for raw in raw_results:
            results.append({
                "command": raw["cmd"],
                "returncode": 0 if raw["success"] else 1,
                "stdout": raw["output"],
                "stderr": raw.get("error") or "",
                "elapsed_ms": int(raw.get("execution_time", 0) * 1000),
                "success": raw["success"],
            })

        # 整体 retry 判定：所有命令都成功 → 跳出
        if all(r["success"] for r in results):
            summary["results"] = results
            summary["elapsed_ms"] = elapsed_ms
            break

        # 有失败但还有 retry 机会
        if attempt < retries:
            time.sleep(5)
            continue

        # 最后一次：保留结果
        summary["results"] = results
        summary["elapsed_ms"] = elapsed_ms
        break

    # 统计：success/failed 都从 results 数（filtered 后的命令数），total 保持原始命令数
    # 一致性约束：success + failed == len(results) <= total
    summary["success"] = sum(1 for r in summary["results"] if r["success"])
    summary["failed"] = sum(1 for r in summary["results"] if not r["success"])
    return summary


def main():
    host = os.environ.get("_PMK_HOST", "").strip()
    port = int(os.environ.get("_PMK_PORT", "22"))
    user = os.environ.get("_PMK_USER", "").strip()
    password = os.environ.get("_PMK_PASS", "")
    commands_json = os.environ.get("_PMK_COMMANDS_JSON", "[]")
    timeout = int(os.environ.get("_PMK_TIMEOUT", "30"))
    output_format = os.environ.get("_PMK_OUTPUT_FORMAT", "json")
    retries = int(os.environ.get("_PMK_RETRIES", "0"))
    continue_on_error = os.environ.get("_PMK_CONTINUE_ON_ERROR", "true").lower() == "true"

    if not host or not user or not password:
        print("❌ 缺少 _PMK_HOST / _PMK_USER / _PMK_PASS 环境变量", file=sys.stderr)
        sys.exit(2)
    try:
        commands = json.loads(commands_json)
    except json.JSONDecodeError as e:
        print(f"❌ _PMK_COMMANDS_JSON 解析失败: {e}", file=sys.stderr)
        sys.exit(2)
    if not commands:
        print("❌ _PMK_COMMANDS_JSON 为空（至少 1 条命令）", file=sys.stderr)
        sys.exit(2)

    summary = run_commands(host, port, user, password, commands, timeout, retries, continue_on_error)

    if output_format == "json":
        print(json.dumps(summary, ensure_ascii=False, indent=2))
    else:
        for idx, r in enumerate(summary["results"], start=1):
            status = "✓" if r["success"] else "✗"
            print(f"[{idx}/{summary['total']}] {r['command']} ({r['elapsed_ms']}ms, rc={r['returncode']}, {status})")
            if r["stdout"]:
                print(r["stdout"], end="" if r["stdout"].endswith("\n") else "\n")
            if r["stderr"]:
                print(f"STDERR: {r['stderr']}", file=sys.stderr)
        if summary["failed"] == 0:
            print(f"✅ {summary['success']}/{summary['total']} 成功 (总耗时 {summary['elapsed_ms']}ms)")
        else:
            print(f"❌ {summary['success']}/{summary['total']} 成功, {summary['failed']} 失败 (总耗时 {summary['elapsed_ms']}ms)")

    # 文档发现原则：跑完命令末尾输出文档链接（stderr，不污染 JSON）
    # 与 _lib.sh:_print_doc_links 保持一致（其他 6 个脚本走 stdout，因为不返 JSON）
    script_name = os.environ.get("_PMK_SCRIPT_NAME", "paramiko-batch-exec")
    docs_prefix = os.environ.get("OPS_DOCS_PREFIX", "/opt/docs")
    print("", file=sys.stderr)
    print("── 文档 ─────────────────────────────────", file=sys.stderr)
    print(f"📖 用法:        {docs_prefix}/ops-toolkit.md#{script_name}", file=sys.stderr)
    print(f"📖 凭据来源:    {docs_prefix}/ops-toolkit.md#凭据来源", file=sys.stderr)
    print("─────────────────────────────────────────", file=sys.stderr)

    sys.exit(0 if summary["failed"] == 0 else 1)


if __name__ == "__main__":
    main()
