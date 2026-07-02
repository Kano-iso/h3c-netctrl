# v24-bugfix-ui-feedback-and-loopback Design

## Context

v2.3.1 修了 `_check_l3_interface` 错判 L2 + `_enrich_interface_names` 补查真实 name。但用户实测发现 3 个残留 bug：
1. UI 改层级 / 配 IP / 备份后，日志显示"执行成功"但页面没同步（用户怀疑后端根本没下发）
2. LoopBack0 仍显示 L2（v2.3.1 修过但漏了一条 path）
3. 改层级按钮对 Loopback / Vlan-interface 默不作声，无明确提示

## 根因（已定位）

### Bug 3 根因（`interface.py:228-255 _detect_layer`）
```python
L3_NAME_PATTERN = re.compile(r"^(Vlan-interface|LoopBack|Vsi-interface)\d+", re.IGNORECASE)
```

匹配 `LoopBack0` ✓，但 H3C V7 Ifmgr 兜底成 Description `Loopback_VTEP_ID` 时**不匹配**（小写 loopback + 下划线）。
- 已有 `_enrich_interface_names` 补查真实 name（line 1002 调用），但**只在 `_check_l3_interface`（IPv4 配置路径）调用**
- `get_interfaces` 路由（line 434 调用）也有，但**只走**这条路径
- **关键**：补查成功后传给 `_detect_layer` 的 `name` 字段应该是真 name（`LoopBack0`），但实测 Ifmgr 兜底时 `port_layer` 仍是 None，`name` 已被替换成补查的 `LoopBack0`，那应该能匹配……

**重新审视**：如果 `_enrich_interface_names` 补查成功，name 应是 `LoopBack0` → L3_NAME_PATTERN 匹配 → 判 L3 ✓
但用户实测仍是 L2 → 说明**补查失败了**（`get_interface_name_by_index` 对某些接口返回 None）→ name 仍是 `Loopback_VTEP_ID` → 不匹配 → 判 L2

**真正的 fix**：扩 `_detect_layer` 加 Description 弱匹配兜底。

## Goals / Non-Goals

**Goals:**
- 区分"真下发" vs "护栏拒"日志
- Loopback / Vsi / Vlan 在 description 兜底时仍判 L3
- link-mode 按钮对 L3 接口直接不渲染（不是禁用）
- 护栏拒返回结构化 `reason_code`

**Non-Goals:**
- 不重写 link-mode 业务逻辑
- 不动 NETCONF 协议层
- 不改前端 store 架构（这是 v24-feat-async-backup-status 的事）

## Decisions

### 决策 1：日志区分"真下发" vs "护栏拒"
**选 A**：OperationLog 加 `result` 字段（success / failed / guard_rejected）
- ✅ 用户看日志能区分
- ✅ 数据库 schema 兼容（默认值 success）
- ❌ 加 migration

**否决 B**：另开 GuardRejectionLog 表
- 表多，JOIN 复杂

### 决策 2：Loopback 弱匹配规则
**选 A**：name 包含 `loopback` / `vsi` / `vlan-interface` 关键字（不要求紧跟数字）→ L3
```python
# 在 _detect_layer 加：
if any(kw in name.lower() for kw in ("loopback", "vsi", "vlan-interface")):
    return "L3"
```
- ✅ 兼容 `Loopback_VTEP_ID` / `VSI_TUNNEL` / `Vlan_interface10` 各种兜底
- ❌ 弱匹配可能误判（如 description 含 "loopback" 但实际是物理口）

**辅助规则**：必须 `port_layer` 缺省 / 是 None 时才走弱匹配
```python
if port_layer is None and any(kw in name.lower() for kw in ("loopback", "vsi", "vlan-interface")):
    return "L3"
```

### 决策 3：link-mode 改层级按钮不显示还是禁用
**选 A**：Loopback / Vsi / Vlan-interface 直接不渲染 "改层级" 按钮
- ✅ 用户看不到按钮就不会点
- ✅ 避免误点后默不作声
- ❌ 物理口和逻辑口区分需要前端知道 layer

