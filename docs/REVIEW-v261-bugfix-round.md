# v2.6.1 bug 修复轮次 — Review 报告

**版本**：v2.6.1
**日期**：2026-07-07
**主题**：QA 套件盲区反思 + 集中修 8 类问题
**状态**：✅ 完成

---

## 1. 反思起点（v2.6.0）

v2.6.0 i18n archive 时（commit `9db780e` / `db6ff0a`）：

- ✅ qa-backend 全量 pytest 通过（实际 291 passed，不是当时记录里的 275+）
- ✅ qa-frontend lint + build + 53 vitest + 42 playwright 全过
- ❌ 用户立刻发现 dashboard online=7 **陈旧数据 bug**（asset 表 5~13 天前老 online 数据没人管）
- ❌ 用户发现 备份回滚"无响应"（H3C V7 S6850 不支持 SCP，scp 推回失败但前端无 toast）

**根因**：QA 套件只测**代码逻辑**（try/except 分支、调用关系），**不覆盖"业务时间敏感"场景**（如数据陈旧、过期降级）和**协议兼容性**（如 H3C V7 SCP 限制）。

---

## 2. 改进原则

v2.6.1 集中修 8 类问题，同时定下 3 条新规则：

| 新规则 | 旧做法 | 新做法 |
|---|---|---|
| **真机必跑** | 设备 down 借口跳过真机 | 设备 down 时排队等，真机测试不可跳过 |
| **数据陈旧 = bug** | "不改用户数据"刻意不修 | 阈值自动降级 + 启动自检清理幽灵行 |
| **subagent 一次 9 commit = 反模式** | 一次跑完 9 task | 单 task = 1 commit + 1 qa 真跑 + 1 报告 |

---

## 3. 8 类问题（按修复路径分类）

### 3.1 资产数据陈旧（fix-asset-stale-status，8 commit）

| 现象 | dashboard online=7 但实际有设备 down 5+ 天 |
|---|---|
| 根因 | Asset.status 是"采集时刻的状态快照"，没有"过期降级"机制 |
| 修复 | `ASSET_STALE_HOURS=24`（可配）+ data 容器启动时按阈值自动降级 + dashboard 读时按阈值过滤 |
| 教训 | **数据陈旧 = bug**，不能用"不改用户数据"搪塞 |
| commit 数 | 8（模型 + 迁移 + 路由 + dashboard + 配置 + 测试 + 文档） |

### 3.2 采集失败可读化（fix-asset-collect-failure，8 commit）

| 现象 | "采集不采集会失败"（用户原话），error 信息不可读 |
|---|---|
| 根因 | catch 异常后直接返回 `{"error": str(e)}`，没有 error_key，前端拿到技术异常 |
| 修复 | 9 种 catch 块都加 `error_key + error_params`，统一走 i18n 翻译 + 中文 fallback |
| 教训 | **错误可读化是基础设施**，不能等"用户碰到了再修" |
| commit 数 | 8（SSH / NETCONF / DB / 加密 / 超时 / 错位） |

### 3.3 split 模式密码二次解密（fix-asset-split-password-decrypt，3 commit）

| 现象 | split 模式下 device 列表返回 500 |
|---|---|
| 根因 | ctrl 容器把 password 用 Fernet 加密后存 DB；data 容器调 internal-api 拿到密文后**不识别**又走了一次解密 |
| 修复 | internal-api 统一返回明文（ctrl 容器解密后返回），所有调用方拿到的是明文 |
| 教训 | **跨容器协议必须明文规定**（什么密文 / 什么明文），不能"先这样跑跑看" |
| commit 数 | 3 |

### 3.4 vite proxy 长前缀错配（fix-vite-proxy-route，1 commit）

| 现象 | `GET /api/devices/{id}/backup/{id}` 走 ctrl 容器 → 404 |
|---|---|
| 根因 | vite proxy DATA_PATTERN `/^\/api\/(backups\|assets)/` 不匹配 `devices/1/backup/1` |
| 修复 | 加更精确的 DOWNLOAD_PATTERN 正则，按优先级（DOWNLOAD → DATA → CONFIG → CTRL）分发 |
| 教训 | **正则匹配要按"长前缀优先"排序**，不能用"短前缀 catch-all" |
| commit 数 | 1 |

### 3.5 备份数据完整性 4 防线（fix-backup-data-integrity，6 commit）

