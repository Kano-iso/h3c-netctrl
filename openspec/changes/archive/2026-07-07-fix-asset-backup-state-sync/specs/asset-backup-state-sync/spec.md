# asset-backup-state-sync — Specification

## 范围

本 spec 描述 v2.6.1 修复"资产状态与备份入口未同步"的 5 个独立任务：

1. **Task 1：后端 asset 校验 + force 参数** —— `POST /api/devices/{id}/backup` 和 backup-async 端点
2. **Task 2：数据库迁移** —— `backups` 表加 `forced` 列（alembic up/down）
3. **Task 3：前端按钮 + force 勾选框 + 二次确认 + i18n** —— Devices.vue / CMDB.vue
4. **Task 4：测试** —— qa-backend 4 unit + 真机 2 集成
5. **Task 5：Archive + RELEASE-NOTES 同步** —— A 类文档

不影响：v2.6.0 i18n、v2.4.1 split 架构、backup 业务逻辑（走 SSH/NETCONF 通道不变）、asset 状态机、UI 实时刷新（依赖 dashboard 轮询）。

---

## Task 1：后端 asset 校验 + force 参数

### 当前行为（v2.6.0）

`backend/app/routers/backup.py`：
- `POST /api/devices/{id}/backup`（同步）—— 不查 asset 状态，直接调 BackupManager.create_backup
- `POST /api/devices/{id}/backup-async`（异步）—— 同上

前端"备份"按钮 `:disabled="!deviceStatus || busyId !== null"`，只看 device CRUD 状态（创建/启用/禁用），不看 asset 最近采集结果。

→ **资产 offline 时仍可点备份，且能成功**（backup 走 SSH/NETCONF 独立通道，与 asset 状态解耦）。

### 期望行为（v2.6.1）

| asset.status | force 参数 | 行为 |
|---|---|---|
| `online` | (任意) | 正常备份 |
| `offline` / `never_collected` / `stale` | 不传 / `false` | 返回 422 `BACKUP_DEVICE_OFFLINE` |
| `offline` / `never_collected` / `stale` | `true` | 备份成功 + 落 `backups.forced=1` + 日志 `force_backup device_id=...` |

### 实现

#### 1.1 新增 `backend/app/utils/asset_guard.py`

```python
from sqlalchemy.orm import Session
from app.database import SessionLocal
from app.models import Asset


def check_asset_online(device_id: int, force: bool = False) -> bool:
    """查 assets 表 status，若 ≠ online 抛 BackupError。
    force=True 时跳过校验（仍记录日志用于审计）。
    """
    if force:
        from app.utils.logger import get_logger
        get_logger(__name__).warning(
            f"force_backup device_id={device_id} skip asset check"
        )
        return True
    db: Session = SessionLocal()
    try:
        asset = db.query(Asset).filter(Asset.device_id == device_id).first()
        if not asset or asset.status != "online":
            from app.utils.backup_manager import BackupError
            raise BackupError(
                f"BACKUP_DEVICE_OFFLINE device_id={device_id} status={asset.status if asset else 'never_collected'}"
            )
        return True
    finally:
        db.close()
```

#### 1.2 `backend/app/routers/backup.py` 同步端点

```python
@router.post("/devices/{device_id}/backup")
def create_backup(device_id: int, request: Request):
    force = request.query_params.get("force", "").lower() == "true"
    check_asset_online(device_id, force=force)  # v2.6.1 fix-asset-backup-state-sync Task 1
    # ... 原有逻辑 ...
    if force:
        backup.forced = True  # Task 2 字段
    db.commit()
```

#### 1.3 `backend/app/routers/backup.py` 异步端点

```python
@router.post("/devices/{device_id}/backup-async")
def create_backup_async(device_id: int, request: Request, background: BackgroundTasks):
    force = request.query_params.get("force", "").lower() == "true"
    check_asset_online(device_id, force=force)  # v2.6.1
    # ... 原有异步逻辑 ...
```

