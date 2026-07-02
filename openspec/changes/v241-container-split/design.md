# v241-container-split Design

## 决策记录

### D1: 3 容器 vs 2 容器 vs 4 容器

**选 3（ctrl / config / data）**：
- 2 容器（core/asset）：故障域不够细，改端口和 CMDB 采集仍争资源
- 4 容器（再拆 auth/monitor）：当前无 auth 需求，monitor 是 v3.0+ 的事，v2.4.1 过度拆分增加复杂度
- 3 容器：故障域清晰（设备身份 / 配置下发 / 数据采集），v3.0 VPC 直接落在 config 容器

### D2: 各自 SQLite vs 统一 Postgres

**选各自 SQLite**：
- v2.4.1 重点是故障域隔离，不是数据库升级
- 迁 Postgres 工作量大（迁移工具、主从、备份策略），当前 ROI 低
- 评估点：v2.4.1 收尾时决策 v2.5/v3.0 是否迁

### D3: HTTP REST + X-Internal-Token vs gRPC

**选 HTTP REST**：
- 当前跨容器调用极少（启动时拉 device 列表 + 改配置后写日志），不需要 gRPC 性能
- HTTP REST 简单可控，FastAPI 自带支持，无额外依赖
- gRPC 引入 protobuf 编译 + 新依赖，复杂度 ROI 低

### D4: 前端 Vite proxy vs nginx

**选 Vite proxy**：
- 开发环境已有 Vite dev server，加 proxy 规则即可
- 不引入 nginx/Traefik 额外容器，保持简单
- 生产环境（未来）再用 nginx 做反向代理

### D5: 数据库迁移策略

**选拆分脚本（不删数据）**：
- monolith 的 `dev.db` 包含 5 张表，拆成 3 个 `.db`
- 提供 `scripts/migrate-v241-split-db.py`（正向）和 `scripts/rollback-v241-split-db.py`（回退）
- 迁移时保留原 `dev.db` 不删（备份）

---

## 文件变更清单

### 新增文件

| 文件 | 说明 |
|---|---|
| `backend/ctrl/main.py` | ctrl 容器入口（device + log + dashboard router） |
| `backend/config/main.py` | config 容器入口（interface + vlan + execute + batch router） |
| `backend/data/main.py` | data 容器入口（asset + backup + task router） |
| `backend/app/internal_api.py` | 内部 API 客户端（httpx + 重试 + 超时 + X-Internal-Token） |
| `backend/app/middleware.py` | 中间件：`verify_internal_token` |
| `backend/ctrl/Dockerfile` | ctrl 容器镜像 |
| `backend/config/Dockerfile` | config 容器镜像 |
| `backend/data/Dockerfile` | data 容器镜像 |
| `scripts/migrate-v241-split-db.py` | 数据库拆分迁移脚本 |
| `scripts/rollback-v241-split-db.py` | 数据库合并回退脚本 |

### 修改文件

| 文件 | 变更 |
|---|---|
| `docker-compose.dev.yml` | 拆 backend → ctrl + config + data 3 service，更新 ports + volumes + env |
| `frontend/vite.config.js` | proxy 规则按路径分发到 3 后端 |
| `backend/app/routers/dashboard.py` | 聚合查询走内部 API 调 data 容器 |
| `backend/app/routers/device.py` | 删除设备时通知 data 清理关联 asset/backup（内部 API） |
| `backend/app/routers/interface.py` | 改配置后 POST /internal/logs（调 ctrl）+ POST /internal/backup（调 data） |
| `.env.example` | 加 INTERNAL_CTRL_URL / INTERNAL_CONFIG_URL / INTERNAL_DATA_URL / INTERNAL_API_TOKEN |

### 不变文件

| 文件 | 原因 |
|---|---|
| 所有 router 业务逻辑 | 只改 main.py 入口 + 跨容器调用，核心逻辑不变 |
| 前端所有组件 | API 路径不变，Vite proxy 透明转发 |
| `models.py` | 每个容器只 import 需要的表（ctrl import Device/Log，config 无持久化表，data import Asset/Backup/Task） |
| `task_manager.py` | 仍在 data 容器，逻辑不变 |

---

## 内部 API 详细设计

### internal_api.py（客户端）

