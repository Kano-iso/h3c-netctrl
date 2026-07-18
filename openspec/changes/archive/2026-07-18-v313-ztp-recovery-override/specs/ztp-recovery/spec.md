# ztp-recovery Specification

## ADDED Requirements

### Requirement: ZTP 恢复上线 override

系统 MUST 支持为已有设备写入一次性 ZTP 恢复配置。

#### Scenario: 写入恢复 override

- WHEN 用户提交目标管理 IP、平台、账号
- THEN 后端 MUST 写入共享 state 文件
- AND MUST NOT 修改 `.env`
- AND MUST NOT 改变正常新设备上线序列
- AND MUST NOT 自动触发备份回滚

#### Scenario: 清除恢复 override

- WHEN 用户清除恢复配置
- THEN 后端 MUST 删除共享 state 文件
- AND ztp-server MUST 恢复默认 `autocfg.cfg`

### Requirement: ztp-server runtime 渲染

ztp-server MUST 在运行中感知 override 文件变化，并重渲染 TFTP 根目录下的 `autocfg.cfg`。

#### Scenario: override 生效

- WHEN override 文件存在
- THEN `autocfg.cfg` MUST 使用 override 中的 host / platform / sysname / credential

#### Scenario: override 不存在

- WHEN override 文件不存在
- THEN `autocfg.cfg` MUST 使用 env vars 默认配置

### Requirement: OOB VRF 基础配置

autocfg.cfg MUST 配置 OOB 管理 VRF，并将 physical OOB 口绑定到该 VRF。

#### Scenario: 模板包含 mgt VRF

- WHEN 渲染 `autocfg.cfg`
- THEN 配置 MUST contain `ip vpn-instance mgt`
- AND physical OOB 口 MUST contain `ip binding vpn-instance mgt`
