# H3C NetCtrl v1.0 实现文档

> 面向开发者/AI 助手的实现记录，记录蓝图与实际实现的差异、踩坑记录、技术决策

## 1. 项目概览

### 1.1 目标

基于 NETCONF over SSH 的 H3C 交换机轻量网控平台，v1.0 实现单设备管理 + VLAN CRUD。

### 1.2 技术栈

| 层 | 技术 | 版本 |
|---|---|---|
| 后端框架 | FastAPI | 0.115.x |
| NETCONF 客户端 | ncclient | 0.6.16 |
| SSH 传输 | paramiko | **2.10.3**（降级，见踩坑 3.1） |
| ORM | SQLAlchemy | 2.x |
| 数据库 | SQLite | 系统自带 |
| 密码加密 | cryptography/Fernet | 44.x |
| 前端 | 原生 HTML + Bootstrap 5 | CDN |
| 反向代理 | Nginx | alpine |
| 容器化 | Docker Compose | v2 |

### 1.3 目录结构

```
h3c-netctrl/
├── backend/
│   ├── app/
│   │   ├── __init__.py
│   │   ├── main.py              # FastAPI 入口，路由注册，启动事件
│   │   ├── config.py            # pydantic Settings，从 .env 加载配置
│   │   ├── database.py          # SQLAlchemy engine + session + Base
│   │   ├── models.py            # Device ORM 模型
│   │   ├── schemas.py           # Pydantic 请求/响应模型
│   │   ├── netconf_client.py    # NETCONF 连接管理器
│   │   ├── routers/
│   │   │   ├── device.py        # 设备 CRUD + 连接测试
│   │   │   └── vlan.py          # VLAN CRUD
│   │   └── utils/
│   │       ├── crypto.py        # Fernet 加密/解密
│   │       └── logger.py        # 日志配置
│   ├── Dockerfile.dev
│   └── requirements.txt
├── frontend/
│   ├── index.html
│   ├── js/
│   │   ├── api.js               # 统一 API 调用 + 错误展示 + loading
│   │   ├── device.js            # 设备管理逻辑
│   │   └── vlan.js              # VLAN 管理逻辑
│   ├── css/style.css
│   └── nginx.conf
├── data/                        # SQLite 数据库文件（挂载）
├── logs/                        # 应用日志（挂载）
├── docker-compose.dev.yml
├── Makefile
├── .env.example
└── .gitignore
```

---

## 2. 蓝图 vs 实际实现

### 2.1 架构层面

| 设计蓝图 | 实际实现 | 差异原因 |
|---|---|---|
| H3C VLAN 命名空间 `conf:vg` | `http://www.h3c.com/netconf/config:1.0` | H3C 实际设备的 NETCONF 命名空间与文档不一致，通过实际探测确认 |
| VLAN 数据结构 `Vlan/VlanInterfaces/VlanInterface` | `VLAN/VLANs/VLANID/ID` | H3C 设备的 VLAN XML 结构与标准 YANG 模型不同，是厂商私有结构 |
| paramiko 最新版 | paramiko 2.10.3 | 最新版 paramiko 3.x 不支持 H3C 旧设备的 SSH 密钥交换算法 |
| 多设备支持 | 单设备 | v1.0 刻意简化，数据库模型已预留扩展能力 |
| PostgreSQL | SQLite | v1.0 轻量化选择，SQLAlchemy ORM 抽象便于后续迁移 |

### 2.2 API 设计

蓝图设计的 API 端点与实际实现一致，无差异：

| 端点 | 方法 | 功能 |
|---|---|---|
| `/api/device` | GET | 获取设备信息 |
| `/api/device` | POST | 创建设备 |
| `/api/device` | PUT | 更新设备 |
| `/api/device/test` | POST | 测试连接 |
| `/api/vlans` | GET | 查询 VLAN 列表 |
| `/api/vlans` | POST | 创建 VLAN |
| `/api/vlans/{id}` | PUT | 修改 VLAN |
| `/api/vlans/{id}` | DELETE | 删除 VLAN |
| `/health` | GET | 健康检查 |