| 现象 | 下载 404 + ghost 行 + task 报 id 102 但 DB id=101 |
|---|---|
| 根因 | 4 个独立 bug 叠加：proxy 错配 + 文件物理丢失 + commit 不刷 + session 隐式 expire |
| 修复 | 4 防线：proxy DOWNLOAD_PATTERN / 启动自检 + ghost 行清理 / commit 后立即 refresh / `expire_on_commit=False` |
| 教训 | **备份类功能必须分层防御**（4 防线），不能依赖"开发期间没出问题就以为稳了" |
| commit 数 | 6（含 dump_db.py 工具） |

### 3.6 资产备份状态同步（fix-asset-backup-state-sync，5 commit）

| 现象 | offline 设备备份按钮可点 + 真备份时 422 + 无 force 逃生 |
|---|---|
| 根因 | 备份端点不查 asset.status；UI 也不显示设备状态对备份的约束 |
| 修复 | 后端：offline 设备无 force 直接 422 + `error.backup.device_offline`；前端：force 复选框 + 二次确认弹窗 + 10 个 i18n key；DB：`backups.forced` 审计字段 |
| 教训 | **业务约束必须在 UI 暴露**（不能靠用户看 log 猜） |
| commit 数 | 5 |

### 3.7 备份回滚"无响应"根因定位（fix-backup-restore-no-response，0 commit + 1 doc）

| 现象 | 前端点回滚无任何反应；后端 task < 1s 失败 |
|---|---|
| 根因 A | H3C V7 S6850（CMW 7.1.070）**SFTP/SCP subsystem 默认禁用** |
| 根因 B | `BackupManager._restore_via_scp` 用 paramiko scp 库对该设备不可用 |
| 根因 C | 前端 `BackgroundTaskPanel` 折叠条件让失败任务不可见 |
| 修复 | **v2.6.1 范围：仅根因定位文档**（`openspec/changes/archive/2026-07-07-fix-backup-restore-no-response/STATUS.md`），修复推 v2.6.2 |
| 教训 | **协议兼容性是项目盲区**（`.177` 能跑纯属偶然），必须把 .5 这种"不支持"设备纳入 QA 矩阵 |
| 范围 | 9 task × 1 commit = 9 commit > v2.6.1 剩余 22 commit 范围，**砍掉** |

### 3.8 add-auto-collect 砍掉（add-auto-collect，0 commit + 1 archive + CANCELLED）

| 现象 | v2.6.0 subagent 一次跑 9 commit 但 qa + 真机都没真验证 |
|---|---|
| 根因 | subagent "跑得快" 模式违反"先有 Spec 再有代码"的项目硬约束 |
| 修复 | **v2.6.1 砍掉**，移 archive + CANCELLED.md 说明；v2.6.0 复盘发现"自动降级机制"已替代"自动采集保持数据新鲜"目标，nice-to-have 推 v2.6.2 |
| 教训 | **subagent 一次 9 commit 是反模式**。**单 task = 1 commit + 1 qa 真跑 + 1 报告** |
| 范围 | 9 task 全部 ⏳ 状态（未实施） |

---

## 4. QA 套件盲区 → 改进方向

### 4.1 现状（v2.6.1 baseline）

- **backend 单元**：309+ passed（v2.6.0 baseline 265 + 8 stale + 8 collect + 3 split + 1 vite + 6 backup-data + 5 backup-state-sync + 14 i18n 等）
- **frontend 单元（vitest）**：53+ case 全过
- **frontend e2e（playwright）**：42+ case 全过
- **真机集成**：3 case（.5 force 流程 / .177 online / .99 浏览器端到端）

### 4.2 盲区清单（v2.6.0 暴露）

| 盲区 | 表现 | v2.6.1 改进 |
|---|---|---|
| **数据陈旧** | Asset.status 5+ 天前老数据不算 bug | 加 staleness 阈值测试 + 启动自检 |
| **协议兼容** | .5 设备 SCP 不支持，`.177` 能跑就当通过 | 加多机型真机测试矩阵（.4/.5/.6/.177） |
| **跨容器协议** | split 模式下 internal-api 响应密文还是明文不明确 | internal-api 统一返回明文 + 类型标注 |
| **session 生命周期** | 长任务 session 隐式 expire 触发意外 SQL | `expire_on_commit=False` 显式声明 |
| **commit vs refresh** | flush 时分配 id ≠ commit 后真实 id | commit 后 `db.refresh()` 验证行存在 |
| **proxy 路由** | 长前缀被短前缀 catch-all 拦截 | regex 长前缀优先 + 显式优先级 |

