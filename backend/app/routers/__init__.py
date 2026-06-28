"""
Routers 模块集合

未来容器解耦蓝图（v2.1.x patch 预留，未实际拆）
当前 monolith 全部加载；v2.3 拆 asset / v3.0 加 sdn / 未来 monitor
详见 docs/CONTAINER-DECOUPLING.md

未来归属对照表（仅注释，import 结构不变）：

| Router              | 当前   | 未来归属 | 理由                          |
|---------------------|--------|----------|-------------------------------|
| device.py           | core   | core     | 设备 CRUD + NETCONF           |
| vlan.py             | core   | core     | NETCONF VLAN                  |
| interface.py        | core   | core     | NETCONF 接口配置              |
| execute.py          | core   | core     | SSH 命令派发                  |
| log.py              | core   | core     | 操作日志                      |
| auth.py             | core   | core     | 基础设施                      |
| health.py           | core   | core     | 基础设施                      |
| dashboard.py        | core   | core     | 仪表盘聚合                    |
| batch.py            | core   | core     | 批量操作（跨 core router）    |
| asset.py            | core   | asset    | cmdb / 资产采集               |
| backup.py (v2.2)    | core   | asset    | 备份 I/O 重，v2.3 拆出         |
| sdn.py (v3.0)       | —      | sdn      | VPC + etcd                    |
| monitor.py (未来)   | —      | monitor  | 实时指标 / 告警               |
"""
