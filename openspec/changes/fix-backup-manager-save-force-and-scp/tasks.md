## 1. 后端依赖

- [x] 1.1 `backend/requirements.txt` 加 `scp>=0.14.0`
- [x] 1.2 重新 build backend 镜像（如需要）
- [x] 1.3 验证 `import scp` 在容器内可用

## 2. backup_manager.py 修改

- [x] 2.1 替换 `import`：`from scp import SCPClient`
- [x] 2.2 新增 `_force_save_via_ssh_shell()`：invoke_shell + 发 `save force` + 检测 "Y/N" + 发 `Y` + 等待 "successfully" 或 5s 超时
- [x] 2.3 修改 `_force_save_on_device` 调用新方法
- [x] 2.4 修改 `pull_file`：`open_sftp` → `SCPClient(client.get_transport()).get(...)`
- [x] 2.5 增加 `logger.info` 业务日志（备份开始 / 成功 / 失败）
- [x] 2.6 错误处理：保存失败 / SCP 失败 → 抛 BackupError 带详细中文
- [x] 2.7 `_restore_via_ssh` 改 SCP（保持一致性）

## 3. 容器测试

- [ ] 3.1 重建 backend 容器
- [ ] 3.2 验证容器内 `python -c "from scp import SCPClient; print('ok')"`

## 4. 真机验证（192.168.100.4 Leaf-03）

- [ ] 4.1 `_force_save_via_ssh_shell` 在真机上 < 5s 完成（DEBUG 日志看）
- [ ] 4.2 `POST /api/devices/4/backup` < 30s 完成
- [ ] 4.3 `/data/backups/4/` 落盘 startup.cfg + running.cfg（ls 看）
- [ ] 4.4 `cat /data/backups/4/*startup.cfg` 内容可读
- [ ] 4.5 `GET /api/devices/4/backup` 返回 2 条
- [ ] 4.6 锁定 / 解锁 OK
- [ ] 4.7 删除非锁定 OK（锁定拒绝）
- [ ] 4.8 触发 6 次非锁定备份 → 只留 5 份（轮转验证）
- [ ] 4.9 `POST /api/backups` < 60s 完成（6 台串行）
- [ ] 4.10 设备端 `display startup` 状态正确

## 5. 收尾

- [ ] 5.1 commit 代码（按子模块分批）
- [ ] 5.2 archive change
- [ ] 5.3 更新 `v21x-patch-backup-backend` 的 spec 追加修订（本 change 是它的补丁）
- [ ] 5.4 archive `backup-frontend`（依赖已满足）

## 6. 文档

- [ ] 6.1 `openspec/specs/fix-backup-manager-save-force-and-scp/spec.md` 规范化
- [ ] 6.2 `VERSION-ROADMAP.md` v2.2 状态推进 (3/3 完成)
