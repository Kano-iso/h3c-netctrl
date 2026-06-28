# v2.2.0 Release Notes

**发布日期**：2026-06-29
**Tag**：`v2.2.0`
**对比 v2.1**：4 个主 change + 2 个 patch + 4 个收尾 bug fix，共 19 commits

---

## 1. 主题

**网控增强** —— 把 v2.1.x 灰度的备份前端补齐，新增接口 VPN 联动 + L2/L3 状态展示，补齐 link type / IP 编辑能力，修复收尾发现的 4 个关键 bug。

---

## 2. 包含的 changes

| change-id | 主题 | 归档目录 | 关键能力 |
|---|---|---|---|
| `interface-vpn-instance-and-l2-l3` | 接口 L2/L3 展示 + IP + VPN instance 联动 | [2026-06-28-interface-vpn-instance-and-l2-l3](openspec/changes/archive/2026-06-28-interface-vpn-instance-and-l2-l3/) | VPN 创建/绑定/解绑/删除；接口 L2/L3 + mode 展示 |
| **`v2.2.1 patch`** `fix-vpn-and-l2l3-ux-bugs` | unbind 预校验 + Modal 顶部加现有 VPN 列表 | [2026-06-28-fix-vpn-and-l2l3-ux-bugs](openspec/changes/archive/2026-06-28-fix-vpn-and-l2l3-ux-bugs/) | UX bug 修复（"解绑后看不到实例"） |
| **`v2.2.2 patch`** `fix-vpn-edit-capabilities` | link type 调整 + L3 接口配 IP | [2026-06-28-fix-vpn-edit-capabilities](openspec/changes/archive/2026-06-28-fix-vpn-edit-capabilities/) | 补齐"调整 link type"和"配 L3 IP"两个缺失能力 |
| `backup-frontend` | 备份前端 UI（Devices.vue 表格行 + BackupListModal + CMDB 全量按钮） | [2026-06-28-backup-frontend](openspec/changes/archive/2026-06-28-backup-frontend/) | 全局 Backup 页 + 设备行入口 + CMDB 顶部全量按钮 |

**说明**：v2.1.x 灰度版 `v21x-patch-backup-backend`（后端 7 个 API）随本次发版合并，归档为 [2026-06-28-v21x-patch-backup-backend](openspec/changes/archive/2026-06-28-v21x-patch-backup-backend/)。

---

## 3. 收尾时实测发现 + 修复的 4 个 bug

| commit | 根因 | 影响 |
|---|---|---|
| `e86d95c` fix(backup-frontend): list 嵌套结构 / 类型列 / deviceId null | 后端 list 返回 `{device_id, total, backups:[...]}` 嵌套结构，前端 `r.data` 当数组用 → 页面崩溃；类型列用错字段名；BackupListModal 在 deviceId=null 时挂载报 Vue warn | Backup.vue 加载崩溃、BackupListModal 类型列空白、Vue 控制台 warn |
| `752e11a` fix(backup-frontend): record_log 去重 + Logs actionOptions | 路由层和 BackupManager 内部均调用 `record_log` → 日志重复 + device_name 字段不一致；Logs.vue 缺少 backup_* actionOptions → 无法按操作类型筛选 | 备份操作日志重复 / 无法按 backup 类目筛日志 |
| `24288f3` fix(backup-frontend): backupApi.create 缺 body → 422 | `apiCall` POST 时 Content-Type 写死但缺 body 字段 → fetch 发空 body + Content-Type: application/json → FastAPI 422 "Field required: body" → `r.success` undefined → 前端显示"备份失败" | **单设备备份失败（用户实测反馈）** |
| `8b9251b` fix(backup-frontend): restore 默认 with_reboot=true | 前端 `backupApi.restore` 不传 body → 后端 `with_reboot` 默认 False → 只"推 + set as startup"不 reboot → 设备 running-config 不变 → 用户实测"回滚没效果" | **回滚看起来无效（用户实测反馈）** |