#### 1.4 i18n key

`backend/app/i18n_keys.py` + `backend/app/i18n/locales/{zh-CN,en-US}.json`：
- `error.backup.device_offline` → "设备未采集/离线，请先采集后再备份" / "Device not collected/offline, please collect first"

### 验收

- [ ] `pytest tests/test_backup_asset_guard.py` 4 case 全过
- [ ] 真机 .177（online）`POST /api/devices/7/backup` 返回 200 + backup 行
- [ ] 真机 .4（offline）`POST /api/devices/4/backup` 返回 422 `BACKUP_DEVICE_OFFLINE`
- [ ] 真机 .4（offline）`POST /api/devices/4/backup?force=true` 返回 200 + `backups.forced=1`
- [ ] 异步端点 4 个 case 行为一致

---

## Task 2：数据库迁移（backups.forced）

### 当前行为（v2.6.0）

`backups` 表 schema：
```sql
CREATE TABLE backups (
    id INTEGER PRIMARY KEY,
    device_id INTEGER NOT NULL,
    filename VARCHAR NOT NULL,
    file_path VARCHAR NOT NULL,
    backup_type VARCHAR,
    size INTEGER,
    content_hash VARCHAR,
    locked BOOLEAN DEFAULT 0,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    -- ... 无 forced 字段
)
```

### 期望行为（v2.6.1）

加 `forced BOOLEAN NOT NULL DEFAULT 0`。

### 实现

#### 2.1 `backend/alembic/versions/<revision>_add_forced_to_backups.py`

```python
"""add forced column to backups (v2.6.1 fix-asset-backup-state-sync Task 2)"""
from alembic import op
import sqlalchemy as sa

revision = "260_add_forced_to_backups"
down_revision = "<prev>"  # 填当前 head revision
branch_labels = None
depends_on = None

def upgrade():
    op.add_column(
        "backups",
        sa.Column("forced", sa.Boolean(), nullable=False, server_default=sa.text("0")),
    )

def downgrade():
    op.drop_column("backups", "forced")
```

#### 2.2 `backend/app/database.py` 模型

```python
class Backup(Base):
    # ... 现有字段 ...
    forced: Mapped[bool] = mapped_column(default=False, server_default="0")  # v2.6.1
```

#### 2.3 Task 1 端点引用

同步/异步端点在 force=True 时 `backup.forced = True`（见 Task 1.2/1.3）。

### 验收

- [ ] `alembic upgrade head` 成功，`PRAGMA table_info(backups)` 含 `forced` 列
- [ ] `alembic downgrade -1` 成功，列删除
- [ ] 真机 force=True 备份后查 DB `SELECT forced FROM backups ORDER BY id DESC LIMIT 1` = 1
- [ ] 不破 v2.6.0 backup 流程（monolith + split）

---

## Task 3：前端按钮 + force 勾选框 + 二次确认 + i18n

### 当前行为（v2.6.0）

`frontend/src/views/Devices.vue`：
- 行内"备份"按钮 `:disabled="!device.status"` 或类似（只看 device CRUD 状态）
- 无 force 勾选框
- 无二次确认弹窗

### 期望行为（v2.6.1）

| asset.status | force 勾选 | 按钮状态 | 点击行为 |
|---|---|---|---|
| `online` | (不可见) | enabled | 弹"立即备份"对话框 → 提交 |
| `offline` 等 | 未勾选 | disabled + tooltip | — |
| `offline` 等 | 已勾选 | enabled | 弹 ConfirmModal（强制备份确认）→ 确认 → 提交 `force=true` |

### 实现

#### 3.1 `frontend/src/views/Devices.vue`

