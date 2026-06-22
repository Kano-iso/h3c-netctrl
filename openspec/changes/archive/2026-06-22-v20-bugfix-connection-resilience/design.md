## Context

真实设备测试（192.168.100.100）发现的痛点：
- 设备 NETCONF 失败后，错误信息只有"连接被拒绝"或"No route to host"
- 用户配置 access vlan 200 但 VLAN 200 未创建，设备端报错
- 连续操作后设备 NETCONF 进程可能挂掉，端口不可达，没有重试

业界网络自动化工具（Ansible、NAPALM）的通用做法：
1. 连接前先做网络层诊断（ping → TCP 端口探测）
2. 协议层连接失败时指数退避重试
3. 业务操作前预校验（如 VLAN 是否存在）
4. 所有失败必须有结构化错误信息

## Goals / Non-Goals

**Goals:**
- 接口配置前先校验 VLAN 是否存在
- NETCONF 连接失败时分类错误：网络不通 / 端口关闭 / 认证失败 / 协议错误
- NETCONF 操作自动重试 2 次（指数退避）
- 渐进式诊断：ping → nc → netconf
- 错误日志必须可读，记录到 log 表的 error_message 字段

**Non-Goals:**
- 不做 SSH 端的改造（运维终端已用 SSH）
- 不做连接池（避免引入额外复杂度）
- 不改前端主要功能

## Decisions

### D1: 渐进式设备诊断

**选择**：在 NetconfClient.connect 之前，先做：
1. `ping` 检测网络可达性
2. `nc` 检测端口开放
3. `netconf` 建立 SSH+NETCONF session

**理由**：快速定位是网络问题、端口问题、还是认证/协议问题。

### D2: 自动重试（指数退避）

**选择**：NETCONF 连接/操作失败时，自动重试 2 次，间隔 1s/2s

**理由**：H3C NETCONF 偶发连接失败是已知的，重试能解决大部分瞬时问题。但不能无限重试，避免卡住。

### D3: VLAN 预校验

**选择**：接口配置前，先 get-config 查询 VLAN 是否存在

**理由**：H3C 的 `port access vlan X` 严格要求 VLAN 存在，否则返回 error。提前校验能给用户更明确的提示。

### D4: 错误信息分级

**选择**：将错误分为四级，错误信息中文：
- 网络层：设备不可达，请检查 IP 和网络
- 端口层：NETCONF 端口 830 未开放，请检查 netconf service enable
- 认证层：用户名或密码错误
- 协议层：NETCONF 协议错误，{具体 message}

**理由**：用户能根据错误信息快速知道该查哪里。

## Risks / Trade-offs

- 渐进式诊断会增加 200-500ms 延迟 → 对单次接口配置可接受
- VLAN 预校验需要多一次 NETCONF 查询 → 简单查询，耗时 < 1s
- 重试最多 3 次 → 失败 case 最多等待 1+2=3s，可接受
