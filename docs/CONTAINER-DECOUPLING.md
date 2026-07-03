# 容器拆分蓝图（v2.4.1 已实施）

**状态**：v2.4.1 已实施（替换 v2.4.0 蓝图中的 sdn-control/data/monitor 方案 + v2.3 早期 2 容器 core/asset 评估）
**关联 change**: [openspec/changes/v241-container-split/](../openspec/changes/v241-container-split/)
**实施时序**: v2.4.0 蓝图定稿 → **v2.4.1 拆 3 容器实施（本版本）** → v2.4.2 灰度上线 → v2.5/v3.0 评估迁 Postgres

---

## v2.4.0 → v2.4.1 关键变化

| 维度 | v2.4.0 蓝图 | v2.4.1 实施决策 | 理由 |
|---|---|---|---|
| 容器数 | 3（sdn-control + data + monitor） | **3（ctrl + config + data）** | sdn-control 装太多（device+interface+vlan+execute+batch+log+auth+dashboard），拆得不平均；monitor v2.4 无实际业务，先不立容器 |
| 数据归属 | 3 容器各自独立 SQLite | **3 容器各自独立 SQLite**（保持） | v2.4.1 不迁 Postgres（决策点 v2.5/v3.0） |
| 内部通信 | Docker internal network + HTTP REST + X-Internal-Token | **保持**（httpx 客户端 + 3 次指数退避 + 5s 超时） | 简单可控，复杂度 ROI 低于 gRPC |
| monitor 容器 | v2.4 基础（v3.0+ 完善） | **暂不立容器** | v2.4 无实际监控业务，避免空容器；v3.0 VPC 落地时再评估 |
| 渐进式上线 | 一次切换 | **monolith（默认）+ split（profile: split）双模式共存** | 故障可秒级回退到 monolith，降低上线风险 |

---

## 3 容器职责（ctrl / config / data）

| 容器 | 职责 | 资源特征 | 数据库表 | 外部端口 |
|---|---|---|---|---|
| **ctrl** | 设备身份中心：device CRUD / 操作日志 / dashboard 聚合 | 高频读写，CPU 中 | `devices` / `logs` / `alembic_version` | 8001 |
| **config** | 设备配置中心：interface / vlan / execute / batch（SSH/NETCONF 下发） | 高频 NETCONF，CPU 重 | 无业务表（设备查询走 internal_api 调 ctrl） | 8002 |
| **data** | 数据采集存储：asset / backup / task（CMDB + 备份 + 异步任务） | 低频批处理，I/O 重 | `assets` / `backups` / `tasks` / `alembic_version` | 8003 |

**v3.0 扩展预留**：
- ctrl → 增加 VPC 联动逻辑
- data → 长保留历史 + 监控指标存储（monitor 容器 v3.0 评估时再立）

---

## 拓扑图

```
                          前端 (Vue.js 5173)
                               │
                               ▼
   ┌────────────────────────────────────────────────┐
   │       Vite proxy (按路径分发, VITE_SPLIT_MODE) │
   │       monolith 模式: 全部 → backend:8000      │
   │       split 模式: 按路径 → ctrl/config/data    │
   └────────┬───────────────┬──────────────┬────────┘
            │               │              │
            ▼               ▼              ▼
    ┌──────────────┐ ┌──────────────┐ ┌──────────────┐
    │    ctrl      │ │   config     │ │     data     │
    │   :8001      │ │    :8002     │ │    :8003     │
    │              │ │              │ │              │
    │  device      │ │  interface   │ │  asset       │
    │  log         │ │  vlan        │ │  backup      │
    │  dashboard   │ │  execute     │ │  task        │
    │  auth        │ │  batch       │ │              │
    │  health      │ │              │ │              │
    │              │ │              │ │              │
    │ SQLite       │ │ (无业务表)   │ │ SQLite       │
    │ /data/ctrl.db│ │              │ │ /data/data.db│
    └──────┬───────┘ └──────┬───────┘ └──────┬───────┘
           │                │                │
           └────────────────┴────────────────┘
                            │
                内部通信: X-Internal-Token
                (Docker internal network h3c-net)
                httpx + 3 次指数退避 + 5s 超时
```

