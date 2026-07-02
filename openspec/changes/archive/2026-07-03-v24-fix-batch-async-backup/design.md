# v24-fix-batch-async-backup Design

## 涉及文件

| 文件 | 改动 |
|---|---|
| `frontend/src/stores/task.js` | 加 `submitBatchBackup(devices, types, labelFn)` 方法 |
| `frontend/src/views/Backup.vue` | `handleFullBackup` 加 ASYNC 分支 |
| `frontend/src/views/CMDB.vue` | `handleFullBackup` 加 ASYNC 分支 + import taskStore + ASYNC_MODE |

## task.js submitBatchBackup 设计

```javascript
/**
 * 批量提交备份任务（全量备份用）
 * @param {Array<{id, name}>} devices - 设备列表
 * @param {Array<string>} types - 备份类型
 * @param {Function} labelFn - 可选，自定义 label 生成器
 * @returns {Array<{success, task_id?, error?}>} 每台设备的提交结果
 */
async function submitBatchBackup(devices, types, labelFn) {
  const results = []
  for (const d of devices) {
    const label = labelFn ? labelFn(d) : `全量备份 ${d.name || '#' + d.id}`
    const r = await submitBackup(d.id, types, label)
    results.push({ device_id: d.id, ...r })
  }
  return results
}
```

- 串行提交（for 循环，不用 Promise.all），避免瞬间 N 个 HTTP 请求打爆后端
- 每台设备提交后立即返回 task_id，后台 TaskManager 串行执行（max_workers=1）
- 返回每台设备的提交结果（成功/失败），调用方可选展示

## Backup.vue handleFullBackup ASYNC 分支

```javascript
async function handleFullBackup() {
  if (fullBackingUp.value) return

  // ASYNC 模式：循环提交，不阻塞
  if (ASYNC_MODE) {
    const types = fullBackupType.value === 'all' ? ['startup', 'running'] : [fullBackupType.value]
    const results = await taskStore.submitBatchBackup(
      devices.value,
      types,
      (d) => `全量备份 ${d.name}`
    )
    const failed = results.filter(r => !r.success)
    if (failed.length) {
      errMsg.value = `${failed.length} 台设备提交失败: ${failed[0].error}`
    }
    return  // 不弹结果 Modal，BackgroundTaskPanel 显示每任务
  }

  // 同步模式（v2.3 行为不变）
  fullBackingUp.value = true
  fullResult.value = null
  const types = fullBackupType.value === 'all' ? ['startup', 'running'] : [fullBackupType.value]
  const r = await backupApi.createAll({ types })
  fullBackingUp.value = false
  if (!r.success) {
    errMsg.value = r.error || '全量备份失败'
    return
  }
  fullResult.value = r.data || { success: [], failed: [] }
  fullResultOpen.value = true
  await loadAll()
}
```

## CMDB.vue 同理

加 `import { useTaskStore }` + `const ASYNC_MODE = import.meta.env.VITE_ASYNC_BACKUP === 'true'` + `handleFullBackup` 加 ASYNC 分支。

CMDB.vue 的设备列表变量是 `items`（含 `id` / `name`），传给 `submitBatchBackup`。

## 不改后端

复用 `POST /api/devices/{device_id}/backup-async`，TaskManager 已有 max_workers=1 串行保证。
