# v311-ztp-landing — Tasks

> **状态**：Propose → Design → Apply 阶段（**实施清单**）
> **每 Task = 1 个 commit**（user 规则）；13 个 Task 拆解
> **前置**：proposal.md + design.md + specs/ztp-landing/spec.md 已就位

---

## T0 准备（OpenSpec 流程初始化）

- [x] 0.1 `openspec new change v311-ztp-landing` 创建 change 目录
- [x] 0.2 写 `proposal.md`（v3.1.1 设计意图 + 范围 + 决策）
- [x] 0.3 写 `design.md`（技术方案 + autocfg.cfg.j2 模板 + 部署 + 风险）
- [x] 0.4 写 `tasks.md`（本文件，13 个 Task 拆解）
- [x] 0.5 写 `specs/ztp-landing/spec.md`（capability spec）

---

## 1. T1 平台命令探针（**Apply 第 1 步，必须先跑**）

> **目的**：确认 autocfg.cfg 模板命令在 2 平台（.26 R7643P02 / .177 T7064P15）真实支持情况
> **工具**：ops-toolkit `paramiko-batch-exec.sh`（所有探针走容器，**不**裸写 SSH）
> **关键约束**：T1 通过后才进 T2（jinja2 模板 + entrypoint）；T1 失败 → 决策 C 重新评估
>
> **user 2026-07-18 接手修正**：
> - `.177` 是完整 ZTP 主验证设备，先在 `.177` 验证一切无误
> - `.26` 是 EVE-NG 借用的 V9850/RSTN 测试设备，`.177` 后必须做适配性验证
> - `.5` 不跑完整 ZTP；已发生的 `.5` 探针只作为 S6850/LSTN 命令佐证
> - OOB 口名按现网探测，不把 `MGE`/`MEth` 写成跨设备绝对规则；必须确保命中的是真实 physical OOB 口

### 1.1 .5 R6555（S6850 平台）探针（**已做，仅作佐证；不跑完整 ZTP**）

> **user 2026-07-18 接手修正**：.5 不跑完整 ZTP 验证（生产/现网参考设备，谨慎）。已经完成的 OOB/static 命令探针保留为 LSTN 佐证。

### 1.2 .26 R7643P02（V9850 平台）探针

> **范围**：5 条核心探针（**用户 2026-07-18 指示"26 可以探索一下"**）

- [x] 1.2.1 `check-host` / `check-netconf` 验证 .26 SSH 22 + NETCONF 830 可达
- [x] 1.2.2 探针 #1：探测 V9850 physical OOB 口（实测 `MGE0/0/0` 存在，`MEth0/0/0` 不存在）
- [x] 1.2.3 探针 #2：`interface MGE0/0/0 + ip address 192.168.100.50 255.255.255.0 + quit + display this`（V9850 物理 OOB 静态 IP）
- [x] 1.2.4 探针 #3：`netconf ssh server enable`（V9850 SSH 协议支持，no-op 安全）
- [x] 1.2.5 探针 #4：`netconf soap http enable`（V9850 SOAP 协议支持，备选）
- [x] 1.2.6 探针 #5：`authorization-attribute user-role level-15`（V9850 数字等级支持）
- [x] 1.2.7 探针 #6：`authorization-attribute user-role network-admin`（V9850 字符串角色支持，模板统一用此项）
- [x] 1.2.8 探针 #7：`save force`（V9850 save force 支持）
- [x] 1.2.9 记录结果到 `notes.md §T1.2.26`（每条命令成功 / Unrecognized / 错误）
- [x] 1.2.10 结果已纳入 T7/notes 提交（未单独拆 T1.2 commit）

**T1.2 验收**：
- .26 SSH 22 + NETCONF 830 通
- 探针 #1/#2 确认 V9850 OOB 口存在 + 静态 IP 命令支持
- 探针 #3/#4 确认 V9850 NETCONF 用 SSH 还是 SOAP
- 探针 #5/#6 确认 V9850 user-role 命名
- 探针 #7 确认 V9850 save force 支持