---

## API 路由归属表（实际拆分）

| router | monolith 模式 | split 模式归属 | 备注 |
|---|---|---|---|
| `device.py` | backend | **ctrl** | 设备 CRUD / 详情 |
| `log.py` | backend | **ctrl** | 操作日志（高频写） |
| `dashboard.py` | backend | **ctrl** | 仪表盘聚合查询（跨容器查 data 降级） |
| `auth.py` | backend | **ctrl** | 认证授权 |
| `health.py` | backend | **ctrl**（+ 各容器自检） | 基础 health 路由 |
| `interface.py` | backend | **config** | 接口配置 + VPN instance |
| `vlan.py` | backend | **config** | VLAN 配置 |
| `execute.py` | backend | **config** | SSH 终端 + 异步执行 |
| `batch.py` | backend | **config** | 批处理任务 |
| `asset.py` | backend | **data** | 资产采集 |
| `backup.py` | backend | **data** | 备份 + 异步任务管理 |
| `task.py` | backend | **data** | 异步任务管理（与 backup 一起） |
| `ctrl_internal.py` | — | **ctrl** | `GET /internal/devices` + `GET /internal/devices/{id}` + `POST /internal/logs` |
| `data_internal.py` | — | **data** | `POST /internal/backup` + `GET /internal/backups/{device_id}` |

**前端无感**：API 路径不变，Vite proxy 按路径分发（split 模式）或全部转 backend（monolith 模式）。

---

## 容器间通信

### 协议
- **HTTP REST**（不用 gRPC，复杂度 ROI 低）
- **Docker internal network** `h3c-net`（容器间无外部网络暴露，通过容器名 DNS 解析）

### 寻址（12-factor）
- **环境变量注入**：`INTERNAL_CTRL_URL` / `INTERNAL_CONFIG_URL` / `INTERNAL_DATA_URL`
- **Docker DNS**：容器名解析（`http://ctrl:8000` / `http://config:8000` / `http://data:8000`）
- **禁止硬编码 IP:Port**（违反 12-factor，迁移/扩容困难）

### 鉴权
- **X-Internal-Token** 头：所有跨容器请求必须带
- `INTERNAL_API_TOKEN` 环境变量：3 容器共享同一密钥（env 注入）
- `verify_internal_token` 中间件：ctrl / config / data 各自实现，仅拦截 `/internal/*` 路径

### 超时与重试
- 超时 5s
- 重试 3 次，指数退避（1s / 2s / 4s）
- 失败记录中文错误（不暴露技术异常）

### 典型通信场景

| 调用方 | 被调方 | 接口 | 场景 |
|---|---|---|---|
| config | ctrl | `GET /internal/devices/{id}` | 接口配置/批量执行前查 device 凭据 |
| config | ctrl | `POST /internal/logs` | 配置下发后记录操作日志 |
| data | ctrl | `GET /internal/devices/{id}` | 备份前查 device 凭据 |
| data | ctrl | `GET /internal/devices` | 全量备份前拉所有设备 |
| data | ctrl | `POST /internal/logs` | 备份完成/失败后记录日志 |
| ctrl | data | `GET /internal/assets` | dashboard 聚合查询资产（降级容错） |

---

## 统一设备访问模式（关键设计）

**问题**：config 和 data 容器没有 `devices` 表，但需要 device 凭据（host/port/username/password）才能下发配置或备份。

**解决方案**：`backend/app/utils/device_access.py` 统一封装

