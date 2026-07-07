# fix-backup-restore-support — Tasks

## Task 列表（9 task 串行 + 1 平行）

| # | Task | 文件 | 依赖 | commit msg | 状态 |
|---|---|---|---|---|---|
| T1 | 后端 `check_restore_support(device)` probe | `backend/app/utils/backup_manager.py` | — | `feat(backup): add check_restore_support probe` | ⏳ |
| T2 | restore_async 端点预检 + 422 | `backend/app/routers/backup.py` | T1 | `feat(backup): restore_async 预检不支持设备` | ⏳ |
| T3 | `_restore_via_scp` 详细错误日志 | `backend/app/utils/backup_manager.py` | — | `fix(backup): _restore_via_scp 详细 paramiko 错误` | ⏳ |
| T4 | 前端 toast 系统（taskStore 失败时弹） | 多文件 | — | `feat(frontend): toast 系统 + taskStore 失败触发` | ⏳ |
| T5 | BackgroundTaskPanel "最近失败"高亮 | `frontend/src/components/BackgroundTaskPanel.vue` | T4 | `feat(frontend): 任务面板失败高亮` | ⏳ |
| T6 | device.status 加 `restore_unsupported` 字段 | `backend/app/schemas/*.py` + router | T1 | `feat(backup): device.status 加 restore_unsupported 字段` | ⏳ |
| T7 | mock scp.put 抛 Channel closed 测试 | `backend/tests/test_backup_api.py` | T1, T2, T4 | `test(backup): mock scp.put Channel closed 测试` | ⏳ |
| T8 | 真机 .177 + .5 双向验证 | （验证记录） | T1, T2 | `test(backup): 真机 .177 + .5 双向验证记录` | ⏳ |
| T9 | docs/ops-toolkit.md S6850 SCP 限制说明 | `docs/ops-toolkit.md` | T1, T8 | `docs(ops-toolkit): S6850 SCP 限制说明` | ⏳ |

## 实施时序图

```
T1 (probe)
├──→ T2 (端点预检)
│       │
│       ├──→ T7 (mock 测试)
│       │       │
│       │       └──→ T8 (真机双向验证)
│       │               │
│       │               └──→ T9 (文档)
│       │
│       └──→ T6 (status 字段)
│
├──→ T3 (错误日志)
│
└──→ T4 (toast 系统)
        │
        └──→ T5 (面板高亮)
```

## 每 Task 详细

### T1：后端 `check_restore_support(device)` probe

**目标**：新建 `BackupManager.check_restore_support()` 方法，probe 设备是否支持 SCP 推回。

**实现**（`backend/app/utils/backup_manager.py`）：
```python
def check_restore_support(self) -> dict:
    """Probe 设备是否支持 SCP 推回（v2.6.2 fix-backup-restore-support Task 1）

    试推 1 字节 dummy 文件，捕获 SSHException
    - 成功 → 删除 dummy 文件，返回 {supported: True}
    - 失败 → 返回 {supported: False, reason: "Channel closed" | ...}
    """
    client = self._connect_ssh()
    try:
        dummy_name = f"_probe_{int(time.time())}.tmp"
        dummy_content = io.BytesIO(b"\x00")
        try:
            scp = SCPClient(client.get_transport())
            try:
                scp.putfo(dummy_content, dummy_name)
                # 推成功，清理（用 SSH exec channel 跑 delete 命令）
                chan = client.invoke_shell()
                chan.send(f"delete /unreserved flash:/{dummy_name}\n".encode())
                time.sleep(1)
                chan.close()
                return {"supported": True, "reason": "scp push ok"}
            finally:
                scp.close()
        except Exception as e:
            return {"supported": False, "reason": str(e), "error_type": type(e).__name__}
    finally:
        client.close()
```

**单测**（`backend/tests/test_backup_api.py`）：
- mock scp.put 抛 `paramiko.ssh_exception.SSHException("Channel closed.")` → 返回 `{supported: False, reason: "Channel closed."}`

**commit**：`feat(backup): add check_restore_support probe`
**status**：⏳

---

### T2：restore_async 端点预检 + 422

