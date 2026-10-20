"""Tests for the batch generation module.

The generation page and the generation worker had drifted apart: the page
connected to signals (``status_message``, ``card_generated``,
``generation_finished``) that the worker never declared, so pressing
"Launch Batch Generation" raised an ``AttributeError`` and the run never
started.  These tests lock the two sides together and cover the parallel
rendering path.
"""

import time
from pathlib import Path

import pytest

from id_card_generator.core.models import (
    CanvasElement,
    PhotoMatchResult,
    RenderResult,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.core.constants import MatchStatus
from id_card_generator.generation.batch_generator import BatchGenerator
from id_card_generator.generation.generation_worker import GenerationWorker
from id_card_generator.ui.generation_page import GenerationPage


def _template() -> TemplateDefinition:
    """A minimal but complete card template."""
    template = TemplateDefinition(
        name="Test Card",
        width_px=320,
        height_px=200,
        dpi=300,
        background_color="#FFFFFF",
    )
    template.elements = [
        CanvasElement(
            id="title",
            name="Title",
            type="static_text",
            x=20,
            y=20,
            width=280,
            height=40,
            static_content="Hello",
            z_index=1,
        )
    ]
    return template


def _records(count: int) -> list:
    return [
        SourceRecord(
            row_index=i,
            raw_pin=f"{i:06d}",
            pin=f"{i:06d}",
            data={"PIN Number": f"{i:06d}", "Name": f"Person {i}"},
        )
        for i in range(count)
    ]


# ---------------------------------------------------------------------------
# Worker / page contract
# ---------------------------------------------------------------------------
def test_worker_exposes_every_signal_the_page_uses():
    """The page must only connect to signals the worker actually declares."""
    for signal_name in (
        "progress_updated",
        "status_message",
        "record_finished",
        "batch_finished",
        "error_occurred",
    ):
        assert hasattr(GenerationWorker, signal_name), signal_name


def test_page_connects_only_to_existing_signals(qtbot):
    """Connecting the page to the worker must not raise."""
    page = GenerationPage()
    qtbot.addWidget(page)
    page.show()

    template = _template()
    page.set_generation_context(
        template=template,
        records=_records(3),
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
    )

    worker = GenerationWorker(
        template=template,
        records=[],
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
    )
    # The same wiring the page performs in _start_generation.
    worker.progress_updated.connect(page._on_progress)
    worker.status_message.connect(page._on_status)
    worker.record_finished.connect(page._on_card_generated)
    worker.batch_finished.connect(page._on_finished)
    worker.error_occurred.connect(page._on_error)
    worker.deleteLater()


def test_generation_runs_end_to_end(qtbot, tmp_path: Path):
    """A full batch run renders every card and reports the summary."""
    page = GenerationPage()
    qtbot.addWidget(page)
    page.show()

    template = _template()
    records = _records(4)
    page.set_generation_context(
        template=template,
        records=records,
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
    )

    summaries = []
    page.generation_completed.connect(summaries.append)

    page._start_generation()

    for _ in range(400):
        if summaries:
            break
        qtbot.wait(25)

    assert summaries, "the generation did not report a result"
    summary = summaries[0]
    assert summary.completed_count == 4
    assert summary.failed_count == 0
    assert len(summary.results) == 4
    assert summary.cancelled is False

    # The page is usable again and the navigation is unlocked.
    assert page.btn_generate.isEnabled()
    assert not page.btn_cancel.isEnabled()
    assert page.btn_goto_review.isEnabled()
    page.shutdown()


def test_generation_reports_a_missing_template(qtbot):
    """Without a template the run is refused with a hint, not a crash."""
    page = GenerationPage()
    qtbot.addWidget(page)
    page.show()

    page.set_generation_context(
        template=None,
        records=_records(2),
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
    )

    page._start_generation()
    assert not page.notice.isHidden()
    assert page.btn_generate.isEnabled()


def test_generation_reports_missing_records(qtbot):
    """Without records the run is refused with a hint."""
    page = GenerationPage()
    qtbot.addWidget(page)
    page.show()

    page.set_generation_context(
        template=_template(),
        records=[],
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
    )

    page._start_generation()
    assert not page.notice.isHidden()


# ---------------------------------------------------------------------------
# Batch generator
# ---------------------------------------------------------------------------
def test_parallel_generation_keeps_the_record_order(tmp_path: Path):
    """The results follow the order of the records, not the render order."""
    records = _records(40)
    summary = BatchGenerator.generate_batch(
        template=_template(),
        records=records,
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
        target_dir=tmp_path,
        workers=4,
    )

    assert summary.completed_count == 40
    assert [r.pin for r in summary.results] == [r.pin for r in records]


def test_sequential_and_parallel_generation_agree(tmp_path: Path):
    """Both execution modes produce the same outcome."""
    records = _records(12)

    serial = BatchGenerator.generate_batch(
        template=_template(),
        records=records,
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
        target_dir=tmp_path / "serial",
        workers=1,
    )
    parallel = BatchGenerator.generate_batch(
        template=_template(),
        records=records,
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
        target_dir=tmp_path / "parallel",
        workers=4,
    )

    assert serial.completed_count == parallel.completed_count
    assert [r.pin for r in serial.results] == [r.pin for r in parallel.results]
    assert [r.success for r in serial.results] == [r.success for r in parallel.results]


def test_generation_reports_the_progress(tmp_path: Path):
    """The progress callback is called once per record."""
    seen = []
    BatchGenerator.generate_batch(
        template=_template(),
        records=_records(10),
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
        target_dir=tmp_path,
        progress_callback=lambda done, total, pin, msg: seen.append((done, total)),
        workers=2,
    )
    assert len(seen) == 10
    assert seen[-1] == (10, 10)


def test_generation_can_be_cancelled(tmp_path: Path):
    """A cancelled run stops early and is flagged as cancelled."""
    seen = []

    def _cancel() -> bool:
        return len(seen) >= 3

    summary = BatchGenerator.generate_batch(
        template=_template(),
        records=_records(200),
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
        target_dir=tmp_path,
        progress_callback=lambda done, total, pin, msg: seen.append(done),
        cancel_check=_cancel,
        workers=1,
    )

    assert summary.cancelled is True
    assert summary.completed_count < 200


def test_missing_photo_policy_is_respected(tmp_path: Path):
    """A record without a photo is skipped when the policy says so."""
    from id_card_generator.core.constants import MissingPhotoPolicy

    records = _records(2)
    match_results = {
        records[0].record_id: PhotoMatchResult(
            pin=records[0].pin,
            record_id=records[0].record_id,
            status=MatchStatus.MATCHED,
            photo_path=str(tmp_path / "missing.jpg"),
        )
    }

    settings = RenderSettings()
    settings.missing_photo_policy = MissingPhotoPolicy.SKIP_RECORD

    summary = BatchGenerator.generate_batch(
        template=_template(),
        records=records,
        match_results=match_results,
        column_mappings={},
        settings=settings,
        target_dir=tmp_path,
        workers=1,
    )

    assert summary.skipped_count == 2
    assert summary.completed_count == 0


def test_resolve_workers_scales_with_the_batch():
    """The worker count grows with the batch but stays bounded."""
    assert BatchGenerator.resolve_workers(1) == 1
    assert BatchGenerator.resolve_workers(20) == 1
    assert BatchGenerator.resolve_workers(40) == 2
    assert BatchGenerator.resolve_workers(200) > 1
    assert BatchGenerator.resolve_workers(100000) <= 8
    assert BatchGenerator.resolve_workers(100000, workers=3) == 3


# ---------------------------------------------------------------------------
# Review step (re-render a single card)
# ---------------------------------------------------------------------------
def test_review_can_regenerate_a_single_card(qtbot, tmp_path: Path):
    """The review page re-renders a card through the batch generator."""
    from id_card_generator.core.models import ReviewStatus
    from id_card_generator.review.review_manager import ReviewManager
    from id_card_generator.ui.review_page import ReviewPage

    template = _template()
    records = _records(2)
    match_results = {
        rec.record_id: PhotoMatchResult(
            pin=rec.pin,
            record_id=rec.record_id,
            status=MatchStatus.MATCHED,
            photo_path=str(tmp_path / f"{rec.pin}.jpg"),
        )
        for rec in records
    }
    for rec in records:
        (tmp_path / f"{rec.pin}.jpg").write_bytes(b"photo")

    page = ReviewPage()
    qtbot.addWidget(page)
    page.show()

    page.template = template
    page.source_records_map = {rec.record_id: rec for rec in records}
    page.match_results_map = match_results
    page.column_mappings = {}
    page.manager = ReviewManager()
    page.manager.initialize_from_generation(
        source_records=records,
        generation_results=[
            RenderResult(record_id=rec.record_id, pin=rec.pin, success=True)
            for rec in records
        ],
    )

    page._regenerate_current()

    # The card was re-rendered and the review record points at the new file.
    rec = page.manager.records[0]
    assert rec.rendered_image_path, "the card was not re-rendered"
    assert Path(rec.rendered_image_path).exists()
    assert page.notice.severity == "success"
