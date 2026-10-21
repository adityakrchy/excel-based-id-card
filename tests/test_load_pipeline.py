"""Tests for the streamed spreadsheet load pipeline (worker nodes)."""

from __future__ import annotations

import threading
from datetime import datetime
from pathlib import Path

import openpyxl
from PySide6.QtCore import Qt

import id_card_generator.data.load_pipeline as load_pipeline_module
from id_card_generator.core.models import SourceRecord
from id_card_generator.data.data_validator import DataValidator
from id_card_generator.data.excel_importer import ExcelImporter
from id_card_generator.data.load_pipeline import (
    LoadRequest,
    LoadStatus,
    SpreadsheetLoadPipeline,
    configured_chunk_size,
    process_pool_enabled,
)
from id_card_generator.ui.components.record_table import RecordTableModel


def make_workbook(path: Path, rows: int = 120) -> Path:
    """Build a mixed-content workbook: numbers, dates, NaN gaps, Kruti strings, blanks."""
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["PIN Number", "Employee ID", "Name", "Salary", "Joined On", "Kruti Text", ""])
    kruti_samples = ["dkehMd dke", "efUnze Tbk", "piA fjdk lka"]
    for i in range(rows):
        ws.append(
            [
                f"PIN{i:05d}" if i % 17 else f"  PIN{i:05d}  ",  # whitespace variant
                f"EMP-{i:04d}",
                f"Worker {i}",
                1000 + i + 0.5 if i % 4 == 0 else 1000 + i,      # mixed int/float column
                datetime(2024, 1, 1 + (i % 28)) if i % 3 else None,
                kruti_samples[i % len(kruti_samples)] if i % 5 == 0 else "",
                f"duplicate cell {i % 12}",                      # blank header column
            ]
        )
    wb.save(str(path))
    return path


# ---------------------------------------------------------------------------
# Golden parity: the streamed pipeline must match the legacy facade exactly.
# ---------------------------------------------------------------------------
def test_pipeline_matches_legacy_import(tmp_path):
    path = make_workbook(tmp_path / "parity.xlsx", rows=90)
    legacy_cols, legacy_records = ExcelImporter.import_data(path)

    pipeline = SpreadsheetLoadPipeline()
    result = pipeline.run_sync(LoadRequest(file_path=path))

    assert result.status == LoadStatus.COMPLETE
    assert result.columns == legacy_cols
    assert result.committed_rows == len(legacy_records) == 90
    assert result.report is not None
    assert len(result.annotations) == len(result.records)
    for got, want in zip(result.records, legacy_records):
        assert got.row_index == want.row_index
        assert got.pin == want.pin
        assert got.raw_pin == want.raw_pin
        assert got.data == want.data


def test_validation_annotations_match_mutation(tmp_path):
    """The non-mutating analysis produces the same lists mutate-then-check would."""
    records = [
        SourceRecord(row_index=i, raw_pin="", pin="", data={"n": str(i)})
        for i in (1, 2)
    ]
    records.append(
        SourceRecord(row_index=3, raw_pin=" dup ", pin="dup", data={})
    )
    records.append(
        SourceRecord(row_index=4, raw_pin="dup", pin="dup", data={})
    )

    report, annotations = DataValidator.analyze_records(records)
    # Nothing was written back to the records.
    assert all(not r.validation_errors and not r.validation_warnings for r in records)

    assert report.total_records == 4
    assert report.missing_pins == 2
    assert report.duplicate_pins == {"dup": 2}

    # The annotations mirror what validate_records would have done.
    DataValidator.validate_records(records)
    for record, (errors, warnings) in zip(records, annotations):
        assert record.validation_errors == errors
        assert record.validation_warnings == warnings


# ---------------------------------------------------------------------------
# Order guarantee across worker nodes
# ---------------------------------------------------------------------------
def test_chunks_commit_in_strict_order(tmp_path, monkeypatch):
    monkeypatch.setenv("ID_STREAM_LOAD_CHUNK", "100")
    monkeypatch.setenv("ID_STREAM_LOAD_WORKERS", "3")
    assert configured_chunk_size(600) == 100

    path = make_workbook(tmp_path / "chunks.xlsx", rows=600)
    pipeline = SpreadsheetLoadPipeline()
    chunks: list[tuple[int, int, int]] = []

    pipeline.chunk_ready.connect(
        lambda _token, start, records: chunks.append(
            (start, len(records), records[0].row_index if records else -1)
        ),
        Qt.DirectConnection,
    )
    result = pipeline.run_sync(LoadRequest(file_path=path))

    assert result.committed_rows == 600
    assert len(chunks) == 6
    starts = [start for start, _, _ in chunks]
    assert starts == [0, 100, 200, 300, 400, 500]
    # The first row of every chunk continues the previous one.
    assert [first for _, _, first in chunks] == list(range(1, 601, 100))
    # The merged sheet is contiguous and monotonically indexed.
    indexes = [r.row_index for r in result.records]
    assert indexes == list(range(1, 601))


