# PRD - H3C NetCtrl V2.0

## 版本记录

|版本|日期|作者|变更说明|
|---|---|---|---|
|V2.0|2026-06-14|个人开发|V2.0 PRD，定义网络运维、接口管理、CMDB、批量操作、前端平台化|

---

## 1. 版本概述

### 1.1 现有能力（V1.0 + V1.1 已完成）

|能力|说明|
|---|---|
|设备管理|多设备 CRUD、连接测试、密码加密存储|
|VLAN 管理|基于 NETCONF 的 VLAN 增删改查，H3C 私有 XML 适配|
|操作日志|自动记录设备操作，筛选分页查询|
|前端框架|Vue 3 + Vite + Vue Router，导航栏 + 3 页面|
|容器化部署|Docker Compose 一键启动，前后端分离|
|NETCONF 交互|ncclient + paramiko，5 种连接错误分类|

### 1.2 V2.0 核心目标

**一句话目标**：从"VLAN 管理工具"升级为"网络运维平台"，新增命令执行、接口管理、CMDB 资产、批量操作能力，前端从功能堆砌演进为平台级体验。

---

## 2. V2.0 功能范围

### 2.1 P0 必做功能

|模块|功能点|说明|
|---|---|---|
|网络运维终端|命令派发式执行|输入命令 → paramiko SSH 执行 → 返回输出展示，非交互式|
|接口管理|接口列表、配置查看、Access/Trunk 联动配置|NETCONF get-config 拉取接口，edit-config 下发配置|
|CMDB|设备资产台账|设备型号、SN、固件版本、位置、业务标签等资产信息管理|
|批量操作|多设备命令/配置批量下发|选择多台设备 → 执行同一命令或下发同一配置 → 汇总结果|
|前端平台化|Dashboard + 侧边栏 + 整体视觉升级|从"功能按钮堆砌"演进为"运维平台"体验|
|工程保障|GitHub Actions 基础 CI|推送代码自动跑测试+构建验证，仅作质量兜底，不做自动部署|

### 2.2 V2.0 明确不做

|不做项|原因|
|---|---|
|配置备份/对比/回滚|复杂度高，留待 V2.1|
|拓扑发现/可视化|需 LLDP 解析 + 图形引擎，工作量过大|
|AI 辅助|远期方向，本版不涉及|
|真正交互式终端（xterm.js）|体验难做到位，命令派发式够用|
|用户认证/权限|个人项目无需|
|EVPN/VXLAN/路由|进阶网络能力，留待后续|
|CI/CD 流水线（镜像仓库/自动部署）|项目体量未到，保持本地构建+手动推送方式|

---

## 3. 详细功能需求

### 3.1 网络运维终端

**交互方式：命令派发式（非交互式终端）**

- 页面提供命令输入框 + 输出展示区
- 用户输入命令（如 `display interface brief`），点击执行
- 后端通过 paramiko SSH 连接设备，执行命令，返回文本输出
- 输出区以等宽字体展示，保留原始格式
- 支持命令历史记录（最近 20 条）
- 每次执行自动记录操作日志

**API 设计：**

```
POST /api/devices/{id}/execute
Body: { "command": "display interface brief" }
Response: { "success": true, "data": { "output": "...", "device_name": "..." } }
```

**前端页面：**
- 左侧设备选择（下拉/列表）
- 右侧上方：命令输入框 + 执行按钮
- 右侧下方：输出展示区（等宽字体，保留格式）
- 底部：命令历史快速重发

### 3.2 接口管理

**接口列表：**
- 通过 NETCONF get-config 拉取设备所有接口信息
- 展示接口名称、状态、模式（Access/Trunk/Hybrid）、允许 VLAN、PVID

**联动配置操作：**

核心场景——Trunk 接口联动配置：
1. 选择接口 → 设置为 Trunk 模式
2. 选择允许通过的 VLAN（多选）
3. 设置默认 VLAN（PVID）
4. 一次性下发完整配置（接口模式 + 允许 VLAN + PVID）

核心场景——Access 接口联动配置：
1. 选择接口 → 设置为 Access 模式
2. 选择所属 VLAN
3. 一次性下发完整配置（接口模式 + Access VLAN）

**API 设计：**

```
GET  /api/devices/{id}/interfaces              # 获取接口列表
PUT  /api/devices/{id}/interfaces/{name}/config # 下发接口配置
Body: { "mode": "trunk", "allowed_vlans": [10,20,30], "pvid": 10 }
或:   { "mode": "access", "access_vlan": 100 }
```

**前端页面：**
- 接口列表表格（名称、状态、模式、VLAN 信息、操作按钮）
- 点击"配置"弹出联动配置弹窗
- 模式切换时动态展示对应配置项

### 3.3 CMDB 资产管理

**资产信息字段：**

|字段|类型|说明|
|---|---|---|
|设备基本信息|自动采集|型号、SN、固件版本、CPU/内存（通过 NETCONF 或 SSH 命令获取）|
|设备位置|手动录入|机房、机架、U位|
|业务标签|手动录入|核心/汇聚/接入、业务域等|
|管理状态|手动维护|在线/离线/维护中/已下线|

**功能：**
- 设备详情页增加"资产信息"标签页
- 支持手动编辑资产信息
- 支持一键刷新设备硬件信息（通过 SSH 命令采集）
- 设备列表页展示关键资产信息列

