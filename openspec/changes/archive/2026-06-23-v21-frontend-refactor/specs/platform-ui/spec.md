## Delta: platform-ui (V2.1 modification)

V2.0 阶段的 platform-ui 引入左侧侧边栏 + Dashboard 仪表盘。V2.1 进一步升级视觉表达与导航结构。

## 变更

### Removed
- 左侧深色侧边栏（v2.0 引入）
- 顶栏 + 侧边栏双导航并存模式

### Added
- sticky 顶部 nav（替代侧边栏）
- 三组 mega menu 下拉（运维操作 / 运营管理 / 排查诊断）
- 米白色视觉系统（替代黑底侧边栏 + 浅色内容区）
- 大圆角 + 多层阴影（替代直角 + 平面）
- 苹方优先字体栈 + 数字精致化
- 背景"晨雾"光晕
- 官网式 Footer

### Modified
- 配色：黑/灰对比 → 米白/蓝/灰渐进
- 导航层级：平铺 5 tab → 总览 + 3 大分类下拉
- 视觉密度：紧凑工具风 → 轻盈平台风

## Impact

- App.vue 完全重构
- 10 个 view 视觉适配
- 引入 AppFooter 组件
- 删除 v2.0 侧边栏组件
- 视觉系统 css 重写

## Acceptance Criteria

- [ ] 顶部 nav 在所有 view 顶部 sticky
- [ ] 三个下拉分组可展开，icon + 标题 + 描述齐全
- [ ] 当前路由对应分组高亮
- [ ] 米白底 + 3 段柔光晕（不是纯白）
- [ ] 所有 panel 有圆角 + 三层阴影
- [ ] 所有 view 滚动到底部显示 Footer
- [ ] Dashboard 4 个 KPI 卡片渐变数字（KPI 数字有渐变 + 紧凑字距）
- [ ] 旧的左侧侧边栏彻底删除（不残留）
- [ ] build 通过
