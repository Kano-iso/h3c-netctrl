# Design

## Information Architecture

工作台采用稳定的三段结构：左侧选择业务范围，中间呈现 VPC 与接入关系，右侧解释当前对象；底部记录区承载真实操作过程。窄屏改为顺序堆叠，不依赖缩小浏览器比例。

中间工作区提供三种共享上下文的观察方式，而不是三个互不关联的页面：ATLAS 负责日常业务覆盖与接入入口；PULSE 负责一次操作从意图到设备证据的生命线；STRATA 负责业务、逻辑网络和设备承载的依赖透视。切换时保留当前 VPC，选择操作时自动进入 PULSE。

## Interaction

1. 用户选择已有 VPC。
2. 页面读取 `access-overview`，只展示后端明确返回的绑定、操作、校验和观测。
3. “接入终端”选择 EVPN Leaf、业务接口和目标地址，先调用 `access-preview`。
4. 有 blocker 时停在预览并解释；无 blocker 时由用户确认，调用 `access` 且使用稳定幂等键。
5. 配置完成后进入待接线/待验证；用户显式触发 `complete`。
6. 操作未知时提供 `reconcile`；用户主动撤回时调用 `withdraw`，并明确保留共享 VPC、网关与其他端口。

## State Model

- configuration：执行尝试和逐单元结果。
- validation：主机学习与网关探测结果。
- evidence：采集时间、来源、范围、缺失或过期。
- workflow：预览、执行中、待接线、验证中、已验证、失败、未知、已撤回。

颜色只作辅助，所有状态同时有文字和图标。原始证据按需展开，不把技术字段铺满首屏。

PULSE 优先消费后端 S1-026 的三级 `explanation` 投影：operation 用 intent/scope/safety，unit 用 category/truth_kind/source/scope/observed_at。前端按稳定 code 做 i18n，保留原始字段到技术详情；后端未提供投影时才兼容旧 evidence summary。执行记录、设备观测、系统推断和未决状态使用不同文字，不以相同“成功”覆盖。

## Compatibility

VPC 创建和 Fabric 管理继续使用既有 API，放入次级工具区。旧数据缺少 operation 时按“历史信息不完整”显示，不补造过程。
