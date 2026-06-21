## v20-platform-evolution Tasks

实施顺序：先基础设施 → 再后端能力 → 再前端页面 → 最后集成

---

### Phase 1: 工程基础设施（engineering-infra）

- [x] 1.1 初始化 Alembic，生成 alembic.ini 和 migrations/ 目录
- [x] 1.2 配置 alembic/env.py，关联 SQLAlchemy Base metadata
- [x] 1.3 执行 `alembic stamp head` 标记现有表状态
- [x] 1.4 生成 assets 表 migration 脚本（upgrade + downgrade）
- [x] 1.5 修改 main.py：用 `alembic upgrade head` 替代 `Base.metadata.create_all`
- [x] 1.6 验证 upgrade/downgrade 流程正常
- [x] 1.7 创建 GitHub Actions CI 配置（.github/workflows/ci.yml）
- [x] 1.8 补充后端测试用例（API 端点、XML 构建/解析）
- [ ] 1.9 推送验证 CI 流水线运行正常

### Phase 2: 前端平台化（platform-ui）

- [x] 2.1 安装 Bootstrap Icons 依赖
- [x] 2.2 创建 SideBar 组件（替代 NavBar），包含所有页面入口
- [x] 2.3 更新 App.vue 布局：侧边栏 + 内容区
- [x] 2.4 更新路由表：新增 Dashboard、运维终端、接口管理、CMDB 页面路由
- [x] 2.5 统一配色方案（深色侧边栏 + 浅色内容区）
- [x] 2.6 创建 Dashboard 页面组件（设备统计 + 最近日志 + 最近告警）
- [x] 2.7 新增 GET /api/dashboard 后端端点
- [x] 2.8 设备列表页添加状态指示灯（在线绿/离线灰）
- [x] 2.9 全局页面标题统一 + 图标
- [x] 2.10 自测：侧边栏导航、Dashboard 数据展示、视觉一致性

### Phase 3: CMDB 资产管理（cmdb）

- [x] 3.1 创建 Asset ORM 模型（assets 表），关联 Device
- [x] 3.2 Device 模型添加 asset relationship（一对一）
- [x] 3.3 创建设备时自动创建空 assets 记录
- [x] 3.4 删除设备时级联删除 assets 记录
- [x] 3.5 新增 Asset Pydantic 模型（AssetUpdate）
- [x] 3.6 新增 GET /api/devices/{id}/asset 端点
- [x] 3.7 新增 PUT /api/devices/{id}/asset 端点（手动编辑位置/标签/状态）
- [x] 3.8 新增 POST /api/devices/{id}/asset/refresh 端点（SSH 采集硬件信息）
- [x] 3.9 实现 SSH 命令解析器（display device/version/cpu-usage/memory）
- [x] 3.10 前端：设备详情页增加"资产信息"标签页
- [x] 3.11 前端：CMDB 页面展示资产表格
- [x] 3.12 自测：资产信息查看/编辑/刷新全流程

### Phase 4: 网络运维终端（ops-terminal）

- [x] 4.1 新增 SSH 命令执行工具函数（paramiko exec_command + 超时控制）
- [x] 4.2 新增 POST /api/devices/{id}/execute 端点
- [x] 4.3 命令执行自动记录操作日志（action=execute）
- [x] 4.4 前端：创建运维终端页面组件
- [x] 4.5 前端：设备选择下拉 + 命令输入框 + 执行按钮
- [x] 4.6 前端：输出展示区（等宽字体，保留格式）
- [x] 4.7 前端：命令历史记录（localStorage，最近 20 条）
- [x] 4.8 自测：命令执行、输出展示、超时处理、历史重发

### Phase 5: 接口管理（interface-management）

- [x] 5.1 探测 H3C 接口 NETCONF XML 结构（get-config filter）
- [x] 5.2 实现 SSH `display interface brief` 输出解析器
- [x] 5.3 新增 GET /api/devices/{id}/interfaces 端点
- [x] 5.4 探测 H3C 接口配置 NETCONF XML 结构（edit-config）
- [x] 5.5 实现 Access 模式配置（CLI 命令方式）
- [x] 5.6 实现 Trunk 模式配置（CLI 命令方式，模式+允许VLAN+PVID 联动）
- [x] 5.7 新增 PUT /api/devices/{id}/interfaces/{name}/config 端点
- [x] 5.8 接口配置操作自动记录日志
- [x] 5.9 前端：设备详情页增加"接口管理"标签页
- [x] 5.10 前端：接口列表表格（名称、状态、模式、VLAN 信息）
- [x] 5.11 前端：接口配置弹窗（模式切换动态展示配置项）
- [x] 5.12 自测：接口列表查看、Access/Trunk 联动配置下发

### Phase 6: 批量操作（batch-operations）

- [x] 6.1 新增 POST /api/batch/execute 端点（并行执行+结果汇总）
- [x] 6.2 批量执行自动记录操作日志（action=batch_execute）
- [x] 6.3 前端：设备列表页添加多选功能（勾选框）
- [x] 6.4 前端：批量操作弹窗（命令输入 + 执行按钮）
- [x] 6.5 前端：结果汇总表格（设备名、成功/失败、输出/错误）
- [x] 6.6 自测：多设备批量执行、部分失败不影响其他、结果汇总

### Phase 7: 日志扩展（log-viewer 修改）

- [x] 7.1 日志记录器新增 execute 和 batch_execute 操作类型
- [x] 7.2 前端日志筛选增加"命令执行"和"批量执行"选项
- [x] 7.3 自测：新操作类型日志正确记录和筛选

### Phase 8: 集成与收尾

- [ ] 8.1 全流程自测：Dashboard → 设备管理 → 运维终端 → 接口管理 → CMDB → 批量操作 → 日志
- [ ] 8.2 前端生产构建验证（Dockerfile 多阶段构建）
- [ ] 8.3 更新 docker-compose.dev.yml（如有变更）
- [ ] 8.4 更新 .env.example（如有新增配置项）
- [ ] 8.5 更新 PRD-V2.0.md 验收标准对照
- [ ] 8.6 提交代码并推送到 GitHub