```python
import os
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential

CTRL_URL = os.getenv("INTERNAL_CTRL_URL", "http://ctrl:8000")
CONFIG_URL = os.getenv("INTERNAL_CONFIG_URL", "http://config:8000")
DATA_URL = os.getenv("INTERNAL_DATA_URL", "http://data:8000")
INTERNAL_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")

_headers = {"X-Internal-Token": INTERNAL_TOKEN}

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4))
async def _internal_get(url: str, timeout: float = 5.0):
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.get(url, headers=_headers)
        resp.raise_for_status()
        return resp.json()

@retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=1, max=4))
async def _internal_post(url: str, json_data: dict, timeout: float = 5.0):
    async with httpx.AsyncClient(timeout=timeout) as client:
        resp = await client.post(url, json=json_data, headers=_headers)
        resp.raise_for_status()
        return resp.json()

# 业务调用
async def get_devices():
    return await _internal_get(f"{CTRL_URL}/internal/devices")

async def get_device(device_id: int):
    return await _internal_get(f"{CTRL_URL}/internal/devices/{device_id}")

async def write_log(device_id: int, action: str, status: str, detail: str):
    return await _internal_post(f"{CTRL_URL}/internal/logs", {
        "device_id": device_id, "action": action, "status": status, "detail": detail
    })

async def trigger_backup(device_id: int, types: list):
    return await _internal_post(f"{DATA_URL}/internal/backup", {
        "device_id": device_id, "types": types
    })
```

### middleware.py（鉴权）

```python
from fastapi import Request, HTTPException
import os

INTERNAL_API_TOKEN = os.getenv("INTERNAL_API_TOKEN", "")

async def verify_internal_token(request: Request):
    if request.url.path.startswith("/internal/"):
        token = request.headers.get("X-Internal-Token", "")
        if not token or token != INTERNAL_API_TOKEN:
            raise HTTPException(status_code=403, detail="内部 API 鉴权失败")
```

---

## container 内部路由注册

### ctrl/main.py
```python
app.include_router(device.router, prefix="/api")
app.include_router(log.router, prefix="/api")
app.include_router(dashboard.router, prefix="/api")
# 内部端点
app.include_router(ctrl_internal.router, prefix="/internal")
```

### config/main.py
```python
app.include_router(interface.router, prefix="/api")
app.include_router(vlan.router, prefix="/api")
app.include_router(execute.router, prefix="/api")
app.include_router(batch.router, prefix="/api")
```

### data/main.py
```python
app.include_router(asset.router, prefix="/api")
app.include_router(backup.router, prefix="/api")
# 内部端点
app.include_router(data_internal.router, prefix="/internal")
```

---

## Vite proxy 配置

```javascript
// frontend/vite.config.js
server: {
  proxy: {
    '/api/devices': 'http://ctrl:8000',
    '/api/logs': 'http://ctrl:8000',
    '/api/dashboard': 'http://ctrl:8000',
    '/api/interfaces': 'http://config:8000',
    '/api/vlans': 'http://config:8000',
    '/api/execute': 'http://config:8000',
    '/api/batch': 'http://config:8000',
    '/api/assets': 'http://data:8000',
    '/api/backups': 'http://data:8000',
    '/api/tasks': 'http://data:8000',
  }
}
```

---

## docker-compose 变更

```yaml
services:
  ctrl:
    build: { context: ./backend, dockerfile: ctrl/Dockerfile }
    container_name: h3c-ctrl
    ports: ["8001:8000"]
    volumes: [./backend:/app, ./data:/app/data, ./logs:/app/logs]
    env_file: [.env]
    environment:
      - INTERNAL_CTRL_URL=http://ctrl:8000
      - INTERNAL_CONFIG_URL=http://config:8000
      - INTERNAL_DATA_URL=http://data:8000
    networks: [h3c-net]

  config:
    build: { context: ./backend, dockerfile: config/Dockerfile }
    container_name: h3c-config
    ports: ["8002:8000"]
    volumes: [./backend:/app, ./data:/app/data, ./logs:/app/logs]
    env_file: [.env]
    environment:
      - INTERNAL_CTRL_URL=http://ctrl:8000
      - INTERNAL_CONFIG_URL=http://config:8000
      - INTERNAL_DATA_URL=http://data:8000
    networks: [h3c-net]

  data:
    build: { context: ./backend, dockerfile: data/Dockerfile }
    container_name: h3c-data
    ports: ["8003:8000"]
    volumes: [./backend:/app, ./data:/app/data, ./logs:/app/logs, h3c-netctrl-backups:/data/backups]
    env_file: [.env]
    environment:
      - INTERNAL_CTRL_URL=http://ctrl:8000
      - INTERNAL_CONFIG_URL=http://config:8000
      - INTERNAL_DATA_URL=http://data:8000
    networks: [h3c-net]
```

---

## 故障注入测试场景（v2.4.1 验证）

| 故障 | 预期行为 | 验证 |
|---|---|---|
| `docker stop data` | config 改端口仍成功 + 中文错误"备份服务不可用，配置已生效" | config 接口返 success:true + 业务降级 |
| `docker stop ctrl` | config 使用本地 device 缓存继续工作 | config 接口返 success:true |
| `docker stop config` | data 备份/采集不受影响 | data 接口正常 |
| data 挂时触发备份 | 备份任务失败，不会阻塞主流程 | config 返回 success:true + 提示备份失败 |
| 3 容器都启动后 `docker compose ps` | 3 容器 running | health check 通过 |