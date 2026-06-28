## 1. 蓝图文档

- [ ] 1.1 新建 `docs/CONTAINER-DECOUPLING.md`：
  - 背景：当前 monolith 痛点
  - 4 容器职责表
  - 数据库归属（asset 容器承载 Postgres）
  - 拆分时序（v2.3 / v3.0 / 未来）
  - 技术挑战：跨服务事务、事件驱动
  - 明确标注"本次 change 仅做预留，未真拆"

## 2. 后端 SERVICE_NAME 注入

- [ ] 2.1 `backend/app/main.py` 启动时读取 `SERVICE_NAME` env（默认 `"core"`），log 打印 `service_name={value}`
- [ ] 2.2 验证：未设 env → log `service_name=core`；设 `SERVICE_NAME=asset` → log `service_name=asset`

## 3. Router 注释分组

- [ ] 3.1 `backend/app/routers/__init__.py` 顶部加注释表，每个 router 标注 `# future: core | asset | sdn | monitor`
  - 11 个 router 标注（按当前职责）：
    - `device.py` / `vlan.py` / `interface.py` / `execute.py` / `log.py` → **core**
    - `asset.py` / `backup.py`（未来）→ **asset**
    - `sdn.py`（未来 v3.0）→ **sdn**
    - `monitor.py`（未来）→ **monitor**
    - `auth.py` / `health.py` → **core**（基础设施）
- [ ] 3.2 **不实际移动文件**（保持 import 结构）

## 4. docker-compose 蓝图注释

- [ ] 4.1 `docker-compose.dev.yml` 在 `backend` 服务上方加注释：
  ```yaml
  # ============================================================
  # 未来容器拆分蓝图（v2.3 拆 asset / v3.0 加 sdn / 未来 monitor）
  # 当前 backend 服务 = monolith，承载 core + asset 业务
  # ============================================================
  ```
- [ ] 4.2 **不实际新增 service**

## 5. README 未来架构章节

- [ ] 5.1 `README.md` 在"版本状态"之后新增"未来架构"小节：
  - 4 容器职责简表
  - 数据库归属说明
  - 链接到 `docs/CONTAINER-DECOUPLING.md`

## 6. 验证

- [ ] 6.1 重启后端容器，log 看到 `service_name=core`
- [ ] 6.2 curl `/health` 返回 200
- [ ] 6.3 现有所有 API 行为不变（device / vlan / interface / asset 列表）
- [ ] 6.4 文档结构：`docs/CONTAINER-DECOUPLING.md` 存在，README 链接正确

## 7. 收尾

- [ ] 7.1 提交代码 `chore(arch): 容器解耦蓝图预留（仅注释+env，不真拆）`
- [ ] 7.2 archive change
