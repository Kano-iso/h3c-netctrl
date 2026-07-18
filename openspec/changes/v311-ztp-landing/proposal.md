# v311-ztp-landing

> **版本定位**：v3.1.1 ZTP 落地 — 解决 v3.1.0 留下的 2 个未解决问题
> **范围**：① 1:1 静态 IP 池子（offset 50 跨池，autocfg.cfg 推 static IP 写物理 OOB 口）② autocfg.cfg 多平台适配（jinja2 + 2 平台条件分支：LSTN S6850 / RSTN V9850）
> **依赖**：v3.1.0（ztp-server 容器 + autocfg.cfg T7064P15 模板已闭环）
> **后续**：v3.1.2（自动纳管）/ v3.1.3（资产可见）依赖本 change 落地
> **基线 PRD**：[PRD-V3.1.1.md](../../../../PRD-V3.1.1.md)（v3.1.1 蓝图），但**用户 2026-07-18 复盘调整了设计**（从"mac-binding + autocfg 不推 static + SSH 推" 改为 "offset 50 跨池 + autocfg.cfg 推 static IP"），以本文档为准

***

## Why

v3.1.0 ZTP 调研闭环（决策 B 精简 ZTP），但留下 2 个未解决问题：

1. **IP 不持久**：当前 OOB 口 DHCP lease 12h 后过期，设备 IP 漂移 → controller 失联
2. **多平台模板未适配**：autocfg.cfg 仅在 .177 T7064P15 验证通过，.5 R6555 / .26 R7643P02 设备型号不同，命令支持差异未探针 → 接入新设备时模板不一定生效

**v3.1.0 真机验证已发现的 2 个关键事实**：

- ✅ autocfg.cfg 模板"几乎全工作"（sysname / local-user / ssh / netconf / save force 全生效）
- ❌ `interface Vlan-interface1 + ip address X X` **Unrecognized**（Vlan1 跟着物理 OOB 口的 DHCP 走，T7064P15 不接受手动 static IP）
- ✅ 设备实际 DHCP 走 `M-GigabitEthernet0/0/0` 物理 OOB 口（v3.1.0 release notes L67-72 真机日志已证）
- ✅ v2.x 阶段 .177 startup.cfg 真实配置 = `interface M-GigabitEthernet0/0/0 + ip binding vpn-instance mgt + ip address 192.168.100.177 255.255.255.0`（带外口配 IP 的成功路径）

**为什么 now**：

* v3.1.2（自动纳管）依赖 IP 持久（DHCP lease 漂移会导致 controller 失联）

* v3.1.3（资产可见）依赖多平台适配（不能只支持 .177）

* v3.1.1 是 v3.1 大版本"上线自动化"路径的中间关键一环，不解决就阻塞后续

**用户原话（2026-07-18 拍板）**：

> "我推了 250 之后，映射成啥？映射成另一个池子，比如 150。如果你写 250，那不就是抢占池子了吗？"

→ **1:1 映射 = 跨池偏移**（offset 50）：DHCP 给的 IP X → autocfg.cfg 写 `X - 50`（DHCP 池 .151-.190 → static 池 .101-.140）。**绝对不能自映射**（X → X），否则设备永久占住 DHCP 池地址，下次 lease 续约冲突。

> "我们用静态啊，我们只在第 1 步刚上线的时候获取的时候用动态壁纸而已"

→ **autocfg.cfg 推 static IP**（**写物理 OOB 口** `M-GigabitEthernet0/0/0` for S6850 / `MEth0/0/0` for V9850）。**不**走 mac-binding / `dhcp-host=MAC,IP,infinite` / SSH 推 static IP。**不**走 Vlan-interface1（v3.1.0 失败路径）。

> "不用探索点5（VRF 绑定），然后 26 可以探索一下"

→ T1 探针：3 平台（.5 / .26 / .177）× 7 命令（**#5 VRF 绑定不探**，#6/#7 V9850 差异探针先保留，待 v3.1.1 T1 跑后再定）。

## What Changes

### 设计决策（用户 2026-07-18 拍板）

