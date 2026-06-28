# v2.3-roadmap Tasks

> v2.3-roadmap 是聚合 PRD，每个 sub-change 独立执行独立 archive。
> 本文件列 v2.3 整体推进的里程碑 + 每个 sub-change 内部任务的子文件链接。

## 0. 聚合变更（v2.3-roadmap 本身）

- [ ] 0.1 `add-ops-toolkit-container` —— Propose → Apply → Archive
- [ ] 0.2 `v2.2.1-followup-backup-frontend-ui-tests` —— Propose → Apply → Archive（v2.2.0 收尾时的 follow-up 单独立 change）
- [ ] 0.3 `add-interface-l2-l3-switch` —— Propose → Apply → Archive
- [ ] 0.4 `add-backup-e2e-and-integration-tests` —— Propose → Apply → Archive
- [ ] 0.5 `v2.3-container-decoupling-asset`（可选）—— 评估后决定是否 Propose
- [ ] 0.6 `interface-linked-config` —— 需求具体化后 Propose

## 1. 收尾

- [ ] 1.1 `RELEASE-NOTES-v2.3.0.md` 沿用 v2.2.0 模板 + 合并所有 sub-change release notes
- [ ] 1.2 `VERSION-ROADMAP.md` v2.3 状态：进行中 → 已发版
- [ ] 1.3 `README.md` 版本路线图 / 功能概览 / API 端点 / 版本历史 更新
- [ ] 1.4 push 全部 commits + `git tag v2.3.0`

## 2. 文档

- [ ] 2.1 `RELEASE-NOTES-v2.3.0.md` 统一发版文档
- [ ] 2.2 每个 sub-change 的 `openspec/specs/<change-name>/spec.md` 规范化
- [ ] 2.3 README 引用更新

---

## 子 change 任务列表

### add-ops-toolkit-container

- [ ] A.1 docker-compose.dev.yml 新增 ops-toolkit service（profile: ops）
- [ ] A.2 预装：ping / iputils-ping / netcat-openbsd / openssh-client / python3 / ncclient / netmiko
- [ ] A.3 预制脚本：
  - [ ] A.3.1 `check-host.sh` — ping + nc 22/830
  - [ ] A.3.2 `check-netconf.sh` — python3 + ncclient 测试 NETCONF connect
  - [ ] A.3.3 `ssh-test.sh` — sshpass + 命令
  - [ ] A.3.4 `capture-config.sh` — SCP 拉 startup.cfg 到挂载目录
- [ ] A.4 README "运维排查工具" 一节加 ops-toolkit 用法
- [ ] A.5 真机验证：`docker compose --profile ops run --rm ops-toolkit check-host.sh 192.168.100.4`
- [ ] A.6 Archive

### v2.2.1-followup-backup-frontend-ui-tests

- [ ] B.1 浏览器跑 6.3 Devices.vue 行"备份"按钮 → 弹 Modal
- [ ] B.2 6.4 Modal 中"立即备份" → 新增 1 条
- [ ] B.3 6.5 下载 → 文件落盘可读
- [ ] B.4 6.6 锁定 → 图标变化
- [ ] B.5 6.7 删除非锁定 → 列表减少
- [ ] B.6 6.8 尝试删锁定 → 按钮禁用
- [ ] B.7 6.10 CMDB.vue 顶部"全量备份" → 调用成功
- [ ] B.8 6.11 设备不可达时操作 → 中文错误显示（拔 SSH 但保留 830 端口）
- [ ] B.9 Archive（无新代码，仅真机验证补完）

### add-interface-l2-l3-switch

- [ ] C.1 后端 `backend/app/routers/interface.py` 加 `PATCH /link-mode`（mode=bridge|route, force=bool）
- [ ] C.2 `backend/app/utils/ssh_executor.py` 加 `set_link_mode(if_index, mode)` 走 SSH CLI
- [ ] C.3 护栏：mode=route 二次确认（会清 IP） + mode=bridge 二次确认（会清 L3 配置）
- [ ] C.4 前端 `LinkModeSwitchModal.vue` 二次确认弹窗（force + 警告）
- [ ] C.5 `Interfaces.vue` 接口行加"改层级"按钮（L2/L3 互切）
- [ ] C.6 API 客户端 `interfaceApi.setLinkMode(deviceId, ifIndex, mode, force)`
- [ ] C.7 真机验证：192.168.100.5 找一个 access 接口 → bridge（force=False 路径，先清配置）→ 改回 access → 改 route → 验证 running-config
- [ ] C.8 Archive

### add-backup-e2e-and-integration-tests（**轻量化：不引入新框架**）

> **关键决策**：复用项目已有 `qa-backend` 容器（profile: qa）跑 pytest + paramiko，不引入 Playwright / httpx / Cypress 等新框架。理由：项目已有 QA 基础设施（`backend/tests/` 7 个测试 + `qa-backend` 容器 + `requirements.txt` 已含 `paramiko` + `pytest`），新引入是 over-engineering。

- [ ] D.1 `backend/tests/test_backup_api.py` —— FastAPI TestClient 跑 backup 7 个 API（POST backup / GET list / GET download / DELETE / POST lock / POST restore / POST /backups 全量）
- [ ] D.2 `backend/tests/test_backup_integration.py` —— pytest + paramiko 跑 192.168.100.4 backup + restore 端到端（含 reboot 60-120s verify）
- [ ] D.3 `backend/tests/test_vpn_integration.py` —— pytest + paramiko + ncclient 跑 192.168.100.5 VPN + link type + IP 真机
- [ ] D.4 `.github/workflows/qa.yml` —— `docker compose --profile qa up qa-backend --abort-on-container-exit`
- [ ] D.5 Archive

### v2.3-container-decoupling-asset（评估中）

- [ ] E.1 评估拆 asset 容器的 ROI（开发成本 vs 收益）
- [ ] E.2 如决定拆：Propose → 拆 `asset` service（cmdb + 备份）→ 数据库独立
- [ ] E.3 如不拆：标记 "评估结论：暂不拆，v3.0 VPC 时再统一拆" + 关闭此 change

### interface-linked-config（待具体化）

- [ ] F.1 跟用户确认"接口联动配置"具体包含什么能力
- [ ] F.2 评估能力范围 + 选 NETCONF / SSH CLI 实现路径
- [ ] F.3 Propose → Apply → Archive
