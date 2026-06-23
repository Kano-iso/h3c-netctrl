## Context

下发 trunk 模式接口配置（创客/接口配置模块）持续失败。发起 change 时假设 H3C V7 模型下 trunk 允许 VLAN 走 VLAN/TrunkPorts/TrunkPort/PermitVlanList。实施时对设备做了实地探测 + H3C 官方文档核查，**双重确认该假设错误**：

- H3C 官方命令参考明确说配置 trunk 端口只需 LinkType+PVID
- 设备上唯一已存在的 trunk 接口（if_index=3）只存了 `<LinkType>2</LinkType>`
- 试了 10 个常见 allowed_vlans 字段名 + VLAN/TrunkPorts 节点，全部被设备拒绝
- 历史所有成功的 interface_config 记录全部是 access 模式，无成功 trunk 案例

## Goals / Non-Goals

**Goals:**
- 后端在收到 `mode=trunk and allowed_vlans` 时直接返回明确中文错误，不向设备发送任何 edit-config
- access 模式（mode=access 或 trunk 不带 allowed_vlans）行为保持不变
- 错误信息告知用户如何用 CLI 手工补全

**Non-Goals:**
- 不实现 SSH/CLI 下发路径（独立 change）
- 不修改前端
- 不修改 VLAN 路由

## Decisions

### Decision 1: 显式拒绝 + 明确错误
- 原因：用户决策"先快解"，5 行代码即可，不阻塞 release
- 备选：降级下发（只下发 LinkType/PVID，allowed_vlans 忽略）— 拒绝，会给用户"成功"假象

### Decision 2: 校验放在 `configure_interface` 入口，不放在 `_build_interface_config_xml`
- 原因：避免构造无效 XML，提升错误可读性
- 备选：在 XML 构造层做检查 — 拒绝，错误信息需要访问 device.host 等上下文

### Decision 3: 同时写 `logs` 表
- 原因：保持现有审计链路
- 备选：直接 APIResponse 失败不写日志 — 拒绝，破坏一致性

## Risks / Trade-offs

- [Risk] 用户期望 trunk 配置能落盘，发布后仍需 CLI 手工补全 — 接受，错误信息已说明
- [Trade-off] 显式拒绝 vs 降级 — 已确认走"显式拒绝"，降级会误导用户

## Migration Plan

- 无数据迁移
- 部署：直接覆盖后端容器，hot-reload 或重启 `h3c-netctrl-backend`
- 回退：revert 本次 commit
