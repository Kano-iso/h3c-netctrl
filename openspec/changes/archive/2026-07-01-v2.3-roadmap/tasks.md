# v2.3-roadmap Tasks

> v2.3 定位：**修 bug + 健壮性补全**小版本（非新功能大版本）。所有 sub-change 集中发版 v2.3.0 + v2.3.1 patch。
> v2.3.0 tag (`c6df368`) 当时**没有真机验证**（仅 mock 推断），发版后用户实测发现 2 个 bug
> （fix-loopback-vsi-ipv4 + fix-rotation-total-keep），v2.3.1 修复 + 真机验证。

---

## 0. 聚合变更（v2.3 整体）

- [x] 0.1 `add-v22-qa-repair` (P0) → archive/2026-06-29-add-integration-test-framework
- [x] 0.2 `qa-template-mandatory` (P0) → 落地 openspec/changes/QA-TEMPLATE.md
- [x] 0.3 `add-qa-guide` (P0) → docs/QA-GUIDE.md + archive/2026-06-29-add-integration-test-framework
- [x] 0.4 `add-v22-backup-frontend-ui-tests` (P0) → 实测 6.3-6.8/6.10/6.11 通过
- [x] 0.5 `add-ops-toolkit-container` (P0) → archive/2026-06-29-add-ops-toolkit
- [x] 0.6 `add-interface-l2-l3-switch` (P0) → archive/2026-06-29-fix-link-mode-switch
- [x] 0.7 `add-backup-e2e-and-integration-tests` (P1) → 复用 qa-backend 框架 + 11 真机 case
- [x] 0.8 `add-vitest-component-tests` (P1) → archive/2026-06-29-add-vitest-component-tests（BLOCKED by EACCES，框架就绪）
- [x] 0.9 `v2.3-container-decoupling-asset` (P2) → **2026-06-30 决策：推 v3.0 VPC 一起做** (commit c03ee54)
- [x] 0.10 `interface-linked-config` (P2) → **2026-06-30 决策：用户暂不需要，从 v2.3 PRD 删** (commit c03ee54)

## 1. v2.2.0 QA 漏项补齐（P0，0.1 展开）

### 1.1 后端 API smoke + 错误码
- [x] 1.1.1 `test_smoke.py` 14 端点 existence smoke
- [x] 1.1.2 `test_backup_api.py` 7 API 错误码
- [x] 1.1.3 `test_vpn_api.py` 4 API
- [x] 1.1.4 `test_interface_edit_api.py` 3 API

### 1.2 conftest.py
- [x] 1.2.1 `--integration` CLI option
- [x] 1.2.2 `integration` marker
- [x] 1.2.3 集成测试不通时 skip

### 1.3 真机集成测试
- [x] 1.3.1 `test_backup_integration.py` 192.168.100.177 真机 7/7 PASS
- [x] 1.3.2 `test_vpn_integration.py` 192.168.100.177 真机 2/6 PASS（CRUD）+ 4/6 skip（无物理 GE 口，合理 skip）

### 1.4 验证
- [x] 1.4.1 `pytest tests/ --integration` → **127 passed, 4 skipped, 0 failed**

## 2. backup-frontend UI 验证补（0.4 展开）
- [x] 2.1-2.8 用户实测 6.3-6.8 / 6.10 / 6.11 通过

## 3. ops-toolkit 容器（0.5 展开）
- [x] 3.1-3.5 archive/2026-06-29-add-ops-toolkit

## 4. link mode 切换（0.6 展开）
- [x] 4.1-4.7 archive/2026-06-29-fix-link-mode-switch

## 5. 自动化测试架构（0.7 展开）
- [x] 5.1-5.4 test_backup_api.py / test_backup_integration.py / test_vpn_integration.py + CI 配置

## 6. vitest 组件测试（0.8 展开）
- [x] 6.1-6.5 archive/2026-06-29-add-vitest-component-tests（BLOCKED by EACCES node_modules，框架就绪）

## 7. 收尾 / 发版

