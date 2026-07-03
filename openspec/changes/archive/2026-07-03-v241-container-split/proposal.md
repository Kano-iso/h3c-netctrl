# v241-container-split

> **类型**：platform（容器架构拆分）
> **优先级**：P0
> **目标版本**：v2.4.1
> **前序**：v2.4.0 (tag v2.4.0, 2026-07-02)

---

## Why

**现状**：backend 是 monolith 容器，所有 9 个 router + 5 个 model 塞在一起，资源争抢无隔离：
- 高频 NETCONF（接口/VLAN 配置）和低频批处理（备份/CMDB 采集）共享同一进程
- 备份 I/O 密集（SSH 拉文件 10-30s）会阻塞 NETCONF 配置下发
- 改端口配置时如果 CMDB 同时采集，SSH 连接池争夺
- v3.0 VPC 落地时问题会更严重（VPC 操作链：改设备配置 → 写 VPC 元数据 → 备份 → 日志）

**目标**：拆成 3 个独立容器（ctrl / config / data），每个容器职责清晰、故障域隔离、独立 SQLite。

---

## 3 容器职责

### ctrl 容器（设备身份中心）
- 端口：8000（内部），外部映射 8001
- 数据库：`ctrl.db` → Device + Log
- 路由：`device.py` / `log.py` / `dashboard.py`
- 职责：设备 CRUD + 操作日志 + 仪表盘聚合查询 + 认证（未来）
- 资源特征：高频读（Dashboard 聚合查所有设备），低频写（增删改设备）

### config 容器（设备配置中心）
- 端口：8000（内部），外部映射 8002
- 数据库：`config.db` → 无持久化表（当前是 stateless 配置下发，未来加 VPC 元数据）
- 路由：`interface.py` / `vlan.py` / `execute.py` / `batch.py`
- 职责：NETCONF/SSH 设备配置下发、多命令终端、批量操作、VPN instance（未来）、VPC（v3.0）
- 资源特征：高频 NETCONF + SSH 连接，CPU 中等，连接池密集型

### data 容器（数据采集与存储中心）
- 端口：8000（内部），外部映射 8003
- 数据库：`data.db` → Asset + Backup + Task
- 路由：`asset.py` / `backup.py`
- 职责：CMDB 资产采集、配置备份（手动/回滚/异步任务管理）
- 资源特征：低频批处理，I/O 密集型（SSH 拉文件、SNMP 采集）

---

## 库表归属（谁写谁拥有）

| 表 | Owner | 读者 | 跨容器读方式 |
|---|---|---|---|
| `device` | ctrl | config（NETCONF 连接用）、data（关联 asset/backup） | 内部 API GET /internal/devices，本地缓存 |
| `log` | ctrl | dashboard（聚合） | 同容器 |
| `asset` | data | dashboard（聚合） | 内部 API GET /internal/assets，缓存 |
| `backup` | data | 前端直连 | 同容器 |
| `task` | data | 前端轮询 | 同容器 |

**当前无跨容器写**（所有表只在一个容器写），避免分布式事务。

---

## 内部 API 设计

### 寻址方式
- 容器间通信：Docker 内部 DNS `http://ctrl:8000` / `http://config:8000` / `http://data:8000`
- 环境变量注入（12-factor）：`INTERNAL_CTRL_URL` / `INTERNAL_CONFIG_URL` / `INTERNAL_DATA_URL`
- 代码只读环境变量，不硬编码 IP/端口

### 鉴权
- 所有跨容器请求头带 `X-Internal-Token: ${INTERNAL_API_TOKEN}`
- 3 容器共享同一 token（env 注入）
- 验证中间件 `verify_internal_token`

### 超时与重试
- 超时：5s
- 重试：3 次，指数退避 1s / 2s / 4s
- 失败返回中文错误（不暴露技术异常）

### 内部 API 端点清单

