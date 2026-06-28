## ADDED Requirements

### Requirement: 手动单设备配置备份

`POST /api/devices/{id}/backup` MUST 触发对指定设备的 SFTP 拉取，从设备拉取 `startup.cfg` 和 `running.cfg`（默认都拉，body 可选 `types: ["startup"]` 仅拉一个）。每个文件落盘到 `/data/backups/{device_id}/{ISO8601}_{type}.cfg` 并在 `backups` 表插入一条记录。**不引入定时调度**。

#### Scenario: 单设备双类型备份
- **WHEN** 用户对设备 192.168.100.4 (id=4) 触发备份（不指定 types）
- **THEN** 后端拉 `startup.cfg` 和 `running.cfg`，落盘 2 个文件 + 2 条 records，返回 `{"success": true, "data": {"backups": [{id, type, size, hash}, ...]}}`

#### Scenario: 仅拉 startup
- **WHEN** body `{"types": ["startup"]}`
- **THEN** 后端只拉 `startup.cfg`，返回 1 个备份记录

#### Scenario: SFTP 失败
- **WHEN** 设备不可达或 SFTP 失败
- **THEN** 后端返回 `success=false, error="备份失败: SSH 连接失败"`，不创建任何备份记录

#### Scenario: 备份后自动轮转
- **WHEN** 备份成功后该设备已有 ≥5 个非锁定备份
- **THEN** MUST 删除最旧的非锁定备份（最旧 `created_at`）

### Requirement: 备份文件管理 API

| 端点 | 行为 |
|---|---|
| `GET /api/devices/{id}/backup` | 列表该设备所有备份（id/filename/type/size/created_at/locked） |
| `GET /api/devices/{id}/backup/{bid}` | 下载文件（`Content-Disposition: attachment; filename="{filename}"`） |
| `DELETE /api/devices/{id}/backup/{bid}` | 删除（**锁定状态 MUST 拒绝，返回 403**） |
| `POST /api/devices/{id}/backup/{bid}/lock` | body `{"locked": true}` 锁定 / `{"locked": false}` 解锁 |

#### Scenario: 列表返回
- **WHEN** 调用 list API
- **THEN** MUST 返回按 `created_at DESC` 排序的备份列表

#### Scenario: 下载
- **WHEN** 备份 id 存在
- **THEN** 后端返回文件流，文件名用原始 `filename`，`Content-Type: application/octet-stream`

#### Scenario: 删除锁定备份
- **WHEN** 备份 `locked=True` 时调 DELETE
- **THEN** 返回 `success=false, error="备份已锁定，请先解锁再删除"`，HTTP 403

#### Scenario: 设备删除级联清理
- **WHEN** 设备被删除
- **THEN** MUST 自动删除该设备所有备份文件 + 数据库记录（CASCADE）

### Requirement: 配置回滚

`POST /api/devices/{id}/backup/{bid}/restore` MUST 从指定备份还原到设备。**首选 NETCONF `load-config`**，**fallback SSH 推送 + `startup saved-configuration`**（实施时探测 192.168.100.4 后定）。

#### Scenario: NETCONF load-config 成功
- **WHEN** 备份存在且 H3C 设备支持 NETCONF load-config
- **THEN** 后端 NETCONF 推送配置到设备，返回 `success=true, "配置已还原"`

#### Scenario: SSH 推送回滚
- **WHEN** NETCONF load-config 不可用，fallback SSH
- **THEN** 后端 SFTP 推送 cfg 到设备的 `startup.cfg` + 执行 `startup saved-configuration`，返回 success

#### Scenario: 回滚失败保留原配置
- **WHEN** 回滚过程中网络中断或设备拒绝
- **THEN** 后端 MUST 返回 `success=false, error="回滚失败: ..."`，不破坏设备当前配置

#### Scenario: 回滚二次确认
- **WHEN** 前端调用 restore API
- **THEN** MUST 先在 UI 弹 `ConfirmModal`（variant='danger'，title="回滚配置"），显示备份名 + 时间 + "该操作将覆盖设备当前配置"，确认后才调 API

### Requirement: 全量备份

`POST /api/backups` MUST 对所有设备并发触发 `create_backup(device_id)`。**单台失败不影响其他**。返回 `{"total": N, "success": K, "failed": [{device_id, error}, ...]}`。

