# v2.3-roadmap Tasks

> v2.3 定位：**修 bug + 健壮性补全**小版本（非新功能大版本）。所有 sub-change 集中发版 v2.3.0。

## 0. 聚合变更（v2.3 整体）

- [ ] 0.1 `add-v22-qa-repair` (P0) —— v2.2.0 14 个新 API smoke + 错误码 + 备份/VPN 集成
- [ ] 0.2 `qa-template-mandatory` (P0) —— QA 模板强制（已在 PRD 阶段落地）
- [ ] 0.3 `add-qa-guide` (P0) —— QA 容器使用文档（已完成 docs/QA-GUIDE.md）
- [ ] 0.4 `add-v22-backup-frontend-ui-tests` (P0) —— 6.3-6.8/6.10/6.11 浏览器 UI 端到端
- [ ] 0.5 `add-ops-toolkit-container` (P0) —— ops-toolkit 容器
- [ ] 0.6 `add-interface-l2-l3-switch` (P0) —— link mode 切换（L2↔L3）
- [ ] 0.7 `add-backup-e2e-and-integration-tests` (P1) —— 自动化测试架构
- [ ] 0.8 `add-vitest-component-tests` (P1) —— vitest 前端组件测试
- [ ] 0.9 `v2.3-container-decoupling-asset` (P2，评估中) —— 拆 asset 容器
- [ ] 0.10 `interface-linked-config` (P2，待具体化) —— 接口联动配置

## 1. v2.2.0 QA 漏项补齐（P0，0.1 展开）

> **关键约束**：v2.2.0 发版时跳过了 qa 容器跑 QA，14 个新 API 0 覆盖。本次把测试全补上。

### 1.1 后端 API smoke + 错误码

- [ ] 1.1.1 `backend/tests/test_smoke.py` 加 14 个端点 existence smoke
- [ ] 1.1.2 `backend/tests/test_backup_api.py` —— FastAPI TestClient 跑 backup 7 个 API
  - POST /api/devices/{id}/backup（成功 / 设备不存在 404 / types 非法 422）
  - GET /api/devices/{id}/backup（成功 / 设备不存在 404）
  - GET /api/devices/{id}/backup/{bid}（成功 / 404 / 410 文件丢失）
  - DELETE /api/devices/{id}/backup/{bid}（成功 / 锁定 403 / 404）
  - POST /api/devices/{id}/backup/{bid}/lock（成功 / 404）
  - POST /api/devices/{id}/backup/{bid}/restore（成功 / 404 / 422 body）
  - POST /api/backups（成功 / 无设备 422）
- [ ] 1.1.3 `backend/tests/test_vpn_api.py` —— 跑 VPN 4 个 API
  - POST /api/devices/{id}/vpn-instances（成功 / 设备不存在 / 名称冲突）
  - GET /api/devices/{id}/vpn-instances（成功 / 设备不存在）
  - POST /api/devices/{id}/interfaces/{if_index}/vpn-bind（成功 / 设备不存在 / 接口不存在 / 二次校验）
  - POST /api/devices/{id}/interfaces/{if_index}/vpn-unbind（成功 / 预校验失败 422）
- [ ] 1.1.4 `backend/tests/test_interface_edit_api.py` —— 跑 link-type + ipv4 3 个 API
  - PATCH /api/devices/{id}/interfaces/{if_index}/link-type（成功 / mode 非法 422 / 二次校验）
  - POST /api/devices/{id}/interfaces/{if_index}/ipv4-address（成功 / IP 非法 422 / 已有冲突）
  - DELETE /api/devices/{id}/interfaces/{if_index}/ipv4-address（成功）

### 1.2 conftest.py 改造

- [ ] 1.2.1 加 `--integration` CLI option（默认 False）
- [ ] 1.2.2 加 `integration` marker（默认 skip，需 --integration 开启）
- [ ] 1.2.3 集成测试连不上设备时**标记 skip 不是 fail**（不阻塞 CI）

### 1.3 真机集成测试

