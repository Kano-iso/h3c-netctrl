"""异步任务管理器（v24-feat-async-backup-status）

用 ThreadPoolExecutor 串行执行耗时任务（备份/回滚），
状态持久化到 tasks 表，支持进度更新和取消。

设计：
- max_workers=1（串行，避免 SQLite 写并发冲突）
- 每个任务用独立 DB session（SQLAlchemy session 非线程安全）
- 取消用 threading.Event（协作式取消，任务需自行检查）
- 进度通过 DB session 直接写 tasks 表
"""
import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from app.database import SessionLocal
from app.models import Task

logger = logging.getLogger("app")


class TaskManager:
    """异步任务管理器"""

    def __init__(self, max_workers: int = 1):
        self._executor = ThreadPoolExecutor(
            max_workers=max_workers, thread_name_prefix="task"
        )
        self._cancel_events: dict[int, threading.Event] = {}
        self._lock = threading.Lock()

    def submit(
        self,
        task_type: str,
        device_id: int,
        fn: Callable[..., Any],
        *args,
        **kwargs,
    ) -> int:
        """提交异步任务

        Args:
            task_type: "backup" | "restore"
            device_id: 设备 ID
            fn: 执行函数，签名 fn(task_id, cancel_event, progress_cb, *args, **kwargs) -> result
            *args, **kwargs: 传给 fn 的额外参数

        Returns:
            task_id
        """
        db = SessionLocal()
        try:
            task = Task(
                task_type=task_type,
                device_id=device_id,
                status="pending",
                progress=0,
            )
            db.add(task)
            db.commit()
            db.refresh(task)
            task_id = task.id
        finally:
            db.close()

        cancel_event = threading.Event()
        with self._lock:
            self._cancel_events[task_id] = cancel_event

        def progress_cb(pct: int):
            self._update_progress(task_id, pct)

        def _run():
            self._update_status(task_id, "running", progress=0)
            try:
                if cancel_event.is_set():
                    self._update_status(task_id, "cancelled")
                    return

                result = fn(task_id, cancel_event, progress_cb, *args, **kwargs)

                if cancel_event.is_set():
                    self._update_status(task_id, "cancelled")
                    return

                self._update_status(task_id, "success", progress=100, result=result)
            except Exception as e:
                logger.error(f"任务 {task_id} 执行失败: {e}", exc_info=True)
                self._update_status(task_id, "failed", error=str(e))
            finally:
                with self._lock:
                    self._cancel_events.pop(task_id, None)

        self._executor.submit(_run)
        return task_id

    def get_status(self, task_id: int) -> dict | None:
        """查询任务状态"""
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return None
            return {
                "task_id": task.id,
                "task_type": task.task_type,
                "device_id": task.device_id,
                "status": task.status,
                "progress": task.progress,
                "result": json.loads(task.result_json)
                if task.result_json
                else None,
                "error": task.error,
                "created_at": task.created_at.isoformat()
                if task.created_at
                else None,
                "updated_at": task.updated_at.isoformat()
                if task.updated_at
                else None,
            }
        finally:
            db.close()

    def cancel(self, task_id: int) -> bool:
        """请求取消任务（协作式，任务需自行检查 cancel_event）

        Returns:
            True: 取消请求已发送（任务存在且正在运行）
            False: 任务不存在或已完成
        """
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return False
            # 已终态的任务不能取消
            if task.status in ("success", "failed", "cancelled"):
                return False
        finally:
            db.close()

        with self._lock:
            event = self._cancel_events.get(task_id)
        if event:
            event.set()
            return True
        return False

    def _update_status(
        self,
        task_id: int,
        status: str,
        progress: int | None = None,
        result: Any = None,
        error: str | None = None,
    ):
        """更新任务状态（线程安全，用独立 session）"""
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if not task:
                return
            task.status = status
            if progress is not None:
                task.progress = max(0, min(100, progress))
            if result is not None:
                task.result_json = json.dumps(
                    result, ensure_ascii=False, default=str
                )
            if error is not None:
                task.error = error
            db.commit()
        except Exception as e:
            logger.error(f"更新任务 {task_id} 状态失败: {e}")
            db.rollback()
        finally:
            db.close()

    def _update_progress(self, task_id: int, pct: int):
        """更新任务进度（仅 running 状态时更新）"""
        db = SessionLocal()
        try:
            task = db.query(Task).filter(Task.id == task_id).first()
            if task and task.status == "running":
                task.progress = max(0, min(100, pct))
                db.commit()
        except Exception as e:
            logger.error(f"更新任务 {task_id} 进度失败: {e}")
            db.rollback()
        finally:
            db.close()


# 全局单例
task_manager = TaskManager()
