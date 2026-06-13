## Why

项目从零启动，需要搭建 H3C NetCtrl V1.0 MVP 的完整工程骨架与核心功能，实现通过 Web 页面对单台 H3C 交换机进行 VLAN 增删改查，验证 NETCONF 协议交互链路、容器化开发部署流程的可行性。

## What Changes

- 新建项目工程骨架：FastAPI 后端 + Nginx 前端 + SQLite 持久化 + Docker 容器化
- 实现设备连接管理：录入设备参数、加密存储密码、NETCONF 连接测试
- 实现 VLAN 全量 CRUD：基于 NETCONF get-config / edit-config 操作 H3C 交换机 VLAN
- 实现极简前端页面：单页面集成设备信息、VLAN 表格、操作表单、错误提示
- 实现统一 API 返回格式与错误处理
- 实现可开关的 NETCONF 报文日志（INFO/DEBUG）
- 实现 Makefile 自动化命令与 docker-compose 一键启动

## Capabilities

### New Capabilities
- `project-scaffold`: 项目目录结构、Docker 配置、Makefile、环境变量模板、Git 初始化
- `device-management`: 设备参数录入、密码加密存储、NETCONF 连接测试、SQLite 持久化
- `vlan-management`: VLAN 查询、新增、修改、删除，H3C NETCONF XML 适配，异常统一处理
- `frontend-ui`: 极简单页面，设备信息展示、VLAN 表格、新增/编辑弹窗、错误提示、Loading 状态
- `logging-system`: 环境变量控制日志级别，INFO 记录操作行为，DEBUG 打印 NETCONF 完整报文

### Modified Capabilities
<!-- 无已有能力需要修改 -->

## Impact

- 新增 Python FastAPI 后端服务，依赖 ncclient、sqlalchemy、cryptography 等
- 新增 Nginx 静态前端服务
- 新增 SQLite 数据库文件（宿主机挂载持久化）
- 新增 docker-compose.dev.yml / Dockerfile.dev 容器化配置
- 新增 Makefile 自动化脚本
- 新增 .env.example 环境变量模板
