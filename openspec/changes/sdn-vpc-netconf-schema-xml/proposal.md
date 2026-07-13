# sdn-vpc-netconf-schema-xml

## Why

`2026-07-11-sdn-vpc-deployment-executor` 已 archive，但 **真机下发验证失败**——`.5` 设备 NETCONF edit-config 持续报错 `Element [...h3c-ns...]config does not meet requirement` / `Configuration can not have a textual child element`。

### 根因（探针实测 2026-07-11）

H3C V7 NETCONF **不支持** CLI 文本下发（`<Configuration>vsi vpc0001</Configuration>` 直接被拒）。设备支持的 NETCONF 能力清单（`server_capabilities` 实测）：

| Module | 用途 |
|---|---|
| `config:1.0-L2VPN?module=L2VPN` | L2VPN/VSI/VXLAN 配置 |
| `config:1.0-EVPN?module=EVPN` | EVPN 路由 |
| `config:1.0-L3vpn` | L3VPN vpn-instance |
| `config:1.0-Ifmgr?module=Ifmgr` | Vsi-interface / 接口 |
| `config:1.0-BGP` | BGP 邻居 |
| `config:1.0-Configuration?module=Configuration` | ⚠️ 存在但**只能 schema 化**，不支持文本子节点 |

### 设计错误

`SdnDeploymentExecutor` 当前实现把 CLI 文本包在 `<Configuration>` 节点下发（v3.0 简化方案），**H3C V7 不接受**。正确方式是把每条 CLI 映射成 YANG schema 化 XML（参考 v2.4 中 `vlan.py` / `interface.py` 已用过的 `<top xmlns="..."><VLAN><VLANs><VLANID>...` 模式）。

## What Changes

- **重写 H3C V7 模板输出格式**：从 List[CLI 文本] 改为 List[schema 化 XML 片段]
- **重写 SdnDeploymentExecutor**：去掉 `<Configuration>` 包裹，直接 edit-config 模板生成的 schema 化 XML
- **planned_config 序列化格式变更**：JSON 数组内每条从 `{mode, command}` 改为 `{module, xml}` 或统一 XML 字符串
- **重跑 .5 真机验证**：POST /api/sdn/deployments/1/apply → 验证 `display l2vpn vsi` 出现 vpc0001

## 不在本 change 范围

- 数据模型（`SdnVpc` / `SdnPortBinding` / `SdnDeployment`）不变
- API endpoint（POST /api/sdn/deployments/{id}/apply）签名不变
- 设备白名单（仅 .5 / .6 可下发）不变
- SdnPreflight 6 项预检不变

## 影响范围

| 文件 | 影响 |
|---|---|
| `backend/app/services/templates/h3c_v7_vpc_create.py` | 大改：render() 输出 XML 而非 CLI |
| `backend/app/services/templates/h3c_v7_vpc_delete.py` | 大改：同上 |
| `backend/app/services/templates/h3c_v7_port_bind.py` | 大改：同上 |
| `backend/app/services/templates/h3c_v7_port_unbind.py` | 大改：同上 |
| `backend/app/services/sdn_deployment_executor.py` | 中改：去掉 `<Configuration>` 包裹 |
| `backend/app/services/vpc_config_planner.py` | 小改：serialize/deserialize 适配新格式 |
| `backend/app/schemas.py` | 小改：SdnDeployment.planned_config 注释更新 |
| `backend/tests/test_sdn_*.py` | 跟测：mock 设备响应 |

## QA 验证计划

### 1. 涉及端点 / UI / 设备

| 类别 | 名称 | 涉及文件 |
|---|---|---|
| 后端 API | POST /api/sdn/deployments/1/apply | backend/app/routers/sdn.py |
| 真实设备 | 192.168.100.5 (Leaf-04) | 唯一下发目标 |

### 2. QA 验证项

#### 2.1 后端单元（qa-backend 容器跑）

- [ ] 模板 render 输出符合 schema 化 XML 校验（test_templates_h3c_v7.py）
- [ ] planner serialize/deserialize 往返一致
- [ ] executor mock NetconfClient 验证 XML 入参正确
- [ ] 中文错误信息（"配置下发失败: 设备返回错误: ..."）

#### 2.2 真机集成（qa-backend 容器跑 .5）

- [ ] **先备份 .5 running-config**（vpc-show.sh 拿基线 + capture-config.sh 备份）
- [ ] 探针：单条 schema 化命令下发 + undo（`vsi vpc9999` 试探 schema 写法）
- [ ] 全量下发 deployment 1 → status=success
- [ ] `display l2vpn vsi verbose` 看到 vpc0001
- [ ] `display vxlan tunnel` 看到 VNI 20000
- [ ] `display bgp peer l2vpn evpn` 仍 Established
- [ ] **最后 restore_original_state**（undo vpc0001 + 验证 display 无 vpc0001）
- [ ] reboot 类验证不适用（本次是 edit-config 不是 reboot）

#### 2.3 回归

- [ ] v3.0 已 archive 的 4 个 changes（model-and-foundation / device-templates / deployment-api / deployment-executor）相关测试不破坏
- [ ] qa-backend 全量 pytest 通过
- [ ] 67 SDN tests + 225+ baseline 全过

### 3. 跑法

```bash
# unit
docker compose -f docker-compose.dev.yml --profile qa up qa-backend

# 真机（需 SSH 通 .5）
docker exec h3c-netctrl-ops-toolkit /scripts/vpc-show.sh --device Leaf-04
```

## ADR

- **ADR-106**: H3C V7 NETCONF 业务下发走 schema 化 XML（`<top xmlns="h3c-config-ns"><L2vpnVSIs>...</L2vpnVSIs></top>` 等），不走 CLI 文本（`<Configuration>` 节点被 H3C 拒绝）
- **ADR-107**: planned_config 序列化从 JSON `{mode, command}` 数组改为 JSON `{module, xml}` 数组，每条对应一个 H3C YANG module + schema 化 XML 片段
- **ADR-108**: 每条配置独立 edit-config 调用（不批量），失败立即停 + 错误定位准
