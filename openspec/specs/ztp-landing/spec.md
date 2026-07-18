# ztp-landing Specification

> **新能力**（v3.1.1 引入）：ZTP 落地能力 — DHCP 临时池 + static OOB 管理地址写入 + autocfg.cfg 多平台适配（jinja2 + 2 平台条件分支）
> **范围**：仅 `ztp-server` 容器（`docker/ztp-stack/`），**零业务代码改动**
> **依赖**：v3.1.0（ztp-server 容器基建 + autocfg.cfg T7064P15 模板）
> **后续**：v3.1.2（自动纳管）/ v3.1.3（资产可见）依赖本 spec

---

## 设计上下文（user 2026-07-18 拍板方向）

### 4 条核心方向

1. **静态地址池与 DHCP 临时池隔离**：DHCP 给新设备的地址只用于首次拉取 autocfg.cfg，最终管理地址由 `ZTP_MGMT_IP` 写入 physical OOB 口。v3.1.1 已验证 `.177 → .101`、`.26 → .102`；后续 v3.1.2 再把“DHCP 临时租约 → static 地址”的自动分配逻辑接入 controller。
2. **autocfg.cfg 推 static IP 写物理 OOB 口**（用户原话"我们只在第 1 步刚上线的时候获取的时候用动态壁纸而已"）：S6850 当前实测 = `M-GigabitEthernet0/0/0`；V9850 当前 `.26` 现网实测 = `MGE0/0/0`（不是旧 PRD 写的 `MEth0/0/0`）。后续不把接口名写成跨设备绝对规则，但 MUST 确保命中的是真实 physical OOB 口。**不**走 Vlan-interface1（v3.1.0 失败路径）。
3. **jinja2 通用模板 + 2 平台条件分支**：`lstn`（S6850 平台 = .5 T7064P15-prod + .177 T7064P15-hcl）/ `rstn`（V9850 平台 = .26 R7643P02）。
4. **明确不做**（user 2026-07-18 拍板反对）：
   - mac-binding / `dhcp-host=MAC,IP,infinite`
   - `dhcp-leasefile` 持久化
   - Vlan-interface1 路径
   - VRF 绑定（autocfg.cfg 阶段简化）

### T1 实测发现（2026-07-18 探针记录于 release notes 与 captures）

| 设备 | 实际型号 | 实际软件 | 物理 OOB 口 | user-role 命令 | 首次改密 |
|------|---------|---------|-----------|----------------|---------|
| .5 | S6850 | T7064P15-**prod** | `M-GigabitEthernet0/0/0` | `network-admin` ✅ | `change-password first-login enable` (no-op) |
| .26 | V9850-256H | R7643P02 | 配置文件全名 `M-GigabitEthernet0/0/0`，display brief 简写 `MGE0/0/0` | `network-admin` ✅（`level-15` 也支持）| 同 prod |
| .177 | S6850 | T7064P15-**hcl** | `M-GigabitEthernet0/0/0` | `network-admin` ✅ | **`login-password-change disable`**（HCL 独有） |

---

## ADDED Requirements

### Requirement: 静态 IP 池子与 DHCP 临时池隔离

ztp-server 容器 MUST 支持 DHCP 临时池与 static 管理池**完全分离**，避免设备最终管理地址与租约地址冲突：
- DHCP 池：`192.168.100.151-.190`（40 IP，autocfg 机制临时分配）
- Static 池：`192.168.100.101-.140`（40 IP，autocfg.cfg 内嵌物理 OOB 口静态 IP）
- v3.1.1：static 地址由 `ZTP_MGMT_IP` 指定（`.101` / `.102` 已真机验证）
- v3.1.2：controller 监听上线事件后再实现自动递增/自动分配
- gap：`.141-.150` 10 IP 闲置作安全余量

#### Scenario: .177 真机 PoC 验证