| 决策点          | 方案                                                                 | 理由                                                                 |
| ------------ | ------------------------------------------------------------------ | ------------------------------------------------------------------ |
| 1:1 映射策略     | **DHCP** **`.151+X`** **↔ static** **`.101+X`**（X=0..39，offset 50） | 用户原话"250 映射到 150"是 offset 思想；2 池不重叠，40 对 40 完全对称       |
| DHCP 池       | **192.168.100.151-.190**（40 IP）                                    | 设备首启"一无所知"时分配临时地址（"动态壁纸"）                                  |
| Static 池      | **192.168.100.101-.140**（40 IP）                                    | autocfg.cfg 推的最终 static IP；避开 .100 Spine                          |
| gap 安全余量     | **192.168.100.141-.150**（10 IP）                                    | DHCP 池和 static 池之间留 10 IP 安全间隔（防止 dnsmasq 误配）                |
| static IP 推送通道 | **autocfg.cfg 内嵌**（写物理 OOB 口）                                     | 不走 Vlan-interface1（v3.1.0 Unrecognized）；v2.x 在 M-GE 0/0/0 验证成功      |
| 物理 OOB 口      | **S6850 平台：M-GigabitEthernet0/0/0** / **V9850 平台：MEth0/0/0**     | v2.x .177 startup.cfg 真实配置（M-GE 0/0/0）；V9850 OOB 命名差异（PRD L146）|
| 持久化方式        | **save force**（autocfg.cfg 应用后）                                  | H3C V7 save force v3.1.0 已验证；不需要 dhcp-leasefile 持久化            |
| 模板方案         | **jinja2 通用 + 2 平台条件分支**                                         | 1 份 `autocfg.cfg.j2` 维护，按 `{% if platform == 'lstn' %}` / `{% elif platform == 'rstn' %}` 路由；用户 2026-07-18 拍板 |
| 不走 mac-binding | ✅ 明确不走 `dhcp-host=MAC,IP,infinite`                              | 用户原话"不是 mac 绑定，不用了"；v3.1.1 设计只用 static IP + offset 50 跨池     |
| 不走 Vlan-interface1 | ✅ 明确不走                                                   | v3.1.0 T7064P15 Unrecognized；改走物理 OOB 口                            |
| 不绑 VRF        | ✅ autocfg.cfg 阶段不写 `ip binding vpn-instance mgt`              | v3.1.1 阶段简化（VRF 绑 v2.x .177 已有，但 v3.1.1 新设备可不绑）                  |
| T1 探针 #5（VRF）| ❌ 不探                                                       | 用户 2026-07-18 明确指示"不用探索点5"                                          |
| T1 探针 #6/#7    | ⚠️ 暂保留（V9850 NETCONF + user-role 差异）                          | 跑完 T1 后定 .26 真实命令；如 .26 跟 S6850 一致，删除这两个探针                |

### 范围

#### 1. 1:1 静态 IP 池子（autocfg.cfg 内嵌物理 OOB 口）

* **DHCP 池**：`.151-.190`（40 IP，autocfg 机制临时分配）

* **Static 池**：`.101-.140`（40 IP，autocfg.cfg 内嵌静态 IP）

* **1:1 映射**：DHCP `.151+X` ↔ static `.101+X`（X=0..39，offset 50）

* **gap**：`.141-.150` 10 IP 闲置作安全余量

* **autocfg.cfg 写** `interface M-GigabitEthernet0/0/0 + ip address 192.168.100.101 255.255.255.0`（LSTN 平台）
  或 `interface MEth0/0/0 + ip address 192.168.100.101 255.255.255.0`（RSTN 平台）

* **首设备 PoC 测试**（.177 接入）：
  * DHCP 给 .151（首 IP） → autocfg 拉 `ip address 192.168.100.101 255.255.255.0`（= .151 - 50）→ save
  * 重启后 static .101 持久（DHCP lease 12h 过期不影响）

* **设计原理**：
  * DHCP 与 static 池**完全分离**避免冲突（user 2026-07-18 指出"250 写 250 = 抢占池子"）
  * 物理 OOB 口配 static IP 是 v2.x 验证成功路径（v3.1.0 走 Vlan-interface1 失败，已修正）
  * 不依赖 mac-binding / dhcp-leasefile 持久化（用户明确反对）

#### 2. autocfg.cfg 多平台适配（jinja2 + 2 平台条件分支）

* **统一模板**：`autocfg.cfg.j2`，按 `{{ platform }}` 变量渲染

* **2 平台变量**：`lstn`（S6850 平台 .5 R6555 / .177 T7064P15） / `rstn`（V9850 平台 .26 R7643P02）

* **平台条件分支**：用 `{% if platform == 'lstn' %}` / `{% elif platform == 'rstn' %}` 隔离差异

