# Release Notes: v3.1.1 ZTP 落地

发布日期：2026-07-18

## 版本定位

v3.1.1 把 v3.1.0 调研阶段验证过的 H3C V7 autocfg 机制落到可复用链路：新设备空配置启动后，通过 `ztp-server` 获取 DHCP 临时地址、拉取 `autocfg.cfg`，再把 physical OOB 口写成静态管理 IP，并启用 SSH/NETCONF 与项目统一账号。

本版本仍不做业务配置、不做 VPC/端口绑定、不做 controller 自动纳管；纳管入库和前端可见合并进入 v3.1.2，VPC/业务配置进入 v3.2 之后的能力。

## 核心变化

- `ztp-server` 支持 jinja2 渲染 `autocfg.cfg.j2`，按 `ZTP_PLATFORM=lstn|rstn` 分平台生成配置。
- DHCP 池调整为 `.151-.190`，仅作为首启临时地址；static 管理地址由 `ZTP_MGMT_IP` 指定，已验证 `.101` 和 `.102`。
- LSTN/S6850 使用 physical OOB 口 `M-GigabitEthernet0/0/0`。
- RSTN/V9850 在真实配置中也使用 `M-GigabitEthernet0/0/0`，display brief 中显示为 `MGE0/0/0`。
- `ZTP_SYSNAME` 留空或保持旧默认 `ztp-device` 时，entrypoint 会按管理 IP 派生：`.101 -> ztp-switch-101`、`.102 -> ztp-switch-102`。
- ops-toolkit 新增/加固 `reboot-wait.sh`，支持 reset saved-configuration + reboot + 等待目标 IP 恢复。
- `capture-config.sh` 补齐 H3C V7 低版本 RSA/SCP 兼容参数，`.26` 已成功拉取 startup.cfg。

## 真机验证

| 设备 | 平台 | 结果 |
|---|---|---|
| `.177` | S6850 / T7064P15-hcl / LSTN | reset saved-configuration 后完整 ZTP 成功，最终 static `.101`，SSH 22 + NETCONF 830 通，二次 reboot 后仍为 `.101` |
| `.26` | V9850-256H / R7643P02 / RSTN | reset saved-configuration 后完整 ZTP 成功，最终 static `.102`，sysname `ztp-switch-102`，SSH 22 + NETCONF 830 通，二次 reboot 后仍为 `.102` |
| `.5` | S6850 / T7064P15-prod / LSTN | 不跑完整 ZTP，仅作为 OOB/static 命令探针佐证 |

证据保存在 `openspec/changes/archive/2026-07-18-v311-ztp-landing/captures/ztp-test/`。

## 已知注意点

- v3.1.1 不从 dnsmasq lease 自动计算 static IP；本轮通过 `ZTP_MGMT_IP` 指定，后续 v3.1.2 基于该 static 管理地址做纳管联动，不走 DHCP lease 监听。
- 当前环境重建 `ztp-server` 镜像时曾遇到外部 alpine 镜像代理 401；真机验证使用已有镜像并挂载当前模板/entrypoint 完成，不影响已验证的配置逻辑。
- `.177` 保留 `.101` 验证态，恢复材料已保存；`.26` 经 user 手工恢复后再次执行 `.102` 适配验证。

## 关键提交

- `8551310 test(ztp): T7 容器层 CI 验证`
- `8a7aa03 chore(ztp): T8 qa-backend 回归 N/A`
- `0bc0592 docs(ztp): sync v3.1.1 handoff scope`
- `40257b7 test(ztp): T9 .177 ZTP链路验证与RSTN模板纠偏`
- `bd80e79 fix(ztp): 按管理IP派生sysname并收紧RSTN模板`
- `4472e35 test(ztp): T10 .26 RSTN完整ZTP链路验证`
