## Why

发布前 user feedback 双 bug：

### Bug 1: 不可达设备 status 误判为 "online"

设备 `id=7 (test @ 1.1.1.1)` 实际不可连通（SSH 22 端口 timeout），但调用 `POST /api/devices/7/asset/refresh`：
- 后端返回 `success=true, "硬件信息已刷新"`
- 数据库 `asset.status` 保持 `"online"`
- model/serial_number/firmware_version/software_package 全部 `null`

**根因**：`backend/app/utils/ssh_executor.py::collect_hardware_info`（L205-240）调用 `self.execute("display device")` / `self.execute("display version")`，当 SSH 连接失败时 `execute()` 返回 `{success: false, output: ...}`（不抛异常），`collect_hardware_info` 仅 `if result["success"]:` 跳过该分支，**最终返回空 dict**。

`backend/app/routers/asset.py::refresh_asset`（L88-115）try 块内：
```python
info = executor.collect_hardware_info()  # 返回 {} 不抛异常
asset.model = info.get("model", asset.model)  # 旧值保留
...
asset.status = "online"  # ★ 无条件 online
db.commit()
return APIResponse(success=True, ...)
```
无论 SSH 是否成功，**都把 status 设为 online**。except 分支永远不执行。

### Bug 2: CMDB 表格行加"采集"按钮后整行变胖

`frontend/src/views/CMDB.vue` 表格行操作列 `<th class="w-24">`（96px 固定宽度），加"采集"按钮后操作列实际需要 ~140px，浏览器把整列撑大，导致**整行变胖**。

之前（cmdb-single-asset-refresh change 之前）操作列只有"编辑资产"1 个按钮（~70px），`w-24` 够用。
加"采集"按钮后总宽度溢出，破坏表格布局。

## What Changes

### Bug 1 修复

- **`backend/app/utils/ssh_executor.py::collect_hardware_info`**：增加 SSH 连接预检。第一条 `execute("display device")` 失败时**主动抛 `ConnectionError`**，使调用方能正确进入 except 分支
- **`backend/app/routers/asset.py::refresh_asset`**：增加 `info` 为空校验（`if not any(info.values())`），全空视为采集失败 → 设置 `status="offline"`、返回 `success=false` 错误
- 任一处修复即可，**两层防护**保证：connect 失败抛异常（不依赖 `info` 判断），同时 `info` 全空也判定失败（防御性）

### Bug 2 修复

- **`frontend/src/views/CMDB.vue`**：操作列 `<th class="w-24">` → `<th class="w-32">`（128px），足够容纳 2 个 `btn-soft` 按钮

## Capabilities

### New Capabilities
（无新增，仅修复）

### Modified Capabilities
- `cmdb-single-asset-refresh`：表格行操作列宽度适配
- `cmdb-asset-status`：资产采集状态判定准确性（前后端）

## Impact

- **代码**：
  - `backend/app/utils/ssh_executor.py`：`collect_hardware_info` 增加 1 行预检 + raise
  - `backend/app/routers/asset.py`：`refresh_asset` 增加 1 行 `info` 校验
  - `frontend/src/views/CMDB.vue`：1 处 CSS 宽度调整 `w-24` → `w-32`
- **API 兼容性**：保持
- **数据库**：无迁移，但**已存在的错误 status 数据**（如 id=7 的 online）需要**手动修复**或加一次全量刷新
- **依赖**：无新增
- **回归**：所有可达设备 refresh 行为不变（仍 success + status=online）
