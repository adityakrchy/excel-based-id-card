"""Chunked, cancellable spreadsheet load pipeline backed by worker nodes.

The pipeline replaces the historical blocking call chain
(``ExcelImporter.import_data`` on the GUI thread) with four stages:

* **Stage A** - a single pass over the workbook capturing the raw cell matrix
  (values plus sparse legacy font names) on one worker thread.
* **Stage B** - the matrix is split into row chunks that fan out over a
  scalable pool of worker nodes (threads by default, processes when the
  feature flag ``ID_STREAM_PROCESS_POOL=1`` is set). Chunks are committed to
  the GUI in strict order, so the table streams in progressively while the
  conversion races ahead.
* **Stage C** - validation runs once over the committed records on the
  driver thread (duplication detection needs a global PIN counter) without
  mutating the records, so the GUI thread stays race-free.
* **Stage D** - the merged :class:`LoadResult` (report + annotations +
  runtime metrics) is handed back to the UI.

Cancellation and progress are wired through the central :class:`TaskManager`
while the pipeline itself keeps a ``threading.Event`` for instant, race-free
cancellation of the stage-B pool.
"""

from __future__ import annotations

import concurrent.futures
import logging
import os
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple

from PySide6.QtCore import QObject, QRunnable, QThreadPool, QThread, Signal

from id_card_generator.core.models import SourceRecord
from id_card_generator.core.process_metrics import ProcessMetrics
from id_card_generator.data.data_validator import DataValidator, ValidationReport
from id_card_generator.data.excel_importer import (
    ExcelSheetMatrix,
    ExcelImporter,
    LoadCancelled,
    convert_chunk_job,
)
from id_card_generator.tasks.task_manager import TaskManager

logger = logging.getLogger(__name__)

DEFAULT_ROWS_PER_CHUNK = 2500
MIN_ROWS_PER_CHUNK = 200

# Soft memory guard: log a warning when the import peak crests this (MB).
MEMORY_WARN_MB = 1500.0


class LoadStatus:
    """Final outcome of a load run."""

    COMPLETE = "complete"
    PARTIAL = "partial"
    CANCELLED = "cancelled"
    FAILED = "failed"


@dataclass
class LoadRequest:
    """Everything needed to run one spreadsheet load."""

    file_path: Path
    sheet_name: Optional[str] = None
    header_row: int = 0
    hindi_mode: str = "auto"
    pin_column_hint: Optional[str] = None


@dataclass
class LoadResult:
    """Outcome of one pipeline run, shared with the GUI as a plain object."""

    status: str = LoadStatus.COMPLETE
    run_id: int = 0
    columns: List[str] = field(default_factory=list)
    records: List[SourceRecord] = field(default_factory=list)
    total_rows: int = 0
    committed_rows: int = 0
    failed_chunks: int = 0
    chunk_count: int = 0
    report: Optional[ValidationReport] = None
    annotations: List[Tuple[List[str], List[str]]] = field(default_factory=list)
    worker_count: int = 1
    backend: str = "threads"
    elapsed_seconds: float = 0.0
    rows_per_second: float = 0.0
    peak_memory_mb: float = 0.0
    error_message: str = ""

    def reset_stage_b(self) -> None:
        """Clear stage-B bookkeeping (used when a backend falls back)."""
        self.records = []
        self.committed_rows = 0
        self.failed_chunks = 0
        self.chunk_count = 0
        self.error_message = ""


def configured_worker_count() -> int:
    """Worker-node count for stage B (env override ``ID_STREAM_LOAD_WORKERS``)."""
    override = os.environ.get("ID_STREAM_LOAD_WORKERS")
    if override:
        try:
            return max(1, int(override))
        except ValueError:
            logger.warning("Ignoring invalid ID_STREAM_LOAD_WORKERS=%r", override)
    cores = QThread.idealThreadCount() or 4
    return max(1, min(4, cores - 1))


def process_pool_enabled() -> bool:
    """True when true multiprocess conversion is requested via feature flag."""
    return os.environ.get("ID_STREAM_PROCESS_POOL", "").strip() == "1"