* **差异点**（**T1 探针确定**）：
  * 物理 OOB 口命名（S6850 = `M-GigabitEthernet0/0/0`，V9850 = `MEth0/0/0`）
  * NETCONF 启用命令（S6850 = `netconf ssh server enable`，V9850 待 T1 探针）
  * user-role 命名（S6850 = `network-admin`，V9850 待 T1 探针）

* **通用段**（所有平台共用）：
  * sysname
  * static IP（写物理 OOB 口，offset 50 跨池映射）
  * SSH 服务（`ssh server enable` + VTY 认证 + inbound ssh）
  * 凭据（`local-user` + `password simple` + `authorization-attribute`）
  * `save force` 持久化

#### 3. 模板路由逻辑（entrypoint.sh）

* **输入**：`ZTP_PLATFORM=lstn` env var（默认 `lstn`，向后兼容 v3.1.0）

* **输出**：`autocfg.cfg` 渲染到 `/var/tftp/autocfg.cfg`

* **逻辑**：jinja2 渲染 `autocfg.cfg.j2` → 输出最终 cfg

#### 4. 文档同步

* `docs/ztp-stack.md` 新增多平台验证 SOP + offset 50 跨池映射原理图
* `.env.example` 新增 `ZTP_PLATFORM` 变量（删除 `ZTP_MGMT_IP` / `ZTP_MGMT_MASK` / `ZTP_MGMT_GATEWAY`，autocfg.cfg 不再需要）
* `VERSION-ROADMAP.md` v3.1.1 行状态更新
* `README.md` v3.1.1 行状态更新

### 不在范围（明确边界）

* ❌ **业务配置**（VPC / 端口绑定 / 路由协议）—— v3.0 + v3.2 负责
* ❌ **controller 自动纳管**（DHCP lease → POST /api/devices）—— v3.1.2
* ❌ **前端 ZTP 管理界面**（设备列表实时刷新）—— v3.1.3
* ❌ **DHCP 高可用**（单 dnsmasq 足够测试）
* ❌ **HTTP 协议替换 TFTP**（H3C V7 TFTP 明文风险，v3.1.0 已记录为 v3.x 远期）
* ❌ **设备序列号绑定**（option 82）—— 远期
* ❌ **mac-binding / dhcp-leasefile 持久化**（用户 2026-07-18 明确反对）
* ❌ **Vlan-interface1 路径**（v3.1.0 失败，已走物理 OOB 口）
* ❌ **VRF 绑定**（autocfg.cfg 阶段不绑）

## Capabilities

### New Capabilities

* `ztp-landing`: ZTP 落地能力 — 1:1 静态 IP 池子（offset 50 跨池，autocfg 推 static IP 写物理 OOB 口）+ autocfg.cfg 多平台适配（jinja2 + 2 平台条件分支）

### Modified Capabilities

* 无（v3.1.0 未沉淀 spec，本 change 是 ZTP 第一个正式 spec）

## Impact

| 类型          | 文件                                                             |
| ----------- | -------------------------------------------------------------- |
| 新增          | `docker/ztp-stack/tftp/autocfg.cfg.j2`（jinja2 通用模板，2 平台分支）  |
| 新增          | `openspec/specs/ztp-landing/spec.md`（ZTP 落地 spec）              |
| 修改          | `docker/ztp-stack/entrypoint.sh`（jinja2 渲染 + ZTP\_PLATFORM 路由） |
| 修改          | `docker/ztp-stack/dnsmasq.conf.template`（DHCP 池 .151-.190，**删** dhcp-host / dhcp-leasefile） |
| 修改          | `docker/ztp-stack/Dockerfile`（apk add jinja2 + 模板 COPY 路径调整）   |
| 修改          | `docker-compose.dev.yml`（ztp-server volume 配置调整）                |
| 修改          | `.env.example`（新增 `ZTP_PLATFORM`，**删** `ZTP_MGMT_IP/MASK/GATEWAY`）  |
| 修改          | `docs/ztp-stack.md`（多平台验证 SOP + offset 50 跨池映射说明）                |
| 修改          | `VERSION-ROADMAP.md`（v3.1.1 行状态更新）                             |
| 修改          | `README.md`（v3.1.1 行状态更新）                                      |
| **零业务代码改动** | `backend/` / `frontend/`（本 change 不动业务代码）                      |

## QA 验证计划

### 1. 涉及端点 / UI / 设备