| 端点 | Owner | 调用方 | 触发场景 |
|---|---|---|---|
| `GET /internal/devices` | ctrl | config, data | 启动时拉 device 列表缓存 |
| `GET /internal/devices/{id}` | ctrl | config | NETCONF 连接前查 IP/凭据 |
| `POST /internal/logs` | ctrl | config | 改配置后写操作日志 |
| `GET /internal/assets` | data | ctrl（dashboard） | 仪表盘聚合资产数据 |
| `POST /internal/backup` | data | config | 改配置后自动备份 |
| `GET /internal/backups/{device_id}` | data | config | 备份前检查已有备份 |

---

## 跨容器数据流

### 场景 1：config 启动时拉 device 缓存
```
config 启动 → GET /internal/devices → ctrl 返回所有设备 → 写入本地 config.db 缓存
→ 后续 NETCONF 连接优先读本地缓存 → 缓存 miss 时重拉 ctrl
```

### 场景 2：改端口后自动备份
```
前端 PATCH /api/devices/5/interfaces/2 → config 下发 NETCONF
→ config POST /internal/logs → ctrl 写操作日志
→ config POST /internal/backup → data 触发备份任务
```

### 场景 3：Dashboard 聚合查询
```
前端 GET /api/dashboard → ctrl 查本地 device + log
→ ctrl GET /internal/assets → data 返回资产数据
→ ctrl 聚合返回前端
```

### 场景 4：v3.0 VPC 创建（未来）
```
前端 POST /api/vpc → config 创建 VPC 元数据（本地 config.db）
→ config NETCONF 下发 VRF + 接口绑定 + 路由策略
→ config POST /internal/logs → ctrl 写日志
→ config POST /internal/backup → data 触发备份
```

---

## docker-compose 拆分

### 当前（monolith）
```yaml
services:
  backend:    # 9 router + 5 model, 端口 8000
```

### 拆分后
```yaml
services:
  ctrl:       # device + log + dashboard, 端口 8001:8000
  config:     # interface + vlan + execute + batch, 端口 8002:8000
  data:       # asset + backup + task, 端口 8003:8000
  frontend:   # 不变，Vite proxy 指向 3 后端
```

### 前端适配
- 前端 Vite dev server proxy 配置：按路径前缀分发到不同后端
  - `/api/devices` / `/api/logs` / `/api/dashboard` → ctrl:8000
  - `/api/interfaces` / `/api/vlans` / `/api/execute` / `/api/batch` → config:8000
  - `/api/assets` / `/api/backups` / `/api/tasks` → data:8000
- 前端代码不变（API 路径不变）

### volume 归属
- `h3c-netctrl-backups`：仅挂 data 容器
- `./data/ctrl.db`：挂 ctrl 容器
- `./data/data.db`：挂 data 容器
- `./logs`：3 容器各自挂载

---

## 升级步骤

```bash
# 1. 强制备份
make backup

# 2. 拆分数据库（从 monolith dev.db 迁移到各自 .db）
#    v2.4.1 提供迁移脚本 scripts/migrate-v241-split-db.py

# 3. 启动 3 容器
docker compose -f docker-compose.dev.yml up -d ctrl config data

# 4. 端到端验证
make qa
```

## 回退步骤

```bash
# 停止 3 容器 → 合并数据库 → 启动 monolith
docker compose down
python3 scripts/rollback-v241-split-db.py
docker compose up -d backend
```

---

## Acceptance Criteria

- [ ] 3 容器独立启动，各自监听 8000/8001/8002/8003
- [ ] 前端无感：Vite proxy 路由到正确容器，所有页面正常
- [ ] 内部 API 通信正常（X-Internal-Token 鉴权 + 超时重试）
- [ ] Dashboard 聚合查询跨容器正常
- [ ] 改端口后自动备份触发正常
- [ ] 全量回归 172 passed, 0 failed
- [ ] 升级/回退脚本可执行
- [ ] docs/CONTAINER-DECOUPLING.md 更新为最终方案

---

## QA 验证计划

1. 3 容器启动后 `docker compose ps` 全部 running
2. 前端 Dashboard 页面正常加载（聚合跨容器查询）
3. 设备操作正常：接口配置下发、备份、回滚、全量备份
4. 单元测试：172 passed, 0 failed
5. 集成测试：`--integration` 真机 4 设备 8 场景 PASS
6. 升级/回退脚本执行：数据不丢失