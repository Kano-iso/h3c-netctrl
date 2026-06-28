# v2.2.1-followup-v22-qa-repair

> **补漏 change**：v2.2.0 发版时跳过了 `qa-backend` / `qa-frontend` 容器跑 QA，导致 14 个新 API + 备份 / VPN / link-type / ipv4 业务全无自动化测试。本次 change 把 v2.2.0 漏的 QA 项全量补齐。

## Why

**v2.2.0 现状**（你 2026-06-29 收尾时指出："QA 容器白做了"）：

| 容器 | 跑得通 | v2.2.0 新能力覆盖 | 问题 |
|---|---|---|---|
| `qa-backend` | ✅ 42 tests PASS in 1.16s | **0 / 14 新 API** | backup 7 / VPN 4 / link-type 1 / ipv4 2 全没测 |
| `qa-frontend` | ✅ vite build 2.20s | **0 组件测试** | 只验编译不验逻辑 |

**v2.2.0 引入的新能力**（4 changes + 1 灰度版）：

| 类别 | API 端点 | 现有 test | 缺什么 |
|---|---|---|---|
| **backup (7)** | POST /api/devices/{id}/backup | ❌ | smoke + 错误码 + 中文错误 |
| | GET /api/devices/{id}/backup | ❌ | smoke |
| | GET /api/devices/{id}/backup/{bid} | ❌ | smoke + 404 + 410 |
| | DELETE /api/devices/{id}/backup/{bid} | ❌ | smoke + 锁定 403 |
| | POST /api/devices/{id}/backup/{bid}/lock | ❌ | smoke + locked/unlocked 切换 |
| | POST /api/devices/{id}/backup/{bid}/restore | ❌ | smoke + body 校验 + 设备不存在 |
| | POST /api/backups | ❌ | smoke + 无设备 422 |
| **VPN (4)** | POST /api/devices/{id}/vpn-instances | ❌ | smoke |
| | GET /api/devices/{id}/vpn-instances | ❌ | smoke |
| | POST /api/devices/{id}/interfaces/{if_index}/vpn-bind | ❌ | smoke |
| | POST /api/devices/{id}/interfaces/{if_index}/vpn-unbind | ❌ | smoke + 预校验 |
| **link-type (1)** | PATCH /api/devices/{id}/interfaces/{if_index}/link-type | ❌ | smoke |
| **ipv4 (2)** | POST /api/devices/{id}/interfaces/{if_index}/ipv4-address | ❌ | smoke |
| | DELETE /api/devices/{id}/interfaces/{if_index}/ipv4-address | ❌ | smoke |

**用户原话**（2026-06-29 v2.2.0 收尾时）：
> "我们在 2.2 发版的时候根本就没用 qa 跑过容器吧...这 QA 容器白做了呀...你差哪些 QA 项全量性补"

## What Changes

- **新增 `backend/tests/test_backup_api.py`** —— FastAPI TestClient 跑 backup 7 个 API（成功路径 + 错误码 422/403/404/410 + 中文错误信息）
- **新增 `backend/tests/test_vpn_api.py`** —— 跑 VPN 4 个 API smoke
- **新增 `backend/tests/test_interface_edit_api.py`** —— 跑 link-type 1 + ipv4 2 API smoke
- **更新 `backend/tests/test_smoke.py`** —— 加 14 个新端点的 existence smoke（每个端点至少 1 个 case）
- **新增 `backend/tests/test_backup_integration.py`** —— 真实设备 192.168.100.4 backup + restore 端到端（含 reboot 60-120s verify + n→n+1→n 恢复原状）
- **新增 `backend/tests/test_vpn_integration.py`** —— 真实设备 192.168.100.5 VPN + link type + IP 真机集成
- **可选 `frontend/tests/`** —— vitest 组件测试（如有 v2.3 配套做，先不在本 change）

**装包消耗 = 0**：
- 复用 `qa-backend` 容器（profile: qa）
- 复用 `backend/tests/` 已有 pytest + paramiko
- 复用 `requirements.txt` 已含 `paramiko==2.10.3` + `pytest>=7.0.0`
- 不引入新框架

**约束**：
- 集成测试（192.168.100.4 / .5）需要 SSH 通，需在 conftest.py 加 `--integration` marker 区分（默认不跑，避免阻塞 unit test）
- 集成测试**必须**有 `restore_original_state` 步骤（n → n+1 → n），不能只测 happy path
- 集成测试连不上设备时**标记 skip 而不是 fail**（不阻塞 CI）

## Capabilities

### New Capabilities

| 类别 | 关键能力 |
|---|---|
| 后端 QA：backup 7 API 全覆盖 | smoke + 错误码 + 中文错误 |
| 后端 QA：VPN 4 API 全覆盖 | smoke + 预校验 |
| 后端 QA：link-type + ipv4 全覆盖 | smoke |
| 后端 QA：备份真机集成 | 192.168.100.4 backup + restore 端到端 |
| 后端 QA：VPN + link type + IP 真机集成 | 192.168.100.5 端到端 |

### Modified Capabilities

- `backend/tests/test_smoke.py` 增 14 个端点的 existence smoke

## Impact

- **新增测试文件**：5 个（`test_backup_api.py` / `test_vpn_api.py` / `test_interface_edit_api.py` / `test_backup_integration.py` / `test_vpn_integration.py`）
- **修改测试文件**：1 个（`test_smoke.py` 加 14 smoke）
- **不破坏**：v2.2.0 已发版功能
- **可回退**：直接删 5 个新文件 + revert test_smoke.py
- **跑法**：
  - 默认：`docker compose -f docker-compose.dev.yml --profile qa up qa-backend`（unit + smoke，秒级）
  - 集成：`pytest -m integration`（需 SSH 通设备，分级 marker）

## 顺序与依赖

无依赖，独立 change。**优先级 P0**（v2.2.0 补漏不可推迟太久）。

## 真机验证

- **unit / smoke**：docker compose 起 qa-backend，全 PASS（集成 skip）
- **集成 backup**：
  - 192.168.100.4 (Leaf-03) backup startup/running → 验证 BACKUP_DIR 落盘
  - restore with_reboot=true → 60-120s 等待 SSH 起 → verify running-config
  - **最后必须恢复原状**（n → n+1 → n）
- **集成 VPN**：
  - 192.168.100.5 创建测试 VPN instance → 绑定到测试接口 → 解绑 → 删除
  - **最后必须恢复原状**

## 收尾

- [ ] 1.1 `RELEASE-NOTES-v2.2.0.md` 加"v2.2.0 QA 漏项补齐"小节（这次发版是补漏不发版，单独 archive 即可）
- [ ] 1.2 archive change
- [ ] 1.3 push 全部 commits

## 关联

- 父版本：[v2.2.0 release notes](../../RELEASE-NOTES-v2.2.0.md)
- 依赖：[v2.3-roadmap § 3.3 QA 规范化](../v2.3-roadmap/design.md) —— v2.3.0 计划把 QA 模板化
- 容器定义：[docker-compose.dev.yml `qa-backend` / `qa-frontend`](../../docker-compose.dev.yml)