**目标**：`POST /api/devices/{id}/backup/{bid}/restore-async` 启动前先 check，不支持立即 422。

**实现**（`backend/app/routers/backup.py` line 586 `restore_backup_async`）：
```python
@router.post("/devices/{device_id}/backup/{backup_id}/restore-async", response_model=APIResponse)
def restore_backup_async(...):
    device, password, error = _get_device_with_password(db, device_id)
    if error:
        return error

    backup = db.query(Backup).filter(Backup.id == backup_id, ...).first()
    if not backup:
        return error_response(err.BACKUP_NOT_FOUND, ...)

    # v2.6.2 fix-backup-restore-support Task 2: 启动前 probe
    mgr = _make_manager(device, password)
    support = mgr.check_restore_support()
    if not support.get("supported"):
        return error_response(
            err.RESTORE_NOT_SUPPORTED,
            params={
                "device_ip": device.ip,
                "device_model": device.model or "Unknown",
                "reason": support.get("reason", "unknown"),
            },
            fallback=f"设备 {device.model or device.ip} 不支持 SCP 推回，无法回滚（{support.get('reason')}）",
        )

    task_id = task_manager.submit(...)
    return APIResponse(success=True, data={...})
```

**新增 error key**（`backend/app/utils/error_codes.py`）：
```python
RESTORE_NOT_SUPPORTED = "BACKUP_RESTORE_NOT_SUPPORTED"
```

**commit**：`feat(backup): restore_async 预检不支持设备`
**依赖**：T1（probe 函数）
**status**：⏳

---

### T3：`_restore_via_scp` 详细错误日志

**目标**：失败日志含 paramiko 异常类型 + device 型号 + 完整 error_message。

**实现**（`backend/app/utils/backup_manager.py` line 565 `_restore_via_scp`）：
```python
def _restore_via_scp(self, backup: Backup) -> None:
    client = self._connect_ssh()
    remote_name = f"recover_{backup.id}.cfg"
    try:
        scp = SCPClient(client.get_transport())
        try:
            scp.put(backup.file_path, remote_name)
            ...
        except Exception as e:
            # v2.6.2 fix-backup-restore-support Task 3: 详细错误日志
            logger.error(
                f"SCP 推回失败: device_model={self.device_model or 'Unknown'} "
                f"host={self.host} backup_id={backup.id} "
                f"error_type={type(e).__name__} error_message={e}"
            )
            raise BackupError(
                f"SCP 推回失败 (device={self.host}, type={type(e).__name__}): {e}"
            ) from e
        finally:
            scp.close()
    except Exception as e:
        # BackupError 已 raise，不再嵌套
        if not isinstance(e, BackupError):
            logger.error(f"...")
        raise
    finally:
        client.close()
    ...
```

**commit**：`fix(backup): _restore_via_scp 详细 paramiko 错误`
**依赖**：—
**status**：⏳

---

### T4：前端 toast 系统

**目标**：taskStore 失败时弹 toast，新建 toast 组件 + store。

**新建文件**：

1. `frontend/src/stores/toast.js`（Pinia store）：
   ```javascript
   import { defineStore } from 'pinia'
   import { ref } from 'vue'

   export const useToastStore = defineStore('toast', () => {
     const toasts = ref([])
     function push(type, message, duration = 5000) {
       const id = Date.now() + Math.random()
       toasts.value.push({ id, type, message, duration })
       if (duration > 0) {
         setTimeout(() => remove(id), duration)
       }
     }
     function success(msg) { push('success', msg) }
     function error(msg) { push('error', msg, 8000) }
     function info(msg) { push('info', msg) }
     function remove(id) {
       toasts.value = toasts.value.filter(t => t.id !== id)
     }
     return { toasts, success, error, info, remove }
   })
   ```

2. `frontend/src/components/ToastContainer.vue`：
   - 右上角浮动
   - 4 种类型：success / error / warning / info
   - 自动消失（5s）+ 手动关闭
   - v2.6.2 全部走 i18n

3. `frontend/src/App.vue`：挂载 `<ToastContainer />`