```python
def get_device_with_password(db, device_id):
    # 1. 先尝试本地查（monolith 模式）
    table_unavailable = False
    try:
        device = db.query(Device).filter(Device.id == device_id).first()
    except Exception as e:
        device = None
        table_unavailable = True  # 表不可用 → split 模式

    # 本地表查询成功（monolith 模式）
    if not table_unavailable:
        if device:
            return device, decrypt_password(device.password_encrypted), None
        else:
            # 设备真不存在（本地查到了但返回 None）
            return None, None, APIResponse(success=False, error=f"设备不存在: id={device_id}")

    # 2. 走内部 API（split 模式，data/config 容器无 devices 表）
    from app.internal_api import get_device
    resp = get_device(device_id)
    if not resp.get("success"):
        return None, None, APIResponse(success=False, error=resp.get("error"))
    d = resp["data"]
    # 用 SimpleNamespace 包装 dict，兼容 ORM 属性访问（device.host / device.id 等）
    device_obj = _wrap_device_dict(d)  # 内部 API 已解密 password
    return device_obj, d.get("password", ""), None
```

**关键点**：
- monolith 模式：本地查优先（性能最优，无网络开销）
- split 模式：本地表查询抛 OperationalError → 走 internal_api 兜底
- 设备真不存在（本地查到 None）→ 直接返回错误，不走 internal_api（避免无谓网络调用）
- SimpleNamespace 包装 dict，让上层 router 代码无需感知 monolith/split 模式差异

**日志兜底**：`backend/app/utils/log_recorder.py` 同样设计，split 模式下 config/data 写日志走 ctrl 容器 `POST /internal/logs`。

---

## 数据库策略

**v2.4.1 决策**：3 容器各自独立 SQLite（不迁 Postgres）

**理由**：
- v2.4.1 重点是故障域隔离，I/O 隔离已通过容器拆分实现
- 迁 Postgres 工作量大（迁移工具 / 主从 / 备份策略），v2.4.1 ROI 低
- 评估点：v2.4.1 收尾时决策 v2.5 / v3.0 是否迁

**库表归属**（"谁写谁拥有"原则）：

| 容器 | 拥有的表 | 说明 |
|---|---|---|
| ctrl | `devices` / `logs` / `alembic_version` | 设备身份 + 操作日志 |
| config | 无业务表 | 设备查询走 internal_api 调 ctrl |
| data | `assets` / `backups` / `tasks` / `alembic_version` | 资产 + 备份 + 异步任务 |

**迁移工具**：
- 拆分：`scripts/migrate-v241-split-db.py`（拷贝 dev.db → 3 份 → 各自 DROP 不属于的表 → VACUUM）
- 回退：`scripts/rollback-v241-split-db.py`（优先从 dev.db.bak 恢复 / 无 .bak 时从 3 分库合并）
- 验证：双向数据量一致（7 devices + 586 logs + 7 assets + 35 backups + 27 tasks）

**备份数据**：
- 仅 data 容器拥有
- 共享 `h3c-netctrl-backups` volume 挂到 data 容器
- ctrl/config 触发备份时通过内部 API 调用 data 的 `/internal/backup` 端点

---

## 渐进式上线策略（双模式共存）

### monolith 模式（默认，向后兼容）

```bash
# 启动 monolith backend
docker compose -f docker-compose.dev.yml up -d backend frontend
# → 全部 API 走 backend:8000
```

### split 模式（v2.4.1 新增，按需切换）

```bash
# 启动 3 容器
docker compose -f docker-compose.dev.yml --profile split up -d ctrl config data frontend
# → Vite proxy 按路径分发到 ctrl:8001 / config:8002 / data:8003

# 前端切换 split 模式（环境变量）
VITE_SPLIT_MODE=true  # .env 中设置
```

### 切换验证

切换前：`docker compose down` → `docker compose --profile split up -d` → 验证 → 不满意可 `down` 再切回 monolith。

数据零损失（SQLite 文件独立，monolith 用 `dev.db`，split 用 `ctrl.db` + `data.db`，迁移脚本双向可逆）。

