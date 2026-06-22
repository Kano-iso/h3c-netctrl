## Context

真实设备测试事故复盘：
- 测试时让 AI 自动选 if_index 做测试，AI 选了 if_index=2 (G1/0/1)
- G1/0/1 是设备和本机之间的连接口
- 配置为 access 后链路中断
- 设备 NETCONF 失联，AI 无法恢复

事后用户人工修复了 G1/0/1 = access 100

事故根因：
1. **没有"受保护接口"概念**：任何 if_index 都可以配置
2. **AI 没有"危险操作识别"**：不知道哪些口是关键口
3. **没有二次确认**：误操作立刻生效

业界网络自动化的标准做法：
- 提供"dry-run"模式（先看不下发）
- 提供"safe-list"机制（保护关键口）
- 关键操作二次确认

## Goals / Non-Goals

**Goals:**
- Device 模型增加 `protected_interfaces` JSON 字段（if_index 列表）
- 接口配置前检查 if_index 是否被保护，是则返回明确错误
- 前端提供保护接口配置 UI
- 高风险操作（保护口强制配置）需要 force=true 参数

**Non-Goals:**
- 不做 dry-run（项目用 Python，不做预演成本太高）
- 不做基于接口名的智能识别（用户手动配置最准确）
- 不做操作审计日志（log 表已记录 error_message）

## Decisions

### D1: Device 模型加 protected_interfaces 字段

**选择**：`protected_interfaces: Mapped[str] = mapped_column(Text, default="[]")`，存 JSON 列表

**理由**：
- 用 if_index 而非接口名（NETCONF 配置用 if_index）
- JSON 列表灵活，可以随时增删
- 默认空列表（不保护任何接口，向后兼容）

### D2: 配置前检查

**选择**：在 configure_interface 路由中，先查 Device.protected_interfaces，命中则拒绝

**理由**：
- 简单直接，不影响非保护口的正常配置
- 错误信息明确：哪个 if_index 被保护，提示用户先解除保护或加 force=true

### D3: force 参数（强制配置）

**选择**：InterfaceConfig 增加 `force: bool = False` 字段，force=true 时跳过保护检查

**理由**：
- 紧急情况下用户可能需要配置保护口（如更换链路）
- 通过 API 显式传 force 标识"我知道风险"
- 实际生产中由人工决策 force

### D4: 错误信息中文

**选择**：保护命中时返回：`接口 if_index={X} 在保护列表中，禁止配置。如需配置请加 force=true 或先在设备管理中解除保护`

**理由**：明确告诉用户怎么解决，而不是只说"被保护了"

## Risks / Trade-offs

- 用户可能误把上行口加入保护导致无法配置 → 保护列表可由用户在 UI 中管理
- force=true 无审计 → log 表会记录 force=true，可追溯
