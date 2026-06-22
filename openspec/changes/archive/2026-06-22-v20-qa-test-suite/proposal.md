## Why

最近连续 3 个 bug 都是**自测漏掉的**：
1. H3C Ifmgr 解析器过滤了全部接口（自测时设备不可达，API 返回连接错误以为通过）
2. DeviceResponse Pydantic v2 model_validate 重写错误，GET /api/devices 500
3. DeviceDetail.vue 漏 import computed，**白屏**

根本原因：自测只测了**新增功能**，**没测既有功能回归**。

手测永远不靠谱。每次改完代码要跑遍测试，但目前没有：
- 后端：只有 2 个测试文件，覆盖很少
- 前端：完全没测试，**build 都没跑过**（这正是 #3 白屏漏掉的原因）
- 没有统一的"跑 QA"入口

## What Changes

**后端测试**（pytest + FastAPI TestClient）：
- 全部 8 个路由的 smoke test（保证不报 500）
- 关键 bug 回归测试（DeviceResponse Pydantic 校验、接口解析、接口保护）
- 错误分类函数单测（4 级错误）
- XML 解析函数单测

**前端 build 检查**（npm run build）：
- 所有 .vue 文件能编译
- import/export 引用正确
- 防止漏 import 之类的低级错误

**统一入口**：
- 新增 QA 容器（Docker service），集成后端 pytest + 前端 build
- `make qa` 一键运行所有 QA
- 集成到 CI（GitHub Actions）

## Capabilities

### New Capabilities

- `qa-test-suite`: 项目级 QA 自动化测试

## Impact

- 新增：`backend/tests/test_smoke.py`（全路由 smoke）、`backend/tests/test_bugfix_regression.py`（关键 bug 回归）
- 新增：`frontend` Dockerfile.dev 增加 build 依赖（typescript 相关）
- 新增：`backend/Dockerfile.qa`（QA 容器）
- 新增：`docker-compose.dev.yml` 新增 `qa` 服务
- 新增/修改：`Makefile` 增加 `qa` 目标
- 修改：`.github/workflows/ci.yml` 增加 `make qa` 步骤
- 用户体验：改完代码 `make qa` 一键检查，5-20 秒出结果
