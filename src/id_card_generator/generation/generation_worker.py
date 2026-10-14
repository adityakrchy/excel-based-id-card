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

    # Signals:
    # progress_updated(completed: int, total: int, pin: str, message: str)
    progress_updated = Signal(int, int, str, str)
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
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.template = template
        self.records = records
        self.match_results = match_results
        self.column_mappings = column_mappings
        self.settings = settings
        self.target_dir = target_dir
        self._is_cancelled = False

    def cancel(self) -> None:
        """Request worker cancellation."""
        self._is_cancelled = True

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
                cancel_check=lambda: self._is_cancelled,
            )
            self.batch_finished.emit(summary)
        except Exception as e:
            logger.error("Unexpected error in GenerationWorker: %s", e)
            self.error_occurred.emit(str(e))

    def _on_progress(self, completed: int, total: int, pin: str, msg: str) -> None:
        self.progress_updated.emit(completed, total, pin, msg)
