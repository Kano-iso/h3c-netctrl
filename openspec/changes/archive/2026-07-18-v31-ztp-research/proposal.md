# v31-ztp-research

> **版本定位**：v3.1 候选 change — **ZTP（Zero Touch Provisioning）轻量调研**
> **范围**：**仅调研 + 决策**。**不写任何业务代码**。如不可行，archive 后 v3.1 计划回退。
> **不依赖**：v3.0 sdn-vpc-* 系列（v3.0 与 v3.1 业务正交——v3.1 是"上线自动化"，v3.0 是"已上线后的 SDN 业务"）

---

## Why

v3.0 闭环后，平台已具备"已纳管设备的 SDN 业务能力"。但**设备首次上线**仍是手动流程：

1. 现场运维拿到一台新 H3C V7 设备（.5/.26/.177 系列的 S6850 / V9850）
2. console 线接笔记本 → 进 system-view → 配带外 IP / SSH 22 / NETCONF 830 / 用户名密码 / 路由打通
3. 业务网/带外网调通后，ctrl 容器才能 `POST /api/devices` + SSH/NETCONF 测试纳管
4. 纳管后才进入 v3.0 SDN 业务流（VPC/端口绑定）

**痛点**：
- **扩容慢**：每加 1 台新设备 = 现场手动初始配置 10-20 分钟
- **出错风险**：手动 CLI 易漏配（如 `local-user password complexity` / `ssh server permit ping` / `acl number 2000`）
- **不可重复**：每台设备都要重打一遍相同命令，无版本控制、无审计
- **个人项目体感**：用户原话"我手动打起来就行了，但太麻烦"

**v3.1 愿景**（用户原话 2026-07-17 02:13）：
> "ZTP 不需要做业务配置（路由 / VPC / 路由协议等），**只做'上线'**——SSH 22 + 带外 IP + 830 端口这些基础设施配置，避免我去做一个初始跨配置的能力。"
> "**把机器随便一接进来，然后通过 ztp 一启动，就叭叭叭就起来了，就可以开始纳管。**"

## What Changes

### 主线 1：H3C V7 ZTP 机制调研

调研 3 个测试设备是否支持 ZTP，并验证 ZTP 完成"基础配置自动下发"的能力。

| 设备 | 平台 | 软件 | ZTP 调研重点 |
|---|---|---|---|
| .5  S6850 | LSTN | R6555 | `display ztp status` / `ztp enable` / 配置文件传输 |
| .26 V9850 | RSTN | R7643P02 | 同上（验证 RSTN 平台 ZTP 能力是否与 LSTN 一致）|
| .177 S6850 | LSTN | T7064P15 | 同上（验证同平台不同软件版本 ZTP 能力）|

**关键命令探针**（T2 任务）：
- `display ztp status`（看当前 ZTP 状态）
- `ztp enable`（开 ZTP）
- `display ztp history`（看 ZTP 历史）
- `ztp start`（手动触发 ZTP）

### 主线 2：Controller 侧集成方案设计

调研 controller 端需要哪些组件才能支持 ZTP：

| 组件 | 候选方案 | 调研重点 |
|---|---|---|
| DHCP server | dnsmasq / kea / isc-dhcp | option 66 (TFTP server) / option 67 (bootfile-name) |
| 文件传输 server | TFTP / HTTP / FTP | H3C V7 支持哪些协议（不同平台支持度可能不同）|
| startup.cfg 生成 | Jinja2 模板 + 按 model 渲染 | 模板变量（hostname / 带外 IP / 用户名密码 / SSH/NETCONF 开关）|
| 设备纳管 | ZTP 完成后 ctrl 自动 `POST /api/devices` 录入 | 需 device 主动回调 / ctrl 主动扫描 |

### 主线 3：可行性决策

3 个决策选项（设计决策点在 design.md §3）：

| 选项 | 描述 | 工作量 | 价值 |
|---|---|---|---|
| **A. 全 PoC** | 完整实现 DHCP + 文件 server + 模板 + .177 真机验证 | 多 session / 多 commit | 真正解决上线问题 |
| **B. 半 PoC** | 仅实现 startup.cfg 模板 + 文件 server，DHCP 用现有路由器 | 中等 | 80% 价值，20% 工作量 |
| **C. 不投入** | ZTP 在 H3C V7 不可行 / 投入产出比太低 | 0 | 维持手动上线 |

**T5 任务**：根据 T1-T4 调研结果，输出 1 份决策报告到 `design.md §3`，由用户最终拍板。

## 不在本 change 范围（v3.1 后续 change 处理）

- ❌ 业务配置（VPC / 端口绑定 / 路由协议）→ v3.0 sdn-vpc-* change 已覆盖
- ❌ 前端 ZTP 管理界面 → v3.2 或更后
- ❌ DHCP server 高可用 → 视 A/B 方案决定
- ❌ startup.cfg 模板版本管理 → 视 A/B 方案决定
- ❌ 设备纳管自动发现（ZTP 完成后 controller 自动录入 CMDB）→ 视 A/B 方案决定

## 影响范围

| 类型 | 文件 |
|---|---|
| 新增 | `openspec/changes/v31-ztp-research/design.md`（H3C V7 ZTP 机制 + 集成方案 + 决策）|
| 新增 | `openspec/changes/v31-ztp-research/tasks.md`（5 个调研 task）|
| 新增 | `openspec/changes/v31-ztp-research/specs/sdn-ztp.md`（新 spec delta）|
| 修改 | `VERSION-ROADMAP.md`（v3.1 行状态更新）|
| 修改 | `README.md`（v3.1 行状态更新）|
| 修改 | `PRD-V3.0.md` 或新建 `PRD-V3.1.md`（视决策结果）|
| **零代码** | `backend/` / `frontend/` **本 change 不动一行业务代码** |

## 验收标准

- [ ] T1: 读完 H3C 官方 ZTP 文档（V7 系列），输出 1 份机制总结
- [ ] T2: 在 .5 / .26 / .177 上 probe `display ztp status` / `ztp enable` / `display ztp history`，记录实际行为
- [ ] T3: 在 .5 上做 1 次最小 ZTP 验证（DHCP + TFTP + startup.cfg → 设备自动 reboot + 基础配置生效）—— **真机可选**，失败立即停手
- [ ] T4: 写完 design.md（H3C V7 ZTP 机制 + 3 个集成方案 + 复杂度评估 + 工作量估算）
- [ ] T5: 决策报告（A / B / C）+ 用户最终拍板
- [ ] **不写业务代码**（除 startup.cfg 模板 / Jinja2 demo 之外）
- [ ] 设备最终恢复初始态（任何 probe / ZTP 测试都不能留脏数据）

## 决策回退路径

按 user 原话"**如果不能实现就直接回退掉这个 3.1 版本的这个需求调研**"：
- T2 探针失败（ZTP 命令全部 Unrecognized）→ T5 决策 C（不投入）→ archive change + VERSION-ROADMAP 加 v3.1 行"⏸️ ZTP 不可行，回退"
- T3 验证失败（H3C V7 ZTP 实际不工作）→ 同上
- 用户主动选择 C → 同上

## 不在 OpenSpec 流程外

按 `.trae/rules/qa规范.md` 红线：所有 ZTP 探针**必须**走 ops-toolkit 容器（`paramiko-batch-exec.sh`），不裸写 SSH / paramiko。