**修复策略**：
- `e86d95c` / `752e11a` / `24288f3` —— 前端代码层修
- `8b9251b` —— 改前端默认 `with_reboot=true`（端到端：推 + set as startup + reboot + verify），同时 ConfirmModal 加 `⚠️ 设备将重启 60-120s` 警告，按钮文案改"回滚并重启"

---

## 4. 关键能力清单（用户视角）

### 备份 / 回滚
- **3 个入口**：全局 Backup 页（顶部 4 个 KPI 卡片 + 立即全量按钮）/ 设备行"备份"按钮（Devices.vue 表格行） / CMDB 顶部"全量备份"按钮
- **1 个 Modal 组件**：`BackupListModal`（备份列表 + 5 个操作：下载 / 锁定 / 删除 / 回滚 / 立即备份）
- **后端 7 个 API**：单设备 backup / 全量 backup / list / download / delete / lock / restore
- **回滚策略**：全文本 + SCP 文件级替换（业界主流：RANCID / Oxidized / Ansible Network / NAPALM / H3C iMC），不维护 NETCONF 元素白名单
- **回滚默认端到端**：`with_reboot=true`（推 + set as startup + reboot + retry SSH + verify running-config）
- **轮转**：每设备自动保留最新 5 份未锁定备份，锁定不参与轮转
- **存储**：本地文件 + DB 记录元数据（`BACKUP_DIR` 容器 volume 挂载）

### 接口 VPN 联动
- **查看**：接口表格展示 layer (L2/L3) + mode (access/trunk) + VPN instance 绑定关系
- **创建 VPN instance**：`L3vpn` 模型（YANG 路径 `Ifmgr/Interfaces/Interface/L3vpn`）
- **绑定**：`bind_interface_vpn`（NETCONF edit-config 推 `L3vpn/VpnInstances/VpnInstance`）
- **解绑**：unbind 预校验（先查 L3vpn 现状，零绑定才允许）+ 弹"已绑定 X 个 VPN，是否继续"二次确认
- **删除 VPN instance**：`delete_vpn_instance`（无绑定才能删）

### 接口 L2/L3 + link type + IP 编辑
- **改 link type**（v2.2.2 patch）：`access` ↔ `trunk`，NETCONF edit-config 推 `Ifmgr/Interfaces/Interface/LinkType`，改前 `ConfirmModal` 二次确认"会清空 X 现有 allowed-vlan / access-vlan"
- **L3 接口配 IP**（v2.2.2 patch）：增 / 改 / 删 IPv4 address，NETCONF `IPV4ADDRESS/Ipv4Addresses/Ipv4Address` 模型（清空而非单删是 H3C V7 模型的实际行为）
- **真机验证**：192.168.100.5（用户实测发现 bug 的设备）

---

## 5. 端到端实测状态

| 测试 | 设备 | 状态 |
|---|---|---|
| 单设备 backup | 192.168.100.4 (Leaf-03) | ✅ API + UI |
| 全量 backup | 全部 6 台（test 1.1.1.1 不可达 → 5 成功 1 失败，符合预期） | ✅ UI（用户实测"全量备份可以成功的"） |
| 备份下载 | Leaf-03 | ✅ API |
| 备份锁定 / 解锁 / 删除 | Leaf-03 | ✅ API |
| 锁定禁删 | Leaf-03 | ✅ API |
| **回滚 + n→n+1→n 恢复原状** | Leaf-03 | ✅ **用户实测确认"回滚确实好使"**（reboot + verify 端到端通过） |
| VPN 创建 / 绑定 / 解绑 / 删除 | 192.168.100.5 | ✅ UI（v2.2.1 patch 收尾时实测） |
| 改 link type | 192.168.100.5 | ✅ UI（v2.2.2 patch 收尾时实测） |
| L3 接口配 IP | 192.168.100.5 | ✅ UI（v2.2.2 patch 收尾时实测） |

**未逐一验证**（功能代码 + 路由已就绪）：
- 6.3-6.8 / 6.10 / 6.11 backup-frontend 浏览器 UI 项（Devices.vue 行入口 / Modal / 下载 / 锁定 / 删除 / 锁定禁删 / CMDB 顶部按钮 / 设备不可达错误显示）—— v2.2.1 follow-up 计划补