---

## 升级步骤（monolith → split）

```bash
# 1. 备份（强制）
make backup

# 2. 拉取新代码
git pull

# 3. 数据库拆分（monolith dev.db → ctrl.db + data.db）
python scripts/migrate-v241-split-db.py
# 预期输出: 7 devices + 586 logs → ctrl.db, 7 assets + 35 backups + 27 tasks → data.db

# 4. 停 monolith，启 split 模式
docker compose -f docker-compose.dev.yml down backend
docker compose -f docker-compose.dev.yml --profile split up -d ctrl config data

# 5. 前端切 split 模式
echo "VITE_SPLIT_MODE=true" >> .env
docker compose -f docker-compose.dev.yml restart frontend

# 6. 端到端验证
docker compose -f docker-compose.dev.yml --profile qa up qa-backend
# 预期: 194 passed, 11 skipped, 0 failed
```

## 回退步骤（split → monolith）

```bash
# 1. 停 split 3 容器
docker compose -f docker-compose.dev.yml --profile split down

# 2. 数据库合并（ctrl.db + data.db → dev.db）
python scripts/rollback-v241-split-db.py
# 优先从 dev.db.bak 恢复（最可靠）

# 3. 启 monolith
docker compose -f docker-compose.dev.yml up -d backend frontend

# 4. 前端切回 monolith 模式
sed -i '/VITE_SPLIT_MODE/d' .env
docker compose -f docker-compose.dev.yml restart frontend

# 5. 验证
docker compose -f docker-compose.dev.yml --profile qa up qa-backend
# 预期: 194 passed（monolith 行为不变）
```

**最坏情况**：回退到 v2.4.0 monolith docker-compose，数据零损失（SQLite 文件不变）。

---

## 故障注入验证结果（v2.4.1 实测）

| 故障 | 预期行为 | 实测结果 |
|---|---|---|
| `docker stop data` | ctrl dashboard 降级（assets/backups 表不可用），config 改端口仍成功 | ✅ dashboard 降级到 0,0 + config 业务正常 |
| `docker stop ctrl` | config 返回明确错误"设备查询失败"，data 备份失败明确提示 | ✅ config 返回"设备查询失败: 内部 API 调用失败..." |
| `docker stop config` | ctrl / data 不受影响 | ✅ ctrl dashboard 正常 + data backup/asset 正常 |
| 恢复 3 容器 | 全量回归通过 | ✅ 194 passed, 11 skipped, 0 failed |

**真机 e2e 验证**（192.168.100.4/.5/.100/.177）：
- ✅ 7 台设备列表正常
- ✅ 63 个接口配置下发（NETCONF 真机）
- ✅ running 备份成功（id=102, 8224 bytes）
- ⚠️ startup 备份失败（真机 SCP 问题，与 split 模式无关，monolith 模式同样失败）
- ⏸️ 全量备份异步模式 e2e + 集成测试 4 设备 8 场景（留到发版前）

---

## 已知遗留（v2.4.2 follow-up）

- **Task 4.2**：删除设备时通知 data 清理关联 asset/backup（需新增 data 容器 `DELETE /internal/devices/{id}/cleanup` 端点）
- **Task 8.4/8.5**：全量备份异步模式 e2e + 集成测试 `--integration` 4 设备 8 场景（留到发版前）

---

## Postgres 决策点评估（v2.4.1 收尾）

**决策**：v2.5 **不迁** Postgres（继续 SQLite），v3.0 **再评估**（看 VPC 数据模型复杂度）。

### 当前 SQLite 方案特征

- 3 容器各自独立 SQLite 文件（ctrl.db / data.db，config 无业务表）
- 跨容器查询走 internal_api（HTTP REST + httpx 重试）
- 数据量小（7 devices + 586 logs + 7 assets + 35 backups + 27 tasks，< 1MB）
- 单写者无并发冲突（每表只在一个容器写，无分布式事务）

