# v242-qa-and-tooling Design

> v2.4.2 Change 1 的设计决策与文件清单。

---

## 1. 关键设计决策

### 1.1 ESLint 选型

**方案 A：ESLint 8 + eslint-plugin-vue + @vue/eslint-config-vue**（推荐）
- 包：`eslint@^8.57.0`、`eslint-plugin-vue@^9.0.0`、`@vue/eslint-config-vue@^0.6.0`
- 装包大小：~5MB
- 规则集：`vue3-essential` + `vue3-recommended`（Vue 3 必需 + 推荐）
- 配置：`.eslintrc.cjs`（cjs 兼容 Vite 工程）

**方案 B：ESLint 9 + flat config**（放弃）
- flat config 生态在 Vue 项目还不成熟
- eslint-plugin-vue 9 还在迁移
- 个人项目没必要追新

**方案 C：Biome**（放弃）
- 快，但 Vue SFC 模板 lint 覆盖弱
- 个人项目刚接触 ESLint，引入第二个工具增加学习成本

→ **选 A**

### 1.2 qa-frontend 容器流程

**改前**：
```dockerfile
ENTRYPOINT ["entrypoint-qa.sh"]
CMD ["npm", "run", "build"]
```

**改后**：
```dockerfile
ENTRYPOINT ["entrypoint-qa.sh"]
CMD ["sh", "-c", "npm run lint && npm run build"]
```

**理由**：
- lint 不过 → build 不跑（快速 fail，避免 lint 错被 build 掩盖）
- 单一 `make qa-frontend` 入口，行为可预期
- 未来加 `npm run test:unit` 也只改这一行

### 1.3 默认 test 设备实现

**方案 A：硬编码 IP**（简单）
```bash
DEFAULT_DEVICE_IP="192.168.100.177"
```
- 优点：零依赖
- 缺点：换 IP 改脚本

**方案 B：设备名→IP 映射**（推荐）
```bash
# _lib.sh 加 _resolve_device()
_resolve_device() {
  local device="$1"
  case "$device" in
    test|Test-Switch|Test-Switch-177) echo "192.168.100.177" ;;
    leaf-03|Leaf-03) echo "192.168.100.4" ;;
    leaf-04|Leaf-04) echo "192.168.100.5" ;;
    spine-01|Spine-01) echo "192.168.100.100" ;;
    *) echo "$device" ;;  # 已是 IP 透传
  esac
}
```
- 优点：用户友好，`--device test` 比 `--device 192.168.100.177` 短得多
- 缺点：设备名/IP 变化需改脚本

**方案 C：调后端 API 解析**（过重）
- 每次跑脚本走 HTTP 调 `GET /api/devices` 查 name → IP
- 优点：自动同步
- 缺点：依赖 backend 容器在运行；脚本启动慢；qa 工具的核心理念是"零依赖"——硬编码更纯粹

→ **选 B**（qa 工具是"排错应急用"，硬编码符合工具定位）

### 1.4 qa 工具默认行为

**改前**：
```bash
check-host.sh  # 报错：必须指定 --device
```

**改后**：
```bash
check-host.sh  # 等价 check-host.sh --device test
check-host.sh --device test  # 显式
check-host.sh --device 192.168.100.5  # 显式指生产（不推荐，但允许）
```

**理由**：
- 不带参数 → 默认 test 设备（安全默认）
- 带 `--device test` → 显式 test
- 带 IP → 显式生产（不阻止，但日志打 warn："生产设备，注意操作"）

### 1.5 qa 规范.md 重写

**改前**（第 34 行）：
> archive 前跑前端 build + 组件测试（Archive 阶段必跑）

**改后**：
> archive 前跑前端 **lint + build**（Archive 阶段必跑，秒级自动 guard）
> 组件测试（vitest）暂未引入，等 v2.5 评估

**新增章节**：

```markdown
### qa 默认设备

qa 容器 / ops-toolkit 工具**默认指向** Test-Switch-177 (192.168.100.177)：
- `--device` 不带参数 = test
- `--device test` = 显式 test
- `--device <生产 IP>` = 显式生产（不阻止，日志 warn）

禁止理由：qa 是"反复跑"的工具，误连生产可能导致配置污染。

### MCP 浏览器定位

MCP 浏览器（integrated_browser / Chrome DevTools MCP）= **小测试 / 单功能验证 / 排错**。

**不进 qa 容器**：MCP 跑 1 次分钟级，qa 容器必须秒级自动 guard。

**用法**：
- 验证单个新功能是否 work
- 排查 UI 交互 bug
- 写 E2E 演示

**禁止**：
- 在 qa 容器跑 MCP 浏览器（污染秒级 guard 流程）
- 把 MCP 当回归测试（太慢）
```