**配合**：前端拿到 interfaces 数据时按 `iface.layer` 过滤——L2 才显示按钮

**否决 B**：禁用按钮 + tooltip
- 用户原话："你就干脆就不让它有这个选项"
- 禁用后用户仍可能疑惑"为什么不能改"

## 实施细节

### 修 1：OperationLog.result 字段
```python
# backend/app/models.py OperationLog 加 result 列
result = Column(String, default="success")  # success | failed | guard_rejected

# 护栏拒时
record_log(db, device.id, device.name, "interface_config", 
           details=json.dumps(...), result="guard_rejected")
```

### 修 2：`_detect_layer` 弱匹配
```python
# backend/app/routers/interface.py:228-255
def _detect_layer(iface, ip_addresses, vpn_instance):
    port_layer = iface.get("port_layer")
    if port_layer == 2: return "L3"
    if port_layer == 1: return "L2"
    
    if ip_addresses: return "L3"
    if vpn_instance: return "L3"
    
    name = iface.get("name", "") or ""
    if L3_NAME_PATTERN.match(name): return "L3"
    if SUB_IF_PATTERN.match(name): return "L3"
    
    # v2.4 修复：description 兜底弱匹配（name 含 loopback/vsi/vlan-interface 关键字）
    if port_layer is None:
        name_lower = name.lower()
        if any(kw in name_lower for kw in ("loopback", "vsi", "vlan-interface")):
            return "L3"
    
    return "L2"
```

### 修 3：link-mode reason_code
```python
# backend/app/routers/interface.py link-mode 路由
REASON_CODES = {
    "L3_INTERFACE": "该接口默认是三层接口（如 Loopback / Vsi / Vlan-interface），不支持改层级",
    "PHYSICAL_ONLY": "该接口不是物理接口",
    "IFACE_NOT_FOUND": "接口不存在",
    "MGMT_PROTECTED": "管理口受保护，不允许改层级",
    "DEVICE_OFFLINE": "设备离线",
}

if not is_physical:
    return APIResponse(
        success=False,
        error=reason_text,
        reason_code=reason_code,
        suggested_action="在 L3 配置 IP" if reason_code == "L3_INTERFACE" else None,
    )
```

### 修 4：前端按钮渲染
```vue
<!-- frontend/src/views/Interfaces.vue 模板 -->
<el-button
  v-if="iface.layer === 'L2'"
  @click="openLinkModeModal(iface)"
>改层级</el-button>
```

## Risks / Trade-offs

**[Risk] 弱匹配误判**：description 含 "loopback" 字符串的物理口被误判 L3 → Mitigation
- 物理口 description 不会含 loopback / vsi / vlan-interface
- 加单测：物理口（如 GigabitEthernet0/0/1）description="Uplink to Spine" → 仍判 L2 ✓

**[Risk] 前端按钮不渲染 = 用户不知道有这个功能** → Mitigation
- 在接口列表顶部加说明："L3 接口不可改层级，直接在 L3 配置 IP"
- 鼠标悬停时显示 tooltip

**[Risk] OperationLog.result migration 老数据** → Mitigation
- 默认值 "success"，老记录无影响
- 历史日志查询兼容

## Migration Plan

- 数据库 migration：加 `result` 列，默认 "success"
- 前端无 migration（v-if 兼容旧数据）
- 不破坏 v2.3.1 archive 8 change

## Open Questions

1. **OperationLog.result 是否需要枚举约束？** 数据库层 String 还是 Enum？—— 选 String（扩展灵活）
2. **前端是否需要"操作历史"页签？** 用户能否在设备详情看"过去 24h 改层级记录"？—— 暂不做，归 follow-up
3. **弱匹配规则要不要排除"千兆"等含 "vlan" 字符串？** 物理口 description 不会含 vlan 关键字，概率低

## 关联

- [proposal.md](proposal.md)
- [_detect_layer 代码](file:///root/workpace/h3c-netctrl/backend/app/routers/interface.py#L228-L255)
- [OperationLog 模型](file:///root/workpace/h3c-netctrl/backend/app/models.py)