### 1.3 .177 T7064P15（S6850 平台）复用 v3.1.0 结果

> **范围**：v3.1.0 已验，**不**重跑（除非 v3.1.1 新增的物理 OOB 口 static IP 命令 v3.1.0 没测过）

- [x] 1.3.1 v3.1.0 已验命令（sysname / local-user / ssh / netconf / save force）—— **复用结果**
- [x] 1.3.2 v3.1.0 失败命令（Vlan-interface1 + ip address）—— **已知失败，v3.1.1 改走物理 OOB 口**
- [x] 1.3.3 v3.1.1 新增的 `interface M-GigabitEthernet0/0/0 + ip address X X` 已探针成功；但探针误用 `undo ip address + save force` 造成 `.177` 失联，详见 `notes.md §高危操作红线`
- [x] 1.3.4 记录 v3.1.0 已知结果到 `notes.md §T1.3.177` / `notes.md §.177 探针`

**T1.3 验收**：
- v3.1.0 已知结果已文档化
- 如需重探则完成探针

**T1 总验收**：
- 3 平台探针全部完成
- 物理 OOB 口 static IP 命令在 S6850（.5 / .177）+ V9850（.26）支持情况明确
- V9850 NETCONF 协议（SSH vs SOAP）+ user-role 命名（network-admin vs level-15）明确
- 任一探针失败 → 决策 C 重新评估

---

## 2. T2 autocfg.cfg.j2 模板创建（基于 T1 探针结果）

> **目的**：写 1 份 jinja2 通用模板 + 2 平台条件分支
> **路径**：`docker/ztp-stack/tftp/autocfg.cfg.j2`

- [x] 2.1 创建 `docker/ztp-stack/tftp/autocfg.cfg.j2`（jinja2 模板，**完整**结构见 [design.md Decision 4](design.md)）
- [x] 2.2 模板变量：`platform`（lstn/rstn）/ `mgmt_ip`（默认 `.101`）/ `sysname`（默认随 IP 派生：`ztp-switch-101`）/ `admin_user`（默认 `python`）/ `admin_pass`（默认项目主账密）/ `ztp_date`
- [x] 2.3 LSTN 分支：`interface M-GigabitEthernet0/0/0 + ip address {{ mgmt_ip }} 255.255.255.0`
- [x] 2.4 RSTN 分支：按 T1 现网探测结果使用 `interface MGE0/0/0 + ip address {{ mgmt_ip }} 255.255.255.0`
- [x] 2.5 LSTN 分支 NETCONF：`netconf ssh server enable`
- [x] 2.6 RSTN 分支 NETCONF：T1 探针确认 `netconf ssh server enable` 可用，模板统一使用 SSH NETCONF
- [x] 2.7 LSTN 分支 user-role：`authorization-attribute user-role network-admin`
- [x] 2.8 RSTN 分支 user-role：T1 探针确认 `network-admin` / `level-15` 均可用，模板统一用 `network-admin`
- [x] 2.9 通用段：sysname / local-user / password simple / VTY / save force / password-control 平台分支
- [x] 2.10 验证 jinja2 语法：T7 容器层 CI 已覆盖 LSTN/RSTN 渲染
- [x] 2.11 **commit**: `feat(ztp): T2 autocfg.cfg.j2 jinja2 通用模板（2 平台条件分支 + 物理 OOB 口 static IP）`

**T2 验收**：
- `autocfg.cfg.j2` 文件存在
- jinja2 语法正确（无解析错误）
- 2 平台分支内容符合 T1 探针结果

---

## 3. T3 entrypoint.sh jinja2 渲染 + ZTP_PLATFORM 路由

