# Tasks

- [x] 更新 v3.3 PRD，明确 VPC/EVPN 生命周期闭环范围。
- [x] 扩展 deployment 数据模型，关联端口绑定审计。
- [x] 新增端口绑定 CRUD 与绑定/解绑 deployment API。
- [x] 支持 VPC delete、port bind/unbind、gateway-only delete 执行器动作。
- [x] 增加后端单测覆盖用户动作和状态回写。
- [x] 运行 QA 容器内后端测试。
- [ ] 定义并实现 Fabric 级 VPC 编排：创建 VPC 时默认面向所有 Leaf 生成有序 deployment 集合。
- [ ] 定义 Leaf 设备选择逻辑：默认全 Leaf，可扩展为用户选择部分 Leaf。
- [ ] 增加 VPC 级下发/撤回 API，屏蔽单 deployment 细节。
- [ ] 在真机上使用隔离测试资源验证 create/delete/port-bind/port-unbind/gateway-delete。
- [ ] 增加 display 状态采集与二次校验闭环。
