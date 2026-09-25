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
- [x] 10.1 S2-002 STRATA 接入 VPC state-projection，只读呈现逐 Leaf 目标态、设备观测与逐维差异
- [x] 10.6 S2-015 STRATA 范围例外闭环：成员级创建/编辑/清除，有意不纳入/维护暂停、必填原因、可选到期；有效/过期/异常状态可见，且不改变覆盖、健康或漂移事实。QA：lint/build、70 unit、47 Playwright 全通过
- [x] 10.16 S2-017 STRATA 可行动关注队列：消费后端 blocking/review/deferred 与稳定 category/action，支持差异下钻、显式刷新证据、范围上下文处理；固定声明不代表根因且不自动修复。QA：lint/build、14 个聚焦组件测试、5 个聚焦 Playwright 通过
- [x] 10.2 对 aligned / drifted / unknown / stale / not_applicable 建立独立文案与视觉语义，非 EVPN 设备明确排除
- [x] 10.3 QA 容器通过 lint、type-check、build、63 个组件测试与 46 个浏览器流程；新增 STRATA 组件和浏览器契约覆盖
- [x] 10.4 STRATA 按 Leaf 提供显式证据刷新；普通查询与视图切换不触发设备采集，用户点击后才强制同步并重新读取投影
- [x] 10.5 STRATA 差异行接入 S2-003 脱敏证据指针；右侧详情展示目标来源、快照、采集命令与时间，技术页保留结构化元数据
- [x] 10.6 STRATA 增加全部 / 一致 / 差异 / 证据不足四类 Leaf 筛选与计数，筛选时保持当前 VPC 上下文
- [x] 10.7 S2-005 将设备证据历史时间线接入 Leaf 卡片：按需加载、明确“历史快照 vs 当前目标”、历史点下钻；显式刷新后自动重载已展开轨迹
- [x] 10.8 S2-005 QA：lint、type-check、build、68 个组件测试与 46 个浏览器流程通过；桌面和 390px 窄屏实图复核无溢出
- [x] 10.9 S2-007 将 S2-006 脱敏操作关联接入 STRATA 证据轨迹：时间点仅标示证据归属，不宣称因果；详情可下钻关联 operation/attempt，并复用 PULSE 操作生命线
- [x] 10.10 S2-009 将 S2-008 多对象影响投影接入 PULSE：按后端已证明关系展示 VPC、Leaf、接口与终端，不在前端推导或补造关系，并明确其不是物理拓扑、实时转发路径或因果链
- [x] 10.11 S2-009 QA：lint、type-check、build、69 个组件测试与 46 个浏览器流程通过；桌面与 390px 窄屏均覆盖影响链且无页面横向溢出
- [x] 10.12 S2-011 将 S2-010 相邻快照转变接入 STRATA：时间线标示变化数量，历史详情按维度展示前后状态与保守语义（发现/解除漂移、获得/丢失证据），并明确不宣称根因或操作因果
- [x] 10.13 S2-011 QA：lint、type-check、build、69 个组件测试与 46 个浏览器流程通过；NEXT 聚焦浏览器流程覆盖转变下钻
- [x] 10.14 S2-013 将 S2-012 VPC EVPN Leaf 范围接入 STRATA：独立展示覆盖分母、逐 Leaf 分类与保守原因；不以名称或健康状态二次推断，并明确范围不等于健康度
- [x] 10.15 S2-013 QA：组件与 NEXT 浏览器流程覆盖 targeted/not_targeted、覆盖汇总与语义边界；lint、type-check、build及全量前端回归通过
- [ ] 9.4 等待用户确认是否进入 OpenSpec 收尾与版本集成

## 11. S2-018（真实应用栈 S2 用户故事验收，未触真机）

- [x] 11.1 seed 扩展：第二台 evpn_leaf（Leaf-Spare，未覆盖）+ 非 EVPN（Access-QA），同一 VPC 覆盖 1/2、非 EVPN 不进 scope 分母
- [x] 11.2 fake 收集器新增 collector-mode=drifted：真实 validation/sync API 落库漂移快照 → confirmed_drift blocking；运行末尾恢复 fresh
- [x] 11.3 stack-qa-s2.spec.js 3 条：STRATA 覆盖/分类/coverage_gap 不当漂移；范围例外 PUT/DELETE 闭环（无记录新增、无设备 I/O、attention 变 deferred/恢复）；漂移 + active 例外不吞掉 blocking 事实；浏览器层固定文案
- [x] 11.4 wrapper 注入点修复：S2 系列把 executor/collector 抽到 services 且 validation/sync 路由在 sdn.py → 按调用点模块全局名补全 sdn_mod 替换（仅 qa 通道文件）
- [x] 11.5 QA README / workbench design/spec/tasks + backend handoff/review-response/manifest 同步
- [x] 11.6 完整 stack QA 连续两次全绿（每次 S1 2 + S2 3 = 5 passed）+ BOUNDARY_OK（device-io.log 25 events 全 fake）+ STACK_QA_OK；qa-backend S2-012/014/016 + 迁移 53 passed；frontend lint/build + 受影响 unit 14 passed；OpenSpec strict（backend/workbench）/ manifest JSON / compose config / git diff --check