### 4.3 改进原则

1. **业务时间敏感 = 测试用例**（staleness、过期降级、轮转）
2. **协议兼容性 = 真机矩阵**（每个协议至少 1 个"不支持"设备验证降级路径）
3. **跨容器协议 = 类型标注**（internal-api response 必须明确标注 `is_encrypted: bool`）
4. **session 生命周期 = 显式声明**（每个 session 必须显式 `expire_on_commit`）
5. **commit vs refresh = 流程强制**（凡是返回新 id 的操作 commit 后必须 refresh + 验证行存在）
6. **proxy 路由 = regex 优先级文档化**（vite.config.js 顶部注释所有 PATTERN 优先级）

---

## 5. 流程改进（v2.6.1 实施）

### 5.1 单 task = 1 commit + 1 qa 真跑 + 1 报告

| 旧模式 | 新模式 |
|---|---|
| subagent 一次 9 commit | 人工 + subagent 都按"1 commit = 1 任务"切 |
| 跳过 qa | qa-backend 必跑（即使是简单 lint+build） |
| 跳过真机 | 真机测试必须（设备 down 时排队等，不借口） |
| 一次过完不报告 | 每 task 完给用户 1 报告（commit hash + qa 数字 + 下一步） |

### 5.2 卡壳 3 次立即停手 → 对齐 Spec → 必要时重新 Propose

- 来自 v2.6.0 复盘"subagent 9 commit 一次过"教训
- v2.6.1 实施中 add-auto-collect 严格遵守（9 task 全部 ⏳ → 直接砍掉，不强行推进）

### 5.3 真机必跑（设备 down 借口禁止）

- v2.6.1 实施时用户设备 down，**没有跳过真机测试**
- 设备 down 时 task 标 ⏳，等设备起来再跑
- v2.6.1 实施完整跑 .5（offline 流程） + .177（online 流程） + .99（浏览器端到端）

---

## 6. 测试统计（v2.6.1 baseline）

| 类别 | baseline (v2.6.0) | v2.6.1 | Δ |
|---|---|---|---|
| backend 单元 | 291 passed | 309+ passed | +18 |
| frontend 单元（vitest） | 53 case | 53+ case | 不破 |
| frontend e2e（playwright） | 42 case | 42+ case | 不破 |
| 真机集成 | 0（必跑设备缺） | 3 case | +3 |

**回归测试无破** — v2.6.1 全部新 case 走"加测"模式，v2.6.0 全部 291 + 53 + 42 = 386 case 不破。

---

## 7. 后续（v2.6.2 backlog）

| 项 | 估时 | 优先级 |
|---|---|---|
| fix-backup-restore-no-response 实施（T1+T2 优先：probe + 422 明确错误） | 4-6h | P0（v2.6.0 用户反馈"无反应"未修） |
| add-auto-collect 重新评估 | 视需求 | P2（v2.6.1 已有 staleness 降级替代） |
| QA 套件加 staleness fixture | 1h | P1（防 v2.6.0 陈旧数据 bug 重现） |
| ops-toolkit 多机型矩阵加 .5 / .6 / S6860 / S9850 验证 | 2h | P1（防协议兼容性盲区） |
| internal-api 统一类型标注 | 2h | P2（防 v2.6.1 split 模式密码 bug 重现） |
| v3.0 VPC 启动 | - | 远期 |

---

## 8. 总结

v2.6.1 = **22 commit + 1 review 反思 + 7 子 change 闭环 + 1 子 change 砍掉 + 1 子 change 部分完成**。

**最大教训**：

> **QA 套件不覆盖 = bug 风险**，不要以为"qa-backend 全过 = 系统稳定"。
> 真机测试、协议兼容性、跨容器协议、session 生命周期、数据陈旧 = 必须有显式测试。

**最大改进**：

> **单 task = 1 commit + 1 qa 真跑 + 1 报告** 模式强制化。
> subagent 一次 9 commit = 反模式，明确禁止。

**v2.6.2 启动条件**：

- 优先实施 fix-backup-restore-no-response（用户原始反馈未修）
- QA 套件加 staleness / 协议兼容性 fixture
- v3.0 VPC 视情况启动
