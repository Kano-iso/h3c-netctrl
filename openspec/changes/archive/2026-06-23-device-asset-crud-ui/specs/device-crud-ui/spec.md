## ADDED Requirements

### Requirement: Devices 页面提供新增设备入口

`frontend/src/views/Devices.vue` 顶部 MUST 显示"新增设备"按钮，点击 MUST 打开 `DeviceFormModal`（mode='create'）。提交时 MUST 调 `POST /api/devices`，必填校验（name / host / username / password）失败 MUST 在 Modal 内显示中文错误，不关闭 Modal。

#### Scenario: 新增成功
- **WHEN** 用户在新增设备 Modal 填写 name="Spine-02"、host="192.168.100.101"、username="admin"、password="Admin123!@#" 并提交
- **THEN** 前端调 `deviceApi.create({name, host, port, username, password, protected_interfaces})`；后端返回 `success=true` 后 Modal 关闭、`loadDevices()` 自动刷新、表格新增一行

#### Scenario: 必填字段缺失
- **WHEN** 用户提交时 host 为空
- **THEN** 前端 MUST 在 Modal 顶部 banner 显示"缺少必填字段: host"（不调后端），Modal 保持打开

#### Scenario: 后端报错
- **WHEN** 后端返回 `success=false, error="设备名已存在"`
- **THEN** 前端 MUST 在 Modal 顶部 banner 显示该错误，Modal 保持打开，按钮恢复可点击

### Requirement: Devices 页面提供编辑设备入口

`Devices.vue` 表格每行 MUST 显示"编辑"按钮，点击 MUST 打开 `DeviceFormModal`（mode='edit'）并预填当前设备字段（密码字段留空，placeholder 写"留空表示不修改"）。提交时 MUST 调 `PUT /api/devices/{id}`。

#### Scenario: 编辑保存
- **WHEN** 用户编辑设备 name="Spine-02-Renamed"、host 不变、不填 password 并提交
- **THEN** 前端调 `deviceApi.update(id, {name: "Spine-02-Renamed"})`（password 字段不传）；Modal 关闭、列表刷新

#### Scenario: 修改密码
- **WHEN** 用户在编辑 Modal 填写新 password="NewPass!@#456" 并提交
- **THEN** 前端调 `deviceApi.update(id, {password: "NewPass!@#456"})`；后端重新加密入库

#### Scenario: 保护口编辑
- **WHEN** 用户在编辑 Modal 填写 protected_interfaces="1,5,22"
- **THEN** 前端 split + parseInt + filter 后提交 list `[1, 5, 22]`；保存后表格"保护口"列显示 🛡 3

### Requirement: Devices 页面提供删除设备入口 + 二次确认

`Devices.vue` 表格每行 MUST 显示"删除"按钮，点击 MUST 打开 `ConfirmModal`（variant='danger'）显示设备名 + IP + "该操作不可恢复，关联的资产信息将一并删除"提示。确认后 MUST 调 `DELETE /api/devices/{id}`，成功后刷新列表。

#### Scenario: 删除确认
- **WHEN** 用户点击"删除" → 看到红色确认弹窗（含 "Spine-01" 和 "192.168.100.100"） → 点击"确定删除"
- **THEN** 前端调 `deviceApi.delete(id)`；后端级联删除 Asset；Modal 关闭、列表移除该行

#### Scenario: 取消删除
- **WHEN** 用户点击"删除" → 看到确认弹窗 → 点击"取消"
- **THEN** 前端不调任何 API、Modal 关闭、设备保留

#### Scenario: 删除失败
- **WHEN** 后端返回 `success=false, error="设备正在使用中"`
- **THEN** Modal 关闭失败时保持打开（如已关则 toast/banner 提示）、按钮恢复可点击

### Requirement: DeviceFormModal 组件通用

`DeviceFormModal.vue` MUST 通过 `mode: 'create' | 'edit'` prop 切换行为：
- `mode='create'`：name / host / username / password 必填，标题"新增设备"，提交调 `deviceApi.create`
- `mode='edit'`：所有字段可选，标题"编辑设备：{设备名}"，提交调 `deviceApi.update(id, ...)`，密码字段留空表示不修改
- MUST 用 `v-model:open` 控制显示
- MUST 包含字段：name / host / port（默认 830）/ username / password / protected_interfaces（逗号分隔）
- MUST 在提交期间禁用"确定"按钮并显示 loading 文本
- MUST 校验失败 / 后端报错时在 Modal 顶部 banner 显示中文错误

#### Scenario: 保护口字段校验
- **WHEN** 用户输入 protected_interfaces="1,abc,5.5,22"（混合非整数）
- **THEN** 前端 MUST split + parseInt + filter 后仅保留 `[1, 22]`，跳过非数字项

### Requirement: ConfirmModal 通用组件

`ConfirmModal.vue` MUST 通过 props 接收 `title` / `message` / `confirmText` / `cancelText` / `variant='danger' | 'default'`，通过 `v-model:open` 控制显示，通过 `emit('confirm')` / `emit('cancel')` 通知调用方。variant='danger' 时确认按钮 MUST 用红色（`bg-bad`），variant='default' 时用普通主色（`bg-accent`）。

#### Scenario: 危险确认弹窗
- **WHEN** 父组件传入 variant='danger' / title='删除设备' / message='...'
- **THEN** Modal 显示红色"删除"按钮 + 普通灰色"取消"按钮
