## Context

项目从零开始，本地已有 H3C HCL 模拟器环境（NETCONF over SSH 830端口就绪），开发虚拟机已安装 Docker/Docker Compose。需要搭建完整的 FastAPI + Nginx + SQLite 容器化工程，实现单台 H3C 交换机的 VLAN Web 管控。

当前状态：空项目目录，仅有 PRD 和流程规范文档。

## Goals / Non-Goals

**Goals:**
- 搭建可运行的容器化工程骨架，支持热重载开发
- 实现 NETCONF 协议与 H3C 设备的完整交互链路
- 实现 VLAN 增删改查全流程，前端可操作、错误可读
- 日志系统支持 DEBUG 模式打印完整 NETCONF 报文
- 一条命令启动完整开发环境

**Non-Goals:**
- 多设备管理、批量操作
- 用户认证、权限控制
- 端口配置、Trunk/Access、二层网络
- EVPN/VXLAN/路由等复杂网络业务
- 缓存、消息队列、高可用
- 生产级安全加固

## Decisions

### D1: 后端框架选型 — FastAPI
- **选择**: FastAPI
- **理由**: PRD 明确指定；异步支持好，适合 I/O 密集的 NETCONF 操作；自带 OpenAPI 文档；Python 生态与 ncclient 兼容
- **备选**: Flask（同步、无自动文档）、Django（过重）

### D2: 前端方案 — 纯 HTML + 原生 JS + Bootstrap CDN
- **选择**: 纯 HTML/JS/CSS，引入 Bootstrap CDN 做样式
- **理由**: 极简 MVP，无需构建工具链；Nginx 直接托管静态文件；避免 Node.js 构建依赖
- **备选**: Vue SPA（需构建链，V1.0 过重）、React（同上）

### D3: 数据库 — SQLite + SQLAlchemy
- **选择**: SQLite 文件数据库，SQLAlchemy ORM
- **理由**: 零运维、单文件持久化、挂载宿主机即可；SQLAlchemy 提供后续迁移到 MySQL 的能力
- **备选**: 原生 SQL（无迁移路径）、MySQL（V1.0 过重）

### D4: 密码存储 — Fernet 对称加密
- **选择**: cryptography 库 Fernet 加密
- **理由**: 比 base64 编码更安全，密钥通过环境变量注入，实现简单
- **备选**: base64 编码（非加密，不安全）、bcrypt（用于哈希，不可逆不适合需要解密的场景）

### D5: NETCONF 交互 — ncclient
- **选择**: ncclient 库，标准 NETCONF get-config / edit-config
- **理由**: Python 标准 NETCONF 客户端；支持 H3C 私有 XML namespace；社区成熟
- **关键点**: H3C 设备使用私有 YANG namespace，需在 RPC 中指定正确的 namespace prefix

### D6: 容器化方案 — 双容器 + 宿主机挂载
- **选择**: 后端容器（FastAPI + ncclient）+ 前端容器（Nginx），SQLite 文件挂载宿主机
- **理由**: 最小化容器数量；数据持久化简单；开发环境支持热重载
- **备选**: 三容器（加独立 DB 容器，V1.0 不需要）

### D7: 项目目录结构
```
h3c-netctrl/
├── backend/
│   ├── app/
│   │   ├── main.py          # FastAPI 入口
│   │   ├── config.py        # 配置管理
│   │   ├── database.py      # 数据库连接
│   │   ├── models.py        # SQLAlchemy 模型
│   │   ├── schemas.py       # Pydantic 数据模型
│   │   ├── netconf_client.py # NETCONF 交互封装
│   │   ├── routers/
│   │   │   ├── device.py    # 设备管理路由
│   │   │   └── vlan.py      # VLAN 管理路由
│   │   └── utils/
│   │       └── crypto.py    # 加密工具
│   ├── requirements.txt
│   └── Dockerfile.dev
├── frontend/
│   ├── index.html
│   ├── css/
│   ├── js/
│   └── nginx.conf
├── data/                    # SQLite 持久化（.gitignore）
├── logs/                    # 日志挂载（.gitignore）
├── docker-compose.dev.yml
├── Makefile
├── .env.example
└── .gitignore
```

## Risks / Trade-offs

- **[H3C 私有 XML 规范]** → H3C 设备的 NETCONF XML namespace 与标准 IETF 不同，需在模拟器上实际抓包确认。缓解：开发初期优先用 `get-config` 全量拉取确认 XML 结构，再构造 edit-config
- **[ncclient 会话管理]** → NETCONF SSH 会话需正确关闭，否则设备端会话残留。缓解：使用 context manager 管理连接生命周期
- **[SQLite 并发]** → SQLite 写入并发有限，V1.0 单用户场景无影响，后续迭代需升级。缓解：文档标注此限制
- **[模拟器稳定性]** → HCL 模拟器可能存在 NETCONF 响应延迟或超时。缓解：设置合理的超时时间，错误信息明确提示
