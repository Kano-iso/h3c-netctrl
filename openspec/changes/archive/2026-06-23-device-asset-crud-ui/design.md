## Context

发布前用户实测资产管理 4 个核心能力（新增/编辑/删除设备、编辑资产）全部不可用，但后端 100% 已实现：
- `POST /api/devices`（device.py L49-84）— 创建设备
- `PUT /api/devices/{id}`（device.py L87-115）— 更新设备
- `DELETE /api/devices/{id}`（device.py L118-129）— 删除设备（级联删 Asset，model 已设置 `cascade="all, delete-orphan"`）
- `PUT /api/devices/{id}/asset`（asset.py L56-77）— 更新资产（location / tags / status）
- `POST /api/devices/{id}/asset/refresh`（asset.py L80-118）— SSH 采集硬件（已用）

前端现状：
- `Devices.vue` "新增设备"按钮只是 `alert('新增设备功能待实现（V2.2）')` 占位
- 表格行只有"连接测试"，无编辑/删除
- `CMDB.vue` 只有"全量刷新"，无位置/标签/状态编辑入口
- `api/index.js` 已导出完整 `deviceApi`（list/get/create/update/delete/test）+ `assetApi`（get/update/refresh），**无需改**

修复本质是**前端 UI 补全**：3 个新 Modal 组件 + Devices.vue / CMDB.vue 接入。

## Goals / Non-Goals

**Goals:**
- Devices.vue 提供完整 CRUD UI（新增 / 编辑 / 删除）
- 删除走"硬删 + 二次确认 Modal"（用户已选）
- 资产编辑走统一 Modal（位置 / 标签 / 状态），CMDB + Devices 都可触发
- 密码字段用 `type="password"`，编辑时留空表示不修改
- 保护口（`protected_interfaces`）编辑支持 if_index 逗号分隔列表

**Non-Goals:**
- 不实现批量编辑资产（用户暂不要求，后续 change）
- 不改后端 API / 数据库
- 不实现软删（用户决策"硬删 + 二次确认"）
- 不实现设备导入 / 导出 CSV（后续 change）
- 不实现资产 SSH 采集触发的 UI（已用"全量刷新"按钮）
- 不实现操作历史回滚

## Decisions

### 1. Modal 组件化复用

- **选择**：3 个新组件 `DeviceFormModal.vue`（新增/编辑共用）、`ConfirmModal.vue`（通用确认）、`AssetEditModal.vue`（资产编辑），通过 props 控制 mode / initialData
- **理由**：避免在 Devices.vue 内联大段 Modal 逻辑，组件可单独测试与跨页面复用
- **替代**：行内编辑 / 抽屉 Drawer。Modal 更轻量、聚焦单任务

### 2. 设备 Modal 模式切换

- **选择**：`mode` prop 接受 `'create' | 'edit'`，组件内部按 mode 切换：
  - 标题（新增设备 / 编辑设备）
  - 提交函数（`deviceApi.create` / `deviceApi.update`）
  - 必填字段（新增时 name/host/username/password 必填，编辑时全部可选）
- **理由**：新增/编辑表单结构一致，仅必填与提交不同，1 个组件覆盖 2 个场景
- **替代**：拆 2 个独立组件（DeviceCreateModal / DeviceEditModal）。代码重复，逻辑分散

### 3. 密码字段处理

- **选择**：
  - 新增模式：必填、明文 input
  - 编辑模式：留空表示不修改（避免明文密码在 UI 流转）；如填写则覆盖
- **理由**：避免明文密码在编辑表单预填（即便已解密也不应回显到 UI），用户主动修改才覆盖
- **替代**：始终必填（编辑时强制重新输入）。UX 累赘，密码未变更也要求重输不合理

### 4. 保护口输入：逗号分隔

- **选择**：`protected_interfaces` 字段用单个 `<input>`，占位提示"逗号分隔，如 1,5,22"
- **理由**：后端模型是 `JSON 字符串 list[int]`，前端用逗号分隔字符串最简
- **替代**：多 chip 输入（每个 if_index 单独 tag）。改动大、需求场景少（运维场景才需要），简化为单 input 即可
- **校验**：提交前 `split(',').map(s => parseInt(s.trim(), 10)).filter(Number.isInteger)`

### 5. 二次确认 Modal

- **选择**：`ConfirmModal.vue` 通用组件，props：`title`、`message`、`confirmText='确定'`、`cancelText='取消'`、`variant='danger' | 'default'`
- **理由**：删除操作不可逆，红色按钮 + 设备名/IP 信息确认；未来其他二次确认场景（批量删除等）可直接复用
- **替代**：浏览器原生 `confirm()`。与项目 UI 风格不统一，且 `alert/confirm` 在 OpenSpec 流程中已被决策禁止使用

### 6. AssetEditModal 状态字段

- **选择**：使用现有 `Select` 组件（CMDB/运维终端用过的），选项为后端 `valid_statuses`：online / offline / maintenance / decommissioned / unknown，对应中文：在线 / 离线 / 维护 / 已下线 / 未采集
- **理由**：复用 Select 组件保持 UI 一致；中文 label 通过 `getStatusLabel` 兜底
- **替代**：原生 `<select>`。原生 option 字体不可控（与运维终端决策一致）

### 7. 加载/错误反馈

- **选择**：Modal 提交时按钮 disabled + loading 文本（"创建中..." / "保存中..." / "删除中..."）；后端 `success=false` 时在 Modal 顶部红色 banner 显示 `error`
- **理由**：与现有 Modal 风格（如 batch）一致
- **替代**：toast 通知。引入新组件

### 8. 删除后自动刷新

- **选择**：`deviceApi.delete` 成功后调 `loadDevices()` 重新拉取列表
- **理由**：避免前端缓存导致已删除设备仍显示
- **替代**：手动刷新。让用户感知"我操作成功了"更重要

## Risks / Trade-offs

- **[风险] 编辑时密码字段留空表示不修改，前端需明确提示** → **缓解**：Modal 内 placeholder 写"留空表示不修改"
- **[风险] 保护口字段用户填非数字（"a,b,c"）会报错** → **缓解**：提交前 parseInt + filter，失败提示"保护口必须为 if_index 数字"
- **[风险] 删除后级联删 Asset + Log（如果 Log 也有外键）** → **缓解**：查看 model.py，`Log` 表与 `Device` 无 FK 关系（log 只存 device_id 不引用外键），不会被级联；Asset 有 FK + cascade。已确认安全
- **[风险] Modal 内提交时反复点击** → **缓解**：submitting 时按钮 disabled，onclick 拦截
- **[风险] 设备删除时若还有进行中的 NETCONF 连接** → **缓解**：连接在请求内创建（`with NetconfClient(...)`），不会跨请求持有，删除无竞争
- **[风险] 资产编辑 Modal 在 Devices / CMDB 都需要，组件传 prop 较多** → **缓解**：`v-model:open` + `deviceId` + `asset` 三个核心 prop，其他用默认值

## Migration Plan

- **部署**：纯前端改动，vite HMR 自动热更新；无后端重启、无 DB 迁移
- **回退**：仅前端 UI 改动，回退简单（`git revert` 即可），无数据损坏
- **数据**：不影响后端存储结构
- **首次发布后**：建议在数据库初始 seed 一条"演示设备"（已存在）
