## Capability: engineering-infra

工程基础设施，Alembic 数据库迁移 + GitHub Actions CI。

## Goal

引入 Alembic 管理数据库迁移（替代 create_all），配置 GitHub Actions 基础 CI（推送自动验证）。

## Scope

### In Scope
- Alembic 初始化和配置
- 从现有表结构生成初始 migration（stamp head）
- 新增 assets 表的 migration 脚本
- upgrade/downgrade 命令可用
- GitHub Actions CI 配置（后端测试 + 前端构建验证）
- 后端补充关键测试用例

### Out of Scope
- 自动部署流水线
- 镜像仓库推送
- 生产环境数据库迁移脚本
- 前端 E2E 测试

## API Changes

无新 API。

## Data Model Changes

由 Alembic migration 管理，不再使用 create_all。

## Acceptance Criteria

- [ ] Alembic 已初始化，alembic.ini 和 migrations/ 目录就绪
- [ ] `alembic upgrade head` 可正确创建 assets 表
- [ ] `alembic downgrade -1` 可正确回退
- [ ] 应用启动时使用 `alembic upgrade head` 替代 `create_all`
- [ ] GitHub Actions CI 配置就绪，推送后自动验证
- [ ] 后端至少 5 个测试用例可通过
