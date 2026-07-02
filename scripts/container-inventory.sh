#!/usr/bin/env bash
# container-inventory.sh — 盘点当前 Docker 容器/镜像/volume 基线
# 输出 markdown 到 docs/CONTAINER-INVENTORY.md，同时 echo 摘要
# 用法: ./scripts/container-inventory.sh [--output PATH]
#
# Part of v24-container-cleanup (v2.4 roadmap)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
DEFAULT_OUTPUT="$PROJECT_DIR/docs/CONTAINER-INVENTORY.md"

OUTPUT="${1:-}"
if [[ "$OUTPUT" == "--output" ]]; then
  OUTPUT="${2:-$DEFAULT_OUTPUT}"
else
  OUTPUT="$DEFAULT_OUTPUT"
fi

TIMESTAMP="$(date '+%Y-%m-%d %H:%M:%S %z')"

{
  echo "# Container Inventory"
  echo ""
  echo "> 自动生成 by \`scripts/container-inventory.sh\`"
  echo "> 时间: $TIMESTAMP"
  echo "> 项目: h3c-netctrl (v2.4)"
  echo ""

  echo "## 容器 (docker ps -a)"
  echo ""
  echo "| 名称 | 镜像 | 状态 | 端口 |"
  echo "|---|---|---|---|"
  docker ps -a --format "{{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}" | while IFS=$'\t' read -r name image status ports; do
    # 空 ports 显示 -
    [[ -z "$ports" ]] && ports="-"
    echo "| $name | $image | $status | $ports |"
  done
  echo ""

  echo "## 镜像 (docker images)"
  echo ""
  echo "| 仓库 | 标签 | 大小 | 创建时间 |"
  echo "|---|---|---|---|"
  docker images --format "{{.Repository}}\t{{.Tag}}\t{{.Size}}\t{{.CreatedSince}}" | while IFS=$'\t' read -r repo tag size created; do
    echo "| $repo | $tag | $size | $created |"
  done
  echo ""

  echo "## Dangling 镜像"
  echo ""
  DANGLING_IDS="$(docker images -f "dangling=true" -q 2>/dev/null || true)"
  if [[ -z "$DANGLING_IDS" ]]; then
    echo "- 无 dangling 镜像"
  else
    echo "| ID | 大小 | 创建时间 |"
    echo "|---|---|---|"
    docker images -f "dangling=true" --format "| {{.ID}} | {{.Size}} | {{.CreatedSince}} |"
  fi
  echo ""

  echo "## Volumes (docker volume ls)"
  echo ""
  echo "| Driver | Name |"
  echo "|---|---|"
  docker volume ls --format "{{.Driver}}\t{{.Name}}" | while IFS=$'\t' read -r driver name; do
    echo "| $driver | $name |"
  done
  echo ""

  echo "## 网络 (docker network ls)"
  echo ""
  echo "| Network ID | Name | Driver | Scope |"
  echo "|---|---|---|---|"
  docker network ls --format "{{.ID}}\t{{.Name}}\t{{.Driver}}\t{{.Scope}}" | while IFS=$'\t' read -r id name driver scope; do
    echo "| $id | $name | $driver | $scope |"
  done
  echo ""

  echo "## 基线清单（v2.4 必须保留）"
  echo ""
  echo "| 容器 | 镜像 | 用途 | 来源 |"
  echo "|---|---|---|---|"
  echo "| h3c-netctrl-backend | h3c-netctrl-backend | 后端 API (monolith, v2.4 将拆 3 容器) | docker-compose.dev.yml"
  echo "| h3c-netctrl-frontend | h3c-netctrl-frontend | 前端 Vue.js | docker-compose.dev.yml"
  echo "| h3c-netctrl-qa-backend | h3c-netctrl-qa-backend | QA 后端测试 (profile: qa) | docker-compose.dev.yml"
  echo "| h3c-netctrl-qa-frontend | h3c-netctrl-qa-frontend | QA 前端 build 检查 (profile: qa) | docker-compose.dev.yml"
  echo "| h3c-netctrl-ops-toolkit | h3c-netctrl-ops-toolkit | 运维排错工具 (profile: ops, 按需启动) | docker-compose.dev.yml"
  echo ""

  echo "## 清理建议"
  echo ""
  echo "- **stop 残留容器**: \`docker ps -a --filter status=exited\` 列出的容器，如非必须可 \`docker rm\` 删除（需要时 \`docker compose up\` 重建）"
  echo "- **dangling 镜像**: \`docker image prune -f\` 清理"
  echo "- **未用 volume**: \`docker volume prune -f\` 清理（**注意**: 会删除匿名 volume，命名 volume 保留）"
  echo "- **未用镜像**: 当前无容器引用的镜像可 \`docker rmi\` 删除（需要时重新 pull/build）"
  echo ""
  echo "清理 SOP 详见 [docs/CONTAINER-CLEANUP-SOP.md](CONTAINER-CLEANUP-SOP.md)"
  echo ""

  echo "---"
  echo ""
  echo "Last updated: $TIMESTAMP"
} > "$OUTPUT"

# stdout 摘要
CONTAINER_COUNT=$(docker ps -a -q | wc -l)
RUNNING_COUNT=$(docker ps -q | wc -l)
EXITED_COUNT=$(docker ps -a --filter status=exited -q | wc -l)
IMAGE_COUNT=$(docker images -q | wc -l)
DANGLING_COUNT=$(docker images -f "dangling=true" -q 2>/dev/null | wc -l)
VOLUME_COUNT=$(docker volume ls -q | wc -l)

echo "✅ 容器盘点完成 → $OUTPUT"
echo ""
echo "摘要:"
echo "  容器: $CONTAINER_COUNT (running=$RUNNING_COUNT, exited=$EXITED_COUNT)"
echo "  镜像: $IMAGE_COUNT (dangling=$DANGLING_COUNT)"
echo "  Volumes: $VOLUME_COUNT"
