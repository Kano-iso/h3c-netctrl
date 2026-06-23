## Why

发布前用户实测发现资产管理完全不可用：

1. **Devices.vue 顶部"新增设备"按钮**：实际只是 `alert('新增设备功能待实现（V2.2）')` 的占位弹窗，**后端 `POST /api/devices` 早就实现**（device.py L49-84）但前端没接
2. **设备编辑**：Devices.vue 表格行只有"连接测试"按钮，**没有编辑入口**，但后端 `PUT /api/devices/{id}` 已实现（device.py L87-115）
3. **设备删除**：完全没有删除按钮，但后端 `DELETE /api/devices/{id}` 已实现（device.py L118-129），`Asset` model 设置了 `cascade="all, delete-orphan"`
4. **资产管理（CMDB）**：CMDB.vue 只能"全量刷新"（SSH 采集硬件），**位置 / 标签 / 状态完全无法手动编辑**，但后端 `PUT /api/devices/{id}/asset` 已实现（asset.py L56-77）

后端 100% 能力具备，前端 UI 缺失 → 用户视角下整个资产管理形同写死。这是发布前必须修复的功能性 bug。

## What Changes

### Devices.vue 改造

- **"新增设备"按钮**接 `deviceApi.create`，弹**新增设备 Modal**
- **表格行新增"编辑"按钮**：弹**编辑设备 Modal**（与新增共用同一组件，预填字段）
- **表格行新增"删除"按钮**：弹**二次确认 Modal**（显示设备名 + IP），确认后调 `deviceApi.delete`，后端级联删 Asset
- **保护口**：Modal 包含"保护口（if_index 列表，逗号分隔数字）"字段

### AssetEditModal.vue 新组件

- 跨 CMDB / Devices 复用
- 字段：位置（text input）/ 标签（逗号分隔 text input）/ 状态（Select，5 个值）
- 提交调 `assetApi.update(deviceId, {location, tags, status})`
- 成功后刷新当前视图

### CMDB.vue 改造

- **表格行每行加"编辑资产"按钮** → 打开 AssetEditModal
- 卡片视图：卡片右上角加"编辑"图标
- 顶部 actions 加"批量编辑资产"按钮（选中后多设备同一修改），本期**先不做批量**，仅单设备编辑

### 复用 / 新建

- **新建** `DeviceFormModal.vue`：新增 + 编辑设备共用，预填 + 校验
- **新建** `ConfirmModal.vue`：删除确认、二次确认通用
- **新建** `AssetEditModal.vue`：资产编辑
- **前端** `api/index.js`：`deviceApi` 已齐全（list/get/create/update/delete/test），`assetApi` 已齐全（get/update/refresh），**无需新增**

## Capabilities

### New Capabilities
- `device-crud-ui`：设备 CRUD 界面（新增/编辑/删除 + 二次确认）
- `asset-edit-ui`：资产手动编辑界面（位置/标签/状态 Modal）

### Modified Capabilities
- （无现有 spec 修改）

## Impact

- **代码**：
  - `frontend/src/views/Devices.vue`：替换占位 alert、加编辑 / 删除按钮、引入 Modal
  - `frontend/src/views/CMDB.vue`：每行加"编辑资产"入口
  - `frontend/src/components/`：新增 `DeviceFormModal.vue` / `AssetEditModal.vue` / `ConfirmModal.vue` 三个组件
- **API 兼容性**：后端不动，调用现有 `deviceApi.create/update/delete` + `assetApi.update`
- **数据库**：无迁移
- **依赖**：无新增（Select 组件已存在）
- **回归**：发布前用户实测现有 CRUD 流程全部失败，修复后立即可走通
- **安全**：删除操作二次确认 Modal；密码字段（新增/编辑）使用 `type="password"` 不回显
