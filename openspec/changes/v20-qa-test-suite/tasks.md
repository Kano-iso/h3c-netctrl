## 1. 后端测试

- [x] 1.1 扩展 conftest.py（NetconfClient mock fixture、数据库重置、真实响应样本）
- [x] 1.2 新增 test_smoke.py：8 个路由的 smoke test
- [x] 1.3 新增 test_bugfix_regression.py：3 个关键 bug 回归
  - [x] DeviceResponse Pydantic v2 校验
  - [x] Ifmgr 解析器保留最小接口
  - [x] 接口保护 force 机制
- [x] 1.4 新增 test_netconf_errors.py：4 级错误分类

## 2. 前端 build 检查

- [x] 2.1 验证 `npm run build` 能跑通
- [x] 2.2 新增 frontend/Dockerfile.qa

## 3. QA 容器

- [x] 3.1 新增 backend/Dockerfile.qa
- [x] 3.2 docker-compose.dev.yml 加 qa service（profile qa）

## 4. 统一入口

- [x] 4.1 Makefile 加 `qa` 目标（含错误检测逻辑）
- [x] 4.2 .github/workflows/ci.yml 同步更新

## 5. 验证

- [x] 5.1 `make qa` 跑通：42 pytest PASS + build OK
- [x] 5.2 故意改坏 NONEXISTENT_FN，`make qa` FAIL（error 信息被 grep 到）
- [x] 5.3 提交代码并推送 + Archive 闭环

## 后续可选（用户确认暂不做）

- ESLint + no-undef 规则（抓运行时 undefined 引用）
- vue-tsc 类型检查
- Playwright e2e
