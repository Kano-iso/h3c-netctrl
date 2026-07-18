# Release Notes v3.1.3

> 日期：2026-07-18
> 主题：ZTP 恢复上线旁路功能
> OpenSpec：`v313-ztp-recovery-override`

## 背景

实验设备或模拟器重启后可能丢失配置。过去需要从 console 手工恢复带外管理地址，再回到平台执行纳管与备份回滚。

v3.1.3 提供一个旁路恢复能力：用户在前端临时指定已有设备的 OOB 管理地址，ztp-server 将 `autocfg.cfg` 渲染为该地址，让设备先恢复 SSH / NETCONF / 账号 / OOB 地址。完整配置恢复仍由备份回滚页面独立完成。

## 完成范围

- 新增前端页面：运营管理 → ZTP 恢复。
- 新增 `/api/ztp/recovery-override`：
  - `GET` 查询当前 override
  - `POST` 写入恢复配置
  - `DELETE` 清除恢复配置
- 后端写入共享文件 `data/ztp/recovery_override.json`，不修改 `.env`。
- ztp-server 挂载 `./data/ztp:/ztp-state`，运行时监控 override 并重渲染 `/var/tftp/autocfg.cfg`。
- `ztp_onboard_callback.py` 支持读取 override 中的 host / platform / credential。
- `autocfg.cfg.j2` 标准模板补齐 OOB 管理 VRF：
  - `ip vpn-instance mgt`
  - `interface M-GigabitEthernet0/0/0`
  - `ip binding vpn-instance mgt`
- 备份回滚页面移除“未来”标记；拓扑 / AI 继续保留。

## 边界

- 不自动触发备份回滚。
- 不做 MAC 绑定。
- 不做 DHCP lease 监听。
- 不自动识别是哪台设备。
- 清除 override 后恢复默认 ZTP 序列。

## QA

```bash
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend pytest -q tests/test_ztp_recovery.py tests/test_ztp_onboard.py tests/test_device_api.py
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-frontend npm run test:unit -- src/__tests__/ZtpRecovery.spec.js src/__tests__/Smoke.spec.js
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-frontend npm run build
```

结果：后端 `16 passed`，前端单测 `20 passed`，前端 build passed。

## 已知限制

- 当前环境重建 `ztp-server` 镜像仍遇到外部 alpine 镜像代理 401：
  `docker.m.daocloud.io/v2/library/alpine/manifests/3.20 ... 401 Unauthorized`。
  本次已完成 Compose 配置校验、脚本语法校验、后端 API 实测写入/清除 override；待镜像源恢复后再重建 ztp-server 镜像做容器内 runtime renderer 实测。