- [ ] 1.3.1 `backend/tests/test_backup_integration.py` —— 192.168.100.4 backup + restore 端到端
  - backup startup 端到端（验证 BACKUP_DIR 落盘 + 数据库元数据 + content_hash）
  - backup running 端到端（验证 display current-configuration 文本）
  - restore with_reboot=true 端到端：备份 → 改 → 回滚 → reboot → verify → 恢复原状
  - 锁定禁删（locked=True → DELETE 403）
  - 轮转（创建 6 份 → 第 6 份时第 1 份被删）
  - **每个 case 最后必须 restore_original_state**（n → n+1 → n，不允许只测 happy path）
- [ ] 1.3.2 `backend/tests/test_vpn_integration.py` —— 192.168.100.5 VPN + link type + IP 端到端
  - 创建测试 VPN instance → 绑定到测试接口 → 解绑 → 删除
  - 改 link type（access ↔ trunk）→ 验证 running-config
  - L3 接口配 IPv4（加 / 改 / 清空）→ 验证 running-config
  - **每个 case 最后必须 restore_original_state**（n → n+1 → n）

### 1.4 验证

- [ ] 1.4.1 跑 `docker compose -f docker-compose.dev.yml --profile qa up qa-backend` —— unit + smoke 全 PASS（集成 skip）
- [ ] 1.4.2 跑 `docker compose -f docker-compose.dev.yml run --rm --entrypoint "pytest -m integration -v" qa-backend` —— 集成全 PASS
- [ ] 1.4.3 集成测试**必须实测**，不允许写"理论上能跑"打 [x]
- [ ] 1.4.4 测试总耗时：unit + smoke < 5s，集成 < 5min

## 2. backup-frontend UI 验证补（0.4 展开）

- [ ] 2.1 浏览器跑 6.3 Devices.vue 行"备份"按钮 → 弹 Modal
- [ ] 2.2 6.4 Modal 中"立即备份" → 新增 1 条
- [ ] 2.3 6.5 下载 → 文件落盘可读
- [ ] 2.4 6.6 锁定 → 图标变化
- [ ] 2.5 6.7 删除非锁定 → 列表减少
- [ ] 2.6 6.8 尝试删锁定 → 按钮禁用
- [ ] 2.7 6.10 CMDB.vue 顶部"全量备份" → 调用成功
- [ ] 2.8 6.11 设备不可达时操作 → 中文错误显示（拔 SSH 但保留 830 端口）

## 3. ops-toolkit 容器（0.5 展开）

- [ ] 3.1 `docker-compose.dev.yml` 新增 ops-toolkit service（profile: ops）
- [ ] 3.2 预装：ping / iputils-ping / netcat-openbsd / openssh-client / python3 / ncclient / netmiko
- [ ] 3.3 预制脚本：
  - `check-host.sh` —— ping + nc 22/830
  - `check-netconf.sh` —— python3 + ncclient 测试 NETCONF connect
  - `ssh-test.sh` —— sshpass + 命令
  - `capture-config.sh` —— SCP 拉 startup.cfg 到挂载目录
  - `reboot-wait.sh` —— reboot 后 sleep + retry SSH 60-120s
- [ ] 3.4 README "运维排查工具" 一节加 ops-toolkit 用法
- [ ] 3.5 真机验证：`docker compose --profile ops run --rm ops-toolkit check-host.sh 192.168.100.4`

## 4. link mode 切换（0.6 展开）

- [ ] 4.1 后端 `backend/app/routers/interface.py` 加 `PATCH /link-mode`（mode=bridge|route, force=bool）
- [ ] 4.2 `backend/app/utils/ssh_executor.py` 加 `set_link_mode(if_index, mode)` 走 SSH CLI
- [ ] 4.3 护栏：mode=route 二次确认（会清 IP） + mode=bridge 二次确认（会清 L3 配置）
- [ ] 4.4 前端 `LinkModeSwitchModal.vue` 二次确认弹窗（force + 警告）
- [ ] 4.5 `Interfaces.vue` 接口行加"改层级"按钮（L2/L3 互切）
- [ ] 4.6 API 客户端 `interfaceApi.setLinkMode(deviceId, ifIndex, mode, force)`
- [ ] 4.7 真机验证：192.168.100.5 找一个 access 接口 → bridge（force=False 路径，先清配置）→ 改回 access → 改 route → 验证 running-config

