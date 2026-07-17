# H3C NetCtrl V3.1 PRD：ZTP（Zero Touch Provisioning）整体功能

| 版本 | 日期 | 作者 | 说明 |
|---|---|---|---|
| V3.1 Draft | 2026-07-18 | 用户拍板 + Codex 共创 | V3.1 = ZTP 整体功能大版本蓝图，4 个子阶段（v3.1.0~v3.1.3）逐步落地 |

---

## 1. 背景与目标

### 1.1 背景

当前项目**设备上线流程完全手动**：一线人员接设备 → 串口/console 配管理 IP → 配 SSH 凭据 → 配 NETCONF → 在平台 `POST /api/devices` 添加资产。流程重复、易错，**不符合"白屏用户零操作上线"的目标**。

### 1.2 目标

**新设备插线 + 一次重启即可自动上线**：
1. 自动获取管理 IP（OOB 口 DHCP）
2. 自动应用最小基础配置（sysname / SSH / NETCONF / 凭据）
3. 平台**自动发现并纳管**（白屏用户无需任何操作）
4. 资产自动可见

### 1.3 关键约束

- ✅ **只做基础配置**：SSH 22 + NETCONF 830 + sysname + 凭据
- ❌ **不做业务配置**：VPC / 端口绑定 / 路由协议 / 业务 VLAN
- ❌ **不做配置联动**：ZTP 完成后由 controller 推业务配置
- ✅ **白屏用户零操作**：设备上线 = 平台可见，无需人工

## 2. V3.1 大版本拆分

V3.1 = 4 个子版本（v3.1.0~v3.1.3）逐步落地：

| 子版本 | 主题 | 关键产出 | 状态 |
|---|---|---|---|
| **v3.1.0** | ZTP 调研 | 决策 B 精简 ZTP + 独立 ztp-server 容器 + autocfg.cfg 模板（T7064P15 验证通过）| ✅ **已发版**（[RELEASE-NOTES-v3.1.0.md](RELEASE-NOTES-v3.1.0.md)）|
| **v3.1.1** | ZTP 落地 | 1:1 静态 IP 池子（DHCP 拿 IP 即绑定静态 IP）+ autocfg.cfg 多平台适配（.5 R6555 / .26 R7643P02 / .177 T7064P15 各一份模板）| ⏳ 待启动 |
| **v3.1.2** | 自动纳管 | controller 监听 DHCP lease → 主动 SSH 纳管 → 推业务 IP → 同步资产 | ⏳ 待启动 |
| **v3.1.3** | 资产可见 | 前端可查设备（无需手动 `POST /api/devices`）| ⏳ 待启动 |

## 3. v3.1.1 ZTP 落地

### 3.1 目标

解决 v3.1.0 留下的 2 个未解决问题：
1. **IP 不持久**（当前 OOB DHCP lease 12h 后过期）
2. **多平台模板未适配**（autocfg.cfg 仅在 .177 T7064P15 验证通过，.5 R6555 / .26 R7643P02 未测）

### 3.2 范围

- **1:1 静态 IP 池子方案**：
  - DHCP 池（`192.168.100.200-.250`）+ 静态 IP 池（**1:1 映射**）
  - 设备首次 DHCP 拿 .250 → controller 立即 SSH 推 .250 静态 IP 配置 + 持久化
  - 下次设备重启 → 启动时静态 IP + DHCP 都生效（DHCP 不冲突）
  - 静态 IP 配置覆盖 OOB 口，确保 IP 持久
- **autocfg.cfg 多平台适配**：
  - .5 S6850 R6555（无 autocfg，需要 SSH 推送）
  - .26 V9850 R7643P02（autocfg 命令兼容性）
  - .177 S6850 T7064P15（已验证）
  - **方案 A**：每平台 1 份 autocfg.cfg 模板（按 sysname 路由）
  - **方案 B**：通用模板 + 平台差异条件分支（jinja2 渲染）
- **关闭首次登录改密**：autocfg.cfg 模板加 `password-control login-password-change disable`（v3.1.0 已加）

