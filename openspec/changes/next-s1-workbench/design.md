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

## Real Application-Stack Integration Channel（S1-027）

联调通道与默认 e2e（mock 基线）分离，回答“真实前后端契约是否一致”：

- **单容器栈（S1-028：独立构建 + 运行期硬隔离）**：`qa/Dockerfile.stack-qa` 从**公开固定基础镜像 node:20-alpine** 独立构建（apk 装 python3/venv/系统 chromium，前端依赖走仓库锁文件 `npm ci`，失败即构建失败、无吞错、不依赖本项目预构建镜像）；`qa/docker-compose.stack-qa.yml` 无 env_file、无 docker.sock、`/tmp` 为 tmpfs、仓库与 qa 脚本只读挂载，运行容器 **`network_mode: none`**（构建期联网下载公开依赖，运行期无外部网络，FastAPI/Vite/Chromium 全部经 loopback 通信）。合成 `DB_PATH` / `ENCRYPTION_KEY` / `INTERNAL_API_TOKEN`，绝不读生产 `.env`。
- **真实后端 + 隔离 DB**：`run_stack_qa.sh` 先 seed 合成 EVPN Leaf / tenant / 已部署 VPC / 新鲜验证快照（业务端口可用、predeploy ready），再起 uvicorn（`stack/stack_backend_wrapper.py` 只在进程内替换 `interface.NetconfClient` / `sdn_access.SdnDeploymentExecutor` / `sdn_access.SdnValidationCollector` 为 `stack/stack_fakes.py` 边界 fake，生产入口不加载）。
- **真实前端**：vite dev 以 `VITE_API_MODE=core` + `VITE_API_BACKEND_TARGET=http://127.0.0.1:<port>`（vite.config.js 新增 additive 环境变量，默认不变）代理到真实后端；`playwright.stack.config.js` 只跑 `tests/stack-qa/`，不影响默认 e2e。
- **诚实边界断言**：fake 每次调用写入 `device-io.log`，launcher 事后校验必需事件齐全、netconf 目标必须是 TEST-NET 合成地址；收集器行为由 `collector-mode` 控制文件驱动（fresh / insufficient），支撑“证据不足 → unknown + ambiguous_claims”的诚实状态用例。
- **可清理**：trap EXIT/INT/TERM 统一 kill uvicorn + vite 并删除 `/tmp/stack-qa`；端口被占用时明确失败（退出码 9），绝不触碰 5174 演示环境。

## Compatibility

VPC 创建和 Fabric 管理继续使用既有 API，放入次级工具区。旧数据缺少 operation 时按“历史信息不完整”显示，不补造过程。

## STRATA State Projection（S2-002）

STRATA 读取 S2-001 的只读 `state-projection`，不再用 access-overview 的粗粒度校验灯推测设备状态。首层保留 VPC 业务意图，第二层按 EVPN Leaf 展开；每台 Leaf 同屏呈现目标值、最近设备快照与差异结论，VSI、运行状态、网关接口、L3VNI 和端口绑定均保持独立维度。

`unknown` 表示证据不足，`stale` 表示证据过期，只有有效回读与目标不符才显示 `drifted`；三者使用不同文字和视觉语义。非 EVPN 设备仅显示排除数量，不进入聚合健康度。页面切换和刷新只读取持久化事实，不触发设备采集或配置下发。

## PULSE Operation Impact（S2-009）

PULSE 直接消费 S2-008 持久化操作详情中的 `explanation.impact`，按后端返回顺序呈现 VPC、EVPN Leaf、接入接口和目标终端。关系词仅在后端明确返回对应 relation 时出现；前端不依据节点相邻、名称或当前页面状态补造关系。界面同时固定声明该链路只表达操作记录中的业务影响范围，不是物理拓扑、实时转发路径或因果证明。节点的 `truth_kind` 与 `source` 继续沿用统一 explanation 体系。
