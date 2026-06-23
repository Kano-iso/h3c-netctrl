## 1. 实施快解

- [x] 1.1 在 `configure_interface` 入口增加 `mode=trunk and allowed_vlans` 校验，命中即返回 APIResponse(success=False, error=...) + record_log failed
- [x] 1.2 错误信息模板：`该设备不支持通过 NETCONF 配置 trunk 允许 VLAN 列表（X），请到设备 CLI 手工执行：port trunk permit vlan X`
- [x] 1.3 重启后端容器，确认进程无报错
- [x] 1.4 验证：trunk + allowed_vlans 下发立即返回中文错误（不向设备发送任何请求），logs 表新增 failed 记录（id=85，时间 18:23:47）
- [x] 1.5 验证：access 模式正常下发成功（id=87，时间 18:23:50）
- [x] 1.6 验证：trunk 不带 allowed_vlans 正常下发 LinkType=2（id=86，时间 18:23:48）

## 2. 收尾

- [ ] 2.1 提交代码 `fix: trunk 模式接口带 allowed_vlans 时显式拒绝（NETCONF 设备能力限制）`
- [ ] 2.2 archive change
