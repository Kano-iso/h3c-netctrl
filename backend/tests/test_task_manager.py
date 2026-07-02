"""v24-feat-async-backup-status: TaskManager 单测

覆盖：
- 状态机：pending → running → success
- 状态机：pending → running → failed
- 取消：pending → running → cancelled
- 进度更新
- 持久化（get_status 从 DB 读）
"""
import time

from app.task_manager import TaskManager


def test_task_manager_success_flow():
    """pending → running → success"""
    tm = TaskManager()

    def simple_fn(task_id, cancel_event, progress_cb):
        progress_cb(50)
        time.sleep(0.05)
        return {"result": "ok"}

    task_id = tm.submit("backup", 1, simple_fn)
    # 等待任务完成（max_workers=1，串行）
    time.sleep(1.5)

    status = tm.get_status(task_id)
    assert status is not None, "任务应存在"
    assert status["status"] == "success", f"应为 success，实际 {status['status']}"
    assert status["progress"] == 100
    assert status["result"] == {"result": "ok"}
    assert status["task_type"] == "backup"
    assert status["device_id"] == 1


def test_task_manager_failed_flow():
    """pending → running → failed"""
    tm = TaskManager()

    def fail_fn(task_id, cancel_event, progress_cb):
        progress_cb(30)
        raise Exception("测试错误")

    task_id = tm.submit("restore", 2, fail_fn)
    time.sleep(1.5)

    status = tm.get_status(task_id)
    assert status is not None
    assert status["status"] == "failed", f"应为 failed，实际 {status['status']}"
    assert "测试错误" in status["error"]
    assert status["task_type"] == "restore"


def test_task_manager_cancel():
    """pending → running → cancelled（协作式取消）"""
    tm = TaskManager()

    def long_fn(task_id, cancel_event, progress_cb):
        progress_cb(10)
        for _ in range(100):
            if cancel_event.is_set():
                return {"cancelled": True}
            time.sleep(0.05)
        return {"result": "done"}

    task_id = tm.submit("backup", 3, long_fn)
    time.sleep(0.3)  # 等任务开始运行

    cancelled = tm.cancel(task_id)
    assert cancelled is True, "取消请求应成功"

    time.sleep(1)  # 等任务检查 cancel_event 并退出

    status = tm.get_status(task_id)
    assert status is not None
    assert status["status"] == "cancelled", f"应为 cancelled，实际 {status['status']}"


def test_task_manager_cancel_nonexistent():
    """取消不存在的任务返回 False"""
    tm = TaskManager()
    assert tm.cancel(99999) is False


def test_task_manager_cancel_terminal():
    """已完成的任务不能取消"""
    tm = TaskManager()

    def quick_fn(task_id, cancel_event, progress_cb):
        return {"done": True}

    task_id = tm.submit("backup", 1, quick_fn)
    time.sleep(1)

    # 任务已完成
    status = tm.get_status(task_id)
    assert status["status"] == "success"

    # 尝试取消已完成任务
    assert tm.cancel(task_id) is False


def test_task_manager_progress_update():
    """进度更新到 DB"""
    tm = TaskManager()

    def progress_fn(task_id, cancel_event, progress_cb):
        progress_cb(25)
        time.sleep(0.05)
        progress_cb(75)
        time.sleep(0.05)
        return {"done": True}

    task_id = tm.submit("backup", 1, progress_fn)
    time.sleep(1.5)

    status = tm.get_status(task_id)
    assert status["status"] == "success"
    assert status["progress"] == 100  # 最终 100


def test_task_manager_get_status_nonexistent():
    """查询不存在的任务返回 None"""
    tm = TaskManager()
    assert tm.get_status(99999) is None