**修改**：
- `frontend/src/stores/task.js` `_pollOnce`：检测 task 从 running → failed 时调 `toast.error(...)`
- `frontend/src/i18n/zh-CN.js` + `en-US.js`：加 5 个 i18n key

**i18n key**（10 个）：

| key | zh-CN | en-US |
|---|---|---|
| `component.toast.success` | 成功 | Success |
| `component.toast.error` | 错误 | Error |
| `component.toast.warning` | 警告 | Warning |
| `component.toast.info` | 提示 | Info |
| `component.toast.task_failed` | 任务 #{id} 失败: {error} | Task #{id} failed: {error} |

**commit**：`feat(frontend): toast 系统 + taskStore 失败触发`
**依赖**：—
**status**：⏳

---

### T5：BackgroundTaskPanel 失败高亮

**目标**：任务面板即使折叠，右下角显示红点 + 展开时失败任务加 `text-bad` 高亮。

**实现**（`frontend/src/components/BackgroundTaskPanel.vue`）：
```vue
<!-- 折叠态红点 -->
<template>
  <div v-if="!hasRunning && !expanded && failedCount > 0" 
       class="fixed bottom-4 right-4 z-40 ..." 
       @click="expanded = true">
    <div class="bg-bad text-white px-3 py-2 rounded-full shadow-elevated cursor-pointer">
      <span class="text-xs">{{ failedCount }} 个失败任务</span>
    </div>
  </div>
</template>

<script setup>
const failedCount = computed(() => 
  Object.values(tasks.value).filter(t => t.status === 'failed').length
)
</script>
```

**commit**：`feat(frontend): 任务面板失败高亮`
**依赖**：T4
**status**：⏳

---

### T6：device.status 加 `restore_unsupported` 字段

**目标**：`device.status` 返回 `restore_unsupported: bool`，前端可显示"该设备不支持回滚"标识。

**实现**：
- `backend/app/schemas/device.py` 加 `restore_unsupported: Optional[bool] = None` 字段
- 后端在 `device.status` router（`/api/devices/{id}/status` 或 list）调用 `check_restore_support` 并缓存（v2.6.1 已有 5s TTL 缓存机制）
- 缓存 key：`device:{id}:restore_support`（5s TTL）

**commit**：`feat(backup): device.status 加 restore_unsupported 字段`
**依赖**：T1
**status**：⏳

---

### T7：mock scp.put 抛 Channel closed 测试

**目标**：mock scp.put 抛 `paramiko.ssh_exception.SSHException("Channel closed.")` → 验证后端返回 422 + 前端 toast。

**单测**（`backend/tests/test_backup_api.py`）：
```python
def test_restore_async_returns_422_when_scp_unsupported(client, db, monkeypatch):
    """v2.6.2 fix-backup-restore-support Task 7: 不支持设备 restore_async 422"""
    from app.utils.backup_manager import BackupManager
    from paramiko.ssh_exception import SSHException
    
    def mock_probe(self):
        return {"supported": False, "reason": "Channel closed.", "error_type": "SSHException"}
    
    monkeypatch.setattr(BackupManager, "check_restore_support", mock_probe)
    
    # 创建测试 device + backup
    device = create_test_device()
    backup = create_test_backup(device.id)
    
    r = client.post(f"/api/devices/{device.id}/backup/{backup.id}/restore-async")
    assert r.status_code == 200  # APIResponse 包装
    body = r.json()
    assert body["success"] is False
    assert body["error"]["key"] == "BACKUP_RESTORE_NOT_SUPPORTED"
    assert "不支持" in body["error"]["fallback"]
```

**commit**：`test(backup): mock scp.put Channel closed 测试`
**依赖**：T1, T2
**status**：⏳

---

### T8：真机 .177 + .5 双向验证

**目标**：真机双向验证 — .177（支持）restore 成功；.5（不支持）restore 拒绝并明确错误。

**步骤**：
1. **.177 验证**：
   ```bash
   docker compose --profile qa up qa-backend pytest -k test_restore_177 --integration
   ```
   预期：restore 成功