> **目的**：`entrypoint.sh` 读取 `ZTP_PLATFORM` env var → jinja2 渲染 `autocfg.cfg.j2` → 输出 `/var/tftp/autocfg.cfg`
> **路径**：`docker/ztp-stack/entrypoint.sh`

- [x] 3.1 改 `entrypoint.sh`：在 dnsmasq 启动前加 jinja2 渲染步骤
- [x] 3.2 渲染命令：用 `python3 -c` + jinja2 Template 渲染 env var
- [x] 3.3 输出：`/var/tftp/autocfg.cfg`
- [x] 3.4 启动日志打印：渲染后 autocfg.cfg 前 10 行 + `ZTP_PLATFORM` 值
- [x] 3.5 **commit**: `feat(ztp): T3 entrypoint.sh jinja2 渲染 + ZTP_PLATFORM 路由`

**T3 验收**：
- 容器启动后 `/var/tftp/autocfg.cfg` 内容正确（按 `ZTP_PLATFORM` 路由）
- 启动日志清晰（平台 + 模板前 10 行）

---

## 4. T4 Dockerfile jinja2-cli 依赖

> **目的**：Dockerfile apk add jinja2 + jinja2-cli（用于容器内 jinja2 渲染）

- [x] 4.1 改 `docker/ztp-stack/Dockerfile`：`apk add --no-cache python3 py3-jinja2`
- [x] 4.2 确认 `python3` 可用
- [x] 4.3 验证镜像构建成功：T7 容器层 CI 已通过
- [x] 4.4 验证 jinja2 可用：T7 容器层 CI 已覆盖
- [x] 4.5 **commit**: `feat(ztp): T4 Dockerfile jinja2 依赖（python3 + py3-jinja2）`

**T4 验收**：
- 镜像构建成功
- 容器内 `python3 -c "import jinja2"` 不报错

---

## 5. T5 dnsmasq.conf.template 改造（DHCP 池 .151-.190 + 删除 dhcp-host / dhcp-leasefile）

> **目的**：调整 DHCP 池范围到 .151-.190，**删**除 v3.1.0 的 mac-binding / dhcp-leasefile 持久化（用户 2026-07-18 明确反对）

- [x] 5.1 改 `docker/ztp-stack/dnsmasq.conf.template`：`dhcp-range=${ZTP_DHCP_RANGE_START},${ZTP_DHCP_RANGE_END},${ZTP_DHCP_LEASE}`（默认值 .151-.190）
- [x] 5.2 **删** `dhcp-host=MAC,IP,infinite` 配置（v3.1.1 不做 mac-binding）
- [x] 5.3 **删** `dhcp-leasefile=/var/lib/misc/dnsmasq.leases` 配置（v3.1.1 不做 lease 持久化）
- [x] 5.4 验证：`dnsmasq --test -C /etc/dnsmasq.conf` 配置语法通过（T7 已验证）
- [x] 5.5 **commit**: `feat(ztp): T5 dnsmasq.conf DHCP 池 .151-.190 迁移 + 删除 mac-binding/leasefile（v3.1.1 设计简化）`

**T5 验收**：
- dnsmasq 配置语法通过
- DHCP 池范围 .151-.190 生效
- **不**含 `dhcp-host` / `dhcp-leasefile`

---

## 6. T6 docker-compose.dev.yml + .env.example 调整

> **目的**：调整 ztp-server volume 挂载（删除 `/var/lib/misc`，不需要 lease 持久化）+ `.env` 注入 `ZTP_PLATFORM`

- [x] 6.1 改 `docker-compose.dev.yml`：
  - **删** ztp-server volume `ztp-lease:/var/lib/misc`（v3.1.1 不做 lease 持久化）
  - **不加**额外 TFTP volume：模板已 COPY 到镜像内，容器启动时渲染 `/var/tftp/autocfg.cfg`
