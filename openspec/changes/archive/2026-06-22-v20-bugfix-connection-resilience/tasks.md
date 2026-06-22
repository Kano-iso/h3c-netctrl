## 1. 渐进式设备诊断

- [ ] 1.1 在 utils 中新增 diagnose_device 函数（ping + nc 端口检测）
- [ ] 1.2 NetconfClient.connect 失败时调用 diagnose_device 给出具体原因
- [ ] 1.3 错误信息按四级分类（网络/端口/认证/协议）

## 2. NETCONF 自动重试

- [x] 2.1 在 NetconfClient 中实现重试装饰器（最多 2 次，间隔 1s/2s）
- [x] 2.2 连接失败时记录重试日志

## 3. VLAN 预校验

- [x] 3.1 在 interface.py 中实现 vlan_exists 检查函数（NETCONF get-config）
- [x] 3.2 configure_interface 路由先校验 VLAN，存在再下发配置

## 4. 验证与提交

- [ ] 4.1 真实设备测试：网络不可达、端口关闭、认证失败、VLAN 不存在、VLAN 存在
- [ ] 4.2 前端日志展示验证
- [x] 4.3 提交代码并推送 + Archive 闭环
