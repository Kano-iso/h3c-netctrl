## Context

v2.2 网控增强第一项。系统当前无任何配置存档，误操作后无法回滚。

### 后端能力盘点

- `paramiko` 已在依赖中（`backend/app/utils/ssh_executor.py` 使用 SSHClient）
- `paramiko.SFTPClient.from_transport()` 可直接用于拉取远程文件
- `NetconfClient` 已封装 edit-config，理论上可封装 load-config（需要 H3C 实地探测）
- 数据库：已有 `Device` / `Asset` / `Log` 三张表，无 `Backup` 表

### 设备侧能力盘点（待探测）

- H3C V7 设备支持 SFTP 服务（默认开启，依赖 SSH）
- 文件路径：
  - `startup.cfg` - 启动配置（下一次重启加载）
  - `running.cfg` 或 `current.cfg` - 当前运行配置
  - `cfg/` 目录下可能有备份
- NETCONF `load-config` 协议（RFC 6241）H3C 支持度需确认

### 前端能力盘点

- `ConfirmModal.vue` 已存在，可复用
- `Devices.vue` 操作列已有 4 个按钮（连接测试/资产/编辑/删除），再加"备份"会撑大列宽
- 需要新建 `BackupListModal.vue`（独立组件避免 Devices.vue 臃肿）

## Goals / Non-Goals

**Goals:**
- 手动单设备 + 全量备份（SFTP 拉 startup.cfg + running.cfg）
- 备份文件按设备 ID 目录隔离存储
- 列表 / 下载 / 删除 / 锁定 / 回滚 5 个操作
- 轮转：每设备保留 5 份未锁定的，超出的最旧非锁定自动删
- 锁定备份不被轮转、不能删除（仅可解锁后删）
- 真实设备验证：192.168.100.4 (Leaf-03)
- Docker volume 持久化

**Non-Goals:**
- **不做**定时备份（cron / scheduler）
- **不做**FTP server / SFTP server（仅客户端拉取）
- **不做**"今日份/最近一次"快查界面（用户明确不要）
- **不做**备份加密（备份文件原样存储，由 Docker volume 文件系统权限保护）
- **不做**自动备份（仅手动触发）
- **不做**多设备差异比对（仅单设备回滚）

## Decisions

### 1. 拉取方式：SFTP 主动拉

- **选择**：后端用 `paramiko.SFTPClient.open(f"{path}", "rb")` 主动拉文件
- **理由**：
  - 设备默认开 SFTP 服务（依赖 SSH），无需设备侧额外配置
  - 不需要起 FTP server，链路最简
  - 与现有 `ssh_executor.py` 复用同一 SSH 连接 / 同一认证
- **替代**：
  - 设备主动 SCP 推 → 需要在设备上配置 scp server，用户不友好
  - 走 NETCONF `<copy>` 操作 → 复杂度高，H3C 支持度不确定

### 2. 存储路径：`/data/backups/{device_id}/{timestamp}__{type}.cfg`

- **示例**：
  ```
  /data/backups/4/20260624T103045__startup.cfg
  /data/backups/4/20260624T103045__running.cfg
  ```
- **理由**：
  - 按设备 ID 目录隔离，多设备备份互不干扰
  - 时间戳 ISO 8601 紧凑格式，文件名可排序
  - 类型后缀（startup / running）一目了然
- **替代**：
  - 单文件 + 数据库记录路径 → 设备删除时难清理
  - 用 device.name 做目录 → 重命名设备时备份丢失

### 3. 数据库表 `backups`

```python
class Backup(Base):
    __tablename__ = "backups"
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, ForeignKey("devices.id", ondelete="CASCADE"), nullable=False, index=True)
    filename = Column(String, nullable=False)       # 含类型后缀
    file_path = Column(String, nullable=False)      # 容器内绝对路径
    backup_type = Column(String, nullable=False)    # "startup" | "running"
    size = Column(Integer, nullable=False)
    content_hash = Column(String, nullable=False)   # SHA256 hex
    locked = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False, index=True)
```

- **`locked` 默认 False**
- **`content_hash` 用于回滚时校验**（比对当前设备配置和备份是否真的一致）
- **CASCADE 删除**：设备删除时自动清理备份文件 + 记录

### 4. 轮转策略

- **触发时机**：每次新备份成功后立即轮转（不是 cron 调度）
- **逻辑**：
  1. 查询该设备所有 `locked=False` 的备份，按 `created_at` 升序
  2. 计数 > 5 → 删除最旧的（除锁定外最早）
- **代码位置**：`backup_manager.py::rotate_after_backup(device_id)`
- **替代**：cron 定时轮转 → 用户明确不要

### 5. 回滚实现：NETCONF `load-config` 优先，SSH 推送 fallback