### 3.3 设计决策（待 v3.1.1 change 启动时细化）

- DHCP 池 vs 静态 IP 池：1:1 映射策略（用户已拍板）
- 静态 IP 推送通道：SSH 22（已 v3.0 验证）
- 静态 IP 持久化：autocfg.cfg 模板 vs SSH 推 `save force`（按平台选择）

### 3.4 验收标准

- [ ] .5 / .26 / .177 三平台 autocfg.cfg 模板全部验证通过
- [ ] 1:1 静态 IP 池子在 .177 上验证（空配置启动 → DHCP 拿 .250 → controller SSH 推 .250 静态 IP → 重启后 .250 持久）
- [ ] DHCP lease 过期后设备 IP 仍是 .250（静态 IP 生效）
- [ ] 17 测试覆盖：3 平台 × 5 场景（空配置 / 部分配置 / 静态 IP 已配 / DHCP 冲突 / lease 过期）

## 4. v3.1.2 自动纳管

### 4.1 目标

设备 ZTP 完成后，**controller 主动发现并纳管**，白屏用户无需 `POST /api/devices`。

### 4.2 范围

- **DHCP lease 监听**：
  - 复用 ztp-server 容器 dnsmasq，开启 lease log
  - 解析 log → 提取 IP / MAC / sysname
- **主动 SSH 纳管**：
  - controller 定期 poll DHCP lease log
  - 新设备 → SSH 连接 → 验证凭据 → `POST /api/devices`（设备资产表 + 资产表）
  - 失败重试 + 死信队列
- **推业务 IP**：
  - 纳管成功后 → SSH 推业务 IP（VLAN interface IP / Loopback IP 等）
  - IP 由 controller 维护（避免 DHCP 漂移）

### 4.3 验收标准

- [ ] 新设备 ZTP 完成 60s 内自动出现在 ctrl 容器设备表
- [ ] 资产表同步更新（serial / model / mgmt IP / vendor）
- [ ] 业务 IP 推送成功（VLAN interface / Loopback）
- [ ] 白屏用户**零操作**看到新设备

## 5. v3.1.3 资产可见

### 5.1 目标

前端设备列表 / CMDB / Dashboard 自动显示新设备，**无需手动刷新**。

### 5.2 范围

- **前端实时刷新**：
  - Devices.vue / CMDB.vue 表格自动 poll（5s 间隔）
  - 新设备自动出现在列表
- **Dashboard 统计**：
  - 设备总数 / 在线 / 离线 实时更新
  - 按 vendor / model 分布
- **告警（可选）**：
  - 新设备上线通知（WebSocket / SSE 推送）

### 5.3 验收标准

- [ ] 新设备 ZTP 完成 90s 内前端 Devices.vue 表格自动显示
- [ ] Dashboard 设备总数 +1
- [ ] 用户无需手动刷新页面

## 6. 不做（明确边界）

- ❌ **不做 ZTP 业务配置**：VPC / 端口绑定 / 路由协议 / 业务 VLAN 由 v3.0 骨架 + v3.2 验证负责
- ❌ **不做 etcd 协调**：v3.5 远期
- ❌ **不做前端大屏**：v3.4

## 7. 依赖关系

- v3.1.1 不依赖 v3.1.0 之外的能力
- v3.1.2 依赖 v3.1.1（静态 IP 持久化）
- v3.1.3 依赖 v3.1.2（自动纳管）

## 8. 风险

- **风险 1：多平台 autocfg 模板差异大**：.5 老版本可能不支持某些命令
  - 缓解：先 .5 / .26 / .177 三平台探针，再定模板
- **风险 2：DHCP lease 监听漏报**：dnsmasq log 解析可能漏
  - 缓解：双通道（lease log + 主动扫描网段）
- **风险 3：自动纳管误纳管**：DHCP 租给非 H3C 设备会被误纳管
  - 缓解：先 SSH 验证凭据（验证失败 → 不纳管）
