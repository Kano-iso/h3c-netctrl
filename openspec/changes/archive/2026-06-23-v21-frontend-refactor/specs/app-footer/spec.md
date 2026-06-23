# Capability: app-footer

## Goal

在所有 view 底部展示官网式 Footer，包含品牌介绍、四列链接（产品 / 资源 / 关于）、社交图标、版权与版本信息，强化"产品化"平台感。

## Scope

### In Scope
- 全局 Footer 组件 `AppFooter.vue`
- 4 列布局：
  - **第 1 列**：Logo + 项目简介 + 3 个社交图标（GitHub / 文档 / 邮件）
  - **第 2 列**：产品（设备 / 运维终端 / 接口 / 批量 / CMDB）
  - **第 3 列**：资源（操作日志 / 备份回滚 / 拓扑 / 技术文档 / Changelog）
  - **第 4 列**：关于（项目简介 / 技术栈 / 开发规范 / License / 联系作者）
- 底部版权行：版权信息 + 绿点 v2.0.0 + Built with...
- 风格：米白底（canvas-50）+ 1px 上边线 + 适度留白
- 在所有 view 都显示

### Out of Scope
- 多语言 Footer
- Newsletter 订阅
- 服务状态指示
- 法律页面（隐私 / 服务条款）

## API Changes

无后端 API 变更。

## Implementation

### 文件改动
- 新增 `src/components/AppFooter.vue`
- 修改 `src/App.vue`：在 `<RouterView />` 后挂载 `<AppFooter />`

### 验收标准
- 任何 view 滚动到底部都能看到 Footer
- Footer 风格与整体一致（米白底 + 圆角 chip 社交按钮）
- 4 列在响应式断点下正确折叠（2 列 → 1 列）
- 社交图标 hover 有反馈
- 链接 hover 变 accent 色
- 版权行 v2.0.0 + Built with 文字正确
- build 通过