def test_streamed_append_matches_the_full_reset(qtbot):
    """Appending growing chunks produces the same table as one set_records call."""
    records = [
        SourceRecord(
            row_index=i,
            raw_pin=f"00{i}",
            pin=f"00{i}",
            data={"Name": f"Name {i}", "Dept": "X"},
        )
        for i in range(1, 13)
    ]

    full = RecordTableModel()
    full.set_records(records, ["PIN Number", "Name"])

    stream = RecordTableModel()
    stream.set_columns(["PIN Number", "Name"])
    for part in (records[:5], records[5:], records[:0]):
        stream.append_records(part)

    assert full.rowCount() == stream.rowCount() == 12
    for row in range(full.rowCount()):
        for col in range(full.columnCount()):
            assert (
                full.data(full.index(row, col)) == stream.data(stream.index(row, col))
            ), f"row {row}, column {col} diverged"
    # Searching still works on top of the appended state.
    stream.set_filter("name 3")
    assert stream.rowCount() == 1


# ---------------------------------------------------------------------------
# Cancellation and failure semantics
# ---------------------------------------------------------------------------
def test_cancel_from_another_thread_leaves_a_partial_result(tmp_path, monkeypatch):
    monkeypatch.setenv("ID_STREAM_LOAD_CHUNK", "50")
    monkeypatch.setenv("ID_STREAM_LOAD_WORKERS", "2")
    path = make_workbook(tmp_path / "cancel.xlsx", rows=12000)

    pipeline = SpreadsheetLoadPipeline()
    outcome: dict = {}
    landed = {"chunks": 0}
    # Direct connection: the emission happens on the runner thread while the
    # main thread is sleeping, so the queued form would never fire here.
    pipeline.chunk_ready.connect(
        lambda *_: landed.__setitem__("chunks", landed["chunks"] + 1),
        Qt.DirectConnection,
    )

    def runner():
        try:
            outcome["result"] = pipeline.run_sync(LoadRequest(file_path=path))
        except Exception as e:  # pragma: no cover - guards the failure case
            outcome["error"] = e

    thread = threading.Thread(target=runner)
    thread.start()
    import time

    for _ in range(600):  # wait until at least two chunks streamed in
        if landed["chunks"] >= 2 or outcome.get("result") is not None:
            break
        time.sleep(0.02)
    pipeline.cancel()
    thread.join(30)

    assert "error" not in outcome
    result = outcome["result"]
    assert result.status == LoadStatus.CANCELLED
    assert result.committed_rows < result.total_rows
    # Only the ordered prefix was committed - no holes in the sheet.
    indexes = [r.row_index for r in result.records]
    assert indexes == list(range(1, result.committed_rows + 1))


def test_failed_chunk_stops_at_the_gap(tmp_path, monkeypatch):
    monkeypatch.setenv("ID_STREAM_LOAD_CHUNK", "10")
    path = make_workbook(tmp_path / "gap.xlsx", rows=40)

    original = load_pipeline_module.convert_chunk_job

    def failing_middle(job):
        if job["start"] == 20:
            raise RuntimeError("conversion exploded")
        return original(job)

    monkeypatch.setattr(load_pipeline_module, "convert_chunk_job", failing_middle)

    pipeline = SpreadsheetLoadPipeline()
    result = pipeline.run_sync(LoadRequest(file_path=path))

    assert result.status == LoadStatus.PARTIAL
    assert result.failed_chunks == 1
    assert result.committed_rows == 20
    indexes = [r.row_index for r in result.records]
    assert indexes == list(range(1, 21))  # rows before the gap only


def test_unreadable_file_fails_cleanly(tmp_path):
    broken = tmp_path / "broken.xlsx"
    broken.write_text("this is not a workbook")

    pipeline = SpreadsheetLoadPipeline()
    result = pipeline.run_sync(LoadRequest(file_path=broken))

    assert result.status == LoadStatus.FAILED
    assert result.error_message != ""
    assert result.committed_rows == 0


def test_unknown_sheet_name_fails(tmp_path):
    path = make_workbook(tmp_path / "one_sheet.xlsx", rows=5)

    pipeline = SpreadsheetLoadPipeline()
    result = pipeline.run_sync(
        LoadRequest(file_path=path, sheet_name="Does Not Exist")
    )

    assert result.error_message != ""
    assert "Does Not Exist" in result.error_message


