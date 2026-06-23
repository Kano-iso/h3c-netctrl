# Capability: top-nav

## Goal

替换 V2.0 左侧侧边栏为 sticky 顶部导航栏，按"运维操作 / 运营管理 / 排查诊断"三大分类做 mega menu 下拉，提供现代、轻盈的平台感。

## Scope

### In Scope
- 顶部 sticky nav：52px 高，backdrop-blur-2xl 半透明背景，下边线分隔
- Logo 区：H3C NetCtrl 品牌方块渐变 + 文字
- 总览 tab（独立）
- 三大分类下拉：
  - **运维操作**（设备 / 运维终端 / 接口 / 批量）
  - **运营管理**（CMDB / 备份回滚）
  - **排查诊断**（操作日志 / 拓扑视图 / AI 助手）
- Mega menu 面板：360px 宽，hover/click 展开，icon + 标题 + 描述三段式
- 未来功能打 `未来` 灰色小 tag
- 当前路由对应 tab/分组高亮
- 右侧工具区：搜索 + 通知 + 头像
- 点击外部 / ESC 关闭下拉
- 移动端：保持简单（暂不做适配，PC 优先）

### Out of Scope
- 暗色 / 浅色主题切换
- 多级嵌套下拉（最多二级）
- 键盘导航
- 国际化
- 移动端汉堡菜单

## API Changes

无后端 API 变更。

## Implementation

### 文件改动
- `src/App.vue`：重构为顶部 nav 框架
- `src/router/index.js`（如有）：确保 10 个 view 路由名称稳定
- `src/components/PageHeader.vue`：适配新视觉

### 数据结构

```javascript
const groups = [
  { key: 'ops', label: '运维操作', desc: '直接对设备下发配置', items: [...] },
  { key: 'ops-mgmt', label: '运营管理', desc: '资产盘点 · 配置存档', items: [...] },
  { key: 'debug', label: '排查诊断', desc: '日志 · 拓扑 · AI 辅助', items: [...] }
]
```

### 验收标准
- 顶部 nav sticky，滚动时固定在视口顶部
- 三个下拉 hover 展开，icon + 标题 + 描述清晰
- 当前路由对应分组高亮
- 点击下拉 item 跳转 + 关闭下拉
- 点击外部 / ESC 关闭
- 全部 10 个 view 路由可达
- build 通过