行内结构：
```vue
<td>
  <template v-if="row.assetStatus === 'online'">
    <button class="btn-primary" @click="handleBackup(row)">备份</button>
  </template>
  <template v-else>
    <div class="flex items-center gap-2">
      <label class="text-xs text-warn">
        <input type="checkbox" v-model="row.forceChecked" />
        {{ t('backup.force_label') }}
      </label>
      <button
        class="btn-primary"
        :disabled="!row.forceChecked"
        :title="t('button.disabled.asset_offline')"
        @click="handleForceBackup(row)"
      >备份</button>
    </div>
  </template>
</td>
```

`handleForceBackup` 函数：
```js
async function handleForceBackup(row) {
  const ok = await confirm({
    title: t('backup.force_confirm_title'),
    message: t('backup.force_confirm_msg', { name: row.name }),
    confirmText: t('backup.force_confirm_btn'),
    variant: 'danger',
  })
  if (!ok) return
  await backupApi.create(row.id, { force: true })
  // 刷新列表
}
```

#### 3.2 `frontend/src/views/CMDB.vue`（如有）

全量备份按钮逻辑改为：
- 遍历设备，统计 offline 数量
- 数量 = 0 → 正常"全量备份"
- 数量 > 0 → 弹 ConfirmModal 提示"N 台设备未采集，是否强制全量备份？" → 勾选 confirm → 循环调 backupApi.create(d.id, { force: true })

#### 3.3 i18n key（6 个）

**`frontend/src/i18n/locales/zh-CN.json`**：
```json
{
  "error.backup.device_offline": "设备未采集/离线，请先采集后再备份",
  "button.disabled.asset_offline": "资产未采集/离线，请先采集",
  "backup.force_label": "我已了解风险，仍要备份",
  "backup.force_confirm_title": "强制备份确认",
  "backup.force_confirm_msg": "设备 {name} 资产未采集/离线，强制备份可能掩盖采集问题，是否继续？",
  "backup.force_confirm_btn": "确认强制备份"
}
```

**`frontend/src/i18n/locales/en-US.json`**：
```json
{
  "error.backup.device_offline": "Device not collected/offline, please collect first",
  "button.disabled.asset_offline": "Asset not collected/offline, please collect first",
  "backup.force_label": "I understand the risks, backup anyway",
  "backup.force_confirm_title": "Force Backup Confirmation",
  "backup.force_confirm_msg": "Device {name} asset not collected/offline. Force backup may hide collection issues. Continue?",
  "backup.force_confirm_btn": "Confirm Force Backup"
}
```

**`backend/app/i18n_keys.py`** + `backend/app/i18n/locales/{zh-CN,en-US}.json`：同样 6 个 key（用于后端 422 错误响应）。

### 验收

- [ ] `npm run lint` 通过
- [ ] `npm run build` 通过
- [ ] MCP 浏览器验证 .5 设备行：
  - 资产显示 offline → 备份按钮 disabled + tooltip "资产未采集/离线..."
  - 勾选 force → 按钮 enable
  - 点击 → 弹 ConfirmModal "强制备份确认" → 确认 → 后端 200 + 备份成功
  - 不勾选 force → 按钮 disabled
- [ ] 中英文切换：6 个 key 全部正常翻译
- [ ] 真机 .177（online）行：直接显示"备份"按钮（无 force 勾选框），行为不变

---

## Task 4：测试（qa-backend unit + 真机集成）

### 单元测试（4 case）

`backend/tests/test_backup_asset_guard.py`：

```python
import pytest
from app.utils.asset_guard import check_asset_online
from app.utils.backup_manager import BackupError


def test_check_asset_online_when_online_returns_true(setup_online_asset):
    assert check_asset_online(setup_online_asset) is True


def test_check_asset_online_when_offline_raises(setup_offline_asset):
    with pytest.raises(BackupError, match="BACKUP_DEVICE_OFFLINE"):
        check_asset_online(setup_offline_asset)


def test_check_asset_online_when_never_collected_raises(setup_no_asset):
    with pytest.raises(BackupError, match="BACKUP_DEVICE_OFFLINE"):
        check_asset_online(setup_no_asset)


def test_check_asset_online_with_force_skips_check(setup_offline_asset, caplog):
    with caplog.at_level("WARNING"):
        assert check_asset_online(setup_offline_asset, force=True) is True
    assert "force_backup" in caplog.text
```