- [x] 6.2 改 `.env.example`：
  - **加** `ZTP_PLATFORM=lstn`
  - **加** `ZTP_DHCP_RANGE_START=192.168.100.151`
  - **加** `ZTP_DHCP_RANGE_END=192.168.100.190`
  - **保留** `ZTP_MGMT_IP=192.168.100.101` 作为 v3.1.1 PoC static IP 变量（默认值仍 .101，v3.1.2 再公式化）
  - **删** `ZTP_MGMT_MASK`（autocfg.cfg 模板硬编码 255.255.255.0）
  - **删** `ZTP_MGMT_GATEWAY`（autocfg.cfg 不写 ip gateway）
- [x] 6.3 改 `.env`（实际环境）：已同步 v3.1.1 变量；当前保留 `.26` RSTN 验证态（`ZTP_PLATFORM=rstn` / `ZTP_MGMT_IP=192.168.100.102`），`.env` 为 gitignored 本地运行态，不提交
- [x] 6.4 **commit**: `feat(ztp): T6 .env.example 调整（ZTP_PLATFORM + offset 50 跨池 + 账密统一 + 禁二账号）`

**T6 验收**：
- `docker compose -f docker-compose.dev.yml --profile ops up -d ztp-server` 启动成功
- 容器内 `/var/tftp` 含 `autocfg.cfg.j2` + 渲染后的 `autocfg.cfg`
- 容器内 `/var/lib/misc` **不**存在（已删除）

---

## 7. T7 容器层 CI 验证（秒级）

> **目的**：T2-T6 完成后跑容器层 QA 验证（不需真机）

- [x] 7.1 容器构建：`docker compose -f docker-compose.dev.yml --profile ops build ztp-server`
- [x] 7.2 dnsmasq 配置语法：`docker exec ztp-server dnsmasq --test -C /etc/dnsmasq.conf`
- [x] 7.3 端口监听：`ss -ulnA inet | grep -E '(:67|:69)'`（宿主机）
- [x] 7.4 jinja2 渲染：手动跑 entrypoint 验证 LSTN 分支内容
- [x] 7.5 jinja2 渲染：手动跑 entrypoint 验证 RSTN 分支内容
- [x] 7.6 模板路由：切换 `ZTP_PLATFORM=rstn` 重新启动容器，验证 autocfg.cfg 含现网 RSTN OOB 口 `MGE0/0/0`
- [x] 7.7 DHCP 池范围：dnsmasq log/配置输出 `192.168.100.151 -- 192.168.100.190`
- [x] 7.8 **不**含 dhcp-host：grep `dhcp-host` dnsmasq.conf 实际配置为空（注释除外）
- [x] 7.9 **commit**: `test(ztp): T7 容器层 CI 验证（build + dnsmasq test + jinja2 render + 平台路由）`

**T7 验收**：
- 容器构建成功
- dnsmasq 配置语法通过
- 端口 67/69 监听
- LSTN + RSTN 2 平台 jinja2 渲染正确

---

## 8. T8 ~~qa-backend 回归（必跑）~~ → **N/A（v3.1.1 不适用）**

> **user 2026-07-18 拍板**：T8 qa-backend 回归**不适用 v3.1.1**
>
> **原因**：
> - `qa-backend` 容器 = backend 代码 pytest 回归（覆盖 FastAPI 业务代码）
> - v3.1.1 = 新增 `ztp-server` 基建小工具（dnsmasq + jinja2 + entrypoint.sh），**不动 backend 代码**
> - 跑 qa-backend 复检 = 0 收益（不会因 ztp-server 改动而出现回归）
> - 每次发版全量跑 qa-backend 是合理的（v3.x backend 主线迭代），但**新基建小工具不应绑 qa-backend 全量回归**
>
> **正确的工具分层**：
> - backend 代码变更 → `qa-backend` 全量 pytest
> - 基建工具变更 → **对应的工具层 CI**（T7 容器层 CI 验证 = ztp-server 的正确验证）
> - 真机端到端 → 走 ops-toolkit 探针（T1 + T9-T10）
>
> **未来扩展**：
> - v3.1.2 / v3.1.3 把 ztp-server 集成进 controller → 那时 controller 改 backend 代码，qa-backend 回归才适用
> - 现阶段 ztp-server 独立运行，qa-backend 跳过

