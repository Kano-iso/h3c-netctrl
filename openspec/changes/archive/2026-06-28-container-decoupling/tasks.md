## 1. 蓝图文档

- [x] 1.1 新建 `docs/CONTAINER-DECOUPLING.md`：背景 + 4 容器职责 + 数据库归属 + 拆分时序 + 技术挑战 + 实施入口

## 2. 后端 SERVICE_NAME 注入

- [x] 2.1 `backend/app/main.py` 启动时读取 `SERVICE_NAME` env（默认 `"core"`），log 打印 `service_name={value}`（实测：log `service_name=core (future split: core/asset/sdn/monitor)` ✓）
- [x] 2.2 验证：未设 env → log `service_name=core`；业务行为不变

## 3. Router 注释分组

- [x] 3.1 `backend/app/routers/__init__.py` 顶部加注释表（12 行 router 归属对照表）
- [x] 3.2 import 结构不变

## 4. docker-compose 蓝图注释

- [x] 4.1 `docker-compose.dev.yml` 在 `backend` 服务上方加蓝图注释 + `SERVICE_NAME` env 注入
- [x] 4.2 未新增 service

## 5. README 未来架构章节

- [x] 5.1 `README.md` 在"版本状态"之后新增"未来架构"小节（4 容器简表 + 链接 CONTAINER-DECOUPLING.md）

## 6. 验证

- [x] 6.1 重启后端容器，log 看到 `service_name=core (future split: core/asset/sdn/monitor)` ✓
- [x] 6.2 curl `/health` 返回 200 ✓
- [x] 6.3 现有所有 API 行为不变（`/api/devices` 返回 7 台）✓
- [x] 6.4 文档结构：`docs/CONTAINER-DECOUPLING.md` 存在，README 链接正确 ✓

## 7. 收尾

- [ ] 7.1 提交代码 `chore(arch): 容器解耦蓝图预留（仅注释+env，不真拆）`
- [ ] 7.2 archive change
