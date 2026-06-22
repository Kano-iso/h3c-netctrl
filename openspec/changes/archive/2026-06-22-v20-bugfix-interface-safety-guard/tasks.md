## 1. 后端：模型 + 迁移

- [x] 1.1 Device 模型增加 protected_interfaces 字段（JSON 列表）
- [x] 1.2 Alembic migration 004

## 2. 后端：路由层保护

- [x] 2.1 interface.py 集成保护检查（force=false 默认）
- [x] 2.2 InterfaceConfig 增加 force 字段
- [x] 2.3 设备管理 API 暴露 protected_interfaces 读写

## 3. 前端

- [x] 3.1 DeviceManagement.vue 展示/编辑保护接口（最小化：API 支持，编辑 UI 留待下个变更）
- [x] 3.2 DeviceDetail.vue 配置保护口时显示确认弹窗

## 4. 验证

- [x] 4.1 测试：保护口被拒绝、非保护口正常、force=true 强制配置
- [ ] 4.2 提交代码并推送 + Archive 闭环