### 集成测试（2 case）

`backend/tests/test_backup_force_integration.py`：
- `.177` 完整流程：refresh_asset → backupApi.create → 200 + backups.forced=0
- `.4` 完整流程：refresh_asset 失败 → backupApi.create → 422；改 `?force=true` → 200 + backups.forced=1

### QA baseline

- qa-backend：309 → 313+ passed
- qa-frontend：lint + build 维持

### 验收

- [ ] `qa-backend` 全量测试通过（313+）
- [ ] `qa-frontend` lint + build 通过
- [ ] 真机 .177 backup 成功（asset online，无 force）
- [ ] 真机 .4 backup force 流程全过：422 + force=true → 200

---

## Task 5：Archive + RELEASE-NOTES 同步

### 实施

1. 跑 `openspec-archive-change` 技能走 archive 流程
2. 写 `RELEASE-NOTES-v2.6.1.md`：
   - 标题：v2.6.1 Release Notes
   - commit 序列（5 个 commit，按时间）
   - 测试统计：qa-backend 313+、qa-frontend lint+build、真机 .4 / .177
   - 真机示例：.4 force 备份 log
3. 同步 A 类：
   - `README.md` 顶部版本表加 v2.6.1 + 当前架构表加 forced 字段
   - `VERSION-ROADMAP.md` §1 全景表加 1 行 + §2.6.1 详细章节
   - `PRD-V2.0.md` 不改（v2.6.1 是 patch）
4. 同步 `openspec/specs/`：把 delta spec `openspec/changes/fix-asset-backup-state-sync/specs/asset-backup-state-sync/spec.md` 合并到 main spec `openspec/specs/backup-frontend/spec.md`（或新增 `openspec/specs/asset-backup-state-sync/spec.md`）
5. `git mv openspec/changes/fix-asset-backup-state-sync/ → openspec/changes/archive/2026-07-06-fix-asset-backup-state-sync/`
6. 通知用户 review + 等用户确认 push

### 验收

- [ ] archive 目录有 `<date>-fix-asset-backup-state-sync/`
- [ ] `openspec/changes/fix-asset-backup-state-sync/` 不存在
- [ ] `RELEASE-NOTES-v2.6.1.md` 写完
- [ ] `VERSION-ROADMAP.md` §1 + §2.6.1 同步
- [ ] `README.md` 顶部版本表 + 架构表同步
- [ ] 用户确认 push（**不主动 push**）

---

## 整体回归

### 不破坏

- v2.6.0 i18n
- v2.6.1 fix-asset-stale-status（dashboard staleness 过滤）
- v2.6.1 fix-asset-collect-failure（asset 路由）
- v2.6.1 fix-vite-proxy-route（已有 prefix 路由）
- v2.6.1 fix-asset-split-password-decrypt（password 解密）
- v2.6.1 fix-backup-data-integrity（备份文件持久化）
- v2.4.1 split 模式架构
- BACKUP_KEEP=5 轮转逻辑

### 测试 baseline

- qa-backend 309 → 313+ tests
- qa-frontend lint + build 维持
- 4 unit + 2 真机集成

### 性能

- Task 1 asset 查询：1 次 SELECT WHERE device_id=，< 5ms 开销
- Task 2 alembic 迁移：单列添加，< 1s
- Task 3 前端按钮 disabled：computed 属性，< 1ms 开销
- Task 4 测试：4 unit + 2 集成，总耗时 < 30s

### 风险

- Task 1 测试 fixture 准备：需要 mock assets 表 device_id → status 映射
- Task 3 二次确认弹窗时序：勾选 force → 点击 → ConfirmModal → 确认 → 提交
- Task 2 alembic 迁移：生产 DB 跑前 `make backup`（v2.4.2 起强制）
