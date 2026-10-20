"""Background worker for matching records to photographs and staging them.

Matching tens of thousands of records and copying the matched photographs
into the project workspace must not block the interface, so the whole
pipeline runs on a worker thread.  The worker owns its own matcher instance
so the interface can keep using the live matcher without a data race.
"""

import logging
from typing import Dict, List, Optional

from PySide6.QtCore import QThread, Signal

from id_card_generator.core.models import PhotoMatchResult, ProjectConfiguration, SourceRecord
from id_card_generator.data.photo_matcher import MatchSummary, PhotoMatcher

logger = logging.getLogger(__name__)


class PhotoMatchWorker(QThread):
    """Matches the records against the photo index and stages the results."""

    # (match_results, summary, copied_count)
    matching_finished = Signal(dict, object, int)
    # (error message)
    matching_failed = Signal(str)

    def __init__(
        self,
        matcher: PhotoMatcher,
        records: List[SourceRecord],
        project_config: Optional[ProjectConfiguration] = None,
        copy_to_workspace: bool = True,
        parent=None,
    ):
        super().__init__(parent)
        self._records = records
        self._project_config = project_config
        self._copy_to_workspace = copy_to_workspace
        self._is_cancelled = False

        # A private matcher keeps the live one untouched while we work.
        self._matcher = PhotoMatcher()
        self._matcher.set_indexes(matcher.index, matcher.lower_index)
        self._matcher.set_key_column(matcher.key_column)
        self._matcher.set_affixes(prefix=matcher.prefix, suffix=matcher.suffix)
        self._matcher.overrides = dict(matcher.overrides)

    def cancel(self) -> None:
        """Request cancellation of the running match."""
        self._is_cancelled = True

    def run(self) -> None:
        try:
            if self._is_cancelled:
                return

            results, summary = self._matcher.match_all(self._records)

            if self._is_cancelled:
                return

            copied_count = 0
            if self._copy_to_workspace and self._project_config is not None:
                from id_card_generator.core.project_manager import ProjectManager

                results, copied_count = ProjectManager.copy_matched_photos_to_workspace(
                    self._project_config, results
                )

            if self._is_cancelled:
                return

            self.matching_finished.emit(results, summary, copied_count)

        except Exception as e:
            logger.exception("Error in photo matching thread: %s", e)
            self.matching_failed.emit(str(e))
