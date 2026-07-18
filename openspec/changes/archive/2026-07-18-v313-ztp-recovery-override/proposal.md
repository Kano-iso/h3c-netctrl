# v313-ztp-recovery-override — Proposal

> 版本：v3.1.3
> 主题：ZTP 恢复上线旁路功能

## 背景

模拟器或实验设备重启后可能丢失配置。过去需要人工从 console 登录，手工恢复 OOB 管理地址，再回到平台做纳管和备份回滚。

v3.1.1/v3.1.2 已经具备 ZTP 基础配置与上线纳管能力，本 change 增加一个面向已有设备的兜底入口：临时指定一个已有设备管理地址，让清空配置的设备通过 ZTP 先恢复 OOB 地址与基础管理能力，随后用户可在现有备份回滚页面恢复完整配置。

## 范围

- 前端新增“ZTP 恢复上线”页面，放在运营管理分组。
- 后端新增 ZTP recovery override API：写入 / 查询 / 清除一次性恢复配置。
- ztp-server 读取共享 override 文件并实时重渲染 `autocfg.cfg`。
- autocfg.cfg 标准模板补齐 OOB 管理 VRF：`ip vpn-instance mgt` + OOB 口 `ip binding vpn-instance mgt`。
- 正常新设备上线序列不受影响；清除 override 后恢复 `.101/.102/.103...` 常规路径。
- 去掉“备份回滚”的未来标记。

## 不做

- 不做备份回滚编排自动串联；配置回滚继续由备份回滚页面负责。
- 不做 MAC 绑定、DHCP lease 监听或自动识别是哪台设备。
- 不做复杂 ZTP 生命周期产品页。
