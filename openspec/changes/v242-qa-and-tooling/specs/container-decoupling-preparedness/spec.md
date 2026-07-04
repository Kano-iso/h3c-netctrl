# container-decoupling-preparedness Spec Deltas (v242-qa-and-tooling)

> 本 change 在 [container-decoupling-preparedness](../../specs/container-decoupling-preparedness/spec.md) 之上 MODIFIED：
> 3 容器准备度：qa 工具默认 test 设备约定文档化。

---

## MODIFIED Requirements

### Requirement: 3 容器准备度：qa 工具默认 test 设备约定

`docs/ops-toolkit.md` + `.trae/rules/qa规范.md` MUST 文档化"qa 工具默认指向 test 设备"约定：

- **默认 target**：Test-Switch-177 (192.168.100.177, id=7)
- **强制理由**：qa 工具"反复跑"特性，误连生产可能导致配置污染
- **绕过方式**：显式 `--device <IP>`（不阻止，但日志 warn）
- **覆盖范围**：
  - `ops-toolkit` 6 脚本（check-host / ssh-test / check-netconf / capture-config / reboot-wait / audit-switch）
  - qa-backend 真机 e2e fixture（默认 .177）
  - qa 容器入口 banner（标注默认目标）

#### Scenario: 文档可追溯

- **WHEN** 团队成员查看 `.trae/rules/qa规范.md`
- **THEN** MUST 看到 "qa 默认设备" 章节
- **AND** MUST 看到设备名→IP 映射表
- **AND** MUST 看到 "MCP 浏览器定位" 章节（小测试/不进 qa 容器）