- **WHEN** .177 S6850 T7064P15-hcl reset saved-configuration + reboot（空配置启动）
- **AND** 启动后 autocfg 机制从 DHCP 临时池获取地址
- **AND** TFTP 拉取 `autocfg.cfg` 模板（含 `interface M-GigabitEthernet0/0/0 + ip address 192.168.100.101 255.255.255.0`）
- **THEN** 设备应用配置后 **物理 OOB 口 IP = .101**（**不**保留 DHCP 临时地址）
- **AND** 设备 `save force` 持久化
- **AND** 重启后设备 IP 仍是 **.101**（DHCP lease 12h 过期后仍 .101，static IP 生效）
- **AND** SSH 22 + NETCONF 830 验证通过

#### Scenario: DHCP 池与 static 池不重叠

- **WHEN** 启动 ztp-server 容器并查看 `dnsmasq.conf`
- **THEN** `dhcp-range` 配置范围**不包含** static 池 `.101-.140` 任何 IP
- **AND** static 池**不包含** DHCP 池 `.151-.190` 任何 IP
- **AND** 2 池**完全分离**（0 IP 重叠）

#### Scenario: gap 安全余量

- **WHEN** 设备 DHCP 给 `.141-.150`（理论上不会，但 dnsmasq 误配可触发）
- **THEN** autocfg.cfg 渲染仍正常（gap 10 IP 不参与映射，但不被 dnsmasq 分配）
- **AND** docs/ztp-stack.md 明确标注 `.141-.150` 是安全余量

#### Scenario: 静态地址输入变量验证

- **WHEN** `.env` 设置 `ZTP_MGMT_IP=192.168.100.101`
- **THEN** autocfg.cfg 静态 IP 写 `.101`
- **WHEN** `.env` 设置 `ZTP_MGMT_IP=192.168.100.102`
- **THEN** autocfg.cfg 静态 IP 写 `.102`
- **NOTE**：v3.1.1 阶段不从 dnsmasq lease 自动反推 static 地址；该自动化留给 v3.1.2。

### Requirement: autocfg.cfg jinja2 通用模板 + 2 平台条件分支

ztp-server 容器 MUST 使用 jinja2 通用模板 + 2 平台条件分支（`lstn` / `rstn`）渲染 `autocfg.cfg`：
- 1 份 `autocfg.cfg.j2` 通用模板
- 按 `{{ platform }}` 变量渲染（`lstn` / `rstn`）
- 平台差异用 `{% if platform == 'lstn' %}` / `{% elif platform == 'rstn' %}` 隔离
- 通用段（sysname / SSH / local-user / save force）所有平台共用
- HCL 子分支（`password-control login-password-change disable`）作为 `lstn` 内子条件（仅 .177 T7064P15-hcl 启用）

#### Scenario: jinja2 模板渲染 LSTN 分支

- **WHEN** 容器启动并设置 `ZTP_PLATFORM=lstn`（默认，.5 T7064P15-prod 用）
- **THEN** entrypoint.sh 调用 jinja2 渲染 `autocfg.cfg.j2` → `/var/tftp/autocfg.cfg`
- **AND** 渲染后 autocfg.cfg 内容含 `interface M-GigabitEthernet0/0/0 + ip address 192.168.100.101 255.255.255.0`
- **AND** 渲染后 autocfg.cfg 内容含 `authorization-attribute user-role network-admin`（S6850 验证通过）
- **AND** 渲染后 autocfg.cfg 内容含 `password-control change-password first-login enable`（no-op 安全）
- **AND** 渲染后 autocfg.cfg **不**含 `password-control login-password-change disable`（prod 不支持 Unrecognized）

#### Scenario: jinja2 模板渲染 RSTN 分支

