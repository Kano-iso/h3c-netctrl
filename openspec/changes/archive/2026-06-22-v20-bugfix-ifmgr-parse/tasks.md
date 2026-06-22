## 1. 修复解析逻辑

- [x] 1.1 放宽 _parse_interface_response 的过滤条件，只检查 if_index
- [x] 1.2 Name 缺失时用 IfIndex 生成（If-{if_index}）
- [x] 1.3 LinkType 缺失时默认 access

## 2. 验证

- [x] 2.1 真实设备测试：API 返回非空接口列表
- [x] 2.2 前端能看到接口信息
- [x] 2.3 提交代码并推送 + Archive 闭环
