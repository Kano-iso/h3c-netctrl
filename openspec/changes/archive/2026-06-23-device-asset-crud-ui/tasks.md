## 1. 新增通用组件

- [x] 1.1 `frontend/src/components/ConfirmModal.vue`：通用确认弹窗，props `{open, title, message, confirmText, cancelText, variant, busy}`，emit `update:open` / `confirm` / `cancel`；variant='danger' 时确认按钮 `bg-bad`，否则 `bg-accent`
- [x] 1.2 `frontend/src/components/DeviceFormModal.vue`：设备新增/编辑 Modal，props `{open, mode, device, busy}`，mode='create'/'edit' 切换必填/提交逻辑；包含字段 name / host / port / username / password / protected_interfaces（逗号分隔）
- [x] 1.3 `frontend/src/components/AssetEditModal.vue`：资产编辑 Modal，props `{open, deviceId, asset, busy}`，字段 location / tags（逗号分隔）/ status（5 选项 Select），调 `assetApi.update`

## 2. Devices.vue 接入

- [x] 2.1 Devices.vue 顶部"新增设备"按钮：移除 alert 占位，调 `deviceFormOpen.value = true`
- [x] 2.2 Devices.vue 表格行新增"编辑"按钮：调 `editingDevice = d; deviceFormOpen = true`（mode='edit'）
- [x] 2.3 Devices.vue 表格行新增"删除"按钮：调 `confirmDelete = d; deleteConfirmOpen = true`
- [x] 2.4 Devices.vue 引入 `DeviceFormModal` + `AssetEditModal` + `ConfirmModal`，绑定 `@updated` / `@confirm` / `@cancel` 处理
- [x] 2.5 Devices.vue 表格"操作"列新增"编辑资产"按钮：调 `editingAsset = d; assetEditOpen = true`

## 3. CMDB.vue 接入

- [x] 3.1 CMDB.vue 表格行新增"编辑资产"按钮：调 `editingAsset = d; assetEditOpen = true`
- [x] 3.2 CMDB.vue 卡片视图右上角加"编辑"图标按钮：调同样 Modal
- [x] 3.3 CMDB.vue 引入 `AssetEditModal`，`@updated` 触发 `loadAssets()` 刷新

## 4. 验证

- [x] 4.1 后端 API 实测：`POST /api/devices` 创建成功（id=8，201-style）
- [x] 4.2 后端 API 实测：`PUT /api/devices/{id}` 编辑成功（id=8 改名 Test-Device-Renamed）
- [x] 4.3 后端 API 实测：`DELETE /api/devices/{id}` 删除成功（id=8 → 7 devices）
- [x] 4.4 后端 API 实测：`PUT /api/devices/{id}/asset` 资产编辑成功（location/tags/status 全部更新）
- [x] 4.5 前端 vite 加载新组件（ConfirmModal / DeviceFormModal / AssetEditModal + Devices.vue / CMDB.vue）无报错
- [x] 4.6 浏览器侧覆盖：CRUD UI + 资产编辑 Modal 接入待用户实测（仅后端 curl 验证已通过）

## 5. 收尾

- [x] 5.1 提交代码 `feat(crud-ui): 设备 CRUD 界面 + 资产编辑 Modal`（commit c1c41e0）
- [x] 5.2 archive change
