# sdn-vpc-model-and-foundation — Design

> 配套 proposal.md，本文件回答**怎么实现**（架构 / 数据流 / 边界 / 决策记录）

---

## 1. 架构定位

本 change 是 v3.0 SDN 的**第 0 层（数据骨架）**：

```
v3.0 SDN 分层架构
├── L0 数据骨架      ← 本 change (sdn-vpc-model-and-foundation)
│   ├── 5 张表
│   ├── SdnAllocator
│   ├── CRUD API
│   └── 单测
│
├── L1 端口绑定      → sdn-port-binding（next）
├── L2 设备配置模板  → sdn-vpc-device-templates（next）
├── L3 配置下发      → sdn-deploy
├── L4 状态采集      → sdn-collect
└── L5 可视化校验    → sdn-validate
```

**L0 不依赖 L1-L5**。L1-L5 都依赖 L0 的模型字段。

## 2. 数据模型（5 张表）

### ER 图（简化）

```
sdn_tenants (1) ──── (N) sdn_vpcs (1) ──── (N) sdn_port_bindings
                          │
                          ├── (N) sdn_deployments
                          │
                          └── (N) sdn_validation_snapshots
```

### 关键字段语义

| 表 | 关键字段 | 含义 |
|---|---|---|
| `sdn_tenants` | `rd` / `import_rt` / `export_rt` / `l3_vni` | 系统自动分配，**全局唯一**（unique 约束）|
| `sdn_vpcs` | `vni` / `vsi_name` / `vsi_interface` / `vlan_id` | 设备侧 L2VNI + VSI 标识 |
| `sdn_port_bindings` | `if_index` / `interface_name` / `access_vlan` / `service_instance` | 端口 ↔ VPC 关系 |
| `sdn_deployments` | `action` / `planned_config` / `status` | 部署记录 |
| `sdn_validation_snapshots` | `snapshot_data` / `validation_result` | 采集快照 |

### CASCADE 策略

- `sdn_tenants` 删除 → **CASCADE** `sdn_vpcs` / `sdn_port_bindings` / `sdn_deployments` / `sdn_validation_snapshots`
- `sdn_vpcs` 删除 → **CASCADE** `sdn_port_bindings` / `sdn_deployments` / `sdn_validation_snapshots`
- `devices` 删除 → CASCADE `sdn_port_bindings` / `sdn_deployments` / `sdn_validation_snapshots`（**已有 7 commit 之前的 device model 配置**）

## 3. 编号分配策略（SdnAllocator）

### 决策表

| 资源 | 分配方式 | 起点 env | 唯一性保证 |
|---|---|---|---|
| tenant RD | `f"{SDN_RD_BASE}:{tenant_id}"` | `SDN_RD_BASE=100` | tenant_id 唯一 |
| tenant import RT | `f"{SDN_RT_BASE}:{tenant_id}"` | `SDN_RT_BASE=100` | tenant_id 唯一 |
| tenant export RT | `f"{SDN_RT_BASE}:{tenant_id}"` | `SDN_RT_BASE=100` | tenant_id 唯一 |
| tenant L3VNI | `max(l3_vni) + 1` 取 `SDN_L3VNI_START` 较大 | `SDN_L3VNI_START=10000` | DB unique 约束 |
| vpc VNI (L2VNI) | `max(vni) + 1` 取 `SDN_L2VNI_START` 较大 | `SDN_L2VNI_START=20000` | DB unique 约束 |
| vpc Vsi-interface | `max(vsi_interface) + 1` 起步 1 | 硬编码 1 | DB unique 约束 |
| vpc VLAN | `max(vlan_id) + 1` 起步 2 | 硬编码 2 | 设备侧全局唯一 |
| vpc gateway_ip | CIDR 末位可用地址 | — | — |
| vpc gateway_mac | `f"00-00-00-00-{vni:04x}-01"` | — | — |

### 冲突处理

- DB unique 约束冲突 → 捕获 `IntegrityError` → 返回对应 i18n error_key
- 名称冲突 → 业务层 pre-check → 返回 `SDN_TENANT_NAME_EXISTS`

## 4. 关键设计决策（ADR）

### ADR-001：VSI name 命名规则

**决策**：`f"vpc{vpc_id:04d}"`（如 `vpc0001`, `vpc0002`）

- **理由**：
  - 短（≤16 字符，H3C 设备侧 VSI 名称上限）
  - 全球唯一（vpc_id 主键）
  - 不依赖 tenant_name/vpc_name（改名不影响 VSI）
- **替代方案**：`f"vsi_{tenant}_{vpc}"` 弃用（太长 / 含特殊字符风险）

### ADR-002：L3VNI 起点 10000+（非 3000）

**决策**：L3VNI 从 10000 起（L2VNI 从 20000 起）

- **理由**：
  - 保留设备侧 1-9999 给预留 / 系统 VNI（包括设备自动创建的 3000）
  - 与现有 .2/.3 设备的 Auto_L3VNI3000 不冲突
- **未来**：device-templates change 会决定是否复用设备 3000

### ADR-003：RD/RT 用 100:tenant_id 起步

**决策**：`SDN_RD_BASE=100`（默认 100，可改）

- **理由**：跟 .2/.3 现状的 `1:200` / `1:300` 不冲突（用 100 段）
- **未来**：device-templates change 会根据现网实际 RD 段决定是否调整

### ADR-004：L3VNI 全局唯一（保守策略）

**决策**：`l3_vni` 加 `unique=True`

- **理由**：v3.0 P0 阶段 tenant 数量少，全局唯一避免任何 RD/RT 冲突
- **未来**：fabric 全 unique 还是 per-tenant 复用，由 v3.0.1+ 演进

## 5. 边界与不做的事

| 边界 | 不做 | 留给 |
|---|---|---|
| 设备配置 | 不生成 H3C CLI 命令 | `sdn-vpc-device-templates` |
| 配置下发 | 不连 NETCONF/SSH | `sdn-deploy` |
| 端口绑定 | 不创建 `SdnPortBinding` 记录 | `sdn-port-binding` |
| 状态采集 | 不调用 display 命令 | `sdn-collect` |
| 部署记录 | 不写 `SdnDeployment` | `sdn-deploy` |
| 校验快照 | 不写 `SdnValidationSnapshot` | `sdn-validate` |

## 6. split 容器兼容

- 5 张表由 `config` 容器唯一持有（v2.4.1 split 架构约定）
- Alembic 迁移 007 在 config 容器内 `alembic upgrade head` 时建表
- 幂等守卫：`if "sdn_tenants" in insp.get_table_names(): return`
- 设备执行层（L2-L5）将来会涉及 ctrl / config / data 三容器协同，本 change 不涉及

## 7. 测试策略

- 19 个单测：覆盖 tenant CRUD（8）+ vpc CRUD（7）+ allocator 边界（4）
- 不需要真机（mock NETCONF）
- 不跑集成（integration marker 默认 skip，符合 v2.3+ QA 规范）
- `pytest -m "not integration"` 必须全过

## 8. 风险与回退

| 风险 | 缓解 | 回退 |
|---|---|---|
| RD 段与现网冲突 | env vars 可调 | `alembic downgrade -1` |
| VNI 10000+ 与设备侧预留冲突 | 后续 device-templates 适配 | env 调整 |
| CASCADE 删除误删 | PATCH 端点不暴露删除 | 备份库表 |