- **选择**：
  - **首选**：NETCONF `load-config` (RFC 6241) `<load-configuration>` 操作
    - 优点：原子、官方支持、可指定 `replace` / `merge` / `create` 策略
    - 风险：H3C V7 是否完整支持 `load-config`（含 startup + running）需探测
  - **Fallback**：SSH 推 startup.cfg 到设备 + `startup saved-configuration` + 不 reboot
    - 优点：兼容性好
    - 缺点：影响运行时（不是原子），需要确认 H3C 命令细节
- **验证流程**：
  1. 在 192.168.100.4 上探测 NETCONF `load-config` 支持
  2. 失败 → 用 SSH 推送
- **决策延迟**：实施时探测后定，先写设计留双路径

### 6. 锁定 vs 删除语义

- **选择**：
  - `DELETE /api/devices/{id}/backup/{bid}` → 若 `locked=True` 返回 403
  - `POST /api/devices/{id}/backup/{bid}/lock` body `{"locked": true/false}` 切换
- **理由**：单一接口控制锁定状态，UI 上 "🔒 锁定 / 🔓 解锁" 切换
- **替代**：
  - DELETE hard 不可逆 → 但锁定是软保护，用户主动解锁可删
  - 锁定通过 PATCH /api/.../backup/{bid} 改 locked 字段 → 过度设计

### 7. 全量备份并发策略

- **选择**：
  - `POST /api/backups` 触发时，并发对所有设备调 `create_backup`
  - `asyncio.gather(*tasks)` + `return_exceptions=True`
  - 返回 `{"total": N, "success": K, "failed": [{device_id, error}, ...]}`
- **理由**：
  - 6 台设备规模下并发节省时间
  - 单台失败不影响其他
  - 前端展示聚合结果
- **替代**：串行执行 → 慢，UX 差

### 8. 备份并发锁

- **选择**：同设备 5 秒内重复触发备份 → 返回 429 Too Many Requests
- **理由**：避免 SFTP 连接竞争、文件覆盖
- **实现**：`redis`-like 全局 dict（in-memory，够用）；非分布部署
- **替代**：DB 锁表 → 过度设计

### 9. UI 入口

- **选择**：
  - `Devices.vue` 表格行操作列加"备份"按钮 → 打开 `BackupListModal`
  - Modal 内：列表（id/时间/类型/大小/锁定状态）+ 操作按钮（下载/删除/锁定/回滚）+ "新建备份" 按钮
  - `CMDB.vue` 顶部加"全量备份"按钮（次要入口）
- **理由**：与现有 CRUD UI 模式一致
- **替代**：
  - 独立 `/backup` 页面 → 过度设计，单设备 backup 操作频率不高
  - 抽屉 Drawer → 与现有 Modal 范式不一致

## Risks / Trade-offs

- **[风险] H3C V7 NETCONF `load-config` 不支持 → 回滚失败** → **缓解**：探测后用 SSH 推送 fallback
- **[风险] 备份文件含敏感信息（密码、密钥）→ 文件系统权限** → **缓解**：Docker volume 默认 root:root，宿主机权限 0700
- **[风险] SFTP 拉大文件超时** → **缓解**：H3C 配置文件通常 < 1MB，30s timeout 足够
- **[风险] 备份时设备正好在写入配置 → 拉到的文件不完整** → **缓解**：先调 `save force` 命令强制保存（如果设备支持），再 SFTP 拉
- **[风险] 回滚误操作** → **缓解**：回滚前必须二次确认 Modal + 显示目标备份内容预览（前 200 字符）
- **[风险] 备份文件被误删** → **缓解**：锁定机制（用户主动锁定关键备份）
- **[风险] docker volume 满** → **缓解**：5 份 × N 设备 × 1MB ≈ 30MB / 6 台，体积可控

## Migration Plan

- **数据库**：
  ```bash
  alembic revision --autogenerate -m "add backups table"
  alembic upgrade head
  ```
  降级：`alembic downgrade -1`（删除 backups 表 + 文件）
- **部署**：
  1. 改 `docker-compose.dev.yml` 加 volume
  2. 改 `.env.example` 加 BACKUP_DIR / BACKUP_KEEP
  3. 启动后端自动跑 alembic upgrade
  4. 前端 vite HMR 自动加载
- **回退**：git revert + alembic downgrade
- **数据**：新表无历史数据，干净
- **测试**：
  1. 192.168.100.4 单设备备份 → 文件落地
  2. 全量备份 → 6 个文件落地
  3. 锁定一个 → 触发 6 次备份后该文件仍在
  4. 触发 6 次非锁定备份 → 旧的被轮转
  5. 改设备配置 → 备份 → 改回来 → 比对原备份 = 当前（哈希一致）
  6. 改设备配置 → 备份 → 恢复备份 → 当前 = 备份
