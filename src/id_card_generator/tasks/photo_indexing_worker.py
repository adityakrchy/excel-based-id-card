"""Background worker thread for asynchronous high-performance photo directory scanning."""

import logging
from pathlib import Path
from typing import Dict, List, Tuple
from PySide6.QtCore import QThread, Signal

from id_card_generator.data.photo_scanner import PhotoScanner

logger = logging.getLogger(__name__)


class PhotoIndexingWorker(QThread):
    """Worker thread streaming photo indexing results in real-time batches without freezing UI."""

    # (batch_tuples_list, total_count_so_far, latest_file_name)
    batch_discovered = Signal(list, int, str)
    # (exact_index, lower_index, total_files)
    indexing_finished = Signal(dict, dict, int)
    indexing_failed = Signal(str)
    indexing_cancelled = Signal()

    def __init__(self, photo_dir: Path, batch_size: int = 150, parent=None):
        super().__init__(parent)
        self.photo_dir = Path(photo_dir)
        self.batch_size = batch_size
        self._is_cancelled = False

    def cancel(self) -> None:
        """Request immediate thread cancellation."""
        self._is_cancelled = True

    def run(self) -> None:
        try:
            logger.info("Starting background photo scanning for %s", self.photo_dir)

            def on_batch(batch: List[Tuple[str, str]], total: int, latest_name: str) -> None:
                if not self._is_cancelled:
                    self.batch_discovered.emit(batch, total, latest_name)

            def is_cancelled() -> bool:
                return self._is_cancelled

            exact_idx, lower_idx, total = PhotoScanner.scan_directory_streaming(
                photo_dir=self.photo_dir,
                on_batch=on_batch,
                is_cancelled=is_cancelled,
                batch_size=self.batch_size,
            )

            if self._is_cancelled:
                logger.info("Photo scanning thread cancelled.")
                self.indexing_cancelled.emit()
            else:
                logger.info(
                    "Photo scanning complete: %d files indexed across %d unique stems.",
                    total,
                    len(exact_idx),
                )
                self.indexing_finished.emit(exact_idx, lower_idx, total)

        except Exception as e:
            logger.exception("Error in photo indexing thread: %s", e)
            self.indexing_failed.emit(str(e))
