# v312-ztp-onboard-and-asset-sync — Design

## 设计决策

### 1. 业务归属

本能力归属 `ztp` 业务域，新增 `backend/app/routers/ztp.py` 与 `backend/app/services/ztp_onboarding.py`。

当前运行时先在 monolith 与 ctrl 容器注册：

- monolith：`backend/app/main.py`
- split ctrl：`backend/ctrl/main.py`

理由：

- 产品/代码边界属于 ZTP：API 路径、service 命名、spec 都放在 ztp 域。
- 当前还没有独立 ztp 业务后端容器；`ztp-server` 只是 DHCP/TFTP/autocfg 基建容器，不直接写数据库。
- 因为本轮要写 `devices` 并联动 `assets`，运行时需要挂在有后端数据库/内部 API 能力的 monolith/ctrl 上。
- 后续如果拆出 ztp 业务容器，应迁移 `ztp_onboarding` service，而不是改调用语义。

### 2. 输入模型

`POST /api/ztp/onboard`

```json
{
  "host": "192.168.100.101",
  "name": "ztp-switch-101",
  "username": "python",
  "password": "Admin123!@#",
  "port": 830,
  "platform": "lstn",
  "collect_asset": true
}
```

默认值：

- `name` 不传时按 host 末段派生：`ztp-switch-101`
- `username/password` 可从请求传入；后续如需要再接 `.env` 默认 ZTP 凭据
- `collect_asset=true`

### 3. 幂等策略

- 先按 `host` 查找 existing device。
- 已存在则更新 name / port / username / password / platform。
- 不存在则创建新 device。
- 不依赖 serial 做第一键，因为 serial 需要资产采集成功后才知道。

### 4. ztp-server 上线确认

`ztp-server` 增加可选后台 watcher：

1. 等待 `ZTP_MGMT_IP` 的 SSH 22 与 NETCONF 830 均开放。
2. 调用 `ZTP_ONBOARD_API_URL`，默认 `http://127.0.0.1:8001/api/ztp/onboard`。
3. 后端 API 再做一次 SSH/NETCONF 业务探测与资产采集。

开关：

- `ZTP_ONBOARD_ENABLED=false` 默认关闭，避免 DHCP/TFTP 验证场景误写库。
- 验证 v3.1.2 时显式打开。

### 5. 后端探测与资产采集

最小闭环：

1. 用 `SSHExecutor.execute("display version")` 验证 SSH 22 与凭据。
2. 用 `NetconfClient` 验证 NETCONF 830。
3. 创建/更新 device。
4. 调 `SSHExecutor.collect_hardware_info()` 采集资产。
5. 写入 asset 状态：
   - 成功：`online`
   - 失败：`offline`

### 6. split 模式

- ctrl 容器本地写 `Device`。
- asset 写入走 `internal_api.upsert_asset()` 到 data 容器。
- monolith 直接写本地 `Asset`。

### 7. 返回状态

- `status=success`：设备入库 + 探测通过 + 资产采集成功。
- `status=partial`：设备入库成功，资产采集失败。
- `success=false`：探测失败或参数错误，设备不入库。

## 风险

- NETCONF 探测 mock 与真实设备行为可能有差异：QA 先覆盖业务分支，真机验证按需再跑。
- split 模式 data 容器 internal API 不可达：返回 partial，并在 response 中暴露 `asset_sync_error`。
- 重复纳管时凭据更新可能覆盖人工修改：这是主动纳管动作的预期行为，后续产品页可加确认。
