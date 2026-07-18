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
> **user 2026-07-18 拍板简化**：
> - **T1.1 .5 R6555 探针：跳过**（.5 不跑 ZTP 验证，与 .177 同 S6850 平台，命令支持假设一致）
> - T1.2 .26 R7643P02：完整 7 条探针
> - T1.3 .177 T7064P15：复用 v3.1.0 结果 + 补做 M-GigabitEthernet0/0/0 + ip address 探针（v3.1.1 新增的物理 OOB 方案）

### 1.1 ~~.5 R6555（S6850 平台）探针~~（**跳过**）

> **user 2026-07-18 拍板**：.5 不跑 ZTP 验证（生产设备，谨慎）。T1.1 整段跳过，假设 S6850 平台（.5 R6555）命令与 .177 T7064P15 一致。

### 1.2 .26 R7643P02（V9850 平台）探针

> **范围**：5 条核心探针（**用户 2026-07-18 指示"26 可以探索一下"**）

- [ ] 1.2.1 `check-host` / `check-netconf` 验证 .26 SSH 22 + NETCONF 830 可达
- [ ] 1.2.2 探针 #1：`display interface MEth0/0/0`（确认 V9850 物理 OOB 口存在）
- [ ] 1.2.3 探针 #2：`interface MEth0/0/0 + ip address 192.168.100.50 255.255.255.0 + quit + display this + undo ip address`（V9850 物理 OOB 静态 IP）
- [ ] 1.2.4 探针 #3：`netconf ssh server enable` + `display netconf server status`（V9850 SSH 协议支持？）
- [ ] 1.2.5 探针 #4：`netconf soap http enable` + `display netconf server status`（V9850 SOAP 协议支持？）
- [ ] 1.2.6 探针 #5：`authorization-attribute user-role level-15`（V9850 数字等级？）
- [ ] 1.2.7 探针 #6：`authorization-attribute user-role network-admin`（V9850 字符串角色？）
- [ ] 1.2.8 探针 #7：`save force` + `display saved-configuration | include save`（V9850 save force 支持）
- [ ] 1.2.9 记录结果到 `notes.md §T1.2.26`（每条命令成功 / Unrecognized / 错误）
- [ ] 1.2.10 **commit**: `probe(ztp): T1.2 .26 R7643P02 V9850 平台 7 条命令探针（OOB + NETCONF + user-role + save）`

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
- [ ] 1.3.3 **如需重探**（v3.1.1 新增的 `interface M-GigabitEthernet0/0/0 + ip address X X`）：跑 T1.1.2 同款探针
- [ ] 1.3.4 记录 v3.1.0 已知结果到 `notes.md §T1.3.177`（仅记录，不重跑）

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

- [ ] 2.1 创建 `docker/ztp-stack/tftp/autocfg.cfg.j2`（jinja2 模板，**完整**结构见 [design.md Decision 4](design.md)）
- [ ] 2.2 模板变量：`platform`（lstn/rstn）/ `mgmt_ip`（默认 `.101`）/ `sysname`（默认 `ztp-device`）/ `admin_user`（默认 `admin`）/ `admin_pass`（默认 `admin`）/ `ztp_date`
- [ ] 2.3 LSTN 分支：`interface M-GigabitEthernet0/0/0 + ip address {{ mgmt_ip }} 255.255.255.0`
- [ ] 2.4 RSTN 分支：`interface MEth0/0/0 + ip address {{ mgmt_ip }} 255.255.255.0`（**仅当** T1.2 探针 #2 验证通过）
- [ ] 2.5 LSTN 分支 NETCONF：`netconf ssh server enable`
- [ ] 2.6 RSTN 分支 NETCONF：按 T1.2 探针 #3/#4 结果写（SSH 或 SOAP）
- [ ] 2.7 LSTN 分支 user-role：`authorization-attribute user-role network-admin`
- [ ] 2.8 RSTN 分支 user-role：按 T1.2 探针 #5/#6 结果写（network-admin 或 level-15）
- [ ] 2.9 通用段：sysname / local-user / password simple / VTY / save force / `password-control login-password-change disable`
- [ ] 2.10 验证 jinja2 语法：`jinja2 --version` + `python3 -c "from jinja2 import Template; ..."`
- [ ] 2.11 **commit**: `feat(ztp): T2 autocfg.cfg.j2 jinja2 通用模板（2 平台条件分支 + 物理 OOB 口 static IP）`

