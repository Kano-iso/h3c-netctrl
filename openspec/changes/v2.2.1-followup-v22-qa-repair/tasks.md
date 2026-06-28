# v2.2.1-followup-v22-qa-repair Tasks

> 补 v2.2.0 漏的 14 个新 API + 备份 / VPN 真机集成测试。

## 1. 后端 QA：补 14 个新 API smoke + 错误码

- [ ] 1.1 `backend/tests/test_smoke.py` 加 14 个端点 existence smoke（每个端点 1 个 case，至少 200/400/404/422 之一）
- [ ] 1.2 `backend/tests/test_backup_api.py` —— FastAPI TestClient 跑 backup 7 个 API
  - [ ] 1.2.1 POST /api/devices/{id}/backup（成功 / 设备不存在 404 / types 非法 422）
  - [ ] 1.2.2 GET /api/devices/{id}/backup（成功 / 设备不存在 404）
  - [ ] 1.2.3 GET /api/devices/{id}/backup/{bid}（成功 / 404 / 410 文件丢失）
  - [ ] 1.2.4 DELETE /api/devices/{id}/backup/{bid}（成功 / 锁定 403 / 404）
  - [ ] 1.2.5 POST /api/devices/{id}/backup/{bid}/lock（成功 / 404）
  - [ ] 1.2.6 POST /api/devices/{id}/backup/{bid}/restore（成功 / 404 / 422 body）
  - [ ] 1.2.7 POST /api/backups（成功 / 无设备 422）
- [ ] 1.3 `backend/tests/test_vpn_api.py` —— 跑 VPN 4 个 API
  - [ ] 1.3.1 POST /api/devices/{id}/vpn-instances（成功 / 设备不存在 / 名称冲突）
  - [ ] 1.3.2 GET /api/devices/{id}/vpn-instances（成功 / 设备不存在）
  - [ ] 1.3.3 POST /api/devices/{id}/interfaces/{if_index}/vpn-bind（成功 / 设备不存在 / 接口不存在 / 二次校验）
  - [ ] 1.3.4 POST /api/devices/{id}/interfaces/{if_index}/vpn-unbind（成功 / 预校验失败 422）
- [ ] 1.4 `backend/tests/test_interface_edit_api.py` —— 跑 link-type + ipv4 3 个 API
  - [ ] 1.4.1 PATCH /api/devices/{id}/interfaces/{if_index}/link-type（成功 / mode 非法 422 / 二次校验）
  - [ ] 1.4.2 POST /api/devices/{id}/interfaces/{if_index}/ipv4-address（成功 / IP 非法 422 / 已有冲突）
  - [ ] 1.4.3 DELETE /api/devices/{id}/interfaces/{if_index}/ipv4-address（成功）

## 2. conftest.py 改造

- [ ] 2.1 加 `--integration` CLI option（默认 False）
- [ ] 2.2 加 `integration` marker（默认 skip，需 --integration 开启）
- [ ] 2.3 集成测试连不上设备时**标记 skip 不是 fail**（不阻塞 CI）

## 3. 真机集成测试

- [ ] 3.1 `backend/tests/test_backup_integration.py` —— 192.168.100.4 backup + restore 端到端
  - [ ] 3.1.1 backup startup 端到端（验证 BACKUP_DIR 落盘 + 数据库元数据 + content_hash）
  - [ ] 3.1.2 backup running 端到端（验证 display current-configuration 文本）
  - [ ] 3.1.3 restore with_reboot=true 端到端：备份 → 改 → 回滚 → reboot → verify → 恢复原状
  - [ ] 3.1.4 锁定禁删（locked=True → DELETE 403）
  - [ ] 3.1.5 轮转（创建 6 份 → 第 6 份时第 1 份被删）
  - [ ] 3.1.6 **每个 case 最后必须 restore_original_state**（n → n+1 → n，不允许只测 happy path）
- [ ] 3.2 `backend/tests/test_vpn_integration.py` —— 192.168.100.5 VPN + link type + IP 端到端
  - [ ] 3.2.1 创建测试 VPN instance → 绑定到测试接口 → 解绑 → 删除
  - [ ] 3.2.2 改 link type（access ↔ trunk）→ 验证 running-config
  - [ ] 3.2.3 L3 接口配 IPv4（加 / 改 / 清空）→ 验证 running-config
  - [ ] 3.2.4 **每个 case 最后必须 restore_original_state**（n → n+1 → n）

## 4. 验证

- [ ] 4.1 跑 `docker compose -f docker-compose.dev.yml --profile qa up qa-backend` —— unit + smoke 全 PASS（集成 skip）
- [ ] 4.2 跑 `docker compose -f docker-compose.dev.yml run --rm --entrypoint "pytest -m integration -v" qa-backend` —— 集成全 PASS
- [ ] 4.3 集成测试**必须实测**，不允许写"理论上能跑"打 [x]
- [ ] 4.4 测试总耗时：unit + smoke < 5s，集成 < 5min

## 5. 收尾

- [ ] 5.1 验证 v2.2.0 14 个新 API 全覆盖（README.md 或 RELEASE-NOTES 加"v2.2.0 QA 漏项补齐"小节）
- [ ] 5.2 archive change
- [ ] 5.3 push 全部 commits

## 6. 文档

- [ ] 6.1 `RELEASE-NOTES-v2.2.0.md` 加"v2.2.0 QA 漏项补齐"小节（说明：本次是补漏不发版，单独 archive 即可）
- [ ] 6.2 `VERSION-ROADMAP.md` v2.2.x 加本次补漏记录
- [ ] 6.3 `README.md` 版本历史 + QA 说明更新
- [ ] 6.4 `v2.3-roadmap` 加引用："v2.2.0 QA 补漏已做"
- [ ] 6.5 **`docs/QA-GUIDE.md`**（SOP / 流程 / checklist / 跑法）—— 防止将来忘记 QA 流程
