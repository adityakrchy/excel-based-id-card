"""Background QThread worker for batch generation with real-time Qt signals."""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import QThread, Signal

from id_card_generator.core.models import (
    PhotoMatchResult,
    RenderResult,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.generation.batch_generator import BatchGenerator, GenerationSummary

logger = logging.getLogger(__name__)


class GenerationWorker(QThread):
    """Worker thread running batch generation in the background."""

    # progress_updated(completed: int, total: int, pin: str, message: str)
    progress_updated = Signal(int, int, str, str)
    # status_message(message: str) - human readable log line
    status_message = Signal(str)
    # record_finished(result: RenderResult)
    record_finished = Signal(object)
    # batch_finished(summary: GenerationSummary)
    batch_finished = Signal(object)
    # error_occurred(error_message: str)
    error_occurred = Signal(str)

    def __init__(
        self,
        template: TemplateDefinition,
        records: List[SourceRecord],
        match_results: Dict[str, PhotoMatchResult],
        column_mappings: Dict[str, str],
        settings: RenderSettings,
        target_dir: Optional[Path] = None,
        workers: int = 0,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.template = template
        self.records = records
        self.match_results = match_results
        self.column_mappings = column_mappings
        self.settings = settings
        self.target_dir = target_dir
        self.workers = workers
        self._is_cancelled = False

    def cancel(self) -> None:
        """Request worker cancellation."""
        self._is_cancelled = True

    @property
    def is_cancelled(self) -> bool:
        """True when the run was cancelled."""
        return self._is_cancelled

    def run(self) -> None:
        """Thread execution entry point."""
        logger.info("GenerationWorker started for %d records.", len(self.records))
        try:
            summary = BatchGenerator.generate_batch(
                template=self.template,
                records=self.records,
                match_results=self.match_results,
                column_mappings=self.column_mappings,
                settings=self.settings,
                target_dir=self.target_dir,
                progress_callback=self._on_progress,
                record_callback=self._on_record,
                cancel_check=lambda: self._is_cancelled,
                workers=self.workers,
            )

            if self._is_cancelled:
                summary.cancelled = True

            self.batch_finished.emit(summary)

        except Exception as e:
            logger.exception("Unexpected error in GenerationWorker: %s", e)
            self.error_occurred.emit(str(e))

    def _on_progress(self, completed: int, total: int, pin: str, msg: str) -> None:
        self.progress_updated.emit(completed, total, pin, msg)

    def _on_record(self, result: RenderResult) -> None:
        self.record_finished.emit(result)
        if result.success:
            self.status_message.emit(
                f"[OK] Rendered PIN: {result.pin} -> {result.image_path}"
            )
        else:
            self.status_message.emit(
                f"[ERROR] Failed PIN: {result.pin} - {result.error_message}"
            )