| 类别          | 名称                                         | 涉及文件                                     |
| ----------- | ------------------------------------------ | ---------------------------------------- |
| 容器基建        | ztp-server 容器                              | `docker/ztp-stack/`                      |
| DHCP server | dnsmasq (DHCP + TFTP 二合一)                  | `docker/ztp-stack/dnsmasq.conf.template` |
| TFTP 文件     | autocfg.cfg.j2                             | `docker/ztp-stack/tftp/autocfg.cfg.j2`   |
| 真实设备        | 192.168.100.177 T7064P15（默认测试）             | -                                        |
| 真实设备        | 192.168.100.5 S6850 R6555（v3.1.1 重点适配）     | -                                        |
| 真实设备        | 192.168.100.26 V9850 R7643P02（v3.1.1 重点适配） | -                                        |

### 2. QA 验证项

#### 2.1 容器层（CI 必跑，秒级）

* [ ] `docker compose -f docker-compose.dev.yml --profile ops build ztp-server` 构建成功

* [ ] `dnsmasq --test -C /etc/dnsmasq.conf` 配置语法通过

* [ ] 容器启动后宿主机 `ss -ulnA inet` 看到 `0.0.0.0:67` + `0.0.0.0:69` 监听

* [ ] 容器内 jinja2 渲染成功：`docker exec ztp-server python3 -c "from jinja2 import Template; ..."`

* [ ] 模板路由逻辑：2 平台 env var 切换后 autocfg.cfg 内容差异符合预期
  * `ZTP_PLATFORM=lstn` → autocfg.cfg 含 `interface M-GigabitEthernet0/0/0`
  * `ZTP_PLATFORM=rstn` → autocfg.cfg 含 `interface MEth0/0/0`

* [ ] DHCP 池范围 .151-.190 生效（dnsmasq log 验证）

* [ ] **不**含 `dhcp-host` 配置（用户反对 mac-binding）

#### 2.2 真机集成（按需跑，分钟级，需 SSH 通设备）

* [ ] **T1 三平台探针**（v3.1.1 必须先跑通）：

  * [ ] **.5 R6555**（S6850 平台）：探 `interface M-GigabitEthernet0/0/0 + ip address X X` 1 条命令（确认物理 OOB 静态 IP 支持）

  * [ ] **.26 R7643P02**（V9850 平台）：探 5 条命令
    * `display interface MEth0/0/0` 存在
    * `interface MEth0/0/0 + ip address X X` 静态 IP
    * `netconf ssh server enable` vs `netconf soap http enable`（**T1 后定**）
    * `authorization-attribute user-role network-admin` vs `level-15`（**T1 后定**）
    * `save force`

  * [ ] **.177 T7064P15**（S6850 平台）：v3.1.0 已验 `M-GigabitEthernet0/0/0 + ip address` 路径，**复用 v3.1.0 结果**（除非物理 OOB 口 static IP 命令在 v3.1.0 没测过，需要重探）

* [ ] **.177 完整 ZTP 链路**（默认测试设备）：

  * [ ] 空配置启动 → DHCP 拿 .151（DHCP 池首 IP）→ autocfg 应用 `interface M-GigabitEthernet0/0/0 + ip address 192.168.100.101 255.255.255.0`（= .151 - 50）→ save

  * [ ] 重启后 .101 静态 IP 生效（DHCP lease 12h 过期后仍 .101，**不是 .151**）

  * [ ] SSH 22 / NETCONF 830 验证通过

* [ ] **.5 / .26 至少 1 平台真机验证完整 ZTP 链路**（DHCP → TFTP → autocfg → 应用 → save → 重启 → SSH/NETCONF）

* [ ] **最后必须 restore\_original\_state**（设备恢复到测试前状态）

* [ ] **reboot 类验证必须 sleep + retry 至少 120s**

#### 2.3 回归

* [ ] v3.1.0 已 archive 的 5 个 commit 不破坏（`v31-ztp-research` change）

* [ ] `docker compose -f docker-compose.dev.yml --profile qa up qa-backend` 仍 PASS

* [ ] `docker compose -f docker-compose.dev.yml --profile qa up qa-frontend` lint + build 通过

* [ ] 不破坏现有 3 容器架构（ctrl / config / data 仍 split 默认模式）

### 3. 跑法

