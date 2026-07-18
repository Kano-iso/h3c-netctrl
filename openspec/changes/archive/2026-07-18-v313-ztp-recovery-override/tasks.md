# v313-ztp-recovery-override — Tasks

## T0 OpenSpec

- [x] proposal / tasks 初始化

## T1 后端 API

- [x] 新增 recovery override request schema
- [x] 新增写入 / 查询 / 清除 API
- [x] API 写入共享 state 文件，不直接改 `.env`

## T2 ztp-server runtime override

- [x] ztp-server 增加 runtime renderer
- [x] docker-compose 为 ztp-server 挂载 `./data/ztp:/ztp-state`
- [x] override 清除后自动恢复默认 `autocfg.cfg`

## T3 前端页面

- [x] 新增 ZTP 恢复上线页面
- [x] 新增 nav / route / api client / i18n
- [x] 去掉备份回滚 future 标记

## T4 QA

- [x] qa-backend 目标测试
- [x] qa-frontend vitest 目标测试
- [x] 本地 HTTP/页面可访问验证

## T5 文档与收口

- [x] README / VERSION-ROADMAP / PRD-V3.1 / docs 同步
- [x] RELEASE-NOTES-v3.1.3.md
- [x] archive change
