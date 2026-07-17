# H3C NetCtrl V3.1.2 PRD：自动纳管

| 版本 | 日期 | 作者 | 说明 |
|---|---|---|---|
| V3.1.2 Draft | 2026-07-18 | 用户拍板 + Codex 共创 | V3.1.2 = 自动纳管：controller 监听 DHCP lease → 主动 SSH 纳管 → 推业务 IP → 同步资产 |

---

## 1. 背景与目标

### 1.1 背景

v3.1.1 已实现 1:1 静态 IP 池子 + autocfg.cfg 多平台适配，设备能自动配置 + 拿到持久 IP。

但**设备上线 ≠ 平台可见**：

- 当前仍需白屏用户**手动** `POST /api/devices` 创建设备记录
- 设备表 / 资产表不会自动同步
- 不符合"白屏用户零操作"的目标

### 1.2 目标

**设备 ZTP 完成后，controller 主动发现并纳管**：

1. 监听 ztp-server DHCP lease 变化（新设备上线）
2. controller 主动 SSH 连接新设备（复用 v3.0 通道 + v3.1.1 凭据）
3. 校验凭据 → 自动 `POST /api/devices`（设备表 + 资产表）
4. 推业务 IP（VLAN interface IP / Loopback IP）→ 设备可见业务能力
5. **白屏用户零操作看到新设备**

### 1.3 关键约束

- ✅ **白屏用户零操作**：设备上线 = 平台可见，无需人工 `POST /api/devices`
- ✅ **凭据复用 v3.1.1**：autocfg.cfg 已内置 SSH 凭据
- ✅ **业务 IP 推送**：VLAN interface IP / Loopback IP（**不做 VPC 业务配置**）
- ❌ **不做 ZTP 业务配置**：VPC / 端口绑定 / 路由协议 / 业务 VLAN 推 v3.2
- ❌ **不做 0day 安全审计**：仅做凭据校验，不做"是否 H3C 设备"深度识别

### 1.4 依赖

- **v3.1.1**（已规划）：1:1 静态 IP 池子 + 3 平台模板
- **v3.1.0**（已闭环）：独立 ztp-server 容器（dnsmasq 开启 lease log）
- **v3.0**（已闭环）：业务下发通道（SSH 22 / NETCONF 830）
- **v2.4.1**（已闭环）：ctrl + config + data 3 容器拆分
- **v2.4.2.1**（已闭环）：paramiko-batch-exec.sh（4 级凭据 + Fernet 密文）

---

## 2. V3.1.2 范围

### 2.1 DHCP lease 监听

#### 2.1.1 目标

**实时发现新设备**：DHCP lease log 增量解析，新设备 lease 触发纳管流程。

#### 2.1.2 实现

**复用 ztp-server 容器 dnsmasq**：

- dnsmasq 配 `dhcp-leasefile=/var/lib/misc/dnsmasq.leases`（默认行为）
- 容器挂载 volume：`/var/lib/misc/dnsmasq.leases` → host `./ops-toolkit/ztp/data/leases/`
- controller 侧 `inotify` 监听 lease 文件变化

**controller 端解析**（`config` 容器）：

- lease 文件格式：`{expiry-time} {MAC} {IP} {hostname} {client-id}`
- 新增 lease 解析为：`{MAC, IP, sysname, lease_time}`
- 入库到 `sdn_ztp_discovery` 表（中间表，未纳管前过渡）

#### 2.1.3 设计决策

| 方案 | 优势 | 劣势 | 决策 |
|---|---|---|---|
| **A：inotify 监听 lease 文件** | 实时、零轮询 | 需处理文件轮转 | ✅ **采用** |
| **B：定期轮询 lease 文件** | 简单 | 5-10s 延迟 | 备选 |
| **C：dnsmasq 配 `--log-queries` 解析 syslog** | 已有 syslog 通道 | 解析复杂 | ❌ 不采用 |

### 2.2 主动 SSH 纳管

#### 2.2.1 目标

**新设备 60s 内自动入设备表**，无需人工 `POST /api/devices`。

#### 2.2.2 流程

```
DHCP lease 变化
  ↓
解析新 lease → 提取 {MAC, IP, sysname}
  ↓
入 sdn_ztp_discovery 表（status=discovered）
  ↓
controller 调度任务（每 10s 轮询 discovered 状态）
  ↓
SSH 连接新设备（凭据：复用 .env 注入 DEVICE_USERNAME/PASSWORD）
  ├─ 成功 → 校验凭据 → 采集设备信息
  └─ 失败 → 状态重试（3 次后入死信队列）
  ↓
POST /api/devices（设备表 + 资产表）
  ├─ 成功 → 状态 active
  └─ 失败 → 状态 failed + audit log
```

