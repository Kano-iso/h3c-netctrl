## Context

### 痛点
最近踩了 3 个连续漏测的 bug：
- #1: Ifmgr 解析器漏过滤 — 自测设备不可达，curl 看到"success:false"以为是失败场景，没注意数据根本没出来
- #2: DeviceResponse Pydantic v2 校验 — **GET /api/devices 一直 500**，但自测只测了设备配置 + 接口查询，**没测设备列表**
- #3: DeviceDetail.vue 漏 import — **白屏**，API 都正常，但**根本没打开过浏览器**

### 测试现状
- `backend/tests/test_device_api.py`：~50 行，只测设备 CRUD
- `backend/tests/test_xml_builder.py`：XML 构造函数
- `frontend`：**完全无测试**
- CI：`.github/workflows/ci.yml` 只跑后端 pytest

## Goals / Non-Goals

**Goals:**
- 后端：所有路由的 smoke test，确保不报 500
- 后端：3 个关键 bug 的回归测试，下次类似 bug 自动被抓
- 前端：`npm run build` 必须能编译过
- 统一入口：`make qa`
- QA 容器：独立 Docker service，一次跑完

**Non-Goals:**
- 不做前端 e2e（Playwright）— 容器太重，5s 解决的事不需要 1-2 分钟
- 不做性能测试
- 不做覆盖率统计（不需要量化）
- 不改业务代码

## Decisions

### D1: pytest TestClient 而不是真实 HTTP

**选择**：用 `fastapi.testclient.TestClient(app)`

**理由**：内存中跑，不需要起 uvicorn 进程，速度快（毫秒级），隔离数据库用 /tmp/test_*.db

### D2: 前端 build check 而不是 vue-tsc

**选择**：`npm run build` 而非 `vue-tsc --noEmit`

**理由**：项目无 TypeScript，build 已经能 catch 所有 import/语法错误。`vue-tsc` 收益小、增加配置成本

### D3: QA 容器作为独立 service

**选择**：在 `docker-compose.dev.yml` 加 `qa` service

**理由**：
- 容器内跑测试环境一致
- 用 `depends_on: backend` 验证 backend 起来了
- 用 `profiles: ["qa"]` 让 QA 容器**默认不起**，需要时 `docker compose --profile qa up qa`

### D4: make qa 作为统一入口

**选择**：在 Makefile 加 `qa` 目标

**理由**：
- 一行命令跑完所有 QA
- CI 也能用同样的 `make qa`
- 不依赖操作系统（Make 是 POSIX 标准）

### D5: 关键 bug 回归测试

针对最近 3 个 bug 加测试：
- `test_device_response_pydantic_v2`：mock 一条 Device 记录，model_validate 后的 protected_interfaces 必须是 list[int]，不能是 str
- `test_interface_parser_keeps_minimal_interfaces`：mock 真实 H3C Ifmgr 响应（只有 IfIndex/PVID，无 Name/LinkType），解析后必须有 23 个接口
- `test_interface_protection`：保护 if_index=2 不加 force 必须被拒，加 force=true 通过

## Risks / Trade-offs

- 后端测试需要 mock NETCONF — 已用 `pytest-mock` 的 `mocker.patch` 处理 NetconfClient
- QA 容器需要 2 个 Dockerfile（backend.qa + frontend.qa），用 multi-stage 或者单独目录
- 写测试时间（写 1 次，永久用）
