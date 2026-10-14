"""Centralized background task management and execution framework."""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
import logging
from typing import Any, Callable, Dict, Optional
import uuid

from PySide6.QtCore import QObject, QRunnable, QThreadPool, Signal

logger = logging.getLogger(__name__)


class TaskStatus(str, Enum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class TaskInfo:
    """Runtime tracking model for a background task."""
    task_id: str
    name: str
    status: TaskStatus = TaskStatus.PENDING
    completed_items: int = 0
    total_items: int = 0
    progress_pct: float = 0.0
    message: str = ""
    result: Any = None
    error_message: Optional[str] = None
    cancellable: bool = True
    is_cancelled: bool = False
    started_at: Optional[datetime] = None
    finished_at: Optional[datetime] = None


class TaskSignals(QObject):
    """Qt signals safely communicating worker status to GUI thread."""
    task_started = Signal(str, str)  # task_id, name
    task_progress = Signal(str, int, int, str)  # task_id, completed, total, message
    task_completed = Signal(str, object)  # task_id, result
    task_failed = Signal(str, str)  # task_id, error_message
    task_cancelled = Signal(str)  # task_id


class _TaskWorker(QRunnable):
    """Internal QRunnable executing worker callable in thread pool."""

    def __init__(self, task_info: TaskInfo, task_fn: Callable, signals: TaskSignals):
        super().__init__()
        self.task_info = task_info
        self.task_fn = task_fn
        self.signals = signals
        self.setAutoDelete(True)

    def run(self) -> None:
        self.task_info.status = TaskStatus.RUNNING
        self.task_info.started_at = datetime.now()
        self.signals.task_started.emit(self.task_info.task_id, self.task_info.name)

        def progress_callback(completed: int, total: int, msg: str = "") -> None:
            if self.task_info.is_cancelled:
                return
            self.task_info.completed_items = completed
            self.task_info.total_items = total
            self.task_info.message = msg
            if total > 0:
                self.task_info.progress_pct = round((completed / total) * 100.0, 1)
            self.signals.task_progress.emit(
                self.task_info.task_id, completed, total, msg
            )

        def is_cancelled() -> bool:
            return self.task_info.is_cancelled

        try:
            result = self.task_fn(progress_callback=progress_callback, is_cancelled=is_cancelled)
            if self.task_info.is_cancelled:
                self.task_info.status = TaskStatus.CANCELLED
                self.signals.task_cancelled.emit(self.task_info.task_id)
            else:
                self.task_info.status = TaskStatus.COMPLETED
                self.task_info.result = result
                self.signals.task_completed.emit(self.task_info.task_id, result)
        except Exception as e:
            logger.exception("Task '%s' failed: %s", self.task_info.name, e)
            self.task_info.status = TaskStatus.FAILED
            self.task_info.error_message = str(e)
            self.signals.task_failed.emit(self.task_info.task_id, str(e))
        finally:
            self.task_info.finished_at = datetime.now()


class TaskManager(QObject):
    """Central manager coordinating background workers and emitting UI-friendly signals."""

    _instance: Optional["TaskManager"] = None

    @classmethod
    def instance(cls) -> "TaskManager":
        if cls._instance is None:
            cls._instance = TaskManager()
        return cls._instance

    def __init__(self, parent=None):
        super().__init__(parent)
        self.signals = TaskSignals()
        self._tasks: Dict[str, TaskInfo] = {}
        self.thread_pool = QThreadPool.globalInstance()

    def submit_task(
        self,
        name: str,
        task_fn: Callable[..., Any],
        cancellable: bool = True,
    ) -> str:
        """Submit a callable to the background thread pool.
        
        Args:
            name: Human-readable task description.
            task_fn: Callable accepting (progress_callback, is_cancelled).
            cancellable: Whether this task can be cancelled.
            
        Returns:
            task_id: Unique identifier for tracking.
        """
        task_id = str(uuid.uuid4())
        info = TaskInfo(task_id=task_id, name=name, cancellable=cancellable)
        self._tasks[task_id] = info

        worker = _TaskWorker(task_info=info, task_fn=task_fn, signals=self.signals)
        self.thread_pool.start(worker)
        logger.info("Submitted background task '%s' (ID: %s)", name, task_id)
        return task_id

    def cancel_task(self, task_id: str) -> bool:
        """Request cancellation of an active task."""
        info = self._tasks.get(task_id)
        if info and info.cancellable and info.status == TaskStatus.RUNNING:
            info.is_cancelled = True
            logger.info("Cancellation requested for task '%s' (ID: %s)", info.name, task_id)
            return True
        return False

    def get_task(self, task_id: str) -> Optional[TaskInfo]:
        """Fetch current status and metadata of a task."""
        return self._tasks.get(task_id)
