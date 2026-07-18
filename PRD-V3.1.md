# H3C NetCtrl V3.1 PRD：ZTP（Zero Touch Provisioning）整体功能

| 版本 | 日期 | 作者 | 说明 |
|---|---|---|---|
| V3.1 Draft | 2026-07-18 | 用户拍板 + Codex 共创 | V3.1 = ZTP 整体功能大版本蓝图，v3.1.0 调研、v3.1.1 落地、v3.1.2 联动纳管 |
| V3.1 Revise | 2026-07-18 | 用户拍板 + Codex 共创 | v3.1.2/v3.1.3 合并；移除 DHCP lease 监听路线，改为基于 ZTP static 管理地址的后端纳管 + 前端可见联动 |

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

V3.1 = 3 个子版本逐步落地：

| 子版本 | 主题 | 关键产出 | 状态 |
|---|---|---|---|
| **v3.1.0** | ZTP 调研 | 决策 B 精简 ZTP + 独立 ztp-server 容器 + autocfg.cfg 模板（T7064P15 验证通过）| ✅ **已发版**（[RELEASE-NOTES-v3.1.0.md](RELEASE-NOTES-v3.1.0.md)）|
| **v3.1.1** | ZTP 落地 | ztp-server jinja2 多平台模板 + `ZTP_MGMT_IP` static OOB 写入 + `.177/.26` 真机完整验证 | ✅ **已发版**（[RELEASE-NOTES-v3.1.1.md](RELEASE-NOTES-v3.1.1.md)）|
| **v3.1.2** | ZTP 联动纳管 | 设备完成 ZTP 后，后端按 static 管理地址纳管入库、采集资产，前端通过现有设备/CMDB/Dashboard 接口可见 | ⏳ 待启动 |

## 3. v3.1.1 ZTP 落地（已完成）

### 3.1 目标

解决 v3.1.0 留下的 2 个未解决问题：
1. **IP 不持久**：设备首启 DHCP 只作为临时地址，最终由 autocfg.cfg 写入 physical OOB static IP。
2. **多平台模板未适配**：从单一 autocfg 模板升级为 jinja2 通用模板 + 平台条件分支。

### 3.2 范围

- **DHCP 临时池 + static 管理地址**：
  - DHCP 池 `192.168.100.151-.190` 只用于首启拉取 `autocfg.cfg`
  - static 管理地址由 `ZTP_MGMT_IP` 渲染进 autocfg.cfg，并写入 physical OOB 口
  - `.177` 已验证最终 static `.101`，`.26` 已验证最终 static `.102`
  - v3.1.1 不从 DHCP lease 自动反推 static IP
- **autocfg.cfg 多平台适配**：
  - LSTN/S6850：`M-GigabitEthernet0/0/0`
  - RSTN/V9850：真实配置全名 `M-GigabitEthernet0/0/0`，display brief 简写 `MGE0/0/0`
  - 采用 1 份 `autocfg.cfg.j2` 通用模板，按 `ZTP_PLATFORM=lstn|rstn` 分支渲染
- **关闭首次登录改密**：autocfg.cfg 模板加 `password-control login-password-change disable`（v3.1.0 已加）

### 3.3 设计决策

- 静态 IP 持久化走 autocfg.cfg 写 physical OOB 口 + `save force`
- 不做 mac-binding / `dhcp-host=MAC,IP,infinite`
- 不做 `dhcp-leasefile` 持久化
- 不走 Vlan-interface1
- 不在 v3.1.1 做 controller 自动纳管

### 3.4 验收标准

- [x] `.177` LSTN 完整 ZTP 链路通过：空配置启动 → DHCP → TFTP → static `.101` → SSH/NETCONF → 二次 reboot 持久
- [x] `.26` RSTN 完整 ZTP 链路通过：空配置启动 → DHCP → TFTP → static `.102` → SSH/NETCONF → 二次 reboot 持久
- [x] `.5` 不跑完整 ZTP，仅保留 OOB/static 命令探针佐证
- [x] `reboot-wait.sh` 与 `capture-config.sh` 完成工具加固

## 4. v3.1.2 ZTP 联动纳管

### 4.1 目标

设备 ZTP 完成后，平台能把设备纳入现有设备库和资产库，白屏用户无需手动 `POST /api/devices`。本版本把原 v3.1.2“自动纳管”和 v3.1.3“资产可见”合并：后端一旦有数据，前端用现有接口即可展示。

### 4.2 范围

- **纳管触发**：
  - v3.1.2 不做 DHCP lease 监听；当前 dnsmasq/autocfg 链路无法稳定承载“从租约自动发现最终 static IP”的职责
  - 以后端 API/操作入口接收候选管理地址（例如刚写入的 `ZTP_MGMT_IP`：`.101/.102/...`）作为纳管起点
- **后端联动**：
  - 按管理地址执行 SSH 22 / NETCONF 830 连通性验证
  - 使用项目统一凭据纳管设备，创建或更新 `devices` 记录
  - 触发资产采集，写入或刷新 CMDB 资产信息（model / serial / software / mgmt IP / vendor）
  - 纳管动作需要幂等：同 IP/同设备重复触发时更新已有记录，不制造重复资产
- **前端可见**：
  - Devices / CMDB / Dashboard 复用现有后端数据与刷新逻辑即可可见
  - 本轮不单独做完整 ZTP 产品页面；后续会起独立页面管理上线设备、下线设备和 ZTP 生命周期
- **不做业务配置**：
  - 不推 VPC / 端口绑定 / 路由协议 / 业务 VLAN
  - 不把 ZTP 联动和 v3.0/v3.2 SDN 业务配置混在一个闭环里

### 4.3 验收标准

- [ ] 给定一个已完成 ZTP 的 static 管理地址，后端可一键纳管成功
- [ ] `devices` 表创建/更新正确，重复执行不产生重复设备
- [ ] 资产采集完成后，CMDB 可看到 model / serial / software / mgmt IP / vendor
- [ ] Devices / CMDB / Dashboard 通过现有接口能看到新增设备或统计变化
- [ ] 纳管失败有明确错误原因（SSH 不通 / 凭据失败 / NETCONF 不通 / 资产采集失败）

## 5. 不做（明确边界）

- ❌ **不做 ZTP 业务配置**：VPC / 端口绑定 / 路由协议 / 业务 VLAN 由 v3.0 骨架 + v3.2 验证负责
- ❌ **不做 etcd 协调**：v3.5 远期
- ❌ **不做 DHCP lease 监听自动发现**：当前路线不可稳定落地，不作为 v3.1.2 前置
- ❌ **不做专门 ZTP 产品页面**：后续单独起页面，管理上线设备、下线设备和 ZTP 生命周期

## 6. 依赖关系

- v3.1.1 不依赖 v3.1.0 之外的能力
- v3.1.2 依赖 v3.1.1（静态 IP 持久化）
- 原 v3.1.3 已合并进 v3.1.2，不再单列

## 7. 风险

- **风险 1：多平台 autocfg 模板差异大**：.5 老版本可能不支持某些命令
  - 现状：v3.1.1 已用 `.177/.26` 真机验证收敛；后续新增平台仍需探针
- **风险 2：管理地址来源不可靠**：如果人工/控制器传入错误 IP，纳管会失败
  - 缓解：后端纳管接口必须先做 SSH/NETCONF 探测，并给出明确失败原因
- **风险 3：重复纳管**：同一设备重复触发可能产生重复资产
  - 缓解：按 IP、hostname、serial 等信息做幂等更新
