# auto-collect-scheduler — Spec

> v2.6.1 add-auto-collect

## 背景

v2.6.0 i18n 闭环后用户希望增加"自动采集"机制——data 容器后台 asyncio 任务，每 30 分钟自动遍历所有 device 触发 refresh_asset。

**前置依赖**：
- fix-asset-stale-status：asset 数据 1h 过期自动降级（确保 status 准确性）
- fix-asset-collect-failure：split 模式路由 404 修复
- fix-asset-split-password-decrypt：split 模式密码二次解密修复
- fix-vite-proxy-route：split 模式 vite proxy 路由修复

## 设计

### scheduler 在哪跑

**只 data 容器**（`backend/data_svc/main.py`）：
- asset 业务归 data 容器
- 不在 monolith 跑（避免引入后台任务影响启动时间）
- 不在 ctrl 容器跑（device CRUD 不需要 scheduler）
- 不在 config 容器跑（执行命令按需触发）

### 3 字段配置

```python
AUTO_COLLECT_ENABLED: bool = True          # 总开关（默认开启）
AUTO_COLLECT_INTERVAL_MINUTES: int = 30    # 间隔（最小 5，最大 1440）
AUTO_COLLECT_BATCH_SIZE: int = 3           # 并发（最小 1，最大 7 = H3C max-session）
```

### 失败策略

- 失败跳过 1 轮（本轮失败的 device 不重试，下轮 30min 后自动重试）
- 不重试（避免某台设备持续失败卡住 scheduler）
- log 记录所有失败（i18n key `AUTO_COLLECT_DEVICE_FAIL`）

### 启动失败不阻塞

- scheduler 启动 try/except 包裹
- 失败只记 log，不抛出
- 容器启动仍成功，采集按钮仍可手动触发

## API 影响

- 无（不暴露新 API，纯后台功能）
- 前端无改动

## Capabilities

### Modified Capabilities

- 无（新增功能，不改 spec 语义）

## 影响

- **代码**：见 proposal.md What Changes 节
- **测试**：baseline 302 → 307+ passed（+5 unit）
- **文档**：`docs/AUTO-COLLECT.md` 新建
- **用户体验**：30min 自动采集，仪表盘状态自动保持新鲜

## 非目标

- 不做定时任务可视化
- 不做采集失败告警
- 不做主动告警 email
- 不改 refresh_asset 业务逻辑
- 不重写 ssh_executor

## 验证

### 单元测试（5 case）

1. scheduler start/stop 生命周期
2. 间隔时间正确（mock asyncio.sleep）
3. 失败跳过（mock 1 台失败）
4. 并发限制（batch_size=3）
5. AUTO_COLLECT_ENABLED=False 不启动

### 集成测试（2 case）

1. 真机 .177 自动 refresh 成功
2. 真机 .4 失败后跳过下轮

### qa-backend 全量

- 307+ passed 无回归

### 真机

- data 容器启动 30s 看到 `AUTO_COLLECT_STARTED`
- 1 分钟后看到 `AUTO_COLLECT_CYCLE_DONE`
- .177 status=online + updated_at=now
- .4 status=offline 但 scheduler 不卡住
