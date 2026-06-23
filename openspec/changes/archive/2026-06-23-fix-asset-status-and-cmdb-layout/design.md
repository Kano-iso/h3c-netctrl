## Context

发布前 user feedback 双 bug 修复。

### Bug 1 现状

`ssh_executor.py::execute()` 设计返回 `{success: bool, output: str, execution_time: float}` dict 而非抛异常，调用方根据 success 处理。
`collect_hardware_info()` 利用此特性"优雅降级"：连接失败时跳过解析，最终返回 `{}`。

`asset.py::refresh_asset` 误把"未抛异常"等同于"成功"，**无条件 status="online"**。

### Bug 2 现状

CMDB.vue L170 `<th class="w-24">` 是 96px。加 cmdb-single-asset-refresh 后操作列含"采集 + 编辑资产"两个按钮，理论宽度 140-160px，超出导致整列被撑大、整行变胖。

## Goals / Non-Goals

**Goals:**
- SSH 不可达时 status 正确判为 offline
- CMDB 表格行操作列宽度适配 2 个按钮
- 已有错误数据（如 id=7 的 online）提供修复路径

**Non-Goals:**
- 不实现"未采集"与"离线"的状态细分（保留现有 5 个 status）
- 不改 SSH 连接逻辑
- 不改前端"采集"按钮设计

## Decisions

### 1. 修复点选择：双层防护

- **选择**：
  - `collect_hardware_info` 第 1 次 `execute` 失败时**主动 raise `ConnectionError`**（后端防御性编程）
  - `asset.py::refresh_asset` 检测 `info` 为空 → 视为采集失败（前端/中间层防御）
- **理由**：任一层修复即可工作，双层更安全：
  - 假如 `collect_hardware_info` 被其他路由调用（execute.py 的 batch 等），抛异常能正确传递
  - 假如未来 `collect_hardware_info` 又被改回静默模式，`asset.py` 仍能识别
- **替代**：仅在 `asset.py` 校验（不修 `collect_hardware_info`）。**单一防护**够用但 future-proof 不够

### 2. 抛异常类型：`ConnectionError`

- **选择**：`raise ConnectionError(f"SSH 连接失败或命令无输出: {self.host}")`
- **理由**：Python 内置异常，语义清晰；`asset.py` except 块已能捕获（`except Exception`）
- **替代**：自定义异常类。增加代码，over-engineering

### 3. `info` 全空判定

- **选择**：`if not any(info.values()):` （model/serial/firmware/software 全 None/空）
- **理由**：4 个字段都采集不到说明 SSH 一定失败；如果部分成功（仅采集到 model 没 firmware）仍视为有效
- **替代**：只看 model 字段。覆盖不全，命令偶发失败时不能识别

### 4. 已有错误数据修复

- **选择**：不动老数据，由用户在前端"全量刷新"时自动修正
- **理由**：不引入 DB 直连脚本，避免破坏 OpenSpec 流程；前端用户行为可触发
- **替代**：写 SQL 脚本批量修正。增加维护成本

### 5. 操作列宽度：`w-24` → `w-32`

- **选择**：`w-32`（128px），足够容纳 2 个 `btn-soft !text-[11px] !px-2 !py-1` 按钮（约 60-70px / 个 + 1.5 * 0.25rem gap = ~140px 实际占用）
- **理由**：与 Devices.vue 操作列（`w-72`）相比已经克制
- **替代**：
  - 删掉"采集"按钮：违背 cmdb-single-asset-refresh 设计
  - 把按钮放到卡片底部：改 UI 范式，scope 扩大
  - 表格行折叠 hover 显示：增加交互复杂度

## Risks / Trade-offs

- **[风险] `collect_hardware_info` 抛异常后，其他调用方（execute.py）受影响** → **缓解**：搜索 `collect_hardware_info` 当前仅在 `asset.py::refresh_asset` 被调用，零回归
- **[风险] `info` 全空时返回 `success=false`，用户预期是 success=true** → **缓解**：前端 `refreshOne` 已 `if (!r.success) alert(...)`，行为正确
- **[风险] 双层防护导致状态判定逻辑分裂** → **缓解**：双层是 or 关系（任一触发即失败），互斥而非重复
- **[回归] 可达设备 refresh 行为** → **不受影响**：`info` 非空时仍走原路径
- **[回归] 现有 5 个 status 字段** → **不动**

## Migration Plan

- **部署**：纯后端 + 1 行前端 CSS，restart 后端 + vite HMR
- **回退**：git revert 即可
- **数据**：老错误数据（id=7 等）由用户全量刷新自动修正，无须手工 SQL
- **测试**：用 1.1.1.1 不可达设备验证
