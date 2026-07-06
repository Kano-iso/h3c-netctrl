# fix-asset-backup-state-sync — Proposal

## Why

资产（Asset）状态与备份入口未同步：即使资产 offline，用户仍可点"全量备份 / 单设备备份"按钮并成功执行。

**问题表现**：
- CMDB 页面某设备显示 offline（无最近采集记录）
- 用户点"采集"按钮触发 refresh_asset，失败（设备不在线）
- 但"备份"按钮仍可点，且实际能成功（因为 backup 走 SSH/NETCONF 通道，跟 asset 状态独立）
- 出现"资产说 offline 但备份成功"的逻辑矛盾

**根因**：
- 前端按钮 disabled 条件只看 device.status（设备自身状态，crud 字段），不看 asset.status（最近采集结果）
- 后端 backup 端点（`POST /api/devices/{id}/backup` 和 backup-async）没校验 asset 状态
- asset / backup / device 三套状态相互独立，没有交叉校验

## What Changes

- **后端**：
  - `backend/app/routers/backup.py` 同步备份 + 异步备份端点增加 asset.status 校验
  - 离线/未知资产返回明确错误（如 `err.BACKUP_DEVICE_OFFLINE`）
  - 用户明确选择"强制备份"时可绕过（v2.6.x 不暴露，留 TODO）
- **前端**：
  - `frontend/src/views/Devices.vue` "备份"按钮根据 `asset.status` 禁用
  - `frontend/src/views/CMDB.vue`（如有）"全量备份"按钮同样禁用
  - tooltip 解释为什么禁用（"资产未采集/离线，请先采集"）
- **i18n**：
  - 加 `error.backup.device_offline` 中英文 key
  - 加 `button.disabled.asset_offline` 提示 key

## 设计决策

### 决策 1：offline/never-collected 都禁用，只在 asset.status=online 时启用

- **理由**：asset 状态是"设备可达性"的最准确指标（refresh_asset 内部跑 SSH/NETCONF 自检）
- **取舍**：从采集到备份可能有时间差（asset 陈旧），但可通过 prompt 提示用户重采

### 决策 2：强制备份开关暂不暴露

- **理由**：先堵漏（offline 不能备份），强制备份是高风险操作（可能掩盖问题），推到 v2.7+
- **替代**：tooltip 提示用户"如确需备份，先点采集"（采集失败再判断）

## Apply 拆细（待 Propose 时细化）

按 OpenSpec 流程：
- T1 后端校验
- T2 前端按钮禁用
- T3 i18n key
- T4 测试
- T5 真机验证 + archive

## Impact

- **代码**：
  - `backend/app/routers/backup.py`（+asset 校验）
  - `frontend/src/views/Devices.vue`（按钮 disabled 条件）
  - `frontend/src/views/CMDB.vue`（如有）
  - `backend/app/i18n_keys.py`（+2 key）
  - `frontend/src/i18n/locales/*.json`（+2 key）
- **API**：行为变更（offline 备份 → 失败），但功能等价（用户可先采集再备份）
- **测试 baseline**：309 → 311+ passed（+2 unit）
- **用户体验**：
  - 修复前：asset offline 但可备份，结果矛盾
  - 修复后：asset offline 时按钮灰显 + tooltip 提示

## Non-Goals

- 不做强制备份开关（推到 v2.7+）
- 不改 asset 状态机（status: online / offline / never_collected / stale）
- 不改 backup 业务逻辑（走 SSH/NETCONF 通道不变）
- 不做 UI 状态实时刷新（前端依赖 dashboard 轮询）

## QA 验证计划

### 单元测试（2 case）

1. POST /api/devices/{id}/backup 在 asset.status=offline 时返回失败
2. POST /api/devices/{id}/backup 在 asset.status=online 时正常

### 集成测试（1 case）

1. 真机 .177 先采集 → 备份按钮可用 → 备份成功
2. 真机 .4 不可达 → 资产 offline → 备份按钮 disabled → 后端 422

## 报告（用户原始反馈）

> 全量备份这个方向，资产收集这边并没有把每一个资产都采集，有一些还是离线状态的情况下，依旧可以做全量备份，而且可以点备份的按钮。
> 按理说我资产都不在线，我不应该做任何操作，不应该能够做任何操作，但是我这里依旧可以，但并且可以成功了，那说明我的资产确实在线，那这里没有做到一个同步的效果。
> 起码就是我现在没有做定时去采集的话，那按理说就应该我设备不在线的时候需要手动采集，如果不手动采集就会失效，但实际上并没有这样做。

## 状态

- ⏳ 草稿（v2.6.1 backlog）
- 待 Apply：v2.6.1 push 后启动