### SQLite 方案的优势

1. **零运维**：无 DBA，无主从同步，无单独备份策略（docker volume 即备份）
2. **部署简单**：文件即数据库，docker volume 挂载，故障域隔离清晰
3. **性能足够**：小数据量 + 单写者 + 读多写少，SQLite 读并发无锁
4. **故障恢复快**：容器挂了数据文件还在，重启即恢复

### 何时需要迁 Postgres（触发条件）

| 触发条件 | 当前状态 | 阈值 | 是否触发 |
|---|---|---|---|
| 数据量增长 | < 1MB（7 devices + 586 logs） | > 10万行 / > 1GB | ❌ 未触发 |
| 并发写瓶颈 | 单写者（每表只在一个容器写） | 多容器并发写同一表 | ❌ 未触发 |
| 跨容器事务需求 | 无（所有表只在一个容器写） | VPC 操作链需跨容器原子写 | ⏸️ v3.0 评估 |
| 跨容器聚合查询复杂度 | dashboard 走 1 次 internal_api | 多次聚合 + 复杂 JOIN | ❌ 未触发（已有降级容错） |
| 备份/恢复统一管理 | 各容器独立 SQLite 文件 | 需要统一时间点快照 | ❌ 未触发（数据量小） |

### 迁 Postgres 的成本

1. **运维成本**：Postgres 部署 + 主从 + 备份策略 + 监控告警
2. **迁移工具**：SQLite → Postgres 数据迁移脚本 + Alembic dialect 调整
3. **代码改造**：SQLAlchemy 连接串 + 部分 SQLite 特有 SQL（如 `PRAGMA foreign_keys`）
4. **测试成本**：全量回归 194 用例 + 真机 e2e 4 设备 8 场景重跑
5. **容器架构**：加 postgres 容器 + 数据卷管理 + 内部网络配置

### ROI 评估

- **v2.5 规划**：修 bug + 优化（不是新功能大版本），数据量不会显著增长 → **不迁**
- **v3.0 规划**：VPC + etcd（SDN 起步），VPC 操作链可能涉及跨容器事务（改设备配置 → 写 VPC 元数据 → 备份 → 日志）→ **评估点**
- **优化方向**（v2.5 替代迁 Postgres）：internal_api 加本地缓存（TTL 30s）减少跨容器调用，dashboard 降级容错已有

### 决策结论

| 版本 | 决策 | 理由 |
|---|---|---|
| **v2.5** | ❌ 不迁 Postgres | ROI 不足，SQLite 足够，优化 internal_api 缓存即可 |
| **v3.0** | ⏸️ 评估点 | 看 VPC 数据模型是否需要跨容器事务；如需要则迁，否则继续 SQLite |
| **触发阈值** | 数据量 > 10万行 / 跨容器事务需求 / 并发写瓶颈 | 任一触发即启动迁 Postgres 评估 |

---

## 关联

- 路线图: [VERSION-ROADMAP.md](../VERSION-ROADMAP.md)
- 实施清单: [openspec/changes/v241-container-split/tasks.md](../openspec/changes/v241-container-split/tasks.md)
- 基线清单: [CONTAINER-INVENTORY.md](CONTAINER-INVENTORY.md)
- 清理 SOP: [CONTAINER-CLEANUP-SOP.md](CONTAINER-CLEANUP-SOP.md)
- ops-toolkit: [ops-toolkit.md](ops-toolkit.md)
- QA: [QA-GUIDE.md](QA-GUIDE.md)
- 上版蓝图（v2.4.0 sdn-control/data/monitor 方案）: [archive/2026-07-02-v24-roadmap/](../openspec/changes/archive/2026-07-02-v24-roadmap/proposal.md)
- 早期评估（v2.3 2 容器 core/asset）: [archive/2026-07-02-v2.4-container-decoupling/](../openspec/changes/archive/2026-07-02-v2.4-container-decoupling/proposal.md)
