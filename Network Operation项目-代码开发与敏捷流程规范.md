# Network Operation项目\-代码开发与敏捷流程规范

## 版本变更记录

|版本|日期|更新说明|
|---|---|---|
|V1\.0|2026\-06\-13|初版，适配个人开源/自研项目，定义容器化开发环境、Git极简工作流、版本迭代与本地回退规范|

## 1\. 总体原则

本规范适用于个人 Network Operation 网运自研项目，用于统一本地开发、环境搭建、版本迭代、更新回退、日常迭代，为个人开发固定标准，简化操作、减少环境问题、保证项目可稳步迭代。核心原则如下：

- **完全容器化开发**：宿主机仅安装 Docker 和 SSH 远程连接工具，不安装 Python、数据库、中间件等任何业务依赖，所有开发、运行环境均隔离在容器内，保证环境统一、无本地依赖污染。

- **代码即配置**：所有业务配置、环境依赖声明、数据库迁移脚本、启动脚本、工具脚本全部纳入 Git 版本管理，无本地私有配置，保证项目可复刻、可追溯。

- **可回退性优先**：所有生产版本必须支持极速回退，覆盖代码、镜像、数据库结构与数据全维度，保障线上故障快速止血。

- **简单优先、循序渐进**：初期仅使用 Git 命令行 \+ 本地脚本/Makefile 完成全流程，不强制引入 GitLab/GitHub 等Web平台，后续根据协作需求按需扩容，降低初期开发成本。

- **轻量迭代、够用就好**：不堆砌复杂流程，优先保证个人开发高效、低负担，后续需要扩容协作再升级规范。

## 2\. 开发环境规范（纯容器化、宿主机干净）

### 2\.1 宿主机环境要求

- 操作系统：Ubuntu 20\.04\+ / CentOS 7\+

- 必备软件：Docker Engine 20\.10\+、Docker Compose v2、SSH服务（可选，远程开发使用）

- 项目统一工作目录：`/workspace/h3c-netctrl`

- 约束：禁止在宿主机安装 Python、MySQL、Redis、依赖库等业务环境

### 2\.2 开发容器标准化配置

项目根目录统一提供 `docker-compose.dev.yml`、`Dockerfile.dev`，标准化开发环境，支持热重载、数据持久化、日志留存：

- **后端容器**：Python 3\.10 \+ FastAPI \+ ncclient 网运依赖，挂载本地源码，支持代码热更新，无需重启容器

- **前端容器**：Nginx 静态资源服务，挂载前端编译产物，实现本地预览

- **数据库**：SQLite 文件持久化至宿主机 `./data/dev.db`，开发数据不丢失

- **日志文件**：容器日志统一挂载至宿主机 `./logs/`，方便排查问题、留存日志

### 2\.3 环境启动与停止命令

```bash
# 启动开发环境（依赖变更、首次构建必须加 --build）
docker-compose -f docker-compose.dev.yml up -d --build

# 停止开发容器（保留宿主机数据、日志、数据库文件）
docker-compose -f docker-compose.dev.yml down
```

开发人员全程无需配置本地编程语言、数据库、依赖环境，彻底规避环境不一致问题。

## 3\. Git 敏捷工作流规范

### 3\.1 分支策略（极简稳定，适配单人/小团队敏捷开发）

- **main 分支（生产稳定分支）**：对应线上生产环境最新稳定版本，**禁止直接提交代码**，仅通过合并 dev 分支更新，作为版本打Tag唯一分支。

- **dev 分支（日常开发主分支）**：所有功能迭代、Bug修复的核心分支，所有临时功能分支合并至此，是日常开发、联调的主力分支。

- **feature/xxx 临时功能分支**：单功能、单需求独立开发分支，命名语义化（如 feature/vlan\-manage、fix/netconf\-timeout），功能完成合并至 dev 后立即删除，避免分支堆积。

### 3\.2 版本标签规范

所有生产发布必须在 main 分支打版本标签，作为版本追溯、镜像构建、回退的唯一依据。

标签格式：`v<major>.<minor>.<patch>`（主版本\.次版本\.补丁版本），示例：v1\.0\.0、v1\.0\.1、v1\.1\.0

```bash
# 生产版本打标签标准流程
git checkout main
git merge dev   # 合并开发分支最新稳定代码
git tag v1.0.1
git push origin main --tags
```

