# fix-backup-restore-no-response — 范围文档（v2.6.1 诊断 / v2.6.2 实施）

**状态**：🟡 部分完成。v2.6.1 范围仅根因定位文档，修复实施推 v2.6.2 backlog。

## v2.6.1 范围（已完成）

- ✅ 根因定位（proposal.md 详细记录）
  - **根因 A**：H3C V7 S6850（CMW 7.1.070）SFTP/SCP subsystem 默认禁用
  - **根因 B**：`backup_manager.py` `_restore_via_scp` 用 paramiko scp 库对 .5 设备不可用
  - **根因 C**：前端 `BackgroundTaskPanel` 折叠条件让失败任务不可见
- ✅ 用户原始反馈 + 排查过程记录在 proposal.md

## v2.6.2 backlog 实施项

- ⏳ T1 后端：`check_restore_support(device)` 检测函数（probe 1 字节文件推送）
- ⏳ T2 后端：restore_async 端点启动前先 check，不支持直接 422 + 明确错误
- ⏳ T3 后端：`BackupManager._restore_via_scp` 失败时记录更详细的 paramiko 错误
- ⏳ T4 前端：taskStore._pollOnce 失败时弹全局 toast
- ⏳ T5 前端：BackgroundTaskPanel 加"最近失败"高亮
- ⏳ T6 前端：device.status 加 `restore_unsupported` 字段
- ⏳ T7 测试：mock scp.put 抛 Channel closed → 验证后端返回 422 + 前端 toast
- ⏳ T8 真机：.177（支持 scp）+ .5（不支持 scp）双向验证
- ⏳ T9 文档：更新 docs/ops-toolkit.md 说明 .5 / S6850 设备的 SCP 限制

## v2.6.1 砍掉理由

- **任务量**：9 task × 1 commit = 9 commit，超过 v2.6.1 整体的剩余 22 commit 范围
- **风险大**：改动涉及 NETCONF/CLI/SCP 三种协议切换，需要真机 .5 验证（用户场景仅 1 台）
- **依赖**：restore 路径完整替代需要 backup-internal-api 路径再加固（v2.6.1 已有备份下载加固）
- **不阻塞发版**：v2.6.1 砍掉只影响 restore 体验，备份/采集/资产管理全部稳定

## v2.6.2 实施时序建议

1. **T1 + T2 优先**：最小修复 — 不支持就明确告诉用户，避免"无反应"UX 问题
2. **T3 + T4 + T5 跟随**：错误信息可读化 + 失败提示
3. **T6 + T7 + T8 验证**：device.status 暴露 + 测试 + 真机
4. **T9 文档收尾**：ops-toolkit 加 S6850 设备 SCP 限制说明

## 影响范围

- 所有 H3C V7 设备（S6850 / S6860 / S9850 等）
- 备份历史 UI 中所有 unlock 备份的回滚按钮
- 仅 restore_async 端点受影响，备份路径（拉取 + 保存）正常

## 关联

- v2.6.0 同源问题：拉取靠 SSH exec channel 读命令 + 文本抓取，绕开了 SCP；推回是真正上传文件，绕不开
- v2.6.1 backup-data-integrity 已加固备份拉取链路，但 restore 推回是另一个协议问题，需独立修复
- v2.6.2 启动时新建 `fix-backup-restore-support` change 走完整 Propose + Apply + Archive