- **WHEN** 容器启动并设置 `ZTP_PLATFORM=rstn`（.26 R7643P02 用）
- **THEN** 渲染后 autocfg.cfg 内容含现网探测到的 V9850 physical OOB 口（当前 `.26` 真机配置全名为 `M-GigabitEthernet0/0/0`，display brief 简写为 `MGE0/0/0`）+ `ip address {{ ZTP_MGMT_IP }} 255.255.255.0`
- **AND** 渲染后 autocfg.cfg 内容含 `netconf ssh server enable`（V9850 默认 disabled，显式 enable）
- **AND** 渲染后 autocfg.cfg 内容含 `authorization-attribute user-role {network-admin|level-15}`（T1 探针决定）
- **AND** 渲染后 autocfg.cfg 内容含 `password-control change-password first-login enable`（no-op 安全）

#### Scenario: HCL 子分支（LSTN + HCL_T7064P15=true）

- **WHEN** 容器启动并设置 `ZTP_PLATFORM=lstn` + `ZTP_HCL_T7064P15=true`（.177 T7064P15-hcl 专用）
- **THEN** 渲染后 autocfg.cfg 内容含 `password-control login-password-change disable`（HCL 独有，已验）
- **AND** HCL_T7064P15 未设置或为 false 时，**不**含 `login-password-change disable`

#### Scenario: 模板路由 ZTP_PLATFORM 校验

- **WHEN** 容器启动时 `ZTP_PLATFORM` 值为未知字符串（如 `xxx`）
- **THEN** entrypoint.sh 启动时 warning + fallback 到 `lstn` 模板
- **AND** 容器继续运行（不崩溃）
- **AND** 容器 log 明确打印 "ZTP_PLATFORM=xxx not in [lstn, rstn], fallback to lstn"

### Requirement: 三平台命令差异探针（T1）

v3.1.1 MUST 在 T1 阶段通过 ops-toolkit `paramiko-batch-exec.sh` 探针以下命令在 3 平台的兼容性：
- `interface <OOB> + ip address <ip> <mask>`（物理 OOB 口 static IP 配置）
- `ssh server enable`
- `netconf ssh server enable`
- `password-control change-password first-login enable`（所有平台通用）
- `password-control login-password-change disable`（HCL 独有）
- `save force`
- user-role 命令（`network-admin` / `level-15`，T1 决定 V9850 用哪个）

#### Scenario: .5 T7064P15-prod 命令探针

- **WHEN** 走 ops-toolkit `paramiko-batch-exec.sh --device .5 --command "interface M-GigabitEthernet0/0/0; ip address 192.168.100.50 255.255.255.0; quit; display this; undo ip address"`
- **THEN** 记录命令执行结果（成功 / Unrecognized / 错误）
- **AND** 写入 release notes / captures 证据
- **AND** 至少 1 条核心探针覆盖（物理 OOB 静态 IP）

#### Scenario: .26 R7643P02 命令探针

- **WHEN** 走 ops-toolkit `paramiko-batch-exec.sh --device .26 --command "..."`
- **THEN** 探针 #1：探测 V9850 物理 OOB 口（当前 `.26` 实测 `MGE0/0/0` 存在，`MEth0/0/0` 不存在）
- **AND** 探针 #2：`interface <physical-oob> + ip address 192.168.100.50 255.255.255.0`（V9850 物理 OOB 静态 IP）
- **AND** 探针 #3：`netconf ssh server enable`（V9850 NETCONF 默认 disabled）
- **AND** 探针 #4：`netconf soap http enable`（V9850 NETCONF SOAP 备选）
- **AND** 探针 #5：`authorization-attribute user-role level-15`（V9850 数字等级）
- **AND** 探针 #6：`authorization-attribute user-role network-admin`（V9850 字符串角色）
- **AND** 探针 #7：`save force`（V9850 持久化）
- **AND** 写入 release notes / captures 证据

#### Scenario: .177 T7064P15-hcl 命令探针（回归）

