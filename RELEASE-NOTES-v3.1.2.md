# Release Notes v3.1.2

> 日期：2026-07-18
> 主题：ZTP 联动纳管
> OpenSpec：`v312-ztp-onboard-and-asset-sync`

## 背景

v3.1.1 已经完成 ZTP 首启基础配置：设备能通过 DHCP/TFTP 拉取 `autocfg.cfg`，写入 physical OOB static 管理地址，开启 SSH 22 与 NETCONF 830，并在 `.177` LSTN 与 `.26` RSTN 上完成真机验证。

v3.1.2 补齐“上线后进入平台”的闭环：ZTP 服务确认 static 管理地址已经可达后，主动回调后端，后端完成设备纳管、资产采集和现有页面可见。

## 完成范围

- 新增 `/api/ztp/onboard`：ztp-server 回调入口，按 host 幂等 create/update 设备。
- 新增 `ztp_onboarding` service：纳管前二次确认 SSH 22 + NETCONF 830；探测失败不入库。
- 新增 asset upsert 链路：monolith 本地写 `assets`，split ctrl 通过 data internal API 写 `assets`。
- 新增 `/internal/assets/device/{device_id}/upsert`：供 ctrl 容器同步资产状态。
- 新增 `docker/ztp-stack/ztp_onboard_callback.py`：ztp-server watcher 等待 static 管理地址上线后 POST 后端。
- `entrypoint.sh` 支持 `ZTP_ONBOARD_ENABLED=true` 后台启动 watcher；默认关闭，避免普通 DHCP/TFTP 验证误写库。
- `.env.example` 增加 `ZTP_ONBOARD_*` 参数。

## 行为边界

- 不走 DHCP lease 监听，不从临时 DHCP 地址反推最终 static 地址。
- 不做 VPC、业务 VLAN、路由协议、端口绑定等业务配置。
- 不新增专门 ZTP 前端产品页；Devices / CMDB / Dashboard 通过现有接口自然可见。
- 资产采集失败时不回滚设备纳管，返回 `partial`，并把 asset 标记为 `offline`，便于后续排查。

## QA

```bash
docker compose -f docker-compose.dev.yml --profile qa run --rm qa-backend pytest -q tests/test_ztp_onboard.py tests/test_data_internal.py
```

结果：`12 passed`。