---

## 9. T9 真机 ZTP 链路验证（.177 主验证设备，必须先跑）

> **目的**：.177 完整 ZTP 链路验证（空配置启动 → DHCP .151 → autocfg 应用 → static .101 → save → 重启 → SSH/NETCONF）
> **前置**：T1-T8 全过 + 真机备份 startup.cfg（走 ops-toolkit）

- [x] 9.1 备份 .177 startup.cfg：`backup_177_startup_v311_20260718.cfg` + `backup_177_current_20260718_211812.cfg`
- [x] 9.2 启动 ztp-server 容器（`ZTP_PLATFORM=lstn` + `ZTP_HCL_T7064P15=true`）
- [x] 9.3 验证 ztp-server DHCP 池 .151-.190 + TFTP server .254 + autocfg.cfg 渲染内容（physical OOB 口 M-GigabitEthernet0/0/0 + ip address 192.168.100.101）
- [x] 9.4 reset .177 saved-configuration：`reset saved-configuration`（autocfg 机制触发）
- [x] 9.5 reboot .177：通过 `reboot-wait.sh --reset-saved --wait-ip 192.168.100.101 --timeout 300`
- [x] 9.6 SSH 22 验证 `.101` 通（`check_host_101_after_ztp_20260718.log`）
- [x] 9.7 NETCONF 830 验证 `.101` 通（`check_netconf_101_after_ztp_20260718.log`）
- [x] 9.8 验证 `.101` 配置含 autocfg.cfg 内容（`config_101_after_ztp_20260718.log`）
- [x] 9.9 验证 .177 物理 OOB 口 IP 切到 **.101**（dnsmasq 日志显示 DHCP 临时 `.190` → TFTP 拉配置 → static `.101`）
- [x] 9.10 reboot `.101` 再次重启 → 设备 IP **仍**是 .101（`reboot_wait_101_persistence_retry_20260718.log`）
- [x] 9.11 12h 后（或模拟）验证 DHCP lease 过期后 .177 IP 仍是 .101：本轮以 DHCP release + static 写入 saved-configuration + 二次 reboot 持久化作为放行证据；12h 长周期观察不作为 v3.1.1 release blocker
- [x] 9.12 restore_original_state：按 user 对 .177 可测试性的判断，暂保留 `.101` 验证态；恢复材料 `restore-177.cfg` 已保存
- [x] 9.13 **commit**: `40257b7 test(ztp): T9 .177 ZTP链路验证与RSTN模板纠偏`

**T9 验收**：
- .177 完整 ZTP 链路通过（空配置 → DHCP .151 → static .101 → 重启持久）
- .177 DHCP lease 12h 过期后 IP 仍是 .101
- 设备状态恢复到测试前（restore backup）

---

## 10. T10 .26 R7643P02 真机 ZTP 适配性验证（V9850/RSTN 平台，必须在 .177 后跑）

> **目的**：.26 R7643P02 跑完整 ZTP 链路（验证 V9850 物理 OOB 口命令 + jinja2 模板 RSTN 分支）
> **前置**：T1.2 .26 探针全过 + T9 .177 已闭环
>
> **user 2026-07-18 接手修正**：**.5 R6555 不跑完整 ZTP 验证**；`.26` 是 EVE-NG 借用的 V9850/RSTN 测试设备，必须用于适配性验证。