---

## 3. 踩坑记录

### 3.1 paramiko 版本兼容性（严重）

**现象**：使用 paramiko 3.x 连接 H3C 交换机时报错：
```
SSHException: Incompatible ssh peer (no acceptable kex algorithm)
```

**根因**：H3C 旧款交换机仅支持 `diffie-hellman-group14-sha1` 密钥交换算法，paramiko 3.x 默认不支持 SHA1（安全原因）。

**解决方案**：
1. 降级 paramiko 到 2.10.3
2. 在代码中手动设置 `_preferred_kex`，将 SHA1 算法加入优先列表

```python
paramiko.Transport._preferred_kex = (
    "diffie-hellman-group14-sha1",
    "diffie-hellman-group14-sha256",
    ...
)
```

**教训**：网络设备管理软件必须考虑老旧设备的兼容性，不能盲目升级依赖版本。

### 3.2 H3C VLAN NETCONF 命名空间（严重）

**现象**：使用标准/文档中的命名空间查询 VLAN 返回空数据或错误。

**排查过程**：
1. 尝试 `conf:vg` 命名空间 → 失败
2. 无 filter 的 `get-config` → 获取全量配置，发现 VLAN 数据存在
3. 逐个尝试不同命名空间和 filter 格式
4. 最终确认：`http://www.h3c.com/netconf/config:1.0` + `<VLAN></VLAN>` filter

**实际数据结构**：
```xml
<!-- 查询 filter -->
<top xmlns="http://www.h3c.com/netconf/config:1.0">
    <VLAN></VLAN>
</top>

<!-- 响应 -->
<VLANs>
    <VLANID><ID>1</ID></VLANID>
    <VLANID><ID>100</ID><AccessPortList>2-21</AccessPortList></VLANID>
</VLANs>
```

**教训**：H3C 的 NETCONF 实现是厂商私有的，不要轻信文档，必须通过实际设备探测确认。

### 3.3 Docker 构建速度（中等）

**现象**：首次 Docker 构建耗时 30+ 分钟（pip install 下载慢）。

**解决方案**：配置火山镜像源加速：
- apt: `mirrors.volces.com`
- pip: `mirrors.volces.com/pypi/simple/`

构建时间降至 45 秒（缓存命中时）。

### 3.4 Docker Compose version 字段（轻微）

**现象**：`docker-compose.dev.yml` 中的 `version: "3.8"` 在 Docker Compose V2 中产生弃用警告。

**解决方案**：移除 `version` 字段，Docker Compose V2 不再需要。

---

## 4. 技术决策记录

### 4.1 为什么用 SQLite 而不是 PostgreSQL？

| 因素 | SQLite | PostgreSQL |
|---|---|---|
| 运维复杂度 | 零（文件数据库） | 需要独立容器 + 持久化 |
| 并发写入 | 单写者 | 多写者 |
| v1.0 需求 | 单用户、低频操作 | 不需要 |
| 迁移成本 | 低（SQLAlchemy ORM 抽象） | - |

**决策**：v1.0 用 SQLite，后续如需多实例并发写入再迁移到 PostgreSQL。

### 4.2 为什么用 Fernet 而不是其他加密方案？

- Fernet 是对称加密，密钥通过环境变量注入，满足安全底线
- 不需要额外的密钥管理服务
- cryptography 库是 Python 生态标准，维护活跃

### 4.3 为什么前端用原生 HTML + Bootstrap 而不是 Vue/React？

- v1.0 页面简单（设备信息 + VLAN 表格），不需要 SPA 框架
- 减少构建工具链复杂度（不需要 Node.js、Webpack 等）
- Bootstrap CDN 直接引入，零构建
- 后续如需复杂交互再引入前端框架

### 4.4 为什么代码挂载而不是 COPY 到镜像？

