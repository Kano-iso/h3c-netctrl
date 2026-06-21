## v20-bugfix-ssh-pagination Tasks

- [x] 1.1 重写 ssh_executor.py：invoke_shell + 分页处理 + ANSI 清理
- [x] 1.2 新增 Alembic migration：assets 表增加 software_package 字段
- [x] 1.3 更新 Asset 模型：增加 software_package 字段，去掉 cpu_usage/memory_usage
- [x] 1.4 更新 Asset API：响应包含 software_package
- [x] 1.5 更新 CMDB 前端页面：展示软件包版本，去掉 CPU/内存列
- [x] 1.6 日志详情展开：前端日志条目可点击查看具体报错
- [x] 1.7 运维终端不阻塞：命令执行超5秒提示可切换页面
- [x] 1.8 自测：运维终端执行命令、CMDB 刷新、接口列表、日志展开
- [ ] 1.9 提交代码并推送