- [x] 10.1 备份 .26 startup.cfg（开启 SCP 后通过 `capture-config.sh` 拉取：`startup_26_scp_20260718.cfg`）
- [x] 10.2 切换 `ZTP_PLATFORM=rstn` + 重启 ztp-server 容器（中途因 RSTN 模板风险由 user 中断）
- [x] 10.3 验证 ztp-server 渲染的 autocfg.cfg 含现网探测到的 V9850 physical OOB 口（修正为完整 `M-GigabitEthernet0/0/0`）
- [x] 10.4 reset saved-configuration + reboot .26（`reboot_wait_26_to_102_retry_20260718.log`）
- [x] 10.5 SSH 22 + NETCONF 830 验证通（恢复后 `check-host .26` / `check-netconf .26` 通过）
- [x] 10.6 120s 后验证配置含 autocfg.cfg 内容（`config_102_after_ztp_20260718.log`）
- [x] 10.7 reboot 再次重启 → 设备 IP 仍是 static .102（`reboot_wait_102_persistence_20260718.log`）
- [x] 10.8 restore_original_state 恢复 .26（user 手工恢复，Codex 验证 .26 SSH/NETCONF 正常）
- [x] 10.9 **commit**: `4472e35 test(ztp): T10 .26 RSTN完整ZTP链路验证`

**T10 验收**：
- .26 完整 ZTP 链路通过
- jinja2 平台条件分支工作正常（RSTN → MGE0/0/0）
- 设备状态恢复

---

## 11. T11 .env 残留清理（v3.1.0 决策 B 残留）

> **目的**：清理 .env 残留的 v3.1.0 旧变量（`ZTP_MGMT_IP=.10` / `ZTP_MGMT_MASK` / `ZTP_MGMT_GATEWAY`）

- [x] 11.1 .env 现状：`.10` 残留已不存在；当前 `.env` 是 `.26` RSTN 验证态
- [x] 11.2 保留 `.env` 的 `ZTP_MGMT_IP` 作为 v3.1.1 静态地址输入变量（`.101/.102` 已完成真机验证），不再使用 v3.1.0 的 `.10`
- [x] 11.3 `.env` 不含 `ZTP_MGMT_MASK=255.255.255.0`
- [x] 11.4 `.env` 不含 `ZTP_MGMT_GATEWAY=192.168.100.1`
- [x] 11.5 `.env` 含 `ZTP_PLATFORM`；当前为 `.26` 验证保留 `rstn`，生产默认见 `.env.example` 的 `lstn`
- [x] 11.6 **commit**: 本地 `.env` 为 gitignored 运行态；T11 事实记录纳入 T12 文档提交

**T11 验收**：
- `.env` 不含 v3.1.0 `.10` / MASK / GATEWAY 残留
- `.env` 含 `ZTP_PLATFORM`，默认值以 `.env.example` 为准

---

## 12. T12 文档同步（3 处 A 类 + 1 处 B 类）

> **目的**：同步 3 处 A 类长期维护文档 + 1 处 B 类临时文档

- [x] 12.1 改 `docs/ztp-stack.md`：
  - 新增"DHCP 临时池与 static 管理池"章节
  - 新增"autocfg.cfg 多平台适配"章节（LSTN / RSTN 2 平台分支说明）
  - 新增".177/.26 真机验证结果 + SOP"章节
  - **删/纠偏**"DHCP lease 持久化"与"mac-binding 永久租约"旧口径（v3.1.1 不做）
- [x] 12.2 改 `VERSION-ROADMAP.md`：
  - §1 全景表 v3.1.1 行从 "⏳ 待启动" 改为 "✅ 2026-07-18 (tag: v3.1.1)"
  - §3 详细版本史 加 v3.1.1 章节（commit 列表 + 决策记录）
- [x] 12.3 改 `README.md`：
  - 顶部版本表 v3.1.1 行状态更新
  - "当前架构"章节 v3.1.1 增量能力说明（DHCP 临时池 + static OOB 管理地址 + 2 平台分支）
