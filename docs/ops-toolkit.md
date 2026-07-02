# Ops Toolkit 使用手册

> v2.4 运维排错工具包，容器化、开箱即用。
> 启动: `docker compose -f docker-compose.dev.yml --profile ops run --rm ops-toolkit`
> 容器内脚本目录: `/scripts/`，已软链到 `/usr/local/bin/`

## 快速开始

启动容器后，6 个预制脚本可直接调用（脚本名就是命令名）。

### 凭据来源（重要）

3 种方式（按优先级）：
1. `--device <设备名>`：从后端 API 查 IP + 凭据（推荐，需 backend 容器在运行）
2. `--device <IP> --user <user> --pass <pass>`：显式传参
3. 位置参数 `<ip> <user> <pass>`：兼容 v2.3 旧用法
4. IP 模式 + 环境变量：`SSH_USER=admin SSH_PASS=xxx <脚本> <ip>`

环境变量：
- `BACKEND_URL`: 后端 API 地址（默认 `http://backend:8000`）
- `SSH_USER` / `SSH_PASS`: IP 模式的默认凭据
- `OPS_DOCS_PREFIX`: 文档前缀（默认 `/opt/docs`）

## 脚本清单

### check-host
- 用途：主机连通性检查（ping + SSH 22 + NETCONF 830）
- 用法：`check-host --device <name|ip> [count]`
- 示例：`check-host --device Leaf-04` 或 `check-host 192.168.100.5 3`
- 输出：ping 结果 + SSH 22 端口 + NETCONF 830 端口状态

### ssh-test
- 用途：SSH 交互测试（登录 + 执行命令）
- 用法：`ssh-test --device <name|ip> [command]`
- 默认命令：`display version`
- 示例：`ssh-test --device Spine-01 "display interface brief"`

### check-netconf
- 用途：NETCONF 连接测试（ncclient hello + 能力集）
- 用法：`check-netconf --device <name|ip>`
- 示例：`check-netconf --device Leaf-04`

### capture-config
- 用途：SCP 拉取 startup.cfg 到 /captures/
- 用法：`capture-config --device <name|ip>`
- 输出：`/captures/<ip>_<timestamp>_startup.cfg`
- 示例：`capture-config --device Leaf-04`

### reboot-wait
- 用途：触发 reboot + 等待 SSH 恢复（最多 120s）
- 用法：`reboot-wait --device <name|ip>`
- 注意：会触发设备重启，谨慎使用
- 示例：`reboot-wait --device Test-Switch-177`

### audit-switch
- 用途：一键巡检交换机（display version + display device + display interface brief）
- 用法：`audit-switch --device <name|ip>`
- 示例：`audit-switch --device Leaf-04`

## 设备命名约定

设备名对应后端 CMDB 中的 name 字段：
- Spine-01: 192.168.100.100
- Leaf-01: 192.168.100.2
- Leaf-02: 192.168.100.3
- Leaf-03: 192.168.100.4
- Leaf-04: 192.168.100.5
- Leaf-05: 192.168.100.6
- Test-Switch-177: 192.168.100.177

## 常见错误

| 错误 | 原因 | 解决 |
|---|---|---|
| `后端 API 查询失败` | backend 容器未运行 | `docker compose up -d backend` |
| `设备 'XXX' 未找到` | 设备名拼写错误 | 查后端 CMDB 确认名称 |
| `SSH 22 不通` | 设备未开机 / 防火墙 | `check-host` 先 ping |
| `NETCONF 连接失败` | netconf-agent 未启用 | 设备上 `netconf ssh server enable` |
| `permission denied` | 凭据错误 | 用 `--user --pass` 显式传 |

## 关联文档

- [CONTAINER-CLEANUP-SOP.md](CONTAINER-CLEANUP-SOP.md)：容器清理 SOP
- [CONTAINER-DECOUPLING.md](CONTAINER-DECOUPLING.md)：容器拆分蓝图
- [QA-GUIDE.md](QA-GUIDE.md)：QA 测试指南
- [CONTAINER-INVENTORY.md](CONTAINER-INVENTORY.md)：容器基线清单
