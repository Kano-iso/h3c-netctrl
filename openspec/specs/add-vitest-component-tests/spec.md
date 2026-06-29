# spec: add-vitest-component-tests

## 状态: ⏸️ BLOCKED by env

EACCES on `node_modules/@alloc/...` （node_modules 由 root 拥有，当前 user bytedance 无写权限）。

## 解锁条件

```bash
sudo chown -R $(whoami):$(whoami) frontend/node_modules
```

## 解锁后计划

### 装包
- `vitest` (~20MB)
- `@vue/test-utils` (~5MB)
- `happy-dom` (~5MB)
- 总: ~30MB

### 框架
- `vite.config.js` 加 `test:` 配置 + `environment: 'happy-dom'`
- `package.json` 加 `test:unit` script
- 1 个 smoke test：`src/components/__tests__/Select.spec.js`

## 验收标准（解锁后）

- [ ] `npm run test:unit` 工作
- [ ] 1 个组件 smoke test PASS
- [ ] CI 集成：`qa-frontend` 加 `test:unit` step

## 关联 change
- `openspec/changes/archive/2026-06-29-add-vitest-component-tests/`