- [x] 12.4 改 `.env.example`：T6 已做，T12 二次校验并纠偏 static IP 变量说明
- [x] 12.5 写 `RELEASE-NOTES-v3.1.1.md`：
  - commit 序列
  - 测试统计（T1 探针 + 真机 2 平台 + 工具层 CI）
  - 真机验证示例（.177 + .26 + .5 探针边界）
- [x] 12.6 **commit**: `docs(ztp): T12 v3.1.1 文档同步`

**T12 验收**：
- 3 处 A 类文档同步
- RELEASE-NOTES-v3.1.1.md 新建
- 文档与代码一致

---

## 13. T13 Archive 闭环

> **目的**：change archive 闭环 + 通知 user review

- [ ] 13.1 跑 `openspec status --change v311-ztp-landing --json` 确认所有 task 完成
- [ ] 13.2 跑 `openspec instructions archive --change v311-ztp-landing` 获取 archive 指令
- [ ] 13.3 `git mv openspec/changes/v311-ztp-landing/ → openspec/changes/archive/2026-07-XX-v311-ztp-landing/`
- [ ] 13.4 **删** `notes.md`（v3.1.0 调研笔记 B 类规则，archive 时不归档）
- [ ] 13.5 `git add -A && git commit -m "chore(ztp): v3.1.1 archive"`
- [ ] 13.6 通知 user review，等待反馈后 push + tag
- [ ] 13.7 **commit**: `chore(ztp): T13 v3.1.1 archive 闭环`

**T13 验收**：
- openspec/changes/v311-ztp-landing/ 移到 archive/
- notes.md 已删
- git status 干净
- 等 user 确认 push + tag v3.1.1

---

## 任务统计

| 阶段 | Task 范围 | 数量 | 关键输出 |
|------|---------|------|---------|
| Apply 阶段 | T1 - T11 | 11 | 探针 + 模板 + 容器 + 真机验证 + .env 清理 |
| Archive 阶段 | T12 - T13 | 2 | 文档同步 + change archive |
| **总计** | T1 - T13 | **13** | v3.1.1 ZTP 落地 + 发版 |

---

## 依赖关系

```
T0 (Propose) ─→ T1 (探针) ─→ T2 (jinja2 模板) ─→ T3 (entrypoint)
                                          ↓
                                    T4 (Dockerfile) ─→ T5 (dnsmasq) ─→ T6 (compose + .env)
                                                                                  ↓
                                                              T7 (容器 CI) ─→ T8 (qa-backend 回归)
                                                                                          ↓
                                                              T9 (.177 真机) ─→ T10 (.5/.26 真机)
                                                                                          ↓
                                                              T11 (.env 清理) ─→ T12 (文档) ─→ T13 (archive)
```

**关键依赖**：
- T1 必须先跑（确认命令支持）→ 决定 T2 模板内容
- T2-T6 串行（jinja2 模板 → entrypoint → Dockerfile → dnsmasq → compose）
- T7-T8 可并行（容器 CI + qa-backend 回归）
- T9-T10 串行（`.177` 主验证闭环后，再做 `.26` RSTN 适配性验证；`.5` 不跑完整 ZTP）
- T11 独立（.env 清理）
- T12 依赖 T1-T11 全部完成
- T13 依赖 T12 完成后才能 archive

---

## 每 Task 验收 checklist（user 规则）

按 user 开发规则 V1.0：
- [ ] **可正常运行、编译启动无报错**
- [ ] **不破坏已有功能**（qa-backend baseline 245+ passed）
- [ ] **新功能附带自测验证**（T1-T10 都是真机/T1 探针验证）
- [ ] **符合项目格式与规范**（commit 消息遵循 `<type>: 描述`）
- [ ] **提交信息遵循 `<type>: 描述` 格式，说明改动原因与对应 Spec**
- [ ] **提交前自查格式、逻辑、回归问题**
- [ ] **任务粒度控制在"一次可提交、可自测、可运行"**（每个 Task = 1 commit）
- [ ] **卡壳超过 3 次尝试，立即停手复盘、对齐 Spec**
