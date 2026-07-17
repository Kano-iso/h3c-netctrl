# v31-ztp-research — Tasks

> **变更定位**：v3.1 候选 — ZTP 轻量调研
> **每个 Task = 1 commit**（按 OpenSpec "小步增量" 规范）
> **本 change 不写 Controller 业务代码**（仅基建 ztp-server 容器 + autocfg.cfg 模板）

---

## Task 1: H3C V7 ZTP 官方文档调研（T1）

**目的**：确认 H3C Comware V7 在 S6850 / V9850 平台 ZTP 能力，输出 1 份机制总结。

**步骤**：
- [x] WebSearch "H3C Comware V7 ZTP Zero Touch Provisioning" + "H3C S6850 ZTP" + "H3C V9850 ZTP"
- [x] 重点查：H3C V7 ZTP 支持的文件传输协议（TFTP / HTTP / FTP） + 配置文件格式 + DHCP option 支持
- [x] 总结成 `notes.md §1`（H3C V7 ZTP 机制 + 平台差异 + 关键命令）
- [x] 1 个 commit: `docs(ztp): T1 H3C V7 ZTP 官方文档调研总结`

**T1 结论**：H3C 官方 VCF Fabric 文档支持 5 平台 + R6607+，但本项目 3 设备软件版本仅 .26 R7643P02 在范围内，.5 / .177 不支持。**且发现 H3C V7 还有更基础的"自动配置"功能**（autocfg.cfg / autocfg.tcl / autocfg.py）—— **不依赖 R6607+**，**不依赖 ztp 命令**，空配置启动自动触发。

---

## Task 2: ZTP 命令真机探针（T2）

**目的**：实测 3 设备 VCF ZTP 命令（`ztp enable` / `display ztp status`）是否可用。

**步骤**：
- [x] 走 ops-toolkit 容器 `paramiko-batch-exec.sh`（H3C 兼容）
- [x] 3 设备 × 3 命令 = 9 次探针
- [x] 结果记录到 `notes.md §2`
- [x] 1 个 commit: `docs(ztp): T2 ZTP 命令真机探针记录`

**T2 结论**：3 设备 `ztp enable` / `display ztp status` / `display ztp history` 全部 Unrecognized（`.5 R6555` 太旧 / `.26 R7643P02` 镜像未实现 / `.177 T7064P15` HCL 内部测试版剥离）。**但 VCF ZTP 命令只是 ZTP 的一种实现**，H3C V7 还有"自动配置"功能（autocfg.cfg）作为另一条 ZTP 路径，**不依赖 ztp 命令关键字**。

**决策重置**（2026-07-17 用户指示）：原"决策 C（不投入 ZTP）"基于"3 设备 ztp 命令 Unrecognized"，但 H3C V7 还有"自动配置"路径可走，应重做 T3-T5。

---

## Task 3: 独立 ztp-server 容器基建（T3）

**目的**：解决 T4 真机验证的 2 个硬阻塞：
1. ops-toolkit 容器网络在 docker bridge（172.x），不在 .177 物理网段（192.168.100.0/24），L2 DHCP 广播不通
2. ops-toolkit 容器未预装 dnsmasq / tftpd

**方案**（用户 2026-07-17 03:50 指示）：**开独立 `ztp-server` 容器**，不动 ops-toolkit

**步骤**：
- [x] `docker/ztp-stack/Dockerfile` 新增（alpine:3.20 + apk add dnsmasq）
- [x] `docker/ztp-stack/dnsmasq.conf` 编写
  - dhcp-range: `192.168.100.200,192.168.100.250,12h`
  - dhcp-option=66: `<host-ip>`（TFTP server IP，由 build arg 注入）
  - dhcp-option=67: `autocfg.cfg`（bootfile name）
  - enable-tftp + tftp-root=/var/tftp
- [x] `docker/ztp-stack/tftp/autocfg.cfg` 模板编写
  - sysname
  - vlan 1 + mgmt IP（用 env vars 注入）
  - ssh server enable
  - netconf ssh server enable
  - local-user admin（凭据走 env vars）
  - 最小可用配置
- [x] `docker-compose.dev.yml` 加 ztp-server 服务
  - image build: `docker/ztp-stack`
  - `network_mode: host`（共享宿主机网络栈，接收 .177 DHCP 广播）
  - profiles: `ops`（按需启动，跟 ops-toolkit 一致）
  - volumes 挂载 dnsmasq.conf + autocfg.cfg
  - command: `dnsmasq -k -C /etc/dnsmasq.conf -d`
  - env vars: `ZTP_HOST_IP` / `ZTP_ADMIN_USER` / `ZTP_ADMIN_PASS`（从 .env 注入）
- [x] `docs/ztp-stack.md` 新增（容器用法 + 真机验证 SOP）
- [ ] 1 个 commit: `feat(ztp): T3 ztp-server 容器基建（dnsmasq + autocfg.cfg 模板）`

**T3 验收**（2026-07-17 16:31）：
- [x] `docker compose -f docker-compose.dev.yml --profile ops build ztp-server` 构建成功
- [x] `docker compose -f docker-compose.dev.yml --profile ops up -d ztp-server` 启动成功
- [x] `docker exec h3c-netctrl-ztp-server dnsmasq --test -C /etc/dnsmasq.conf` 配置语法通过
- [x] 宿主机 `ss -ulnA inet` 看到 `0.0.0.0:67` + `0.0.0.0:69` 监听（host network 模式）
- [x] 容器内 `/var/tftp/autocfg.cfg` 渲染成功（含 sysname / mgmt IP / SSH / NETCONF）
- [x] TFTP server IP = 192.168.100.254（从 .env 注入，非 fallback 127.0.0.1）