## 5. 自动化测试架构（0.7 展开）

> **轻量化**：复用 `qa-backend` 容器 + `backend/tests/`，0 装包。

- [ ] 5.1 `backend/tests/test_backup_api.py`（已在 1.1.2 完成）
- [ ] 5.2 `backend/tests/test_backup_integration.py`（已在 1.3.1 完成）
- [ ] 5.3 `backend/tests/test_vpn_integration.py`（已在 1.3.2 完成）
- [ ] 5.4 `.github/workflows/qa.yml` —— `docker compose --profile qa up qa-backend --abort-on-container-exit` + `qa-frontend`

## 6. vitest 组件测试（0.8 展开）

- [ ] 6.1 `frontend/package.json` 加 `vitest` + `@vue/test-utils` + `jsdom`
- [ ] 6.2 `frontend/vitest.config.js` 配置文件
- [ ] 6.3 关键组件测试：
  - `frontend/src/components/BackupListModal.spec.js`（加载 / 锁定 / 删除 / 回滚）
  - `frontend/src/components/LinkModeSwitchModal.spec.js`（二次确认 / force）
  - `frontend/src/views/Devices.vue` 表格行交互（备份按钮）
- [ ] 6.4 `frontend/Dockerfile.qa` 改 `CMD ["npm", "run", "test"]`
- [ ] 6.5 真机验证：`docker compose --profile qa up qa-frontend` —— 编译 + 组件测试全 PASS

## 7. 收尾 / 发版

- [ ] 7.1 `RELEASE-NOTES-v2.3.0.md` 沿用 v2.2.0 模板 + 合并所有 sub-change release notes
- [ ] 7.2 `VERSION-ROADMAP.md` v2.3 状态：进行中 → 已发版
- [ ] 7.3 `README.md` 版本路线图 / 功能概览 / API 端点 / 版本历史 更新
- [ ] 7.4 每个 sub-change archive
- [ ] 7.5 push 全部 commits + `git tag v2.3.0`

## 8. 文档

- [ ] 8.1 `RELEASE-NOTES-v2.3.0.md` 统一发版文档
- [ ] 8.2 每个 sub-change 的 `openspec/specs/<change-name>/spec.md` 规范化
- [ ] 8.3 README 引用更新（QA 流程 / 模板 / 各 sub-change release notes）

---

## 子任务列表（按 sub-change 拆分）

### add-ops-toolkit-container (独立, P0)

- [ ] A.1-A.6 见 § 3

### add-v22-qa-repair (P0)

- [ ] B.1-B.3 见 § 1

### add-v22-backup-frontend-ui-tests (P0)

- [ ] C.1-C.8 见 § 2

### add-interface-l2-l3-switch (P0)

- [ ] D.1-D.7 见 § 4

### add-backup-e2e-and-integration-tests (P1)

- [ ] E.1-E.4 见 § 5

### add-vitest-component-tests (P1)

- [ ] F.1-F.5 见 § 6

### qa-template-mandatory (P0，已落地)

- [ ] G.1 ✅ PRD 阶段已强制：每个 change 的 `proposal.md` 必含 "QA 验证计划" 段
- [ ] G.2 ✅ Apply 阶段必跑 `qa-backend`
- [ ] G.3 ✅ Archive 阶段必跑 `qa-frontend`

### add-qa-guide (P0，已完成)

- [ ] H.1 ✅ `docs/QA-GUIDE.md`（SOP / 流程 / checklist / 跑法）

### v2.3-container-decoupling-asset (评估中)

- [ ] I.1 评估拆 asset 容器的 ROI（开发成本 vs 收益）
- [ ] I.2 如决定拆：Propose → 拆 `asset` service（cmdb + 备份）→ 数据库独立
- [ ] I.3 如不拆：标记"评估结论：暂不拆，v3.0 VPC 时再统一拆" + 关闭此 change

### interface-linked-config (待具体化)

- [ ] J.1 跟用户确认"接口联动配置"具体包含什么能力
- [ ] J.2 评估能力范围 + 选 NETCONF / SSH CLI 实现路径
- [ ] J.3 Propose → Apply → Archive