---

## 6. 已知问题 / 限制

1. **备份 UI 验证不全**：6.3-6.8 / 6.10 / 6.11 浏览器 UI 端到端未逐一测。功能代码 + 路由已就绪 + API 层全 PASS，UI 缺 follow-up
2. **回滚触发设备 reboot**：`with_reboot=true` 是默认行为，reboot 期间 SSH 断 60-120s；如需"不 reboot 模式"可显式传 `with_reboot=false`，但需手动 reload 才能让 running-config 生效
3. **backup-restore 不支持定时备份**：v2.1.x 灰度时已决定取消定时备份，仅手动
4. **OpenSpec 自动化测试覆盖**：当前无 E2E 框架（Playwright / Cypress 未引入），backup-frontend 6.x 类 bug 只能靠人肉或 curl 验证；v2.3 计划引入 Playwright + pytest + paramiko 双层自动化
5. **VPN instance 不可在 UI 创建**（仅 NETCONF 推）：v2.2 当前 UI 只支持"创建 → 立即绑定到当前接口"；如要"创建独立 VPN instance 不绑定"—— v2.3 评估

---

## 7. 升级 / 部署注意

- **数据库**：本次无 schema 变更（备份表 `Backup` 由 v2.1.x 灰度时建好，备份元数据表 `Backup` / 接口绑定关联表无新增字段）
- **环境变量**：本次无新增；如启用备份需 `BACKUP_DIR`（已存在，默认 `./data/backups`）
- **容器**：本次仍 monolith（core 容器未拆），v2.3 计划拆 `asset` 容器（cmdb + 备份）
- **回退路径**：`git revert` 本次 19 commits 即可；不影响 v2.1.x 之前的备份表（`Backup` 是 v2.1.x 灰度建的）

---

## 8. 关键 commit 序列（19 个）

```
a58dc64 docs(roadmap): v2.2.0 发版 + v2.3 backlog 落地
01a4983 chore(openspec): archive backup-frontend + 规范化 spec
8b9251b fix(backup-frontend): restore 默认 with_reboot=true
24288f3 fix(backup-frontend): backupApi.create 补 body 字段
752e11a fix(backup-frontend): backup 路由 record_log 去重
e86d95c fix(backup-frontend): list 嵌套结构 / 类型列 / deviceId null
b09e503 chore(openspec): archive v2.2.1 + v2.2.2 patches
01c10ad feat(interface): link type / IP 编辑能力 (v2.2.2)
a7f0531 docs(roadmap): v2.2 第一项追加 v2.2.1 patch
9e58096 fix(vpn): unbind 预校验补 L3vpn 查询 (v2.2.1)
0058b19 archive: fix-backup-manager-save-force-and-scp
edd6bb4 fix(backup): restore 支持 with_reboot
96a4389 fix(backup): save force 改 invoke_shell + SFTP 改 SCP
1651d10 docs(openspec): propose fix-backup-manager-save-force-and-scp
efd8b29 feat(backup-frontend): Devices.vue / CMDB.vue 接入
7828e90 feat(backup-frontend): Backup.vue 重写
7e36dab feat(backup-frontend): BackupListModal
85c4a79 feat(backup-frontend): api/index.js 加 backupApi
451023e docs(openspec): propose backup-frontend
```

---

## 9. 关联

- 父版本：[v2.1 frontend refactor](openspec/changes/archive/2026-06-23-v21-frontend-refactor/)（无单独 PRD，归档目录只含单 changes）
- 灰度版：[v2.1.x patch 备份后端](openspec/changes/archive/2026-06-28-v21x-patch-backup-backend/)（本次发版合并）
- 蓝图：[docs/CONTAINER-DECOUPLING.md](docs/CONTAINER-DECOUPLING.md)（v2.1.x 预留）
- 下一版：[VERSION-ROADMAP.md § 7 v2.3 backlog](VERSION-ROADMAP.md)

---

**最后更新**：2026-06-29
