# sdn-ztp (新增 spec delta)

> **delta 类型**：新增 spec
> **change-id**：v31-ztp-research
> **生效条件**：T5 决策为 A 或 B 时，本 spec 落地；T5 决策 C 时本 spec 标"⏸️ 不实施"。

---

## ⚠️ T5 决策 C — 本 spec 标 ⏸️ 不实施（2026-07-17）

**决策依据**：
- T1 文档调研：H3C VCF Fabric 文档支持 S6805/S6825/S6850/V9850/S9820 + R6607+，理论可行
- T2 真机探针：3 设备（.5 R6555 / .26 R7643P02 / .177 T7064P15）ZTP 命令**全部 Unrecognized**
- 按 tasks.md T2 卡壳处理规则 → T5 决策 C（不投入）
- 本 spec **不实施**，仅作记录留存
- 设备升级到 R6607+ 或新设备支持 ZTP 时，可重启评估（详见 `design.md §3.5`）

详细决策报告见 `design.md §3.4`。
探针记录见 `notes.md §2`（archive 后删除）。

---

## Purpose

定义 H3C V7 设备 ZTP（Zero Touch Provisioning）自动上线能力，让新设备插电即获得基础配置（SSH 22 + 带外 IP + NETCONF 830 + 凭据），无须现场手动 console 初始配置。

**业务边界**（user 明确 2026-07-17 02:13）：
- ✅ **仅做基础配置**上线（SSH 22 + 带外 IP + NETCONF 830 + 凭据 + 基础路由/ACL）
- ❌ **不做业务配置**（VPC / 端口绑定 / 路由协议 / 业务 VLAN）
- ❌ **不做前端管理界面**（v3.1 仅 backend PoC）

## Requirements

### Requirement: H3C V7 ZTP 命令支持

**H3C V7 S6850 / V9850 设备必须支持以下 ZTP 命令**：
- `display ztp status`（看 ZTP 状态）
- `display ztp history`（看 ZTP 历史）
- `ztp enable`（开启 ZTP）
- `ztp start`（手动触发 ZTP）

#### Scenario: 验证 .5 (S6850 LSTN) ZTP 命令支持

- WHEN 在 .5 设备上执行 `display ztp status`
- THEN 命令成功执行，返回 ZTP 状态（**expected**："ZTP is disabled." 或 "ZTP is enabled."）

#### Scenario: 验证 .26 (V9850 RSTN) ZTP 命令支持

- WHEN 在 .26 设备上执行 `display ztp status`
- THEN 命令成功执行，返回 ZTP 状态

#### Scenario: 验证 .177 (S6850 LSTN 不同软件版本) ZTP 命令支持

- WHEN 在 .177 设备上执行 `display ztp status`
- THEN 命令成功执行，返回 ZTP 状态

### Requirement: Controller 端文件传输服务

**Controller 必须提供 startup.cfg 文件传输服务**（TFTP / HTTP / FTP 之一，由 T1 调研决定）。

#### Scenario: startup.cfg 通过 TFTP / HTTP 下发

- WHEN 设备 ZTP 启动，发送 DHCP DISCOVER
- AND DHCP server 回应 option 66/67（含文件 server IP + bootfile name）
- THEN 设备从文件 server 下载 startup.cfg
- AND 设备应用 startup.cfg 内容
- AND 设备自动 reboot + 启动到完整配置

### Requirement: startup.cfg 模板

**Controller 必须提供 startup.cfg 渲染模板**，按设备型号 + 平台生成不同配置。

#### Scenario: 模板变量注入

- WHEN 用户在 controller 上配置 1 台新设备的参数（hostname / 带外 IP / 用户名密码）
- THEN controller 渲染 startup.cfg 并放入文件 server
- AND 设备 ZTP 时拉取此 startup.cfg

### Requirement: ZTP 完成后设备可达

**ZTP 完成后，设备必须满足**：
- SSH 22 端口开放
- NETCONF 830 端口开放
- 带外 IP 可达
- 用户名密码可用

#### Scenario: ZTP 完成后 ctrl 容器纳管

- WHEN 设备 ZTP 完成并 reboot
- THEN 设备的 SSH 22 / NETCONF 830 端口可被 ctrl 容器访问
- AND 用户可调用 `POST /api/devices` 录入此设备
- AND 设备进入 v3.0 SDN 业务流（VPC/端口绑定）

## 业务下发通道

不涉及（H3C V7 ZTP 走 DHCP + 文件传输，与 v3.0 的 LSTN→SSH 22 / RSTN→NETCONF schema XML 通道正交）。

## 约束

按 `.trae/rules/project-convention.md`：
- 调研笔记 → `openspec/changes/<id>/notes.md` → archive 时**删除**（不归档）
- 任何探针 → ops-toolkit 容器
- 凭据 → `.env` 注入（startup.cfg 模板走 env vars）
- 设备最终恢复初始态

## 与 v3.0 关系

- v3.0 = 已纳管设备的 SDN 业务能力（VPC/端口绑定）
- v3.1 = 设备首次上线能力（ZTP）
- 两者**正交**，v3.1 完成后 v3.0 流程不变

## 不在本 spec 范围

- 业务配置（VPC/路由/VLAN）→ v3.0
- 前端 ZTP 管理界面 → v3.2+
- DHCP server 高可用 → 视 PoC 范围
- 设备纳管自动发现 → 视 PoC 范围