### 3\.3 Commit 提交规范（强制统一）

统一提交格式，保证提交记录清晰、可追溯、适配后续迭代复盘。

格式：`<type>: 简短功能/修复描述`

Type 类型定义：

- **feat**：新增业务功能、接口、模块

- **fix**：线上/测试Bug修复、逻辑异常修复

- **docs**：文档更新、规范补充、注释完善

- **refactor**：代码重构、逻辑优化，无功能变更

- **chore**：构建脚本、Docker配置、Makefile、依赖版本调整

规范示例：

- feat: add vlan delete API

- fix: netconf session timeout handling

- chore: update dev docker dependency version

### 3\.4 协作模式说明

初期完全基于 Git 命令行完成所有操作，无需依赖 GitLab/GitHub 可视化平台，降低流程复杂度。后续多人协作、需要代码评审、CI/CD自动化时，再按需引入代码托管平台，流程无需重构。

## 4\. 代码迭代与生产发布流程

### 4\.1 日常开发迭代流程

```bash
git checkout dev
git pull origin dev        # 同步远程最新代码，避免冲突
# 完成代码开发、自测、联调
git add .
git commit -m "feat: xxx功能开发"
git push origin dev
```

### 4\.2 生产版本发布准备

```bash
git checkout main
git merge dev              # 合并开发分支稳定代码
git tag v1.0.1             # 打生产版本标签
git push origin main --tags
```

### 4\.3 生产镜像构建规范

```bash
# 基于生产Dockerfile构建版本镜像，同时绑定latest标签
docker build -t h3c-netctrl:v1.0.1 -f Dockerfile.prod .
docker tag h3c-netctrl:v1.0.1 h3c-netctrl:latest
```

### 4\.4 生产环境部署流程

```bash
# 停止旧服务、部署新版本镜像
docker-compose -f docker-compose.prod.yml down
docker-compose -f docker-compose.prod.yml up -d
```

补充：如果涉及数据库表结构改动，需要提前执行 Alembic 迁移脚本，保证本地/新版本代码兼容数据库结构。

## 5\. 版本回退策略（个人迭代兜底）

### 5\.1 代码版本回退

**方式一（推荐）：git revert 保留完整提交历史，可追溯**

```bash
git checkout main
git revert HEAD
git push origin main
```

**方式二（紧急兜底）：重置至指定稳定标签，谨慎使用**

```bash
git reset --hard v1.0.0
git push origin main --force
```

### 5\.2 Docker镜像回退

```bash
# 下线新版本、重置旧稳定镜像为latest、重新部署
docker-compose -f docker-compose.prod.yml down
docker tag h3c-netctrl:v1.0.0 h3c-netctrl:latest
docker-compose -f docker-compose.prod.yml up -d
```

### 5\.3 数据库回退规范

- SQLite阶段：每次生产部署自动备份数据库快照，回退时直接替换对应时间点备份文件

- MySQL迭代阶段：通过 Alembic downgrade 命令回退库表结构，同时恢复前置数据备份

- 强制要求：所有生产部署前，执行数据库自动备份，路径 `./backups/prod_<timestamp>.db`

### 5\.4 回退自查清单（个人自用）

1. 确认对应历史版本镜像本地存在

2. 确认对应数据库备份文件完好

3. 停止当前业务读写操作，避免数据错乱

4. 完成代码、镜像、数据库统一回退

5. 自测核心功能恢复正常

## 6\. 旧版本残留问题规避方案

|场景|核心问题|解决方案|
|---|---|---|
|Git分支切换|分支依赖变更导致容器运行报错、环境异常|统一使用 `make dev-rebuild` 无缓存重建镜像，同步最新依赖|
|数据库结构变更|新旧代码与库表结构不兼容，引发报错|全量使用Alembic管理迁移脚本，所有DDL变更留痕，支持upgrade/downgrade|
|镜像磁盘堆积|历史旧镜像占用服务器磁盘空间|定时清理：保留30天内镜像，执行 `docker image prune -a --filter "until=720h"`|
|挂载卷数据残留|旧数据库文件存在废弃字段/表，引发兼容问题|严格区分 dev\.db / prod\.db；废弃结构通过迁移脚本清理，异常时重建数据卷|

