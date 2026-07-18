# v312-ztp-onboard-and-asset-sync — Tasks

## T0 OpenSpec

- [x] proposal / design / tasks / spec 初始化

## T1 后端 ZTP onboard API

- [x] 新增 `backend/app/routers/ztp.py`
- [x] 新增 `backend/app/services/ztp_onboarding.py`，ZTP 业务逻辑不塞进 device/asset router
- [x] 新增 `ZtpOnboardRequest` schema
- [x] monolith 与 ctrl 容器注册 `/api/ztp/onboard`
- [x] 实现 host 幂等 create/update
- [x] 实现 SSH 22 + NETCONF 830 探测
- [x] 记录 onboard 操作日志

## T2 asset 联动

- [x] 抽出可复用 asset upsert helper
- [x] monolith 本地 upsert asset
- [x] split ctrl 通过 data internal API upsert asset
- [x] data internal 新增 `/internal/assets/device/{device_id}/upsert`
- [x] asset 采集成功/失败状态清晰

## T2b ztp-server 上线确认与回调

- [x] 新增 `docker/ztp-stack/ztp_onboard_callback.py`
- [x] `entrypoint.sh` 支持 `ZTP_ONBOARD_ENABLED=true` 后台启动 watcher
- [x] watcher 等待 static 管理 IP SSH 22 + NETCONF 830 开放后 POST `/api/ztp/onboard`
- [x] `.env.example` 增加 `ZTP_ONBOARD_*` 配置，默认关闭

## T3 QA

- [x] mock SSHExecutor / NetconfClient，虚构 IP 完成 onboard 成功链路
- [x] 重复 onboard 幂等更新，不新增重复设备
- [x] asset 采集失败返回 partial 且 asset offline
- [x] 增删查闭环：onboard → list/get device → get asset → delete device
- [x] data internal asset upsert 单测
- [x] qa-backend 容器跑目标测试

## T4 文档与归档

- [x] README / VERSION-ROADMAP / PRD-V3.1 按 v3.1.2 完成态同步
- [x] RELEASE-NOTES-v3.1.2.md
- [x] archive change
- [ ] push/tag 等 user review 后执行