# ---------------------------------------------------------------------------
# Production path through the TaskManager (request_load)
# ---------------------------------------------------------------------------
def test_request_load_streams_through_the_task_manager(qtbot, tmp_path, monkeypatch):
    monkeypatch.setenv("ID_STREAM_LOAD_CHUNK", "300")
    path = make_workbook(tmp_path / "tasked.xlsx", rows=1000)

    pipeline = SpreadsheetLoadPipeline()
    seen: dict = {"columns": None, "chunks": [], "finished": None, "progress": 0}

    def on_columns(token, columns, total_rows):
        seen["columns"] = (token, list(columns), total_rows)

    def on_chunk(token, start, records):
        seen["chunks"].append((token, start, len(records)))

    def on_rows(token, committed, total, message):
        seen["progress"] += 1

    def on_finished(result):
        seen["finished"] = result

    pipeline.columns_ready.connect(on_columns)
    pipeline.chunk_ready.connect(on_chunk)
    pipeline.rows_loaded.connect(on_rows)
    pipeline.import_finished.connect(on_finished)

    token = pipeline.request_load(LoadRequest(file_path=path))
    qtbot.waitUntil(lambda: seen["finished"] is not None, timeout=30000)

    result = seen["finished"]
    assert result.status == LoadStatus.COMPLETE
    assert result.run_id == token
    assert pipeline.active_run == -1  # the pipeline went back to idle
    assert seen["columns"] is not None
    event_token, columns, total = seen["columns"]
    assert event_token == token
    assert total == 1000
    assert len(columns) == 7
    assert sum(count for _, _, count in seen["chunks"]) == 1000
    starts = [start for _, start, _ in seen["chunks"]]
    assert starts == sorted(starts) and starts[0] == 0
    assert seen["progress"] > 0


# ---------------------------------------------------------------------------
# Optional process-pool backend (Phase 4, feature-flagged)
# ---------------------------------------------------------------------------
def test_process_pool_backend_is_flagged(tmp_path, monkeypatch):
    monkeypatch.setenv("ID_STREAM_PROCESS_POOL", "1")
    monkeypatch.setenv("ID_STREAM_LOAD_WORKERS", "2")
    assert process_pool_enabled()

    path = make_workbook(tmp_path / "processes.xlsx", rows=64)
    legacy_cols, legacy_records = ExcelImporter.import_data(path)

    pipeline = SpreadsheetLoadPipeline()
    result = pipeline.run_sync(LoadRequest(file_path=path))

    # The backend may fall back to threads on platforms where spawning is
    # restricted, but the output must stay identical either way.
    assert result.status == LoadStatus.COMPLETE
    assert result.backend in ("processes", "threads")
    assert result.columns == legacy_cols
    assert result.committed_rows == len(legacy_records)
    for got, want in zip(result.records, legacy_records):
        assert got.row_index == want.row_index
        assert got.data == want.data


# ---------------------------------------------------------------------------
# UI responsiveness while a large import streams in
# ---------------------------------------------------------------------------
def test_page_import_keeps_event_loop_alive(qtbot, tmp_path, monkeypatch):
    """A big CSV loads through the streamed pipeline without starving the GUI."""
    import csv as csv_module

    from PySide6.QtCore import QTimer

    from id_card_generator.ui.data_source_page import DataSourcePage

    monkeypatch.setenv("ID_STREAM_LOAD_CHUNK", "250")
    rows = 6000
    path = tmp_path / "big.csv"
    with path.open("w", newline="") as f:
        writer = csv_module.writer(f)
        writer.writerow(
            ["PIN Number", "Employee ID", "Name", "Designation", "Salary", "Kruti Text"]
        )
        for i in range(rows):
            writer.writerow(
                [
                    f"PIN{i:06d}",
                    f"EMP-{i:04d}",
                    f"Worker {i}",
                    "Officer",
                    1000 + i,
                    "dkehMd dke" if i % 7 == 0 else "",
                ]
            )

    page = DataSourcePage()
    qtbot.addWidget(page)

    ticks: list[int] = []
    ticker = QTimer()
    ticker.setInterval(20)
    ticker.timeout.connect(lambda: ticks.append(1))
    ticker.start()

    page.load_file(path)
    # Poll instead of waitSignal: the repo's threaded photo tests use the
    # same pattern, and cross-thread queued signals proved slippery here.
    qtbot.waitUntil(lambda: len(page.records) >= rows, timeout=30000)
    qtbot.wait(120)  # let the terminal handler land (summary + notice)
    ticker.stop()

    assert len(page.records) == rows
    assert page.record_model.rowCount() == rows
    assert not page._import_busy, "the import never finished"
    # The GUI thread kept painting while the pipeline converted the rows.
    assert len(ticks) > 5, f"UI starved: only {len(ticks)} timer pulses during load"