2. **.5 验证**：
   - 用 MCP 浏览器访问 UI，触发 .5 设备的 restore
   - 预期：toast 弹"设备 S6850 不支持 SCP 推回，无法回滚"
   - 任务状态：failed（不进入 running）

**commit**：`test(backup): 真机 .177 + .5 双向验证记录`（commit 内容是验证日志）
**依赖**：T1, T2
**status**：⏳

---

### T9：docs/ops-toolkit.md S6850 SCP 限制说明

**目标**：ops-toolkit 文档加"S6850 系列 SCP 限制"小节。

**实现**（`docs/ops-toolkit.md` 新增小节）：
```markdown
## S6850 / S6860 / S9850 系列 SCP 限制

H3C V7 S6850 (CMW 7.1.070) 等系列**默认禁用 SFTP/SCP subsystem**：

| 操作 | SSH exec channel | SCP/SFTP |
|---|---|---|
| `display version` | ✅ | — |
| `display current-configuration` | ✅ | — |
| **推送文件**（scp.put / sftp.put） | — | ❌ `Channel closed` |

**影响**：
- 备份**拉取**（display + 文本抓取）不受影响
- 备份**回滚推回**（需要真上传文件）❌ 不支持

**工作流**：
- 用 ops-toolkit 验证设备协议支持：
  ```bash
  ops-toolkit paramiko-batch-exec --device test --command "scp /a/b localhost:/dev/null" 2>&1
  # .5 设备：失败
  # .177 设备：成功
  ```
- 用 NetCtrl UI：点"回滚" → 不支持设备立即 toast 提示

**参考**：H3C V7 S6850 CMW 7.1.070 设备手册
```

**commit**：`docs(ops-toolkit): S6850 SCP 限制说明`
**依赖**：T1, T8
**status**：⏳

---

## 串行实施顺序

```
Day 1: T1 (probe) → T2 (端点预检)
Day 2: T3 (错误日志) + T4 (toast 系统)
Day 3: T5 (面板高亮) + T6 (status 字段)
Day 4: T7 (mock 测试) + T8 (真机验证)
Day 5: T9 (文档收尾) + archive 闭环
```

**为什么这样排**：
- T1 是所有依赖的根（probe 函数必须先做）
- T2 是最小修复（用户已经反映"无反应"，必须先落地）
- T3 + T4 平行（错误日志 vs toast 系统是不同代码域）
- T5 跟在 T4 后（面板高亮依赖 toast 系统视觉风格）
- T6 单独做（schema 变更需独立 commit）
- T7 + T8 在所有代码 commit 后做（测试 + 验证）
- T9 文档收尾

## 闭环 checklist

Apply 阶段（每 Task 后）：
- [ ] T1 后：`docker compose --profile qa up qa-backend pytest -k check_restore`
- [ ] T2 后：`qa-backend pytest` 全过
- [ ] T3 后：`qa-backend pytest` 全过
- [ ] T4 后：`qa-frontend lint + build`
- [ ] T5 后：`qa-frontend lint + build`
- [ ] T6 后：`qa-backend pytest` 全过
- [ ] T7 后：`qa-backend pytest` 全过（含新测试）
- [ ] T8 后：MCP 浏览器 .177 + .5 双向验证
- [ ] T9 后：文档链接检查

Archive 阶段：
- [ ] `qa-backend` 全量 pytest（与 245+ baseline 对比）
- [ ] `qa-frontend` lint + build + vitest + playwright
- [ ] `docs/REVIEW-v262-bugfix-round.md` 写（如 v2.6.1 反思有更新点）
- [ ] `openspec/specs/backup-restore-support/spec.md` 主 spec 写
- [ ] 2 个 change archive 闭环（`git mv` 到 `archive/2026-07-08-*`）

发版前：
- [ ] RELEASE-NOTES-v2.6.2.md 写完
- [ ] VERSION-ROADMAP.md 加 §v2.6.2 详细 + §1 全景表加 1 行
- [ ] README.md 顶部版本表 + 当前架构表同步
- [ ] git tag v2.6.2 + push（需用户确认）

## 状态

- 🟢 实施中（v2.6.2 backlog 主项）
