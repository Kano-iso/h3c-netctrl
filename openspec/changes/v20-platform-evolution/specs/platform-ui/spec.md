## Capability: platform-ui

前端平台化演进，侧边栏导航 + Dashboard + 视觉升级。

## Goal

将前端从"功能按钮堆砌"演进为"运维平台"体验：侧边栏导航、Dashboard 仪表盘、统一视觉风格。

## Scope

### In Scope
- 侧边栏导航组件（替代顶部 NavBar）
- Dashboard 仪表盘页面（设备概览、最近操作、最近告警）
- 统一配色方案（深色侧边栏 + 浅色内容区）
- 状态指示灯（在线绿/离线灰/告警红）
- 图标辅助（Bootstrap Icons）
- 页面布局统一（标题 + 内容区 + 面包屑）

### Out of Scope
- 暗色主题切换
- 国际化
- 移动端适配
- 自定义仪表盘布局

## API Changes

### 新增端点
| 方法 | 路径 | 说明 |
|------|------|------|
| GET | /api/dashboard | 获取仪表盘数据 |

**响应体：**
```json
{
  "success": true,
  "data": {
    "device_stats": { "total": 5, "online": 3, "offline": 2 },
    "recent_logs": [...],
    "recent_failures": [...]
  }
}
```

## Data Model Changes

无。Dashboard 数据从现有 devices 和 logs 表聚合查询。

## Acceptance Criteria

- [ ] 侧边栏导航展示所有页面入口，当前页高亮
- [ ] Dashboard 展示设备总数/在线/离线统计
- [ ] Dashboard 展示最近 5 条操作日志
- [ ] Dashboard 展示最近 5 条失败操作
- [ ] 统一配色方案，视觉风格一致
- [ ] 设备列表页设备状态有颜色指示
