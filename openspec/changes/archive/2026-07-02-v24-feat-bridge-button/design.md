# v24-feat-bridge-button Design

## Context

v2.3 的 `PATCH /devices/{id}/interfaces/{if_index}/link-mode` 后端**双向支持** `mode=bridge|route`：

```python
# backend/app/routers/interface.py:1143
@router.patch("/devices/{device_id}/interfaces/{if_index}/link-mode")
def switch_link_mode(device_id, if_index, body: LinkModeSwitch):
    # body.mode: "bridge" | "route" — 两个方向都走同一条 SSH CLI 路径
    commands = ["system-view", f"interface {name}", f"port link-mode {body.mode}"]
```

护栏也双向生效：
- `L3_NAME_PATTERN`（LoopBack/Vsi/Vlan）→ 拒（reason_code=L3_INTERFACE）
- `protected` → 拒（需 force=true）
- `port_layer` 查不到 → NETCONF 查 name 失败 → 拒

但前端 `Interfaces.vue` 只做了单向（L2→route），`requestSwitchLinkMode` 硬编码 `targetMode = 'route'`：

```javascript
// 修前（v24-bugfix-ui-feedback-and-loopback 4.2b 状态）
async function requestSwitchLinkMode(iface) {
  const targetMode = 'route'  // 硬编码，永远是"改三层"
  ...
}
```

按钮 v-if 也只对 L2 显示：
```vue
<button v-if="i.layer !== 'L3'" @click="requestSwitchLinkMode(i)">改三层</button>
```

L3 物理口（被切到 route 的 GE/TE）既没有"改二层"按钮，也没有"改三层"按钮（layer=L3 挡住了"改三层"），只有"改 IP"。**回退无门**。

## Goals / Non-Goals

**Goals:**
- L3 物理口（GE/TE 等被切到 route）显示"改二层"按钮，点击切回 bridge
- L3 虚接口（LoopBack/Vsi/Vlan）不显示"改二层"按钮（后端会拒，前端 UX 优化）
- "改三层"按钮现有行为不变

**Non-Goals:**
- 不改后端
- 不改 SSH Executor
- 不改护栏

## Decisions

### 决策 1：前端如何区分"L3 物理口" vs "L3 虚接口"

**选 A**：前端加 `isL3VirtualInterface(name)` 函数，用 name 判断
```javascript
function isL3VirtualInterface(name) {
  const n = (name || '').toLowerCase()
  return ['loopback', 'vsi', 'vlan-interface'].some(kw => n.includes(kw))
}
```
- ✅ 与后端 `L3_NAME_WEAK_PATTERNS` 弱匹配一致（v24-bugfix-ui-feedback-and-loopback 已落地）
- ✅ 改动最小（1 个函数 + v-if 条件）
- ✅ 后端护栏兜底（即使前端误判，后端 L3_NAME_PATTERN 也会拒）

**否决 B**：后端返回 `link_mode_switchable: bool` 字段
- ❌ 要改后端 schema + get_interfaces 返回结构，改动放大
- ❌ 前端复制正则成本低，后端护栏兜底足够安全

**否决 C**：前端复制 `_looks_like_physical_port` 正则
- ❌ 物理口正则更长（GE/TE/Eth/聚合...），维护成本高
- ❌ 反向判断（不是虚接口 = 可切）更简单

### 决策 2：requestSwitchLinkMode 改造方式

**选 A**：加 `targetMode` 参数
```javascript
async function requestSwitchLinkMode(iface, targetMode = 'route') {
  // targetMode: 'route'（改三层）| 'bridge'（改二层）
  ...
}
```
- ✅ 一个函数服务两个方向，DRY
- ✅ 二次确认弹窗文案用 targetMode 动态生成

**否决 B**：新开 `requestSwitchToBridge` 函数
- ❌ 重复代码（force=false 预检 + ConfirmModal + force=true 执行逻辑一样）

### 决策 3：按钮显示条件

```vue
<!-- L2 物理口：改三层（现有） -->
<button v-if="i.layer !== 'L3'" @click="requestSwitchLinkMode(i, 'route')">改三层</button>

<!-- L3 物理口：改二层（新增） -->
<button
  v-if="i.layer === 'L3' && !isL3VirtualInterface(i.name)"
  @click="requestSwitchLinkMode(i, 'bridge')"
>改二层</button>

<!-- L3 接口：改 IP（现有） -->
<button v-if="i.layer === 'L3'" @click="openIpModal(i)">改 IP</button>
```

- L3 物理口：显示"改二层" + "改 IP"两个按钮
- L3 虚接口：只显示"改 IP"（isL3VirtualInterface 拦"改二层"）
- L2 物理口：只显示"改三层"

## 实施细节

### 改 1：isL3VirtualInterface 函数

```javascript
// frontend/src/views/Interfaces.vue <script setup>
// v24-feat-bridge-button: 判断是否天生 L3 虚接口（LoopBack/Vsi/Vlan）
// 与后端 L3_NAME_WEAK_PATTERNS 一致，后端护栏兜底
function isL3VirtualInterface(name) {
  const n = (name || '').toLowerCase()
  return ['loopback', 'vsi', 'vlan-interface'].some(kw => n.includes(kw))
}
```

### 改 2：requestSwitchLinkMode 加 targetMode 参数

```javascript
// 修前
async function requestSwitchLinkMode(iface) {
  const targetMode = 'route'  // 硬编码
  ...
}

// 修后
async function requestSwitchLinkMode(iface, targetMode = 'route') {
  // targetMode: 'route'（改三层）| 'bridge'（改二层）
  ...
}
```

函数体内 `targetMode` 已用于 API 调用，无需改其他地方。

### 改 3：按钮 v-if

```vue
<button
  v-if="i.layer !== 'L3'"
  @click="requestSwitchLinkMode(i, 'route')"
>改三层</button>

<button
  v-if="i.layer === 'L3' && !isL3VirtualInterface(i.name)"
  @click="requestSwitchLinkMode(i, 'bridge')"
>改二层</button>
```

### 改 4：二次确认弹窗文案

```javascript
// linkModeChange.value.message 动态生成
const targetLayerText = targetMode === 'route' ? '三层（route）' : '二层（bridge）'
message: data.message || `切换接口 ${iface.name} 到 ${targetLayerText} 模式`
```

## Risks / Trade-offs

**[Risk] 前端正则与后端漂移**：后端加新 L3 虚接口类型时前端不知道
→ Mitigation：后端护栏兜底（L3_NAME_PATTERN 拒），前端误判只影响 UX（多显示一个按钮），点了后端拒 + reason_code 弹窗

**[Risk] H3C V7 切 link-mode 清 L2 配置**：route→bridge 时 H3C V7 会清 IP 配置
→ Mitigation：二次确认弹窗已含 H3C V7 行为警告（v24-bugfix 已加），用户确认才执行

**[Risk] 端口被切到 route 后无 IP 无 L2 配置**：切回 bridge 后是"裸口"
→ Mitigation：现有行为（v2.3 已知），用户需重新配 access vlan。弹窗文案已说明

## Migration Plan

- 无数据库 migration
- 无后端改动
- 前端纯增量（新按钮 + 函数参数化），不影响现有"改三层"流程

## Open Questions

无。后端 API 已双向支持，前端补按钮是明确需求。

## 关联

- [proposal.md](proposal.md)
- 后端 link-mode 路由：[backend/app/routers/interface.py:1143](../../backend/app/routers/interface.py)
- 前端待改：[frontend/src/views/Interfaces.vue:263-322](../../frontend/src/views/Interfaces.vue)