- [x] 7.1 sub-change 全部 archive（6 个 archive/2026-06-29-* + fix-loopback-vsi-ipv4 + fix-rotation-total-keep）
- [x] 7.2 `RELEASE-NOTES-v2.3.0.md` 已写（archive 6 sub-change 时合并）
- [x] 7.3 README 引用更新
- [ ] 7.4 archive fix-loopback-vsi-ipv4 / fix-rotation-total-keep / v2.3-roadmap
- [ ] 7.5 写 RELEASE-NOTES-v2.3.1.md
- [ ] 7.6 push 全部 commits + `git tag v2.3.1`（**待用户确认**）

## 8. v2.3.1 patch 修复（c6df368 tag 后用户实测发现）

- [x] 8.1 fix-loopback-vsi-ipv4：3 bug + 11 单测 + 真机 192.168.100.5 验证
  - Bug A: _check_l3 判 L2 → _enrich_interface_names 补查真实 name
  - Bug B: IPv4 clear XML key 错 → build_ipv4_address_clear_entries_xml 用 (IfIndex, Ipv4Address)
  - Bug C: link-mode 早期拒逻辑反 → 重写护栏
- [x] 8.2 fix-rotation-total-keep：BACKUP_KEEP 语义改"总份数（含锁定）"+ 7 单测 + 177 真机验证
- [x] 8.3 集成测试选口加固：_filter_safe_ifaces 三重防护（if_index ∈ [32, 4095) + 物理口名字）
- [x] 8.4 vpn_name 加 ts 后缀 + _check_netconf_reachable 加重试扛 177 抖动
- [x] 8.5 177 真机清理：4 个 test_vpn_bind_1_XXXXX 残留已 ncclient NETCONF 删掉
- [x] 8.6 **fix-test-link-mode-hardcoded-ifindex**：test_link_mode_switch_real_device 硬编码 if_index=2（GE1/0/1）摧毁用户接入口 L2 配置 → 改查接口 + 过滤 [32, 4095) 物理 L2 口 + 177 跑过 0 残留（commit 待）
- [x] 8.7 **fix-test-vpn-cleanup**：test_create_vpn_instance / test_delete_vpn_instance / test_bind_unbind_vpn 改用 try/finally + vpn_created/vpn_bound 标记，避免 177 上 VPN 残留（之前 8.5 只清，不防再产生）
- [x] 8.8 177 真机再清 3 个 test_vpn_bind_1_43956/57599/95204 残留（8.5 清后新产生的，证明 cleanup 路径必要）

---

## 子任务列表

### add-ops-toolkit-container (P0) ✅
- A.1-A.6 archive/2026-06-29-add-ops-toolkit

### add-v22-qa-repair (P0) ✅
- B.1-B.3 archive/2026-06-29-add-integration-test-framework

### add-v22-backup-frontend-ui-tests (P0) ✅
- C.1-C.8 用户实测通过

### add-interface-l2-l3-switch (P0) ✅
- D.1-D.7 archive/2026-06-29-fix-link-mode-switch

### add-backup-e2e-and-integration-tests (P1) ✅
- E.1-E.4 11 真机 case

### add-vitest-component-tests (P1, BLOCKED by env) ✅
- F.1-F.5 archive/2026-06-29-add-vitest-component-tests

### qa-template-mandatory (P0, 落地) ✅
- G.1 ✅ proposal.md 必含"QA 验证计划"段
- G.2 ✅ Apply 阶段跑 qa-backend
- G.3 ✅ Archive 阶段跑 qa-frontend

### add-qa-guide (P0) ✅
- H.1 ✅ docs/QA-GUIDE.md

### v2.3-container-decoupling-asset → v3.0
- I.1 ✅ 评估 ROI → 推 v3.0
- I.2 → v3.0 做
- I.3 ✅ v2.3 不拆

### interface-linked-config → 删除
- J.1 ✅ 跟用户确认 → 暂不需要
- J.2 → N/A
- J.3 ✅ 从 v2.3 PRD 删

### v2.3.1 patch ✅
- fix-loopback-vsi-ipv4: 3 bug + 11 单测 + 真机 192.168.100.5 验证
- fix-rotation-total-keep: BACKUP_KEEP 总份数含锁定 + 7 单测 + 177 真机验证