**T2 验收**：
- `autocfg.cfg.j2` 文件存在
- jinja2 语法正确（无解析错误）
- 2 平台分支内容符合 T1 探针结果

---

## 3. T3 entrypoint.sh jinja2 渲染 + ZTP_PLATFORM 路由

> **目的**：`entrypoint.sh` 读取 `ZTP_PLATFORM` env var → jinja2 渲染 `autocfg.cfg.j2` → 输出 `/var/tftp/autocfg.cfg`
> **路径**：`docker/ztp-stack/entrypoint.sh`

- [ ] 3.1 改 `entrypoint.sh`：在 dnsmasq 启动前加 jinja2 渲染步骤
- [ ] 3.2 渲染命令：`python3 -c "from jinja2 import Template; print(Template(open('/var/tftp/autocfg.cfg.j2').read()).render(platform=os.environ.get('ZTP_PLATFORM', 'lstn'), mgmt_ip=os.environ.get('ZTP_MGMT_IP', '192.168.100.101'), sysname=os.environ.get('ZTP_SYSNAME', 'ztp-device'), admin_user=os.environ.get('ZTP_ADMIN_USER', 'admin'), admin_pass=os.environ.get('ZTP_ADMIN_PASS', 'admin'), ztp_date=datetime.now().strftime('%Y-%m-%d')))"`
- [ ] 3.3 输出：`/var/tftp/autocfg.cfg`
- [ ] 3.4 启动日志打印：渲染后 autocfg.cfg 前 10 行 + `ZTP_PLATFORM` 值
- [ ] 3.5 **commit**: `feat(ztp): T3 entrypoint.sh jinja2 渲染 + ZTP_PLATFORM 路由`

**T3 验收**：
- 容器启动后 `/var/tftp/autocfg.cfg` 内容正确（按 `ZTP_PLATFORM` 路由）
- 启动日志清晰（平台 + 模板前 10 行）

---

## 4. T4 Dockerfile jinja2-cli 依赖

> **目的**：Dockerfile apk add jinja2 + jinja2-cli（用于容器内 jinja2 渲染）

- [ ] 4.1 改 `docker/ztp-stack/Dockerfile`：`apk add --no-cache python3 py3-jinja2 py3-jinja2-cli`（jinja2-cli 提供命令行工具，备选；entrypoint.sh 用 `python3 -c` 即可）
- [ ] 4.2 确认 `python3` 已存在（alpine:3.20 默认有）
- [ ] 4.3 验证镜像构建成功：`docker compose -f docker-compose.dev.yml --profile ops build ztp-server`
- [ ] 4.4 验证 jinja2 可用：`docker exec ztp-server python3 -c "import jinja2; print(jinja2.__version__)"`
- [ ] 4.5 **commit**: `feat(ztp): T4 Dockerfile jinja2 依赖（python3 + py3-jinja2）`

**T4 验收**：
- 镜像构建成功
- 容器内 `python3 -c "import jinja2"` 不报错

---

## 5. T5 dnsmasq.conf.template 改造（DHCP 池 .151-.190 + 删除 dhcp-host / dhcp-leasefile）

> **目的**：调整 DHCP 池范围到 .151-.190，**删**除 v3.1.0 的 mac-binding / dhcp-leasefile 持久化（用户 2026-07-18 明确反对）