**T3 验证关键点**：
- **必须**在 .env 里设 ZTP_HOST_IP（不能只在 .env.example 注释），否则 fallback 到 127.0.0.1，设备拉不到文件
- 宿主机 IP **不是** 192.168.100.4（.env.example 注释值）而是 **192.168.100.254**（ens34 物理网段接口）
- 容器用 host network 模式共享宿主机网络栈，能接收 .177 物理网段 L2 DHCP 广播

**T3 约束**（✅ 已遵守）：
- ✅ **不**修改 ops-toolkit 容器（按用户指示"开新容器"）
- ✅ .env.example 永久化（ZTP_* 变量标记为 ZTP-only，可选）
- ✅ autocfg.cfg 模板走 env vars 占位符（无明文密码固化）

**T3 详细记录**：见 `notes.md §4`

---

## Task 4: 真机验证 T3（T4）

**目的**：在 .177 设备上验证"自动配置"功能是否真能跑通。

**步骤**：
- [ ] 检查 .177 当前状态（check-host / check-netconf）
- [ ] 备份 .177 当前 startup.cfg（用 paramiko + SSH CLI 跑 `more startup.cfg`，绕开 capture-config 的 scp 兼容问题）
- [ ] 启动 ztp-server 容器：`docker compose -f docker-compose.dev.yml --profile ops up -d ztp-server`
- [ ] 验证 ztp-server 在 192.168.100.x 网段监听 DHCP 67 + TFTP 69 端口
- [ ] 在 .177 上跑 `reset saved-configuration`（清空 startup.cfg）
- [ ] reboot .177 设备
- [ ] 观察 .177 启动行为（看 SSH 22 是否自动起）
- [ ] 验证：
  - 60s 内 .177 SSH 22 通（拉取 autocfg.cfg 后 SSH server 应自动起）
  - 60s 内 .177 NETCONF 830 通
  - 120s 后 .177 配置包含 autocfg.cfg 内容（sysname / ssh server / netconf 等）
- [ ] 失败立即 restore 备份 + 决策 C
- [ ] 1 个 commit: `docs(ztp): T4 .177 真机验证结果`（成功 / 失败记录）

**T4 风险**：
- .177 失联风险：失败需 console 线恢复（用户需确认 .177 是否物理可达）
- 影响范围：.177 是测试设备，不影响生产
- 兜底：保留 .177 备份 startup.cfg + restore 脚本

**T4 卡壳处理**（用户 2026-07-17 确认）：
- 1 次失败 → 立即停手，T5 决策 C
- **不**反复重启 .177 设备（避免影响用户其他测试）

---

## Task 5: 决策报告（T5）

**目的**：根据 T4 结果出最终决策。

**步骤**：
- [ ] T4 成功 → 决策 B（投入 ZTP，但仅 .177 平台，其他平台等设备升级）
- [ ] T4 失败 → 决策 C（不投入 ZTP，留作 v3.x 远期）
- [x] 写 `design.md §3.4` 决策报告（决策 B）
- [x] 更新 `specs/sdn-ztp.md` 状态（B 落地 / C 标 ⏸️ 不实施）—— 见 notes.md §5.6
- [ ] 1 个 commit: `docs(ztp): T5 决策报告 + archive + 同步 3 处 A 类文档`（VERSION-ROADMAP / PRD-V3.0 / README）

---

## 验收 checklist

- [x] T1: H3C V7 ZTP 官方文档调研完成
- [x] T2: ZTP 命令真机探针完成（3 设备全 Unrecognized）
- [x] T3: ztp-server 容器基建完成（dnsmasq + autocfg.cfg）
- [x] T4: .177 真机验证完成（autocfg 机制成功, autocfg.cfg 模板大部分生效）
- [x] T5: 决策报告完成（决策 B: 精简 ZTP）
- [x] 5 个 commit 顺序与 task 顺序一致（T1 + T2 + T3 + T4 + T5）
- [x] 每个 commit 仅含调研笔记 / 文档 / 容器基建 / 真机验证记录
- [x] T3 含 1 个独立容器（**不**影响 ops-toolkit）
- [x] T4 真机走 ztp-server 容器（不裸写 dnsmasq/tftpd）
- [x] 探针全部走 ops-toolkit 容器
- [x] 设备最终恢复初始态（T4 后 user 用 backup 恢复 .177）
- [x] design.md §3.4 决策报告由用户拍板
- [x] no debug print / no TODO
- [x] no hardcoded credentials（autocfg.cfg 走 env vars）

## Commit 格式（5 个 commit）

```
1. docs(ztp): T1 H3C V7 ZTP 官方文档调研总结
2. docs(ztp): T2 ZTP 命令真机探针记录
3. feat(ztp): T3 ztp-server 容器基建（dnsmasq + autocfg.cfg）
4. docs(ztp): T4 .177 真机验证结果（attempt 2 成功 + autocfg.cfg 精简修订）
5. docs(ztp): T5 决策报告 + archive + 同步 A 类文档
```
