"""Unit tests for background task manager."""

import time
from PySide6.QtCore import QCoreApplication
from id_card_generator.tasks.task_manager import TaskManager, TaskStatus


def test_task_manager_success():
    manager = TaskManager.instance()

    def dummy_task(progress_callback, is_cancelled):
        for i in range(1, 4):
            if is_cancelled():
                return None
            progress_callback(i, 3, f"Step {i}")
            time.sleep(0.01)
        return "SUCCESS"

    task_id = manager.submit_task("Test Job", dummy_task)
    
    # Process event loop briefly to allow runnable execution
    deadline = time.time() + 2.0
    while time.time() < deadline:
        QCoreApplication.processEvents()
        info = manager.get_task(task_id)
        if info and info.status == TaskStatus.COMPLETED:
            break
        time.sleep(0.02)

    info = manager.get_task(task_id)
    assert info is not None
    assert info.status == TaskStatus.COMPLETED
    assert info.result == "SUCCESS"
    assert info.completed_items == 3
