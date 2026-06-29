# add-vitest-component-tests

## Status: ⚠️ BLOCKED by env

### Why blocked
`npm install` 写入 `node_modules/@alloc/...` 报 EACCES（node_modules 由 root 拥有，当前 user bytedance 无写权限）。
- 修复：sudo chown -R bytedance:bytedance node_modules（需用户授权）
- 暂未授权

### 计划（解锁后）
1. 装包：`npm i -D vitest @vue/test-utils happy-dom`
2. `vite.config.js` 加 `test:` 配置 + `environment: 'happy-dom'`
3. `package.json` 加 `test:unit` script
4. 1 个 smoke test（验证框架可用）：`src/components/__tests__/Select.spec.js`
5. CI: `npm run test:unit`

### 装包消耗（解锁后）
- vitest: ~20MB
- @vue/test-utils: ~5MB
- happy-dom: ~5MB
- 总: ~30MB（比 Playwright 300MB 轻 10 倍）

### 暂存
- v2.3.0 不含此 change
- 留待环境修复后做
- P1 优先级

## Resolution
需要 `sudo chown -R $(whoami):$(whoami) node_modules` 才能继续。
EOF