```bash
# 容器构建（CI 必跑）
docker compose -f docker-compose.dev.yml --profile ops build ztp-server

# 模板渲染验证（CI 必跑）
docker compose -f docker-compose.dev.yml --profile ops run --rm ztp-server \
    sh -c "python3 -c \"from jinja2 import Template; print(Template(open('/var/tftp/autocfg.cfg.j2').read()).render(platform='lstn', mgmt_ip='192.168.100.101', admin_user='admin', admin_pass='admin'))\""

# 真机集成（按需，需 .177 / .5 / .26 可达）
# 1. 启动 ztp-server（ZTP_PLATFORM=lstn 默认）
docker compose -f docker-compose.dev.yml --profile ops up -d ztp-server

# 2. T1 探针（走 ops-toolkit paramiko-batch-exec.sh）
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit \
    paramiko-batch-exec.sh --device .5 --command "interface M-GigabitEthernet0/0/0; ip address 192.168.100.50 255.255.255.0; quit; display this; undo ip address"

# 3. 备份目标设备 startup.cfg（paramiko 走 ops-toolkit）
docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit \
    paramiko-batch-exec.sh --device test --command "more startup.cfg" > /tmp/backup-177.cfg

# 4. reset saved-configuration + reboot（走 ops-toolkit）
# 5. 观察 60s 内 SSH/NETCONF 通
# 6. 120s 后验证配置含 autocfg.cfg 内容（含 static IP .101）
# 7. 失败立即 restore 备份
# 8. 测试完恢复原状（restore_original_state）

# 回归
docker compose -f docker-compose.dev.yml --profile qa up qa-backend
docker compose -f docker-compose.dev.yml --profile qa up qa-frontend
```

### 4. 验收标准

* [ ] 1:1 静态 IP 池子在 .177 上验证（空配置 → DHCP 拿 .151 → static IP **.101**（= .151 - 50）→ 重启持久）

* [ ] DHCP lease 12h 过期后 .177 仍 **.101**（static IP 生效，已脱离 DHCP 池）

* [ ] .5 / .26 三平台 autocfg.cfg 模板 jinja2 渲染成功（LSTN → M-GigabitEthernet / RSTN → MEth0/0/0）

* [ ] .5 / .26 至少 1 平台真机验证完整 ZTP 链路

* [ ] 容器构建 + 模板渲染 + qa-backend + qa-frontend 全 PASS

* [ ] 真机集成 restore\_original\_state（不污染设备状态）

* [ ] 文档：proposal.md / design.md / tasks.md / RELEASE-NOTES 都引用本 QA 段

* [ ] ZTP 探针全部走 ops-toolkit 容器（不裸写 SSH / paramiko）

## 决策回退路径

* T1 三平台探针失败（任一平台命令全部 Unrecognized）→ 决策 C 重新评估（ZTP 不可行）

* T5 真机验证失败 ≥ 1 平台 → 文档记录"该平台需商用 R6607+ 升级后才能 ZTP"，v3.1.1 仅 .177 / .5（或 .26）单平台落地

* v3.1.1 投入产出比不划算（jinja2 模板适配成本高）→ 决策 C 回退

* user 主动选择 C → archive change + VERSION-ROADMAP 标 v3.1.1 "⏸️ ZTP 不可行"

## 风险与边界

### 业务边界（user 明确）

* ✅ ZTP **只做基础配置**：sysname + 物理 OOB 口 static IP（offset 50 跨池）+ SSH 22 + NETCONF 830 + 凭据
* ❌ ZTP **不做业务配置**：VPC / 端口绑定 / 路由协议
* ❌ ZTP **不做 controller 自动纳管**（v3.1.2 范畴）
* ❌ ZTP **不做前端 ZTP 界面**（v3.1.3 范畴）

### 技术风险

| 风险                | 缓解                                                    |
| ----------------- | ----------------------------------------------------- |
| 物理 OOB 口配 static IP 跨平台支持差异 | T1 探针先做 S6850 / V9850，发现 Unrecognized 立即备选命令或标 skip |
| 2 平台 NETCONF 差异   | T1 探针 #6 验证 V9850 用 SSH vs SOAP 协议；如差异大则 RSTN 模板分支用 SOAP |
| 2 平台 user-role 差异  | T1 探针 #7 验证 V9850 用 network-admin vs level-15；如差异大则 RSTN 模板分支用对应命令 |
| H3C V7 TFTP 明文密码  | 已记录为 v3.x 远期（HTTP 协议 + password hash）；v3.1.1 接受明文风险   |
| 设备失联风险            | 真机测试前必备份 startup.cfg + restore 脚本（ops-toolkit）        |
| v3.1.0 决策 B 回归风险   | v3.1.0 已删 `interface Vlan-interface1` 行，v3.1.1 改走物理 OOB 口，命令完全不同；回归测试必跑 |
| 模板路由误判            | 严格按 env var `ZTP_PLATFORM` 路由（lstn / rstn）；默认 `lstn` 兼容 v3.1.0 |