- **WHEN** 走 ops-toolkit `paramiko-batch-exec.sh --device .177 --command "interface M-GigabitEthernet0/0/0; ip address 192.168.100.50 255.255.255.0; quit; display this; undo ip address"`
- **THEN** v3.1.0 已验命令应仍工作（无回归）
- **AND** v3.1.1 新增的 `interface M-GigabitEthernet0/0/0 + ip address X X` 命令应**新**成功（T7064P15 v3.1.0 仅有 `ip gateway` Unrecognized）
- **AND** v3.1.0 已验 `password-control login-password-change disable` 在 T7064P15-hcl 工作（HCL 独有）

#### Scenario: T1 探针失败处理

- **WHEN** 任一平台核心命令探针失败（Unrecognized 或语法错误）
- **THEN** 文档或 release notes 记录失败原因
- **AND** 对应 jinja2 平台条件分支用备选命令或标 skip
- **AND** 不阻塞 v3.1.1 发版（已知限制，记录于 docs/ztp-stack.md）

### Requirement: 真机 ZTP 链路验证

v3.1.1 MUST 在 .177 上验证完整 ZTP 链路（autocfg 机制）：空配置启动 → DHCP 拿 .151 → TFTP 拉 autocfg.cfg → 应用 → static .101 → save → 重启 → SSH/NETCONF 通。

#### Scenario: .177 完整 ZTP 链路

- **WHEN** 备份 .177 当前 startup.cfg（走 ops-toolkit）
- **AND** 在 .177 上跑 `reset saved-configuration`
- **AND** ztp-server 容器运行（DHCP + TFTP 就绪，`ZTP_PLATFORM=lstn` + `ZTP_HCL_T7064P15=true`）
- **AND** reboot .177
- **THEN** 60s 内 .177 SSH 22 通（`paramiko-batch-exec.sh --device .177 --command "display version"`）
- **AND** 60s 内 .177 NETCONF 830 通（`check-netconf.sh .177`）
- **AND** 120s 后 .177 配置含 autocfg.cfg 内容（sysname / 物理 OOB 口 static IP .101 / SSH / NETCONF / HCL 改密）
- **AND** 重启 .177（再次 reboot）→ 设备 IP **仍**是 .101（static 持久）
- **AND** DHCP lease 12h 过期后设备 IP 仍是 .101

#### Scenario: 真机集成 restore_original_state

- **WHEN** T9 真机验证完成（无论成功/失败）
- **THEN** .177 设备最终恢复测试前状态，或经 user 明确同意后保留验证态并保存恢复材料
- **AND** 不允许只测 happy path 且不留下恢复路径

#### Scenario: reboot 类验证等待

- **WHEN** 设备 reboot 后做连通性检查
- **THEN** 必须 sleep + retry 至少 120s（不允许 1 次 timeout 失败就推断不通）

### Requirement: .26 RSTN 真机 ZTP 适配性验证

v3.1.1 MUST 在 `.177` 主验证通过后，在 `.26` RSTN/V9850 平台做真机 ZTP 适配性验证：
- `.26` 是 EVE-NG 借用的 V9850/RSTN 测试设备，代表 v3.2 EVENG/虚拟化验证方向
- `.26` 验证重点是 physical OOB 口、RSTN 平台模板、user-role、NETCONF、save 行为
- `.5` 不跑完整 ZTP；已完成的 `.5` OOB/static 命令探针只作为 S6850/LSTN 参考

#### Scenario: .26 真机 ZTP 适配性验证

- **WHEN** `.177` 完整 ZTP 主验证已通过
- **AND** `.26` V9850/RSTN 真机可达（T1 探针 SSH + NETCONF 通）
- **THEN** 切换 `ZTP_PLATFORM=rstn` 重启 ztp-server
- **AND** jinja2 渲染 RSTN autocfg.cfg，内容含当前现网探测到的 physical OOB 口（`.26` 当前为 `MGE0/0/0`）
- **AND** 验证 `.26` ZTP 链路通（autocfg 应用 + static IP 持久 + SSH/NETCONF 通）

