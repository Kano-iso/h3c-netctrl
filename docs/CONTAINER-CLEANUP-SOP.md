# Container Cleanup SOP

> v24-container-cleanup (v2.4 roadmap)
>
> 清理 Docker 容器/镜像/volume 的标准操作流程，确保可回退、可追溯。

---

## 必须保留（v2.4 基线）

### 容器

| 容器 | 来源 | 用途 | 何时删除 |
|---|---|---|---|
| h3c-netctrl-backend | docker-compose.dev.yml | 后端 API | 仅在 v24-container-decoupling-3tier 拆 3 容器后 |
| h3c-netctrl-frontend | docker-compose.dev.yml | 前端 Vue.js | 永不 |
| h3c-netctrl-qa-backend | docker-compose.dev.yml (profile: qa) | QA 后端测试 | 永不 |
| h3c-netctrl-qa-frontend | docker-compose.dev.yml (profile: qa) | QA 前端 build 检查 | 永不 |
| h3c-netctrl-ops-toolkit | docker-compose.dev.yml (profile: ops) | 运维排错工具 | 永不（但可 stop） |

### 镜像

| 镜像 | 用途 | 何时删除 |
|---|---|---|
| h3c-netctrl-backend | 后端容器镜像 | 仅在拆 3 容器后 |
| h3c-netctrl-frontend | 前端容器镜像 | 永不 |
| h3c-netctrl-qa-backend | QA 后端镜像 | 永不 |
| h3c-netctrl-qa-frontend | QA 前端镜像 | 永不 |
| h3c-netctrl-ops-toolkit | 运维工具镜像 | 永不 |
| python:3.10-slim | 后端基础镜像 | 永不（Dockerfile FROM） |

### Volumes

| Volume | 用途 | 何时删除 |
|---|---|---|
| h3c-netctrl_h3c-netctrl-backups | 备份文件持久化 | 永不（含历史备份） |

---

## 可安全清理

### Exited 残留容器

**判断标准**: `docker ps -a --filter status=exited` 列出的容器，且非 ops-toolkit（ops-toolkit 按需启停是正常的）。

**清理命令**:
```bash
# 列出 exited 容器
docker ps -a --filter status=exited --format "{{.Names}}\t{{.Status}}"

# 删除单个（如 qa-frontend exited 残留）
docker rm h3c-netctrl-qa-frontend

# 需要时重建：docker compose -f docker-compose.dev.yml --profile qa up qa-frontend
```

**回退**: `docker compose up` 重建容器（镜像未删，秒级恢复）。

### Dangling 镜像

**判断标准**: `docker images -f "dangling=true"` 列出的镜像（无标签的中间层）。

**清理命令**:
```bash
docker image prune -f
```

**回退**: 重新 `docker compose build` 会重新生成中间层。

### 未用镜像

**判断标准**: `docker images` 列出但无任何容器引用的镜像。

**排查命令**:
```bash
# 列出所有镜像
docker images

# 检查镜像是否被容器引用
docker ps -a --format "{{.Image}}" | sort -u
```

**当前已知未用镜像**（v2.4 盘点）:
- `h3c-config:latest` — 10 天前创建，无容器引用，疑似旧版测试遗留
- `nginx:alpine` — 5 周前拉取，当前 docker-compose 无 nginx 服务

**清理命令**:
```bash
docker rmi h3c-config:latest nginx:alpine
```

**回退**: 需要时重新 `docker build` 或 `docker pull`。

### 匿名 Volume

**判断标准**: `docker volume ls` 列出但无名称（只有 64 字符 hash ID）的 volume。

**排查命令**:
```bash
# 列出匿名 volume
docker volume ls -f dangling=true

# 检查 volume 是否被容器引用
docker ps -a --format "{{.Names}}" | while read c; do
  echo "=== $c ==="
  docker inspect "$c" --format '{{range .Mounts}}{{.Name}}{{"\n"}}{{end}}' 2>/dev/null
done
```

**清理命令**:
```bash
# 谨慎：只删确认无引用的匿名 volume
docker volume rm <volume-id>
# 或一键清理（会删所有匿名 volume，命名 volume 保留）
docker volume prune -f
```

**回退**: 匿名 volume 删除后数据丢失，需确认无重要数据。

---

## 清理流程

### Step 1: 盘点基线
```bash
make container-inventory
# 生成 docs/CONTAINER-INVENTORY.md
```

### Step 2: 人工核对
- 打开 `docs/CONTAINER-INVENTORY.md`
- 确认"必须保留"清单的容器/镜像/volume 都在
- 列出 stale 项（exited 容器 / dangling 镜像 / 未用 volume）

### Step 3: 清理
按上述"可安全清理"章节执行，每步记录：
```bash
# 记录清理操作到 git
git add docs/CONTAINER-INVENTORY.md
git commit -m "chore(cleanup): 清理 stale 容器/镜像 (v24-container-cleanup)"
```

### Step 4: 验证
```bash
# 重新盘点
make container-inventory
# 对比清理前后，确认"必须保留"项 100% 一致
diff <(git show HEAD:docs/CONTAINER-INVENTORY.md) docs/CONTAINER-INVENTORY.md
```

---

## 关联

- 基线清单: [CONTAINER-INVENTORY.md](CONTAINER-INVENTORY.md)
- 拆容器蓝图: [CONTAINER-DECOUPLING.md](CONTAINER-DECOUPLING.md)
- v24-roadmap: [openspec/changes/v24-roadmap/proposal.md](../openspec/changes/v24-roadmap/proposal.md)
