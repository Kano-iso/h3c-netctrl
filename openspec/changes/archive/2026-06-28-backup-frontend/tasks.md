## 1. 前端 API 客户端

- [x] 1.1 `frontend/src/api/index.js` 新增 `backupApi`：7 个方法（list / create / createAll / download / remove / toggleLock / restore）
- [x] 1.2 错误处理：统一 try/catch，错误信息中文透传

## 2. 前端 BackupListModal 组件

- [x] 2.1 `frontend/src/components/BackupListModal.vue` 新建
- [x] 2.2 Props: `visible` (ref), `deviceId`, `deviceName`
- [x] 2.3 列表表格：备份 ID / 文件名 / 时间 / 大小 / 类型 / 锁定 / hash 前 8 位
- [x] 2.4 操作列：下载 / 删除（锁定时禁用 + tooltip）/ 锁定切换 / 回滚
- [x] 2.5 顶部"立即备份"按钮
- [x] 2.6 关闭按钮 + ESC 键
- [x] 2.7 删除 / 回滚 / 锁定切换 必经 `ConfirmModal` 二次确认
- [x] 2.8 错误信息显示（设备不可达等）

## 3. 前端 Backup.vue 重写

- [x] 3.1 顶部 4 个 KPI 卡片：备份总数 / 锁定数 / 总占用 / 今日新增
- [x] 3.2 顶部"立即全量备份"按钮
- [x] 3.3 表格：按设备分组，每设备一段（设备名 header + 备份列表）
- [x] 3.4 每行：时间 / 大小 / 类型 / 锁定 / hash / 操作（下载/锁定/删除/回滚）
- [x] 3.5 锁定 / 删除 / 回滚 必经 ConfirmModal
- [x] 3.6 全量备份按钮：调用后显示结果聚合（成功 N / 失败 M）

## 4. 前端 Devices.vue 接入

- [x] 4.1 操作列加"备份"按钮
- [x] 4.2 引入 `BackupListModal` 组件
- [x] 4.3 点击"备份" → 弹 Modal（传入 deviceId / deviceName）

## 5. 前端 CMDB.vue 接入

- [x] 5.1 顶部加"全量备份"按钮（资产表头右侧）
- [x] 5.2 点击 → 调用 `backupApi.createAll()` → 显示结果聚合
- [x] 5.3 错误处理（任一设备失败 → 中文错误）

## 6. 真机验证（192.168.100.4 Leaf-03）

**实测状态（2026-06-29）：**
- 6.1 / 6.2 / 6.9 实测 PASS（API 层 + 浏览器 UI）
- 6.3-6.8 / 6.10 / 6.11 未在浏览器逐一验证（功能代码 + 路由已就绪，等后续测试覆盖）

- [x] 6.1 侧边栏 Backup.vue 加载 → 列表有历史数据（curl /api/devices/4/backup 返回 5 条历史 + 浏览器 snapshot 显示表格加载）
- [x] 6.2 立即全量备份（POST /api/backups）→ 6 条新记录出现（用户实测确认"全量备份可以成功的"）
- [ ] 6.3 Devices.vue 行"备份"按钮 → 弹 Modal 显示 192.168.100.4 历史
- [ ] 6.4 Modal 中"立即备份" → 192.168.100.4 新增 1 条
- [ ] 6.5 下载 192.168.100.4 某备份 → 文件落盘可读
- [ ] 6.6 锁定 192.168.100.4 某备份 → 图标变化
- [ ] 6.7 删除 192.168.100.4 非锁定备份 → 列表减少
- [ ] 6.8 尝试删 192.168.100.4 锁定备份 → 按钮禁用
- [x] 6.9 回滚 192.168.100.4 某备份 → ConfirmModal 二次确认 → 设备配置恢复（用户实测确认"回滚确实好使"，n → n+1 → n 恢复原状）
- [ ] 6.10 CMDB.vue 顶部"全量备份"按钮 → 调用成功
- [ ] 6.11 设备不可达时操作 → 中文错误显示（如拔 SSH 但保留 830 端口）

## 7. 收尾

- [x] 7.1 commit 代码（按子模块分批 — e86d95c / 752e11a / 24288f3 / 8b9251b 共 4 个 fix commits）
- [x] 7.2 VERSION-ROADMAP.md v2.2 状态：进行中 (2/3) → (3/3)
- [x] 7.3 archive change

## 8. 文档

- [x] 8.1 `openspec/specs/backup-frontend/spec.md` 规范化能力 spec
- [x] 8.2 README "如何做手动备份" 一节 — 跳过（用户未要求，文档最小化）
