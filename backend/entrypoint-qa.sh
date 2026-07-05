#!/bin/sh
# entrypoint-qa.sh — qa 容器入口脚本（sh 兼容，alpine + debian 都跑）
# 输出 QA-GUIDE 文档链接 banner，然后 exec 测试命令
# Part of v24-toolkit-ux-and-doc-discovery (v2.4 roadmap)

echo "════════════════════════════════════════════════════════════"
echo "  📖 QA-GUIDE:    /opt/docs/QA-GUIDE.md"
echo "  📖 QA 模板:     /opt/docs/openspec/QA-TEMPLATE.md"
echo "════════════════════════════════════════════════════════════"
echo ""

# exec 替换当前进程为实际命令
exec "$@"
