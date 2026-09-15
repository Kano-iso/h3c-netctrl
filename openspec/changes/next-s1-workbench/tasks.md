# Tasks

- [x] 1. 对齐 S1 后端接口与现有页面基线
- [x] 2. 扩展前端 API 客户端的 preview/execute/operation/overview 契约
- [x] 3. 重构 VPC 业务范围、关系工作区和对象详情
- [x] 4. 实现终端接入预览、确认、待接线、验证、对账和撤回流程
- [x] 5. 增加加载、空、错误、未知、部分失败与窄屏状态
- [x] 6. 更新中英文文案和组件测试
- [x] 7. QA 容器执行 lint、type-check、build、vitest
- [x] 8. 浏览器验证桌面与窄屏布局及终端接入主流程
- [x] 8.1 将 ATLAS / PULSE / STRATA 落为共享 VPC 上下文的三种观察方式
- [x] 8.2 在 PULSE 展示操作意图、作用域、逐单元结果与证据，在 STRATA 区分目标、观测和推断
- [x] 8.3 为 5174 隔离预览增加非生产数据提示，并增加三视角浏览器回归
- [x] 8.4 接入 S1-026 真实 explanation 契约，以 i18n 呈现执行记录/设备观测/系统推断/未决状态；技术详情保留原始证据
- [x] 9.1 S1-027 真实应用栈隔离联调：组合镜像 + 隔离 compose + seed/边界 fake/launcher + 独立 Playwright spec
- [x] 9.2 S1-027 契约修复：后端接受前端语义 mode `l2`（schema + plan_port_bind 归一化）并加回归测试
- [x] 9.3 S1-027 在干净环境重复通过真实栈联调；后端/前端基线不回归
- [x] 9.5 S1-028 QA 通道可复现性整改：镜像改 FROM node:20-alpine 公开基座独立构建（前端锁文件 npm ci、失败即构建失败、删除 || true 吞错），compose 运行容器 network_mode: none（构建期联网、运行期无网络、loopback 内联调），文档口径同步
- [ ] 9.4 等待用户确认是否进入 OpenSpec 收尾与版本集成
