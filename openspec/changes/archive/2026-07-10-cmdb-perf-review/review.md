# localhost:5173 CMDB 页面首屏缓慢排查与修复记录

日期：2026-07-10  
范围：开发环境 `http://localhost:5173/#/cmdb` 及依赖的设备列表接口  
状态：已定位根因，已完成最小修复，已做本地验证

## 1. 问题描述

用户反馈：

- Chrome 访问 `http://localhost:5173/#/cmdb` 及其子页面时首屏明显缓慢
- 现象不仅出现在 Chrome，Firefox、虚拟机宿主机访问同一地址也慢
- 页面最终可以打开，但通常要等待约 5-10 秒
- 初步怀疑是代理导致本地 `localhost` 没有绕过代理

## 2. 排查目标

本次排查重点分两层：

1. 先确认慢点是否发生在浏览器到 `localhost:5173` 这一跳
2. 再确认是否是 Vite/dev-server 之后的 API 链路拖慢页面

## 3. 排查过程与证据

### 3.1 本机代理环境

宿主机环境变量存在全局代理：

```bash
HTTP_PROXY=http://127.0.0.1:6678
HTTPS_PROXY=http://127.0.0.1:6678
http_proxy=http://127.0.0.1:6678
https_proxy=http://127.0.0.1:6678
```

同时未发现 `NO_PROXY/no_proxy` 配置。

说明：

- 这是一个次级风险，意味着部分命令行工具可能不会自动绕过本地地址
- 但它不是这次 5-10 秒延迟的主根因，因为后续直连后端端口的测试也复现了相同慢点

### 3.2 5173 端口实际服务情况

`5173` 由 Docker 暴露，前端服务为 `h3c-netctrl-frontend` 容器内的 Vite dev server。

关键链路：

- 宿主机 `localhost:5173`
- Docker 端口转发
- Vite dev server
- `/api/*` 再由 `frontend/vite.config.js` 内的自定义 proxy 转发到 `ctrl/config/data` 容器

### 3.3 直接测接口时延

对关键接口做了直连测试，结果如下：

```text
GET /api/dashboard  -> ~24ms
GET /api/devices    -> ~9.6s
```

说明：

- 慢点不在页面静态资源本身
- 慢点集中在 `GET /api/devices`
- CMDB / 设备相关页面首屏慢，本质上是被设备列表接口拖住

### 3.4 根因定位到后端设备列表逻辑

代码位置：

- [backend/app/routers/device.py](/root/workpace/h3c-netctrl/backend/app/routers/device.py)
- [backend/app/utils/backup_manager.py](/root/workpace/h3c-netctrl/backend/app/utils/backup_manager.py)

排查发现 `GET /api/devices` 原实现中，对每一台设备都会执行：

`_get_restore_support_cached(device)`

而该函数内部会调用：

`BackupManager.check_restore_support()`

这个探测会：

1. SSH 连接设备
2. 尝试走 SCP 推一个 dummy 文件
3. 再做清理

这意味着“设备列表接口”在返回列表前，会对所有设备做串行 SSH/SCP 探测。

### 3.5 实测设备探测耗时

当前库内共有 8 台设备。逐台探测耗时实测如下：

```text
192.168.100.100  ~1.08s
192.168.100.2    ~1.07s
192.168.100.3    ~1.08s
192.168.100.4    ~1.08s
192.168.100.5    ~0.07s
192.168.100.6    ~1.11s
192.168.100.177  ~1.07s
192.168.100.99   ~3.11s
```

总耗时约 9.6 秒，与 `GET /api/devices` 的实测总耗时一致。

结论：

- 页面慢不是浏览器问题
- 页面慢不是 Vite 本身问题
- 页面慢不是本地回环网络问题
- 页面慢的主因是：设备列表接口把“协议能力探测”塞到了首屏同步路径里

## 4. 为什么“关代理后还是慢”

因为主耗时不在浏览器访问 `localhost` 这一跳，而在后端主动去连设备这一跳。

即使浏览器完全绕过代理，只要 `GET /api/devices` 继续逐台 SSH/SCP 探测，页面仍然会慢。

所以这次问题里：

- 代理配置问题：存在，但不是主根因
- 后端列表接口同步探测：是主根因

## 5. 修复方案

修复原则：做最小变更，只消除首屏阻塞，不改备份/回滚主流程。

已修改：

- `GET /api/devices` 默认不再执行 `restore_support` 探测
- 仅当显式传 `include_restore_support=true` 时，才填充 `restore_unsupported`
- 详情接口 `GET /api/devices/{id}` 保持原行为不变

代码变更位置：

- [backend/app/routers/device.py](/root/workpace/h3c-netctrl/backend/app/routers/device.py)

回归测试新增：

- [backend/tests/test_smoke.py](/root/workpace/h3c-netctrl/backend/tests/test_smoke.py)

新增测试覆盖：

- 默认列表接口不触发 `_get_restore_support_cached`
- 显式 `include_restore_support=true` 时仍可触发探测

## 6. 修复后验证结果

修复后重新测时延：

```text
GET http://127.0.0.1:8001/api/devices   -> 4ms ~ 34ms
GET http://127.0.0.1:5173/api/devices   -> ~6ms
```

结论：

- 列表接口从 9.6 秒下降到毫秒级
- `5173` 入口链路也恢复到毫秒级
- 本次首屏性能问题已被直接修复

## 7. 风险评估

这是一个低风险修复，原因如下：

- 只影响设备列表接口
- 不影响单设备详情接口
- 不影响备份、回滚、资产采集、NETCONF/SSH 主流程
- 前端当前并未消费 `restore_unsupported` 字段，因此默认返回 `null` 不会造成功能倒退

需要注意：

- 如果后续前端确实要在“设备列表页”直接展示回滚能力，建议改成异步懒加载，或单独能力接口，不能再放回同步列表接口里

## 8. 对线上发布的建议

建议开发团队在线上发布前同步做以下检查：

1. 确认线上前端是否依赖设备列表中的 `restore_unsupported`
2. 若依赖，改为单设备详情懒加载或单独批量能力接口
3. 保留本次默认不探测的行为，避免线上设备数增加后再次出现 N 秒级首屏

## 9. 次级建议：代理绕过本地地址

虽然这次不是主根因，但仍建议补齐本地绕过配置，降低后续排查噪音。

责任边界说明：

- 开发团队关注应用程序本身的接口时延、首屏加载路径、是否把高成本探测放进同步请求
- 代理策略、本地回环地址绕过、宿主机/虚拟机网络路径、系统级浏览器代理策略，应由运维团队或网络运维团队额外支撑
- 因此本节内容属于环境治理建议，不应作为开发团队处理本次应用性能问题的前置条件

建议至少加入：

```bash
NO_PROXY=localhost,127.0.0.1,::1
no_proxy=localhost,127.0.0.1,::1
```

如果浏览器代理由系统统一接管，也应在系统代理或代理工具中加入本地绕过规则。

## 10. 结论

本次 `localhost:5173/#/cmdb` 页面缓慢问题，根因不是浏览器访问本地地址慢，也不是代理本身直接拖慢了前端静态资源，而是后端 `GET /api/devices` 在首屏路径中串行执行了 8 台设备的 SSH/SCP 能力探测，累计造成约 9.6 秒延迟。

本次已通过最小改动将探测移出默认列表路径，实测把接口时延从秒级降回毫秒级，可作为开发团队归档和上线前评审依据。