def configured_chunk_size(total_rows: int) -> int:
    """Rows per chunk (env override ``ID_STREAM_LOAD_CHUNK``).

    The automatic default scales between :data:`MIN_ROWS_PER_CHUNK` and
    :data:`DEFAULT_ROWS_PER_CHUNK`; an explicit override is honoured as-is
    (above a small sanity floor) so tuning tests can force small chunks.
    """
    override = os.environ.get("ID_STREAM_LOAD_CHUNK")
    if override:
        try:
            return max(20, int(override))
        except ValueError:
            logger.warning("Ignoring invalid ID_STREAM_LOAD_CHUNK=%r", override)
    return max(MIN_ROWS_PER_CHUNK, min(DEFAULT_ROWS_PER_CHUNK, max(total_rows, MIN_ROWS_PER_CHUNK)))


class _ChunkRunner(QRunnable):
    """Converts one chunk job on a worker node and stores the ordered result.

    Results are stored under the chunk's positional index, never under the
    row offset, so the ordering bookkeeping stays trivial.
    """

    def __init__(self, pipeline: "SpreadsheetLoadPipeline", job: Dict[str, Any], index: int):
        super().__init__()
        self._pipeline = pipeline
        self._job = job
        self._index = index
        self.setAutoDelete(True)

    def run(self) -> None:
        if self._pipeline._cancel_event.is_set():
            return
        try:
            _, _, records = convert_chunk_job(self._job)
            self._pipeline._store_chunk_result(self._index, records)
        except Exception as e:  # report at the end; partial data keeps flowing
            logger.error("Chunk conversion failed at row %s: %s", self._index, e)
            self._pipeline._store_chunk_error(self._index, e)