## 7\. 敏捷自动化 Makefile 脚本

项目根目录统一封装常用命令，简化操作、统一执行标准，规避人为操作失误。

```makefile
.PHONY: dev dev-rebuild prod prod-rebuild stop logs backup clean

# 启动开发环境
dev:
	docker-compose -f docker-compose.dev.yml up -d

# 无缓存重建开发环境（依赖更新必用）
dev-rebuild:
	docker-compose -f docker-compose.dev.yml down
	docker-compose -f docker-compose.dev.yml build --no-cache
	docker-compose -f docker-compose.dev.yml up -d

# 启动生产环境
prod:
	docker-compose -f docker-compose.prod.yml up -d

# 无缓存重建生产环境
prod-rebuild:
	docker-compose -f docker-compose.prod.yml down
	docker-compose -f docker-compose.prod.yml build --no-cache
	docker-compose -f docker-compose.prod.yml up -d

# 停止所有环境
stop:
	docker-compose -f docker-compose.dev.yml down
	docker-compose -f docker-compose.prod.yml down

# 实时查看后端日志
logs:
	docker-compose -f docker-compose.dev.yml logs -f backend

# 自动备份生产数据库
backup:
	mkdir -p ./backups
	cp ./data/prod.db ./backups/prod_$$(date +%Y%m%d_%H%M%S).db

# 彻底清理环境（谨慎使用）
clean:
	docker-compose -f docker-compose.dev.yml down -v
	docker-compose -f docker-compose.prod.yml down -v
	docker system prune -f
```

常用操作示例：

```bash
make dev        # 启动开发环境
make logs       # 实时查看后端日志
make backup     # 一键备份生产数据库
make prod       # 启动生产服务
make stop       # 停止所有容器环境
```

## 8\. 版本迭代兜底习惯（个人开发自用）

为保证迭代稳定、不丢数据、不炸环境，个人迭代固定以下习惯：

6. **更新必备份**：每次版本迭代、结构改动前执行 `make backup`

7. **保留稳定镜像**：本地留存上一个可用稳定版本，防止新版本崩环境

8. **版本标签固定**：正式迭代版本打Tag，不随意覆盖、删除，方便回溯

9. **数据库变更可回退**：所有表结构改动，保证 Alembic 支持升级/回退

10. **偶尔自测回退流程**：保证自己能快速修复迭代翻车问题

11. **版本留痕**：通过 version\.txt 记录当前迭代版本，方便自己对照排查问题

## 9\. 项目交付/归档清单

项目完整归档资产，方便后续复盘、迁移、复用：

- 容器化开发环境配置：docker\-compose\.dev\.yml、Dockerfile\.dev

- 生产环境部署配置：docker\-compose\.prod\.yml、Dockerfile\.prod

- Git分支策略、Commit规范、版本标签规范

- 开发、构建、发布、回退全流程操作手册

- 数据库迁移与回退标准方案

- 自动化Makefile工具脚本

- 线上风险规避与回退检查清单

## 10\. 个人迭代优化建议（轻量实用）

结合网运项目特性，额外增加可落地的优化方案，规避后续迭代风险，适配交付要求：

### 10\.1 新增简易代码自测规范

个人开发完成后，必须简单自测再提交合并，避免大量Bug堆积：接口连通性、参数校验、异常场景、设备模拟交互自测。

### 10\.2 新增版本发布日志规范

每次迭代打Tag后，简单更新 `RELEASE.md`：版本号、新增功能、修复问题、结构改动要点，方便自己复盘迭代进度。

### 10\.3 环境隔离强化

严格区分开发、本地运行环境的数据库与配置，避免测试数据、临时配置污染正式迭代版本。

### 10\.4 个人操作风控

环境清理、数据库回退、镜像删除属于高危操作，操作后自查一遍，避免误删项目文件与数据。

### 10\.5 后续可迭代升级方向

项目稳定后，可按需升级：接入自动化构建、日志监控、自动打包等能力，无需现在一开始就搞复杂。

## 11\. 说明

本规范为**个人自研项目专属轻量流程**，无企业复杂合规、审计、团队管控负担。全程简单、落地、够用，适配个人独立开发、迭代、归档、复盘，后续需要多人协作或商用交付时，再按需升级为企业级规范即可。



> （注：文档部分内容可能由 AI 生成）