- 开发环境需要热重载，代码挂载后 uvicorn 自动检测变更
- 依赖（pip install）在镜像内，保证环境一致性
- 生产环境应改为 COPY + 不挂载

---

## 5. 数据库设计

### 5.1 Device 表

| 字段 | 类型 | 说明 |
|---|---|---|
| id | INTEGER PK | 自增主键 |
| name | VARCHAR | 设备名称 |
| host | VARCHAR | 设备 IP |
| port | INTEGER | NETCONF 端口（默认 830） |
| username | VARCHAR | SSH 用户名 |
| password_encrypted | VARCHAR | Fernet 加密后的密码 |
| created_at | DATETIME | 创建时间 |
| updated_at | DATETIME | 更新时间 |

### 5.2 扩展性

- Device 模型已预留多设备扩展（id 自增主键）
- v1.0 的 `db.query(Device).first()` 可直接改为 `db.query(Device).all()` 或 `db.query(Device).filter_by(id=device_id)`
- VLAN 数据不持久化在数据库中，直接从设备实时查询（v1.0 设计决策）

---

## 6. 镜像大小分析

| 镜像 | 大小 | 组成 |
|---|---|---|
| h3c-netctrl-backend | 563MB | Debian 87MB + Python 46MB + **gcc 175MB** + pip 包 105MB |
| h3c-netctrl-frontend | 93MB | Alpine 9MB + nginx 52MB + 配置 32MB |

**已知问题**：gcc 编译依赖未在 pip install 后删除，占 175MB。

**优化方案**（v1.1 执行）：
```dockerfile
RUN apt-get update && apt-get install -y --no-install-recommends gcc && \
    pip install --no-cache-dir -r requirements.txt && \
    apt-get purge -y gcc && apt-get autoremove -y && \
    rm -rf /var/lib/apt/lists/*
```
预计可减至 ~380MB。

---

## 7. 回滚方案

### 7.1 代码回滚

8 次 git commit，每次对应一个 Phase：
```
f3a9b1e feat: init project with OpenSpec proposal
48809b5 chore: add .gitignore and .env.example
f74f471 feat: add project scaffold (Task 1.1-1.8)
21ca4f1 feat: add backend core modules (Task 2.1-2.6)
799238f feat: add device management and NETCONF client (Task 3.1-3.6)
7cab554 feat: add VLAN management (Task 4.1-4.7)
442293e feat: add logging system (Task 5.1-5.4)
d583ff9 feat: add frontend UI (Task 6.1-6.7)
655163f fix: adapt VLAN NETCONF XML, fix paramiko compat (Task 7.1-7.6)
8049211 chore: archive v1-mvp-foundation
```

回滚命令：`git revert <commit-hash>` 或 `git checkout <commit-hash>`

### 7.2 数据库备份

```bash
make backup  # 备份到 backups/dev_YYYYMMDD_HHMMSS.db
```

### 7.3 待补强

- [ ] 引入 Alembic 做 DB migration（upgrade/downgrade）
- [ ] 加 `make rollback` 自动化脚本
- [ ] 版本发布前强制 `make backup`

---

## 8. 提交历史与 OpenSpec 对应

| Commit | OpenSpec Phase | 说明 |
|---|---|---|
| f74f471 | Phase 1: Project Scaffold | 目录结构、Docker、Makefile |
| 21ca4f1 | Phase 2: Backend Core | config、database、models、schemas、crypto |
| 799238f | Phase 3: Device Management | 设备 CRUD、NETCONF 客户端 |
| 7cab554 | Phase 4: VLAN Management | VLAN CRUD、NETCONF XML 构造 |
| 442293e | Phase 5: Logging | 日志系统、DEBUG XML 报文 |
| d583ff9 | Phase 6: Frontend UI | HTML + Bootstrap + JS |
| 655163f | Phase 7: Integration | 集成验证、H3C 适配修复 |