---

## 2. 文件清单

### 2.1 新增文件

| 文件 | 用途 |
|---|---|
| `frontend/.eslintrc.cjs` | ESLint 配置（vue3-essential + vue3-recommended） |
| `frontend/.eslintignore` | 忽略 dist / node_modules / coverage |

### 2.2 修改文件

| 文件 | 改动 |
|---|---|
| `frontend/package.json` | 加 devDependencies: eslint + eslint-plugin-vue + @vue/eslint-config-vue；加 scripts: `lint: "eslint --ext .js,.vue src --max-warnings 0"` |
| `frontend/Dockerfile.qa` | CMD 改 `sh -c "npm run lint && npm run build"` |
| `ops-toolkit/scripts/_lib.sh` | 加 `_resolve_device()` 函数 + `DEFAULT_DEVICE=test` |
| `ops-toolkit/scripts/check-host.sh` | 接受 `--device` 默认 `test` |
| `ops-toolkit/scripts/ssh-test.sh` | 同上 |
| `ops-toolkit/scripts/check-netconf.sh` | 同上 |
| `ops-toolkit/scripts/capture-config.sh` | 同上 |
| `ops-toolkit/scripts/reboot-wait.sh` | 同上 |
| `ops-toolkit/scripts/audit-switch.sh` | 同上 |
| `ops-toolkit/entrypoint.sh` | banner 加"📌 默认目标：Test-Switch-177 (192.168.100.177)" |
| `.trae/rules/qa规范.md` | 重写：lint + build + 默认 test 设备 + MCP 边界 |
| `docs/ops-toolkit.md` | 新增"设备名→IP 映射表" + `--device test` 说明 |
| `docs/QA-GUIDE.md` | 新增"qa 默认设备"小节 |
| `backend/tests/conftest.py` | 真机 e2e fixture 默认指向 .177（不改 split_integration 的 mock 测试） |

### 2.3 不修改

- 后端代码、3 容器拓扑、`docker-compose.dev.yml`
- 现有 214 passed 测试

---

## 3. 升级回退

### 升级

```bash
git pull
docker compose -f docker-compose.dev.yml build qa-frontend ops-toolkit
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-frontend
# 预期：lint + build 都过
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit check-host.sh
# 预期：默认连 192.168.100.177
```

### 回退

```bash
git revert <commit>
docker compose -f docker-compose.dev.yml build qa-frontend ops-toolkit
# 行为恢复 v2.4.1
```

---

## 4. 风险评估

| 风险 | 等级 | 缓解 |
|---|---|---|
| ESLint 规则太严，存量代码 lint 不过 | 中 | 加 `.eslintrc.cjs` 时先跑一遍看 issue 数；过 50+ 就放宽规则或 `--max-warnings 0` 改为只报 error |
| 硬编码 .177 IP 换地址需改脚本 | 低 | 在文档显眼位置标注；qa 工具是排错应急，影响面小 |
| qa 工具默认改 .177，老用户习惯 `.5` | 低 | 在 banner + 文档双标注；qa 工具可显式 `--device <IP>` 绕过 |
| `.trae/rules/qa规范.md` 改了影响 IDE 自动行为 | 低 | `.trae/rules/` 是项目规则文档，不被 CI 读取，仅 AI 参考 |
| qa-frontend 容器 `lint && build` 比纯 build 慢 | 低 | ESLint 全量跑 ~3-5s，可接受 |

---

## 5. 验证 checklist

- [ ] `npm run lint` 跑通（0 error，过 warnings）
- [ ] `docker compose --profile qa run --rm qa-frontend` 跑通（lint + build）
- [ ] 故意改 1 个文件（unused import）→ 重跑 → 失败
- [ ] `ops-toolkit check-host.sh`（不带参数）→ 指向 .177
- [ ] `ops-toolkit check-host.sh --device test` → 指向 .177
- [ ] `ops-toolkit check-host.sh --device 192.168.100.5` → 显式指生产 + warn 日志
- [ ] qa-backend `pytest` 仍 214 passed
- [ ] `.trae/rules/qa规范.md` 改写完成
- [ ] `docs/ops-toolkit.md` 设备名映射表更新
- [ ] `docs/QA-GUIDE.md` 默认设备小节更新