**API 设计：**

```
GET    /api/devices/{id}/asset          # 获取资产信息
PUT    /api/devices/{id}/asset          # 更新资产信息
POST   /api/devices/{id}/asset/refresh  # 刷新硬件信息
```

**数据库新增 `assets` 表：**

|字段|类型|说明|
|---|---|---|
|id|INTEGER 主键|自增|
|device_id|INTEGER 外键|关联 devices.id|
|model|VARCHAR|设备型号|
|serial_number|VARCHAR|SN 序列号|
|firmware_version|VARCHAR|固件版本|
|cpu_usage|VARCHAR|CPU 使用率|
|memory_usage|VARCHAR|内存使用率|
|location|VARCHAR|物理位置|
|tags|VARCHAR|业务标签（逗号分隔）|
|status|VARCHAR|管理状态（online/offline/maintenance/decommissioned）|
|updated_at|DATETIME|更新时间|

### 3.4 批量操作

**功能：**
- 选择多台设备（勾选）
- 输入一条命令或选择一个配置模板
- 批量执行，汇总展示每台设备的执行结果
- 支持导出执行结果

**API 设计：**

```
POST /api/batch/execute
Body: {
  "device_ids": [1, 2, 3],
  "command": "display version"
}
Response: {
  "success": true,
  "data": {
    "results": [
      { "device_id": 1, "device_name": "SW-1", "success": true, "output": "..." },
      { "device_id": 2, "device_name": "SW-2", "success": true, "output": "..." },
      { "device_id": 3, "device_name": "SW-3", "success": false, "error": "连接超时" }
    ]
  }
}
```

**前端页面：**
- 设备列表页增加多选功能
- 选中后出现"批量操作"按钮
- 弹窗输入命令 → 执行 → 进度条 → 结果汇总表格

### 3.5 前端平台化演进

**当前问题：**
- 页面只有功能按钮，缺乏"平台"感
- 无 Dashboard 总览
- 导航结构简单

**演进方案：**

1. **侧边栏导航**（替代顶部导航）
   - 仪表盘（Dashboard）
   - 设备管理
   - 网络运维
   - 操作日志
   - CMDB 资产

2. **Dashboard 仪表盘**
   - 设备总数 / 在线数 / 离线数
   - 最近操作日志（5 条）
   - 最近告警/失败操作（5 条）

3. **视觉升级**
   - 统一配色方案（深色侧边栏 + 浅色内容区）
   - 卡片式布局
   - 状态指示灯（在线绿/离线灰/告警红）
   - 图标辅助（使用 Bootstrap Icons 或 Material Icons）

---

## 4. 数据库变更

### 4.1 新增表

**assets 表**（见 3.3 节）

### 4.2 迁移方案

- 引入 Alembic 管理数据库迁移
- 提供 upgrade/downgrade 脚本
- V1.1 的 devices 表和 logs 表无需变更

---

## 5. API 变更汇总

### 新增端点

|方法|路径|说明|
|---|---|---|
|POST|/api/devices/{id}/execute|命令派发执行|
|GET|/api/devices/{id}/interfaces|获取接口列表|
|PUT|/api/devices/{id}/interfaces/{name}/config|下发接口配置|
|GET|/api/devices/{id}/asset|获取资产信息|
|PUT|/api/devices/{id}/asset|更新资产信息|
|POST|/api/devices/{id}/asset/refresh|刷新硬件信息|
|POST|/api/batch/execute|批量命令执行|

---

## 6. V2.0 验收标准

1. 网络运维页面可输入命令，执行后正确展示设备返回输出
2. 接口管理页面可查看设备接口列表，可完成 Access/Trunk 联动配置下发
3. CMDB 页面可查看/编辑设备资产信息，可一键刷新硬件信息
4. 批量操作可选择多台设备执行命令，汇总展示结果
5. 前端有侧边栏导航 + Dashboard 仪表盘，具备平台级视觉体验
6. 数据库迁移通过 Alembic 管理，支持 upgrade/downgrade
7. 所有新功能操作自动记录日志
8. 容器化部署正常，一键启动
9. GitHub Actions 基础 CI 配置就绪，推送代码自动验证

---

## 7. 开发优先级建议

|优先级|模块|依赖关系|
|---|---|---|
|P0-1|前端平台化（侧边栏 + Dashboard）|无，基础设施|
|P0-2|网络运维终端（命令派发）|依赖侧边栏导航|
|P0-3|接口管理|依赖 NETCONF 接口 XML 探测|
|P0-4|CMDB 资产管理|依赖 assets 表 + Alembic|
|P0-5|批量操作|依赖命令派发能力|
|P0-6|工程保障（GitHub Actions + Alembic）|无，随时可做|

---

## 8. 风险与待确认项

|风险项|说明|应对|
|---|---|---|
|H3C 接口 NETCONF XML 结构|与 VLAN 类似，H3C 私有结构需实际探测|先 SSH 命令采集，再逐步 NETCONF 化|
|Trunk/Access 联动配置 XML|多条配置需原子下发|用 edit-config 的 batch 操作或分步执行+回滚|
|paramiko 命令执行超时|部分命令输出量大|设置合理超时（30s），支持分页输出|
|Alembic 引入|首次引入迁移框架|从现有表结构生成初始 migration|