#### 2.2.3 关键实现

**设备信息采集**（SSH CLI 跑命令，复用 v2.4.2.1 paramiko-batch-exec）：

```bash
display version              # vendor / model / software version
display device manufacture-info  # serial / mac
display interface brief      # interfaces
display current-configuration | include sysname  # sysname 校验
```

**去重策略**：

- `device.mgmt_ip` UNIQUE 约束
- `device.serial` UNIQUE 约束
- 重复 lease → 跳过纳管（仅更新 lease_time）

**重试策略**：

- SSH 连接失败：3 次重试（间隔 30s）
- 凭据校验失败：1 次 + audit log（不重试，避免锁账号）
- API 调用失败：3 次重试（间隔 10s）

**死信队列**：

- 3 次重试后仍失败 → 入 `sdn_ztp_dead_letter` 表
- 白屏用户可在 CMDB 看到死信设备，手动处理

### 2.3 推业务 IP

#### 2.3.1 目标

**纳管成功后推业务 IP**，让设备具备业务能力。

#### 2.3.2 范围

- **VLAN interface IP**（按设备类型分配）
  - leaf 设备：业务 VLAN 100~200
  - spine 设备：业务 VLAN 201~210
- **Loopback IP**（管理用）
  - `10.255.{device_id}.1/32`
- **IP 分配策略**：
  - controller 维护 `ip_pool` 表（VLAN → 网段 → 已分配 IP）
  - 纳管时从池中分配
  - 避免 DHCP 漂移（IP 由 controller 唯一管理）

#### 2.3.3 实现

**业务 IP 推送通道**：

- **首选**：SSH 22 + paramiko（v3.0 骨架已用）
- **fallback**：NETCONF 830（v3.0 已支持）

**配置示例**（VLAN interface IP）：

```text
interface Vlan-interface100
 ip address 10.100.1.1 255.255.255.0
#
interface LoopBack0
 ip address 10.255.{device_id}.1 255.255.255.255
#
save force
```

**不做**：

- ❌ VPC 业务配置（VSI / Vxlan / 端口绑定）
- ❌ 路由协议（OSPF / BGP / 静态路由）
- ❌ 业务 VLAN（除 VLAN interface IP）

### 2.4 资产同步

#### 2.4.1 目标

**纳管时同步资产信息**到 data 容器资产表。

#### 2.4.2 字段映射

| SSH 采集 | 资产表字段 |
|---|---|
| `display version` 的 `H3C` | `vendor` |
| `display version` 的 `S6850-58HF` | `model` |
| `display version` 的 `R6555` | `software_version` |
| `display device manufacture-info` 的 serial | `serial` |
| `display device manufacture-info` 的 mac | `mac_address` |
| `display interface brief` 的接口列表 | `interfaces_count` |
| `display current-configuration` 的 sysname | `sysname` |

#### 2.4.3 实现

- 资产表 `assets` 已有，纳管时 `INSERT INTO assets`
- `device.assets_id` 关联（外键）
- 后续 v3.1.3 资产可见性靠这张表

### 2.5 死信队列 + 告警

#### 2.5.1 死信队列

- 表 `sdn_ztp_dead_letter`：`{mac, ip, sysname, error_type, error_message, retry_count, last_retry_at}`
- 重试规则：3 次后入死信
- 死信处理：白屏用户可手动 `POST /api/devices` 或 `DELETE FROM sdn_ztp_dead_letter` 重新入队

#### 2.5.2 告警（v3.1.2 简化版）

- 死信队列 > 5 条 → 弹 toast 告警（前端 v3.1.3 完善）
- 纳管失败率 > 20%（最近 1h）→ 弹 toast 告警

---

## 3. 设计决策

### 3.1 DHCP lease 监听方案

- **决策**：inotify 监听 lease 文件（方案 A）
- **理由**：实时（< 1s 延迟）+ 零轮询开销
- **备选**：定期轮询（B 方案）作为 fallback（inotify 失败时降级）

### 3.2 凭据复用 v3.1.1

- autocfg.cfg 已内置 SSH 凭据
- controller SSH 连接时用相同凭据（`DEVICE_USERNAME` / `DEVICE_PASSWORD`）
- **好处**：无需为每台设备单独管理凭据
- **风险**：所有 ZTP 设备凭据一致（v3.1.2 接受现状，v3.1.3+ 再优化）

