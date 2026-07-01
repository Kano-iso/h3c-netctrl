# v24-bugfix-interface-display-100 Tasks

> **设备**：192.168.100.100（特例）+ 192.168.100.4 / .5（普通生产对照）
> **重要**：每个 [x] 必须真机实测。debug 阶段先确认根因分支再修。

---

## 1. Debug 阶段（关键）

- [ ] 1.1 backend/app/routers/interface.py `get_interfaces` 路由加 debug 日志（NETCONF filter + 原始 XML 大小）
- [ ] 1.2 真机 192.168.100.100 调 `GET /api/devices/{id}/interfaces` → 抓日志
- [ ] 1.3 真机 192.168.100.4 或 .5 调同样 → 抓日志
- [ ] 1.4 对比 XML 大小 / 字段 / 数量
- [ ] 1.5 决定根因分支：
  - **分支 A（filter 不一致）** → 进入 2.1
  - **分支 B（设备配置差异）** → 进入 2.2
  - **分支 C（parse 漏判）** → 进入 2.3
  - 其他 → 重新分析

## 2. 修复阶段（按 debug 结果）

### 2.1 分支 A：filter 不一致
- [ ] 2.1.1 backend/app/netconf_client.py 统一 NETCONF filter（不 filter AdminStatus）
- [ ] 2.1.2 backend/app/routers/interface.py parse 时只过滤无 Name 的接口
- [ ] 2.1.3 单测 `test_interfaces_include_down`（mock down 接口，验证出现在结果）

### 2.2 分支 B：设备配置差异
- [ ] 2.2.1 100.100 抓 `display interface` 输出（SSH 验证设备本身接口）
- [ ] 2.2.2 普通生产抓同样 → 对比接口数量
- [ ] 2.2.3 统一加 NETCONF filter 请求全接口

### 2.3 分支 C：parse 漏判
- [ ] 2.3.1 backend/app/routers/interface.py `_parse_interface_response` 检查是否有 "down 跳过" 逻辑
- [ ] 2.3.2 如有，移除
- [ ] 2.3.3 加单测 `test_parse_interface_response_includes_down`

## 3. 验证

- [ ] 3.1 修完后 100.100 调接口 → 返回所有接口（含 down）
- [ ] 3.2 修完后普通生产调同样 → 返回所有接口（含 down）
- [ ] 3.3 两边数量 + 字段一致
- [ ] 3.4 前端列表展示无差异（down 接口"已连接"状态 = false）
- [ ] 3.5 `pytest backend/tests/ --integration` → 127 passed

## 4. 收尾

- [ ] 4.1 commit `fix(netconf): 统一接口查询 filter / 移除 down 跳过逻辑（v2.4 patch）`
- [ ] 4.2 commit `test: 单测覆盖 down 接口也列出`
- [ ] 4.3 archive 进 `archive/2026-07-XX-v24-bugfix-interface-display-100/`
- [ ] 4.4 进 v2.4 release notes 合并

## 设备最终状态

- 192.168.100.100 / .4 / .5 接口数据无变化（仅展示修复，不动配置）
- 192.168.100.177 不动

## 关联

- [proposal.md](proposal.md)
- 现有 query 路径：[backend/app/routers/interface.py:319-440 `get_interfaces`](file:///root/workpace/h3c-netctrl/backend/app/routers/interface.py#L319-L440)
- v2.4-roadmap：[openspec/changes/v24-roadmap/proposal.md](../v24-roadmap/proposal.md)
