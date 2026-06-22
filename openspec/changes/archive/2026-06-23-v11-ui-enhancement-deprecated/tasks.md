## v11-ui-enhancement Tasks

实施顺序：先基础设施（导航框架）→ 再后端 API 重构 → 再前端业务页面 → 最后日志功能

---

### Phase 1: 前端框架搭建（nav-framework）

- [ ] 1.1 初始化 Vue 3 + Vite 项目，配置 TypeScript、ESLint
- [ ] 1.2 安装 Vue Router，配置路由表（/、/devices/:id、/logs）
- [ ] 1.3 创建基础布局组件（NavBar + RouterView）
- [ ] 1.4 配置 Vite dev server 代理（/api → 后端 8000）
- [ ] 1.5 迁移 Bootstrap 5 CDN 引入，确保样式正常
- [ ] 1.6 创建空白页面组件（DeviceList、DeviceDetail、LogViewer）占位
- [ ] 1.7 更新 docker-compose.yml：前端容器使用 Vite dev server 模式

### Phase 2: 后端 API 重构（device-management）

- [ ] 2.1 重构 device.py 路由：/api/device → /api/devices，支持多设备 CRUD
- [ ] 2.2 新增 DELETE /api/devices/{id} 端点
- [ ] 2.3 新增 GET /api/devices/{id} 端点
- [ ] 2.4 重构 vlan.py 路由：/api/vlans → /api/devices/{id}/vlans
- [ ] 2.5 VLAN 路由增加 device_id 路径参数，根据设备 ID 查找设备建立 NETCONF 连接
- [ ] 2.6 新增 v1.0 兼容路由层（/api/device 重定向），标记 Deprecation 头
- [ ] 2.7 更新 Pydantic 模型：新增 DeviceListResponse
- [ ] 2.8 自测：所有新端点可通过 Swagger UI 正常调用

### Phase 3: 前端多设备页面（multi-device）

- [ ] 3.1 实现设备列表页面组件（DeviceList.vue），展示所有设备
- [ ] 3.2 实现添加设备弹窗（表单校验：IP、端口、必填项）
- [ ] 3.3 实现删除设备功能（二次确认弹窗）
- [ ] 3.4 实现设备连接状态指示（在线/离线/未知）
- [ ] 3.5 实现设备详情页面组件（DeviceDetail.vue），展示设备信息
- [ ] 3.6 迁移 VLAN 管理功能到设备详情页内
- [ ] 3.7 前端 API 调用层适配新端点路径
- [ ] 3.8 自测：多设备添加、切换、VLAN 操作全流程

### Phase 4: 日志功能（log-viewer）

- [ ] 4.1 新增 Log ORM 模型（logs 表），含 device_id 外键
- [ ] 4.2 创建数据库迁移脚本（Alembic 或手动）
- [ ] 4.3 实现日志记录中间件，自动记录设备操作
- [ ] 4.4 新增 GET /api/logs 端点（支持筛选、分页）
- [ ] 4.5 实现日志查看页面组件（LogViewer.vue）
- [ ] 4.6 实现日志筛选功能（设备、操作类型、时间范围）
- [ ] 4.7 实现日志分页展示
- [ ] 4.8 自测：操作后日志自动记录，日志页面可筛选查看

### Phase 5: 集成与收尾

- [ ] 5.1 更新前端 Dockerfile（多阶段构建：Node.js 构建 → Nginx 运行）
- [ ] 5.2 更新 nginx.conf 适配 Vue SPA 路由（history 模式 fallback）
- [ ] 5.3 更新 docker-compose.yml 适配新前端构建流程
- [ ] 5.4 全流程自测：设备管理 → VLAN 操作 → 日志查看
- [ ] 5.5 移除旧前端文件（index.html、css/、js/）
- [ ] 5.6 更新 .env.example（如有新增配置项）