### 3.3 业务 IP 推送通道

- **首选**：SSH 22 + paramiko（v3.0 骨架已用，参数化模板易实现）
- **fallback**：NETCONF 830（v3.0 已支持，跨平台一致性更好）
- **决策**：v3.1.2 仅 SSH（简化），v3.2+ 评估 NETCONF 推广

### 3.4 设备去重

- `device.mgmt_ip` UNIQUE 约束（数据库层）
- `device.serial` UNIQUE 约束（数据库层）
- 重复 lease → 仅更新 lease_time（视为同一台设备 DHCP renew）

### 3.5 重试策略

- SSH 连接：3 次重试（30s 间隔）
- 凭据校验：1 次（不重试，避免锁账号）
- API 调用：3 次重试（10s 间隔）
- 3 次后入死信队列

### 3.6 不做（明确边界）

- ❌ 不做 VPC 业务配置（VPC / 端口绑定 / 路由协议 / 业务 VLAN → v3.2）
- ❌ 不做 0day 安全审计（仅凭据校验）
- ❌ 不做 AI 辅助识别（远期）
- ❌ 不做 RSTN 平台 NETCONF 推送（v3.1.2 仅 SSH，RSTN NETCONF 推 v3.1.2+ 评估）
- ❌ 不做前端大屏（v3.4）

---

## 4. 验收标准

### 4.1 DHCP lease 监听

- [ ] ztp-server 容器 dnsmasq 开启 lease file 持久化
- [ ] controller 端 `inotify` 监听 lease 文件变化
- [ ] 新 lease 解析准确率 100%（解析为 {MAC, IP, sysname, lease_time}）
- [ ] lease 文件轮转不丢失事件
- [ ] 入 `sdn_ztp_discovery` 表（status=discovered）

### 4.2 主动 SSH 纳管

- [ ] 新设备 DHCP lease 后 60s 内 `sdn_devices` 表出现记录
- [ ] 凭据校验失败 → 1 次后入死信（不重试）
- [ ] SSH 连接失败 → 3 次重试（30s 间隔）后入死信
- [ ] API 调用失败 → 3 次重试（10s 间隔）后入死信
- [ ] 重复 lease → 视为同一设备，不重复纳管
- [ ] 死信队列表 + 告警机制
- [ ] 白屏用户**零操作**看到新设备

### 4.3 业务 IP 推送

- [ ] 纳管成功后业务 IP 推送成功（VLAN interface + Loopback）
- [ ] IP 池维护（VLAN → 网段 → 已分配 IP）
- [ ] 避免 IP 重复分配
- [ ] 推送失败 → 状态回退 + audit log

### 4.4 资产同步

- [ ] 纳管时自动采集（vendor / model / software / serial / mac / sysname）
- [ ] `assets` 表自动 INSERT
- [ ] `device.assets_id` 外键关联

### 4.5 测试覆盖

- [ ] DHCP lease 监听 unit ≥ 5 case
- [ ] SSH 纳管 service unit ≥ 20 case
- [ ] 业务 IP 推送 unit ≥ 10 case
- [ ] 集成测试（lease → 纳管 → 推送 → 资产同步）≥ 10 case
- [ ] 真机测试（3 平台）≥ 9 case
- [ ] 死信队列测试 ≥ 5 case

### 4.6 文档同步

- [ ] `docs/ops-toolkit.md` §ztp-纳管 章节更新
- [ ] `VERSION-ROADMAP.md` v3.1.2 行状态更新（⏳ → ✅）
- [ ] `RELEASE-NOTES-v3.1.2.md` 新建
- [ ] 新增 API 文档（`/api/sdn/discovery/*`）

---

## 5. 依赖关系

### 5.1 上游依赖

- **v3.1.1**（已规划）：1:1 静态 IP 池子 + 3 平台模板（**强依赖**）
- **v3.1.0**（已闭环）：独立 ztp-server 容器（dnsmasq lease log）
- **v3.0**（已闭环）：业务下发通道（SSH 22 / NETCONF 830）
- **v2.4.1**（已闭环）：ctrl + config + data 3 容器拆分
- **v2.4.2.1**（已闭环）：paramiko-batch-exec.sh

### 5.2 下游被依赖

- **v3.1.3**：资产可见（依赖 v3.1.2 自动纳管入设备表 + 资产表）

### 5.3 数据库迁移