- [ ] 5.1 改 `docker/ztp-stack/dnsmasq.conf.template`：`dhcp-range=${ZTP_DHCP_RANGE_START},${ZTP_DHCP_RANGE_END},${ZTP_DHCP_LEASE}`（默认值 .151-.190）
- [ ] 5.2 **删** `dhcp-host=MAC,IP,infinite` 配置（v3.1.1 不做 mac-binding）
- [ ] 5.3 **删** `dhcp-leasefile=/var/lib/misc/dnsmasq.leases` 配置（v3.1.1 不做 lease 持久化）
- [ ] 5.4 验证：`dnsmasq --test -C /etc/dnsmasq.conf` 配置语法通过
- [ ] 5.5 **commit**: `feat(ztp): T5 dnsmasq.conf DHCP 池 .151-.190 迁移 + 删除 mac-binding/leasefile（v3.1.1 设计简化）`

**T5 验收**：
- dnsmasq 配置语法通过
- DHCP 池范围 .151-.190 生效
- **不**含 `dhcp-host` / `dhcp-leasefile`

---

## 6. T6 docker-compose.dev.yml + .env.example 调整

> **目的**：调整 ztp-server volume 挂载（删除 `/var/lib/misc`，不需要 lease 持久化）+ `.env` 注入 `ZTP_PLATFORM`

- [ ] 6.1 改 `docker-compose.dev.yml`：
  - **删** ztp-server volume `ztp-lease:/var/lib/misc`（v3.1.1 不做 lease 持久化）
  - **加** ztp-server volume `ztp-tftp:/var/tftp`（autocfg.cfg.j2 模板源，**只读**）
- [ ] 6.2 改 `.env.example`：
  - **加** `ZTP_PLATFORM=lstn`
  - **加** `ZTP_DHCP_RANGE_START=192.168.100.151`
  - **加** `ZTP_DHCP_RANGE_END=192.168.100.190`
  - **删** `ZTP_MGMT_IP`（autocfg.cfg 模板硬编码 .101）
  - **删** `ZTP_MGMT_MASK`（autocfg.cfg 模板硬编码 255.255.255.0）
  - **删** `ZTP_MGMT_GATEWAY`（autocfg.cfg 不写 ip gateway）
- [ ] 6.3 改 `.env`（实际环境）：同步 .env.example 变更
- [ ] 6.4 **commit**: `feat(ztp): T6 docker-compose + .env 调整（删除 lease volume + ZTP_PLATFORM 注入）`

**T6 验收**：
- `docker compose -f docker-compose.dev.yml --profile ops up -d ztp-server` 启动成功
- 容器内 `/var/tftp` 含 `autocfg.cfg.j2` + 渲染后的 `autocfg.cfg`
- 容器内 `/var/lib/misc` **不**存在（已删除）

---

## 7. T7 容器层 CI 验证（秒级）

> **目的**：T2-T6 完成后跑容器层 QA 验证（不需真机）

- [ ] 7.1 容器构建：`docker compose -f docker-compose.dev.yml --profile ops build ztp-server`
- [ ] 7.2 dnsmasq 配置语法：`docker exec ztp-server dnsmasq --test -C /etc/dnsmasq.conf`
- [ ] 7.3 端口监听：`ss -ulnA inet | grep -E '(:67|:69)'`（宿主机）
- [ ] 7.4 jinja2 渲染：手动跑 entrypoint 验证 LSTN 分支内容
- [ ] 7.5 jinja2 渲染：手动跑 entrypoint 验证 RSTN 分支内容
- [ ] 7.6 模板路由：切换 `ZTP_PLATFORM=rstn` 重新启动容器，验证 autocfg.cfg 含 `MEth0/0/0`
- [ ] 7.7 DHCP 池范围：dnsmasq log 输出 `IP range 192.168.100.151 -- 192.168.100.190`
- [ ] 7.8 **不**含 dhcp-host：grep `dhcp-host` dnsmasq.conf 应为空
- [ ] 7.9 **commit**: `test(ztp): T7 容器层 CI 验证（build + dnsmasq test + jinja2 render + 平台路由）`

**T7 验收**：
- 容器构建成功
- dnsmasq 配置语法通过
- 端口 67/69 监听
- LSTN + RSTN 2 平台 jinja2 渲染正确

---

## 8. T8 qa-backend 回归（必跑）

> **目的**：验证 v3.1.1 零业务代码改动不破坏 backend 245+ passed baseline