class SpreadsheetLoadPipeline(QObject):
    """Runs Stage A-D on worker threads and streams commits to the GUI thread.

    Only the driver thread may emit :attr:`chunk_ready`, so commit order on
    the receiving (GUI) side is guaranteed regardless of which worker node
    finishes first. When the pipeline lives on the GUI thread, its signals
    use queued connections, so every callback lands on the GUI event loop.
    """

    import_started = Signal(str)             # display file name
    columns_ready = Signal(int, list, int)   # run token, columns, total_rows
    stage_changed = Signal(str)              # human readable stage label
    rows_loaded = Signal(int, int, int, str) # run token, committed, total, message
    chunk_ready = Signal(int, int, object)   # run token, start_index, records chunk
    import_finished = Signal(object)         # LoadResult (complete)
    import_failed = Signal(str, object)      # message, LoadResult (partial)
    import_cancelled = Signal(object)        # LoadResult (partial)

    def __init__(self, parent: Optional[QObject] = None) -> None:
        super().__init__(parent)
        self._cancel_event = threading.Event()
        self._active_token: int = -1
        self._task_id: Optional[str] = None
        self._results: Dict[int, List[SourceRecord]] = {}
        self._errors: Dict[int, str] = {}
        self._lock = threading.Lock()
        self._token = 0
        self._pool = QThreadPool()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def is_running(self) -> bool:
        """True while a load task is active."""
        return self._task_id is not None

    @property
    def active_run(self) -> int:
        """The token of the run currently believed to be active (-1 when idle)."""
        return self._active_token

    def cancel(self) -> None:
        """Cancel the active load (safe to call repeatedly)."""
        self._cancel_event.set()
        task_id = self._task_id
        if task_id:
            TaskManager.instance().cancel_task(task_id)
            self._task_id = None

    def shutdown(self) -> None:
        """Stop everything; called on window close."""
        self.cancel()
        try:
            self._pool.waitForDone(3000)
        except Exception:  # pragma: no cover - defensive
            logger.debug("Chunk pool shutdown failed", exc_info=True)

    def request_load(self, request: LoadRequest) -> int:
        """Start a load run through the central TaskManager, cancelling any prior one."""
        self.cancel()
        self._cancel_event.clear()
        with self._lock:
            self._results.clear()
            self._errors.clear()
        self._token += 1
        token = self._token
        self._active_token = token

        def task_fn(progress_callback: Callable, is_cancelled: Callable[[], bool]) -> LoadResult:
            try:
                return self._execute(request, token, progress_callback, is_cancelled)
            except Exception as e:  # guarantee the UI never stays busy forever
                logger.exception("Import task crashed unexpectedly")
                fallback = LoadResult(worker_count=configured_worker_count())
                fallback.run_id = token
                fallback.status = LoadStatus.FAILED
                fallback.error_message = str(e)
                self._emit_if_current(token, lambda: self.import_failed.emit(str(e), fallback))
                self._finalize(token)
                raise

        self._task_id = TaskManager.instance().submit_task(
            f"Import {request.file_path.name}", task_fn, cancellable=True
        )
        self.import_started.emit(request.file_path.name)
        return token

    def run_sync(self, request: LoadRequest) -> LoadResult:
        """Run the whole pipeline on the calling thread (benchmarks/tests)."""
        self.cancel()
        self._cancel_event.clear()
        with self._lock:
            self._results.clear()
            self._errors.clear()
        token = 0
        self._active_token = token
        self._task_id = "sync"
        try:
            return self._execute(request, token, None, None)
        finally:
            self._task_id = None

    # ------------------------------------------------------------------
    # Pipeline stages
    # ------------------------------------------------------------------
    def _is_current(self, token: int) -> bool:
        return token == self._active_token and not self._cancel_event.is_set()

    def _emit_if_current(self, token: int, emitter: Callable[[], None]) -> None:
        if self._is_current(token):
            emitter()

    def _execute(
        self,
        request: LoadRequest,
        token: int,
        progress_callback: Optional[Callable[[int, int, str], None]],
        is_cancelled: Optional[Callable[[], bool]],
    ) -> LoadResult:
        """Stage A -> B -> C -> D driver. Runs on a worker thread (or the caller)."""

        def cancelled() -> bool:
            if self._cancel_event.is_set():
                return True
            return bool(is_cancelled()) if is_cancelled else False

        result = LoadResult(worker_count=configured_worker_count(), backend="threads")
        result.run_id = token
        started = time.monotonic()
        metrics = ProcessMetrics()

        # ---------------- Stage A: capture the raw sheet matrix ----------
        self._emit_if_current(token, lambda: self.stage_changed.emit("Reading workbook"))
        try:
            matrix = ExcelImporter.load_matrix(
                request.file_path,
                sheet_name=request.sheet_name,
                header_row=request.header_row,
                hindi_font_mode=request.hindi_mode,
                pin_column_hint=request.pin_column_hint,
                progress_callback=progress_callback,
                is_cancelled=cancelled,
            )
        except LoadCancelled:
            result.status = LoadStatus.CANCELLED
            self._emit_if_current(token, lambda: self.import_cancelled.emit(result))
            self._finalize(token)
            return result
        except Exception as e:
            result.status = LoadStatus.FAILED
            result.error_message = str(e)
            self._emit_if_current(token, lambda: self.import_failed.emit(str(e), result))
            self._finalize(token)
            return result

        result.columns = list(matrix.columns)
        result.total_rows = matrix.total_rows
        _, mem = metrics.sample()
        result.peak_memory_mb = mem

        self._emit_if_current(
            token,
            lambda: self.columns_ready.emit(token, list(matrix.columns), matrix.total_rows),
        )
        self._emit_if_current(token, lambda: self.stage_changed.emit("Converting records"))

        # ---------------- Stage B: fan out conversion over worker nodes --
        chunk_rows = configured_chunk_size(matrix.total_rows)
        jobs = ExcelImporter.slice_chunk_jobs(matrix, chunk_rows, request.hindi_mode)
        result.chunk_count = len(jobs)
        if not jobs:
            result.elapsed_seconds = max(time.monotonic() - started, 1e-6)
            self._emit_if_current(token, lambda: self.import_finished.emit(result))
            self._finalize(token)
            self._log_metrics(result)
            return result

        interrupted = False
        try:
            if process_pool_enabled():
                result.backend = "processes"
                logger.info(
                    "Stage B on the process pool: %d jobs over %d workers",
                    len(jobs),
                    result.worker_count,
                )
            interrupted = self._run_stage_b(jobs, token, matrix, result, metrics, cancelled)
        except Exception as e:  # backend failure -> guaranteed thread fallback
            logger.warning("Stage B backend failed (%s); retrying with the thread backend", e)
            result.reset_stage_b()
            result.total_rows = matrix.total_rows
            result.backend = "threads"
            with self._lock:
                self._results.clear()
                self._errors.clear()
            interrupted = self._run_stage_b_threads(jobs, token, matrix, result, metrics, cancelled)

        elapsed_partial = max(time.monotonic() - started, 1e-6)
        _, mem = metrics.sample()
        result.peak_memory_mb = max(result.peak_memory_mb, mem)

        if interrupted or cancelled():
            result.status = LoadStatus.CANCELLED
            result.elapsed_seconds = elapsed_partial
            result.rows_per_second = result.committed_rows / elapsed_partial
            self._release_staging()
            self._emit_if_current(token, lambda: self.import_cancelled.emit(result))
            self._finalize(token)
            self._log_metrics(result)
            return result

        if result.failed_chunks:
            result.status = LoadStatus.PARTIAL
            result.elapsed_seconds = elapsed_partial
            result.rows_per_second = result.committed_rows / elapsed_partial
            internal = result.error_message or "A record chunk failed to convert."
            result.error_message = (
                f"{result.failed_chunks} of {result.chunk_count} record chunks failed - "
                f"{result.committed_rows:,} of {result.total_rows:,} rows are shown. "
                "Run Re-import to try again."
            )
            self._release_staging()
            self._emit_if_current(token, lambda: self.import_failed.emit(internal, result))
            self._finalize(token)
            self._log_metrics(result)
            return result

        # ---------------- Stage C: global validation (worker thread) -----
        self._emit_if_current(token, lambda: self.stage_changed.emit("Validating records"))
        if not cancelled():
            report, annotations = DataValidator.analyze_records(result.records)
            result.report = report
            result.annotations = annotations

        elapsed = max(time.monotonic() - started, 1e-6)
        result.status = LoadStatus.COMPLETE
        result.elapsed_seconds = elapsed
        result.rows_per_second = result.committed_rows / elapsed
        self._release_staging()
        self._emit_if_current(token, lambda: self.import_finished.emit(result))
        self._finalize(token)
        self._log_metrics(result)
        return result

    # ------------------------------------------------------------------
    # Stage B backends
    # ------------------------------------------------------------------
    def _run_stage_b(
        self,
        jobs: List[Dict[str, Any]],
        token: int,
        matrix: ExcelSheetMatrix,
        result: LoadResult,
        metrics: ProcessMetrics,
        cancelled: Callable[[], bool],
    ) -> bool:
        """Dispatch chunk jobs across the worker nodes and commit in order."""
        if not jobs:
            return False
        if process_pool_enabled():
            return self._run_stage_b_processes(jobs, token, matrix, result, metrics, cancelled)
        result.backend = "threads"
        return self._run_stage_b_threads(jobs, token, matrix, result, metrics, cancelled)

    def _run_stage_b_threads(
        self,
        jobs: List[Dict[str, Any]],
        token: int,
        matrix: ExcelSheetMatrix,
        result: LoadResult,
        metrics: ProcessMetrics,
        cancelled: Callable[[], bool],
    ) -> bool:
        self._pool.setMaxThreadCount(result.worker_count)
        for index, job in enumerate(jobs):
            self._pool.start(_ChunkRunner(self, job, index))
        return self._drain_ordered(token, matrix, result, metrics, cancelled)

    def _run_stage_b_processes(
        self,
        jobs: List[Dict[str, Any]],
        token: int,
        matrix: ExcelSheetMatrix,
        result: LoadResult,
        metrics: ProcessMetrics,
        cancelled: Callable[[], bool],
    ) -> bool:
        """Optional true-multiprocess conversion (GIL-free, spawn based)."""
        executor = concurrent.futures.ProcessPoolExecutor(max_workers=result.worker_count)
        futures = [executor.submit(convert_chunk_job, job) for job in jobs]
        next_chunk = 0
        try:
            while next_chunk < len(futures):
                if cancelled():
                    return True
                try:
                    _, _, records = futures[next_chunk].result(timeout=0.05)
                    self._store_chunk_result(next_chunk, records)
                except concurrent.futures.TimeoutError:
                    _, mem = metrics.sample()
                    result.peak_memory_mb = max(result.peak_memory_mb, mem)
                    continue
                except Exception as e:  # worker exception -> gap in the chain
                    result.error_message = result.error_message or repr(e)
                    result.failed_chunks += 1
                    break
                self._commit_chunk_in_order(token, result, next_chunk)
                next_chunk += 1
            return False
        finally:
            if self._cancel_event.is_set():
                executor.shutdown(wait=False, cancel_futures=True)
            else:
                executor.shutdown(wait=True)

    # ------------------------------------------------------------------
    # Ordered commit machinery (shared by both backends)
    # ------------------------------------------------------------------
    def _drain_ordered(
        self,
        token: int,
        matrix: ExcelSheetMatrix,
        result: LoadResult,
        metrics: ProcessMetrics,
        cancelled: Callable[[], bool],
    ) -> bool:
        """Consume chunks strictly in order, committing them to the GUI.

        Returns ``True`` when cancellation interrupted the flow. Committing
        stops at the first gap (a failed chunk) so record indexes stay aligned.
        """
        next_chunk = 0
        while next_chunk < result.chunk_count:
            if cancelled():
                return True
            state = self._chunk_state(next_chunk)
            if state == "error":
                with self._lock:
                    message = self._errors.pop(next_chunk, None)
                if message:
                    result.error_message = result.error_message or message
                result.failed_chunks += 1
                break
            if state == "ready":
                self._commit_chunk_in_order(token, result, next_chunk)
                next_chunk += 1
                continue
            # pending: probe whether every runnable retired without staging.
            if self._all_staged_quiet():
                with self._lock:
                    self._errors.setdefault(
                        next_chunk, "Chunk produced no result (worker node lost)"
                    )
                continue
            _, mem = metrics.sample()
            result.peak_memory_mb = max(result.peak_memory_mb, mem)
            self._pool.waitForDone(33)
        return False

    def _store_chunk_result(self, start: int, records: List[SourceRecord]) -> None:
        with self._lock:
            self._results[start] = records

    def _store_chunk_error(self, start: int, error: Exception) -> None:
        with self._lock:
            self._errors.setdefault(start, repr(error))

    def _chunk_state(self, next_chunk: int) -> str:
        """Classify ``next_chunk``: ``ready`` | ``error`` | ``pending``."""
        with self._lock:
            if next_chunk in self._errors:
                return "error"
            if next_chunk in self._results:
                return "ready"
        return "pending"

    def _all_staged_quiet(self) -> bool:
        """True when the pool is idle and nothing new has been staged."""
        with self._lock:
            quiet = not self._results and not self._errors
        return quiet and self._pool.activeThreadCount() == 0

    def _commit_chunk_in_order(self, token: int, result: LoadResult, next_chunk: int) -> None:
        """Commit chunk ``next_chunk`` (staged by the positional index).

        Chunks are contiguous slices of the sheet, so the streaming start
        index of the next chunk equals ``result.committed_rows``. The
        receiver only relies on the emit order (it appends chunks as they
        arrive), which is why every commit happens right here.
        """
        with self._lock:
            records = self._results.pop(next_chunk)
            if records is None:  # pragma: no cover - defensive
                return
            start = result.committed_rows
            result.records.extend(records)
            result.committed_rows = len(result.records)
        message = f"{result.committed_rows:,} / {result.total_rows:,} records"
        self._emit_if_current(
            token,
            lambda s=start, r=records: self.chunk_ready.emit(token, s, r),
        )
        self._emit_if_current(
            token,
            lambda c=result.committed_rows, m=message: self.rows_loaded.emit(
                token, c, result.total_rows, m
            ),
        )

    def _release_staging(self) -> None:
        """Drop pending staging state (committed prefix already in result)."""
        with self._lock:
            self._results.clear()
            self._errors.clear()

    def _finalize(self, token: int) -> None:
        """Mark the pipeline idle when the finished run is the current one."""
        if token == self._active_token:
            self._active_token = -1
            self._task_id = None

    def _log_metrics(self, result: LoadResult) -> None:  # pragma: no cover - logging only
        logger.info(
            "Load pipeline finished: %s of %s rows in %.2fs (%.0f rows/s, %s workers on %s%s, peak %.0f MB)",
            f"{result.committed_rows:,}",
            f"{result.total_rows:,}",
            result.elapsed_seconds,
            result.rows_per_second,
            result.worker_count,
            result.backend,
            ", %d chunk failures" % result.failed_chunks if result.failed_chunks else "",
            result.peak_memory_mb,
        )
        if result.peak_memory_mb > MEMORY_WARN_MB:
            logger.warning(
                "Import peak memory is high (%.0f MB); consider a smaller sheet or fewer open previews.",
                result.peak_memory_mb,
            )
