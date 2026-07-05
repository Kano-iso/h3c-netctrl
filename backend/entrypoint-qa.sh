#!/bin/sh
# entrypoint-qa.sh — qa 容器入口脚本（sh 兼容，alpine + debian 都跑）
# 输出 QA-GUIDE 文档链接 banner + 自动 npm install 同步依赖，然后 exec 测试命令
# Part of v24-toolkit-ux-and-doc-discovery (v2.4 roadmap)
# v2.6：自动 npm install — 宿主机改了 package.json 后无需重 build 镜像，
#   容器启动时自动 sync node_modules（节省重 build 的 15+ 分钟 chromium 重装）
#   lockfile 漂移在 CI 用 `npm ci` 兜底，本地开发 entrypoint 用 `npm install` 灵活

echo "════════════════════════════════════════════════════════════"
echo "  📖 QA-GUIDE:    /opt/docs/QA-GUIDE.md"
echo "  📖 QA 模板:     /opt/docs/openspec/QA-TEMPLATE.md"
echo "════════════════════════════════════════════════════════════"
echo ""

# 同步 npm 依赖（仅当前目录 /app 有 package.json 时才跑）
if [ -f /app/package.json ]; then
    echo "=== 同步 npm 依赖（package.json 改动 → node_modules）==="
    cd /app
    npm install --no-audit --no-fund --prefer-offline 2>&1 | tail -5
    echo ""
fi

# exec 替换当前进程为实际命令
exec "$@"
