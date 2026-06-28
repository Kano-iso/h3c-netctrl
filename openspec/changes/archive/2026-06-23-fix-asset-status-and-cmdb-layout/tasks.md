## 1. Bug 2 修复（CMDB 操作列宽度）

- [x] 1.1 `frontend/src/views/CMDB.vue` L170：`<th class="px-4 py-3 text-right font-medium w-24">` → `<th class="px-4 py-3 text-right font-medium w-32">`

## 2. Bug 1 修复（资产状态判定）

- [x] 2.1 `backend/app/utils/ssh_executor.py::collect_hardware_info` L210-211 后增加：第一条 `execute("display device")` 返回 `success=false` 时 `raise ConnectionError(f"SSH 连接失败或命令无输出: {self.host}")`
- [x] 2.2 `backend/app/routers/asset.py::refresh_asset` L103 后增加：`if not any(info.values()): raise Exception("采集结果为空，SSH 可能未连接")`，走 except 分支

## 3. 验证

- [x] 3.1 设备 1.1.1.1 (id=7) refresh：返回 `success=false, error="采集硬件信息失败: SSH 连接失败或命令无输出: 1.1.1.1（第一条命令 'display device' 失败，output='[Errno None] Unable to connect to port 22 on 1.1.1.1'）"`，status 改为 `offline` ✓
- [x] 3.2 设备 id=1 (Spine-01) refresh：返回 `success=true, "硬件信息已刷新"`，status=`online`，model=`H3C Comware` ✓
- [x] 3.3 CMDB 表格行操作列：HTML 已改 `w-24` → `w-32`，HMR 加载无报错
- [x] 3.4 后端容器 uvicorn --reload 自动重载（volume 挂载），无报错
- [x] 3.5 Vite HMR 加载 CMDB.vue 无报错

## 4. 收尾

- [x] 4.1 提交代码 `fix(asset-status): 不可达设备判 offline + CMDB 操作列宽度适配`（commit 上面）
- [x] 4.2 archive change