- `alembic/versions/011_sdn_ztp_discovery.py`：sdn_ztp_discovery 表
- `alembic/versions/012_sdn_ztp_dead_letter.py`：sdn_ztp_dead_letter 表
- `alembic/versions/013_sdn_ip_pool.py`：sdn_ip_pool 表（IP 分配）
- 3 个迁移幂等（IF NOT EXISTS）

### 5.4 API 端点

- `GET /api/sdn/discovery` — 列出 discovered 设备
- `POST /api/sdn/discovery/{id}/adopt` — 手动纳管（死信恢复）
- `GET /api/sdn/dead-letter` — 列出死信队列
- `POST /api/sdn/dead-letter/{id}/retry` — 重试
- `DELETE /api/sdn/dead-letter/{id}` — 删除死信

---

## 6. 风险

| 风险 | 影响 | 缓解 |
|---|---|---|
| **风险 1：inotify 监听 lease 文件不可靠** | 漏掉新设备 | 备选定期轮询（B 方案），5-10s 延迟 |
| **风险 2：SSH 连接风暴** | ZTP 批量上线时 controller 被打爆 | 限制并发 SSH（max 3）+ 队列 |
| **风险 3：业务 IP 推送失败** | 设备无业务能力 | 状态回退 + audit log + 死信队列 |
| **风险 4：重复 lease 误判** | 同一台设备被多次纳管 | `device.mgmt_ip` UNIQUE 约束 + `device.serial` UNIQUE 约束 |
| **风险 5：凭据复用风险** | 所有 ZTP 设备凭据一致 | v3.1.2 接受现状，v3.1.3+ 评估优化（per-device 凭据 / 证书） |
| **风险 6：DHCP 租给非 H3C 设备** | 误纳管 | SSH 连接 + 校验凭据（v3.1.2 简化），v3.1.3+ 加 `display version` H3C 关键字校验 |

---

## 7. 走法（5 阶段）

| 阶段 | 主题 | 输出 | 依赖 |
|---|---|---|---|
| **T1** | DHCP lease 监听 | controller inotify + sdn_ztp_discovery 表 | v3.1.1 ztp-server |
| **T2** | 主动 SSH 纳管 | SSH 连接 + 凭据校验 + POST /api/devices | T1 |
| **T3** | 业务 IP 推送 | sdn_ip_pool 表 + VLAN/Loopback IP 推送 | T2 |
| **T4** | 死信队列 + 告警 | sdn_ztp_dead_letter 表 + toast 告警 | T1+T2+T3 |
| **T5** | 真机验证 + 文档同步 | 3 平台 × 3 场景 = 9 case + RELEASE-NOTES | T1-T4 |

---

## 8. 不做（明确边界）

- ❌ **不做 VPC 业务配置**：VPC / 端口绑定 / 路由协议 / 业务 VLAN 推 v3.2
- ❌ **不做 0day 安全审计**：仅凭据校验
- ❌ **不做 RSTN 平台 NETCONF 推送**：v3.1.2 仅 SSH
- ❌ **不做前端大屏**：v3.4
- ❌ **不做 AI 辅助识别**：远期
- ❌ **不做 per-device 凭据**：v3.1.2 接受所有 ZTP 设备凭据一致

---

## 9. 与 PRD-V3.1 关系

- **PRD-V3.1** = V3.1 大版本蓝图（4 子版本拆解）
- **PRD-V3.1.1** = V3.1.1 子版本详细 PRD（ZTP 落地）
- **PRD-V3.1.2** = V3.1.2 子版本详细 PRD（本文件，**自动纳管**）
- **PRD-V3.1.3** = V3.1.3 子版本详细 PRD（资产可见）
- 3 个子版本 PRD 独立 OpenSpec change 跟踪
- 共同构成 V3.1 大版本完整 PRD 体系

---

## 10. 参考文档

- [PRD-V3.1.md](PRD-V3.1.md) — V3.1 大版本蓝图
- [PRD-V3.1.1.md](PRD-V3.1.1.md) — V3.1.1 ZTP 落地
- [VERSION-ROADMAP.md §v3.1.2](VERSION-ROADMAP.md) — 版本路线图
- [docs/ztp-stack.md](docs/ztp-stack.md) — ZTP 容器栈详解
- [ops-toolkit/ztp/README.md](ops-toolkit/ztp/README.md) — ztp-server 容器使用
- [RELEASE-NOTES-v3.1.0.md](RELEASE-NOTES-v3.1.0.md) — v3.1.0 调研成果