#### Scenario: 全量备份部分失败
- **WHEN** 6 台设备中 1 台不可达
- **THEN** MUST 返回 `{"total": 6, "success": 5, "failed": [{device_id: 7, error: "..."}]}`，其他 5 台的备份全部成功

#### Scenario: 全量备份并发
- **WHEN** 调用全量备份
- **THEN** 后端 MUST `asyncio.gather` 并发执行，每台独立 `record_log`

### Requirement: 轮转策略：5 份未锁定 + 锁定保护

每次新备份创建成功后 MUST 立即执行轮转：
- 查询该设备所有 `locked=False` 备份
- 按 `created_at ASC` 排序
- 保留最新 5 份，**删除超出部分**（最旧非锁定）
- `locked=True` 的备份**不参与轮转**，永久保留直到用户主动解锁/删除

#### Scenario: 触发 7 次非锁定备份
- **WHEN** 同一设备连续触发 7 次非锁定备份
- **THEN** 该设备 MUST 仅保留 5 份（最近 5 次），最早 2 次被自动删除

#### Scenario: 锁定备份不被轮转
- **WHEN** 备份 A 被锁定，备份 B/C/D/E/F 是非锁定的最新 5 份
- **THEN** 触发第 6 次非锁定备份 G → B 被轮转（最旧非锁定），A 仍保留

### Requirement: Docker volume 持久化

`docker-compose.dev.yml` MUST 新增 volume `h3c-netctrl-backups:/data/backups`，后端启动时 MUST 创建 `/data/backups` 目录（如不存在）并确保可写。

#### Scenario: 容器重启数据保留
- **WHEN** 容器重启后
- **THEN** `/data/backups/` 下历史备份文件**全部保留**

#### Scenario: volume 挂载检查
- **WHEN** 后端启动
- **THEN** MUST 在日志中打印 `backup_dir={BACKUP_DIR}, exists={True/False}`

### Requirement: 配置注入

`.env.example` MUST 新增：
- `BACKUP_DIR=/data/backups`（备份文件存储路径）
- `BACKUP_KEEP=5`（每设备保留非锁定份数）

后端 MUST 从环境变量读取这两项，提供默认值（`/data/backups` / `5`）。

#### Scenario: 自定义 BACKUP_DIR
- **WHEN** `.env` 中设置 `BACKUP_DIR=/custom/path`
- **THEN** 后端 MUST 使用该路径，**而非默认**

### Requirement: 前端备份管理 UI

`frontend/src/components/BackupListModal.vue` MUST 提供：
- 列表：表格 / 时间 / 类型（startup / running）/ 大小 / 锁定状态（🔒/🔓）
- 操作按钮：下载 / 删除 / 锁定切换 / 回滚
- 顶部"新建备份"按钮（弹小 Modal 选 startup / running / 两者）
- 回滚：弹 `ConfirmModal`（danger），确认后调 `/restore`

`frontend/src/views/Devices.vue` 表格行 MUST 加"备份"按钮（操作列），点击打开 BackupListModal。

`frontend/src/views/CMDB.vue` 顶部 MUST 加"全量备份"按钮，点击调 `POST /api/backups`，结果用 toast / 顶部 banner 展示 `total / success / failed`。

#### Scenario: 备份列表显示
- **WHEN** 打开 BackupListModal
- **THEN** MUST 列出该设备所有备份，按时间倒序，锁定项右上角 🔒 图标

#### Scenario: 锁定切换
- **WHEN** 点击 🔓 按钮
- **THEN** 调 `POST /api/devices/{id}/backup/{bid}/lock {locked: true}`，UI 立即更新为 🔒

#### Scenario: 删除提示
- **WHEN** 锁定状态下点击"删除"
- **THEN** MUST 弹 toast/banner 提示"备份已锁定，请先解锁再删除"，不调 API

#### Scenario: 回滚二次确认
- **WHEN** 点击"回滚"按钮
- **THEN** MUST 弹 `ConfirmModal` variant='danger'，title="回滚配置"，message 含备份名 + 时间 + 警告文案，确认后调 restore API

#### Scenario: 全量备份结果
- **WHEN** 点击 CMDB "全量备份"按钮
- **THEN** MUST 调 `POST /api/backups`，完成后顶部 banner 显示 "全量备份完成: 6 成功 / 0 失败"

## MODIFIED Requirements

（无现有 spec 修改）