- [ ] 8.1 `docker compose -f docker-compose.dev.yml --profile qa up qa-backend`
- [ ] 8.2 pytest 全量通过（与 v3.1.0 baseline 对比，**不**允许回归）
- [ ] 8.3 **commit**: `test(ztp): T8 qa-backend 回归通过（245+ passed）`

**T8 验收**：
- qa-backend 全量 pytest PASS

---

## 9. T9 真机 ZTP 链路验证（.177 默认测试设备）

> **目的**：.177 完整 ZTP 链路验证（空配置启动 → DHCP .151 → autocfg 应用 → static .101 → save → 重启 → SSH/NETCONF）
> **前置**：T1-T8 全过 + 真机备份 startup.cfg（走 ops-toolkit）

- [ ] 9.1 备份 .177 startup.cfg：`paramiko-batch-exec.sh --device .177 --command "more startup.cfg" > /tmp/backup-177-ztp.cfg`
- [ ] 9.2 启动 ztp-server 容器（`ZTP_PLATFORM=lstn`）
- [ ] 9.3 验证 ztp-server DHCP 池 .151-.190 + TFTP server .254 + autocfg.cfg 渲染内容（physical OOB 口 M-GigabitEthernet0/0/0 + ip address 192.168.100.101）
- [ ] 9.4 reset .177 saved-configuration：`reset saved-configuration`（autocfg 机制触发）
- [ ] 9.5 reboot .177（自动配置 attempt 1 可能失败，attempt 2 成功）
- [ ] 9.6 60s 内 SSH 22 验证 .177 通（走 `paramiko-batch-exec.sh --device .177 --command "display version"`）
- [ ] 9.7 60s 内 NETCONF 830 验证 .177 通（走 `check-netconf.sh .177`）
- [ ] 9.8 120s 后验证 .177 配置含 autocfg.cfg 内容（`display current-configuration` 应含 `interface M-GigabitEthernet0/0/0` + `ip address 192.168.100.101 255.255.255.0` + `sysname` + `ssh server enable` + `netconf ssh server enable`）
- [ ] 9.9 验证 .177 物理 OOB 口 IP 切到 **.101**（**不**是 .151 DHCP 临时 IP）
- [ ] 9.10 reboot .177 再次重启 → 设备 IP **仍**是 .101（static 持久）
- [ ] 9.11 12h 后（或模拟）验证 DHCP lease 过期后 .177 IP 仍是 .101（offset 50 跨池验证）
- [ ] 9.12 **最后必须 restore_original_state**：restore `/tmp/backup-177-ztp.cfg` 到 .177（避免污染设备）
- [ ] 9.13 **commit**: `test(ztp): T9 .177 完整 ZTP 链路验证（offset 50 跨池 + 物理 OOB 口 static IP）`

**T9 验收**：
- .177 完整 ZTP 链路通过（空配置 → DHCP .151 → static .101 → 重启持久）
- .177 DHCP lease 12h 过期后 IP 仍是 .101
- 设备状态恢复到测试前（restore backup）

---

## 10. T10 .26 R7643P02 真机 ZTP 验证（V9850 平台）

> **目的**：.26 R7643P02 跑完整 ZTP 链路（验证 V9850 物理 OOB 口命令 + jinja2 模板 RSTN 分支）
> **前置**：T1.2 .26 探针全过 + T9 .177 已闭环
>
> **user 2026-07-18 拍板**：**.5 R6555 不跑 ZTP 验证**（生产设备，谨慎；同 S6850 平台已被 .177 覆盖）