#### Scenario: 平台不可达处理

- **WHEN** T1 探针发现 .26 平台 SSH / NETCONF 不可达
- **THEN** 文档或 release notes 记录不可达原因
- **AND** VERSION-ROADMAP 标注 v3.1.1 "部分平台待商用升级后验证"
- **AND** 不阻塞 v3.1.1 发版（已知限制）

### Requirement: 文档同步

v3.1.1 MUST 同步 3 处 A 类文档 + 1 处 B 类文档：
- `docs/ztp-stack.md` 多平台验证 SOP + DHCP 临时池/static 管理池说明
- `VERSION-ROADMAP.md` v3.1.1 行状态更新
- `README.md` v3.1.1 行状态更新
- `RELEASE-NOTES-v3.1.1.md` 新建（commit 序列 + 测试统计 + 真机示例）

#### Scenario: docs/ztp-stack.md 更新

- **WHEN** v3.1.1 archive 阶段
- **THEN** `docs/ztp-stack.md` 新增 "DHCP 临时池与 static 管理池" 章节
- **AND** 新增 "autocfg.cfg 多平台适配（LSTN/RSTN + HCL 子分支）" 章节
- **AND** 新增 "3 平台真机验证 SOP" 章节
- **AND** **删**"DHCP lease 持久化"章节（v3.1.1 不做）
- **AND** **删**"mac-binding 永久租约"章节（v3.1.1 不做）

#### Scenario: VERSION-ROADMAP.md 同步

- **WHEN** v3.1.1 archive 阶段
- **THEN** `VERSION-ROADMAP.md` v3.1.1 行从 "⏳ 待启动" 改为 "✅ YYYY-MM-DD (tag: v3.1.1)"
- **AND** `§1 全景表` 加 v3.1.1 行
- **AND** `§3 详细版本史` 加 v3.1.1 章节

#### Scenario: README.md 同步

- **WHEN** v3.1.1 archive 阶段
- **THEN** `README.md` 顶部版本表 v3.1.1 行更新
- **AND** "当前架构"章节 v3.1.1 增量能力说明（DHCP 临时池 + static OOB 管理地址 + 2 平台分支）

## MODIFIED Requirements

无（v3.1.0 未沉淀 ZTP spec，本 change 是 ZTP 第一个正式 spec）。

## REMOVED Requirements

无（v3.1.0 阶段未沉淀 ZTP spec，不存在"被删除"的需求；之前 design/proposal 中提到的"DHCP lease 持久化"/"Vlan-interface1 路径"/"mac-binding"作为 v3.1.0 调研方向已被 v3.1.1 拍板方向**明确排除**，本 spec 不沉淀这些需求）。

## 范围外（明确边界）

- ❌ **业务配置**（VPC / 端口绑定 / 路由协议）—— v3.0 + v3.2 负责
- ❌ **controller 自动纳管**（DHCP lease → POST /api/devices）—— v3.1.2
- ❌ **前端 ZTP 管理界面**（设备列表实时刷新）—— v3.1.3
- ❌ **DHCP 高可用**（单 dnsmasq 足够测试）
- ❌ **HTTP 协议替换 TFTP**（H3C V7 TFTP 明文风险）—— v3.x 远期
- ❌ **设备序列号绑定**（option 82）—— 远期
- ❌ **per-MAC 静态 IP 分配**（multi-device ZTP）—— v3.1.2 范畴
- ❌ **mac-binding / `dhcp-host=MAC,IP,infinite`**（user 2026-07-18 明确反对）
- ❌ **`dhcp-leasefile` 持久化**（user 2026-07-18 明确反对）
- ❌ **Vlan-interface1 路径**（v3.1.0 失败，已走物理 OOB 口）
- ❌ **VRF 绑定**（autocfg.cfg 阶段简化，user 2026-07-18 明确不探）
