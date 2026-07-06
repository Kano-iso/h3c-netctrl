# fix-backup-restore-no-response — Proposal

## Why

备份回滚（restore）端点无响应：用户在 .5 设备上尝试回滚到旧配置（locked backup）时，前端点击"回滚"按钮无任何反应。

**问题表现**：
- .5 设备有 2 份 locked backup（一份旧配置内容多、一份现网配置内容少）
- 用户在备份历史里选旧配置 → 点"回滚"
- 前端无 loading / 成功 / 失败提示
- 检查网络面板：可能是请求未发出 / 请求未收到 / 收到但 UI 未更新

**根因（待验证）**：
- 候选 1：前端 restore 按钮 disabled 条件错（看错了字段）
- 候选 2：后端 restore 端点拒绝 locked backup 静默（无明确错误响应）
- 候选 3：restore_async 任务调度失败但 UI 无显示
- 候选 4：前端调用错 endpoint（如把 backup_id 拼错）

## What Changes

- **待定**（需先 Propose 阶段做根因定位 + 真机重现）

## 报告（用户原始反馈）

> .5 我有两份配置，都上锁了，这两份配置，有不同，我现网配置是最新的这个，但是我的旧配置比现网配置要多，我尝试把旧配置回滚，在前端点回滚，发现并没有任何反应。
> 回滚操作，我离虽然我知道 qa 不应该做回滚操作的这个内容，因为它太大了，但是现在确实有问题，我来指指出来这个问题了。

## 行动

1. 启动 Propose 阶段，先用 MCP 浏览器在 .5 设备上重现：
   - 打开备份历史列表
   - 选旧配置点"回滚"
   - 看 console / network 请求 / 响应
2. 看后端 restore endpoint（`POST /api/devices/{id}/backup/{bid}/restore` 和 restore-async）有没有错误日志
3. 用 ops-toolkit paramiko-batch-exec 验证设备可达性 + restore 业务逻辑独立跑通
4. 根因确定后细化 tasks.md

## 状态

- ⏳ 草稿（v2.6.1 backlog）
- 待 Apply：v2.6.1 push 后启动，先 Propose 根因定位