- [ ] 10.1 备份 .26 startup.cfg（`paramiko-batch-exec.sh`）
- [ ] 10.2 切换 `ZTP_PLATFORM=rstn` + 重启 ztp-server 容器
- [ ] 10.3 验证 ztp-server 渲染的 autocfg.cfg 含 `MGE0/0/0`（V9850 物理 OOB 口）
- [ ] 10.4 reset saved-configuration + reboot .26
- [ ] 10.5 60s 内 SSH 22 + NETCONF 830 验证通
- [ ] 10.6 120s 后验证配置含 autocfg.cfg 内容（含 `interface MGE0/0/0` + `ip address 192.168.100.101 255.255.255.0` + `sysname` + `ssh server enable` + `netconf ssh server enable`）
- [ ] 10.7 reboot 再次重启 → 设备 IP 仍是 static .101
- [ ] 10.8 restore_original_state 恢复 .26
- [ ] 10.9 **commit**: `test(ztp): T10 .26 V9850 真机 ZTP 链路验证（jinja2 RSTN 分支 + MGE0/0/0 物理 OOB 口）`

**T10 验收**：
- .26 完整 ZTP 链路通过
- jinja2 平台条件分支工作正常（RSTN → MGE0/0/0）
- 设备状态恢复

---

## 11. T11 .env 残留清理（v3.1.0 决策 B 残留）

> **目的**：清理 .env 残留的 v3.1.0 旧变量（`ZTP_MGMT_IP=.10` / `ZTP_MGMT_MASK` / `ZTP_MGMT_GATEWAY`）

- [ ] 11.1 .env 现状：`.10` 是 v3.1.0 阶段"任意选的值"，v3.1.0 决策 B 已声明移除但 .env 残留
- [ ] 11.2 **删** `.env` 的 `ZTP_MGMT_IP=192.168.100.10`（autocfg.cfg 模板硬编码 .101）
- [ ] 11.3 **删** `.env` 的 `ZTP_MGMT_MASK=255.255.255.0`（autocfg.cfg 模板硬编码 255.255.255.0）
- [ ] 11.4 **删** `.env` 的 `ZTP_MGMT_GATEWAY=192.168.100.1`（autocfg.cfg 不写 ip gateway）
- [ ] 11.5 **加** `.env` 的 `ZTP_PLATFORM=lstn`（T6 已做，T11 二次校验）
- [ ] 11.6 **commit**: `chore(ztp): T11 .env 清理（删除 v3.1.0 决策 B 残留 ZTP_MGMT_* + 确认 ZTP_PLATFORM=lstn）`

**T11 验收**：
- `.env` 不含 `ZTP_MGMT_*` 残留
- `.env` 含 `ZTP_PLATFORM=lstn`

---

## 12. T12 文档同步（3 处 A 类 + 1 处 B 类）

> **目的**：同步 3 处 A 类长期维护文档 + 1 处 B 类临时文档

- [ ] 12.1 改 `docs/ztp-stack.md`：
  - 新增"1:1 静态 IP 池子（offset 50 跨池映射）"章节（含原理图）
  - 新增"autocfg.cfg 多平台适配"章节（LSTN / RSTN 2 平台分支说明）
  - 新增"3 平台真机验证 SOP"章节
  - **删**"DHCP lease 持久化"章节（v3.1.1 不做）
  - **删**"mac-binding 永久租约"章节（v3.1.1 不做）
- [ ] 12.2 改 `VERSION-ROADMAP.md`：
  - §1 全景表 v3.1.1 行从 "⏳ 待启动" 改为 "✅ 2026-07-XX (tag: v3.1.1)"
  - §3 详细版本史 加 v3.1.1 章节（commit 列表 + 决策记录）
- [ ] 12.3 改 `README.md`：
  - 顶部版本表 v3.1.1 行状态更新
  - "当前架构"章节 v3.1.1 增量能力说明（offset 50 + 物理 OOB 口 + 2 平台分支）
- [ ] 12.4 改 `.env.example`：T6 已做，T12 二次校验
- [ ] 12.5 写 `RELEASE-NOTES-v3.1.1.md`：
  - commit 序列
  - 测试统计（T1 探针 7 条 + 真机 2 平台 + qa 回归 baseline）
  - 真机验证示例（.177 + .5/.26）
- [ ] 12.6 **commit**: `docs(ztp): T12 3 处 A 类 + 1 处 B 类文档同步（ztp-stack.md / VERSION-ROADMAP / README / RELEASE-NOTES）`

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
- T9-T10 串行（默认测试 .177 闭环后，再做 .5/.26）
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
