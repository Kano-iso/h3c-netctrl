# v242-qa-and-tooling

> **版本定位**：v2.4.2 = **工程化加固 + QA 规范化**小版本。
> **v2.4.1 后续**：v2.4.1 (tag, 2026-07-03) = 3 容器拆分实施
> **v2.4.2 vs v3.0**：
> - v2.4.2 = 优化（qa 规范完善、压测、3 容器 review）
> - v3.0 = 新功能（VPC 联动）

---

## Why

v2.4.1 发版后，QA 工程化债暴露：

1. **前端 QA 无 guard**：`qa-frontend` 容器只跑 `npm run build`，不抓 lint 问题（拼错变量、未使用 import、错误 prop 名）
   - 用户原话："前端测试现在只有 build，它起到什么作用啊？"
2. **qa 工具乱用生产设备**：ops-toolkit 脚本 + 真机 e2e 测试，没有"默认 test 设备"约定
   - 用户原话："qa 用着用着又开始瞎用别的地址了"
   - 必须把 `Test-Switch-177` (192.168.100.177) 写进 qa 工具默认参数
3. **qa 规范文档与实际脱节**：`.trae/rules/qa规范.md` 写"build + 组件测试"，但**组件测试根本没装过**（v2.3.0 vitest BLOCKED by EACCES）
   - 必须重写为"build + lint（+ 未来 vitest）"

---

## What Changes

v2.4.2 Change 1（qa 规范与工具完善）= **3 大主线**：

### 主线 1：前端 ESLint 进 qa 容器

- 装包：`npm i -D eslint eslint-plugin-vue @vue/eslint-config-vue`（~5MB）
- 写 `.eslintrc.cjs`（vue3 必需规则集 + 个人项目精简）
- `package.json` 加 `npm run lint` script
- 改 `frontend/Dockerfile.qa`：build 之前先跑 lint，lint 不过 → build 不跑（快速 fail）
- qa-frontend 容器流程：`lint + build`（秒级，自动 guard）
- 抓的 bug 类型：拼错变量名、unused import、错 prop 名、v-if 引用空对象、双等号、async 不 await

### 主线 2：默认 test 设备硬编码进 qa 工具

- 192.168.100.177 (Test-Switch-177, id=7) 作为 qa 工具的默认目标设备
- 改 `ops-toolkit/scripts/*.sh`：所有脚本支持 `--device test` 别名，等价于 `--device 192.168.100.177`
- 改 `ops-toolkit/scripts/_lib.sh`：`_resolve_device()` 函数先查设备名 → IP 映射 → 默认 `test`
- qa-backend `pytest --integration` 跑真机 e2e 时，自动指向 .177（不污染 .4/.5 生产）
- `docs/ops-toolkit.md` 加 `test` 别名说明
- ops-toolkit 容器入口 banner 标注"默认目标：Test-Switch-177"

### 主线 3：qa 规范文档重写

`.trae/rules/qa规范.md` 改写：
- 第 34 行 "build + 组件测试" → "**lint + build**"（vitest 待 future）
- 新增章节："qa 默认设备"（强制约定 qa 工具不指生产）
- 新增章节："MCP 浏览器定位"（小测试/排错，不进 qa 容器）
- 表格化各工具边界：ESLint / Vitest / build / MCP 浏览器 / 真机 e2e

### 顺序

```
前端 ESLint 装包 + .eslintrc
        ↓
package.json + Dockerfile.qa 改 lint
        ↓
qa 工具默认 test 设备 + 文档
        ↓
qa 规范.md 改写
```

---

## Capabilities

### New Capabilities

| 子能力 | 主题 | 关键能力 | 装包 |
|---|---|---|---|
| `frontend-lint` | 前端 ESLint 进 qa | eslint + eslint-plugin-vue + lint script + qa 容器跑 lint | +5MB |
| `qa-default-test-device` | qa 工具默认 test 设备 | `--device test` 别名 + 设备名→IP 映射 + docs 同步 | 0 |

### Modified Capabilities

- `qa-spec` (existing capability) — 升级：从"build only"升级为"lint + build"，新增"默认 test 设备"约定
- `ops-toolkit-ux` (existing capability) — 升级：所有脚本支持 `--device test` 别名
- `container-decoupling-preparedness` (existing capability) — 升级：qa 工具默认指向 test 设备，避免误连生产

---

## Impact

- **新增包**：3 个（eslint + eslint-plugin-vue + @vue/eslint-config-vue，~5MB）
- **新增 API**：0
- **修改后端代码**：0
- **修改前端代码**：`package.json` + `Dockerfile.qa` + 新增 `.eslintrc.cjs`
- **修改 ops-toolkit**：`scripts/*.sh` + `scripts/_lib.sh`（默认 device=test）
- **修改文档**：`.trae/rules/qa规范.md`（重写）+ `docs/ops-toolkit.md`（新增 test 别名）
- **可回退**：删除 `.eslintrc.cjs` + revert `Dockerfile.qa` + 删 lint script
- **不破坏**：build / qa-backend 单元测试 / v2.4.1 3 容器 / 现有 214 passed

---

## 真机验证

- **设备**：192.168.100.177 (Test-Switch-177)
- **ESLint**：
  - `docker compose --profile qa run --rm qa-frontend` → 跑 lint + build，输出 "📖 lint + build 链接"
  - 故意改 1 个文件（unused import），重跑 → 应 fail
- **qa 默认 test 设备**：
  - `docker compose --profile ops run --rm ops-toolkit check-host.sh --device test` → 验指向 .177
  - `docker compose --profile ops run --rm ops-toolkit ssh-test.sh --device test` → 验 SSH 连 .177 成功
- **回归**：qa-backend 跑 `pytest`，仍 214 passed

---

## 收尾 / 发版

- 1 个 archive：`openspec/changes/archive/2026-07-XX-v242-qa-and-tooling/`
- 更新 `RELEASE-NOTES-v2.4.2.md`（待 v2.4.2 全部 3 个 change 收尾后写）
- 更新 `VERSION-ROADMAP.md` v2.4.2 条目
- `git tag v2.4.2` 在所有 3 个 change 收尾后打

---

## Out of Scope

- 不引入 Vitest 单元测试（v2.3.0 BLOCKED 遗留，user 明确 v2.4.2 暂不做，等 v2.5 再起）
- 不引入 Playwright / Cypress（个人项目 ROI 低）
- 不做 TypeScript 迁移（vue-tsc / TS 太重）
- 不动 3 容器拓扑（v2.4.1 已定稿）
- 不做性能压测（属于 v2.4.2 Change 2）

---

## 关联

- 上版：[RELEASE-NOTES-v2.4.1.md](../../../RELEASE-NOTES-v2.4.1.md)
- 路线图：[VERSION-ROADMAP.md § v2.4.2](../../../VERSION-ROADMAP.md)
- QA 规范：`.trae/rules/qa规范.md`（本次重写）
- QA 文档：[docs/QA-GUIDE.md](../../../docs/QA-GUIDE.md)
- ops-toolkit 手册：[docs/ops-toolkit.md](../../../docs/ops-toolkit.md)
- v2.3.0 vitest BLOCKED 记录：[archive/2026-06-29-add-vitest-component-tests/proposal.md](../2026-06-29-add-vitest-component-tests/proposal.md)
