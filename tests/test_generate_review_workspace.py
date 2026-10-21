"""Tests for the production workspace (generate & review).

Generating and reviewing were merged into one screen, so this module covers
the whole job of the page:

* the run is configured, started and reported with a progress bar, a spinner
  on the button and the CPU / memory of the process,
* the produced cards become a queue that is filtered by their quality,
* the card can be previewed, flipped to the back face and edited.
"""

import pytest

from id_card_generator.core.constants import MatchStatus, MissingPhotoPolicy, ReviewStatus
from id_card_generator.core.models import (
    CanvasElement,
    PhotoMatchResult,
    RenderResult,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.core.process_metrics import ProcessMetrics
from id_card_generator.ui.components.busy_button import BusyButton
from id_card_generator.ui.components.record_list import (
    SEVERITY_ERROR,
    SEVERITY_WARN,
    RecordListEntry,
    RecordListModel,
)
from id_card_generator.ui.production_page import ProductionPage


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
def _template() -> TemplateDefinition:
    """A card template with a front and a back element."""
    template = TemplateDefinition(
        name="Workstation Card",
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
        ),
        CanvasElement(
            id="backnote",
            name="Back Note",
            type="static_text",
            x=20,
            y=120,
            width=280,
            height=40,
            static_content="Terms",
            z_index=1,
            side="back",
        ),
    ]
    return template


def _records(count: int = 8) -> list:
    records = []
    for i in range(count):
        record = SourceRecord(
            row_index=i,
            raw_pin=f"{i:06d}",
            pin=f"{i:06d}",
            data={"PIN Number": f"{i:06d}", "Name": f"Person {i}"},
        )
        records.append(record)
    return records


def _matches(records: list) -> dict:
    return {
        record.record_id: PhotoMatchResult(
            pin=record.pin,
            record_id=record.record_id,
            status=MatchStatus.MATCHED,
            photo_path="",
        )
        for record in records
    }


# ---------------------------------------------------------------------------
# The helpers
# ---------------------------------------------------------------------------
def test_the_button_shows_a_spinner_while_it_is_busy(qtbot):
    """The batch button carries the loader."""
    button = BusyButton("Launch")
    qtbot.addWidget(button)

    assert button.is_busy is False

    button.set_busy(True)
    assert button.is_busy is True
    assert button.isEnabled()

    button.set_busy(False)
    assert button.is_busy is False


def test_the_process_metrics_report_cpu_and_memory():
    """The telemetry of the process is sampled from the standard library."""
    metrics = ProcessMetrics()

    cpu, memory = metrics.sample()
    assert cpu == 0.0  # the first sample has no interval to measure
    assert memory >= 0.0

    cpu, memory = metrics.sample()
    assert 0.0 <= cpu <= 100.0
    assert memory > 0.0


def test_the_record_list_model_tracks_the_entries(qtbot):
    """The model exposes the rows and finds them by record id."""
    model = RecordListModel()
    entries = [
        RecordListEntry(record_id="a", pin="001", name="Ada"),
        RecordListEntry(record_id="b", pin="002", name="Bob", severity=SEVERITY_WARN),
    ]
    model.set_entries(entries)

    assert model.rowCount() == 2
    assert model.entry(1).severity == SEVERITY_WARN
    assert model.row_for_record("b") == 1
    assert model.row_for_record("missing") == -1


# ---------------------------------------------------------------------------
# The run
# ---------------------------------------------------------------------------
@pytest.fixture
def production_page(qtbot):
    page = ProductionPage()
    qtbot.addWidget(page)
    page.show()
    return page


def test_the_page_reports_only_what_matters(production_page: ProductionPage):
    """There is a progress bar, a loader and the process telemetry."""
    # The progress bar shows the cards, not a percentage alone.
    assert production_page.progress_bar.format() == "0 / 0"

    # The button carries the loader.
    assert isinstance(production_page.btn_generate, BusyButton)

    # The telemetry is the CPU load and the memory of the process.
    production_page._on_tick()
    stats = [
        production_page.stat_line._labels[0].text(),
        production_page.stat_line._labels[1].text(),
    ]
    assert stats[0].endswith("%")
    assert stats[1].endswith("MB")


def test_the_context_fills_the_configuration(production_page: ProductionPage):
    """The run configuration mirrors the context of the project."""
    records = _records(6)
    production_page.set_generation_context(
        template=_template(),
        records=records,
        match_results=_matches(records),
        column_mappings={},
        settings=RenderSettings(),
    )

    assert "6 loaded" in production_page.lbl_chk_records.text()
    assert production_page.lbl_chk_template.text() == "Workstation Card"
    assert "PNG" in production_page.lbl_chk_output.text()


def test_the_batch_scope_defaults_to_every_record(production_page: ProductionPage):
    """Without a custom range the whole dataset is rendered."""
    records = _records(6)
    production_page.set_generation_context(
        template=_template(),
        records=records,
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
    )

    assert production_page.btn_scope_all.isChecked()
    assert len(production_page._selected_records()) == 6


def test_the_batch_scope_limits_the_run_to_a_range(production_page: ProductionPage):
    """A custom range renders only the selected records."""
    records = _records(10)
    production_page.set_generation_context(
        template=_template(),
        records=records,
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
    )

    production_page.btn_scope_range.setChecked(True)
    production_page.spin_range_start.setValue(3)
    production_page.spin_range_end.setValue(6)

    selected = production_page._selected_records()
    assert [record.pin for record in selected] == [
        "000002",
        "000003",
        "000004",
        "000005",
    ]


def test_the_output_widgets_drive_the_render_settings(production_page: ProductionPage):
    """The raster output of the panel reaches the render settings."""
    from id_card_generator.core.constants import OutputFormat

    settings = RenderSettings()
    production_page.set_generation_context(
        template=_template(),
        records=_records(3),
        match_results={},
        column_mappings={},
        settings=settings,
    )

    production_page.cmb_format.setCurrentIndex(
        production_page.cmb_format.findData(OutputFormat.JPEG.value)
    )
    production_page.cmb_dpi.setCurrentIndex(production_page.cmb_dpi.findData(600))

    assert settings.output_format.value == "JPEG"
    assert settings.dpi == 600
    assert production_page.lbl_naming.text().endswith(".jpg")


def test_the_progress_moves_the_bar(production_page: ProductionPage):
    """A progress report updates the bar and its text."""
    production_page._on_progress(3, 10, "000001", "Generated")

    assert production_page.progress_bar.value() == 30
    assert production_page.progress_bar.format() == "3 / 10 cards"


def test_the_event_log_collects_the_failures(production_page: ProductionPage):
    """Errors are counted and the log can be filtered down to them."""
    production_page._on_status("[OK] Rendered PIN: 000001")
    production_page._on_status("[ERROR] Failed PIN: 000002 - no photo")

    assert "1 failure" in production_page.lbl_error_count.text()

    production_page.cmb_log_filter.setCurrentIndex(1)
    assert "Failed PIN" in production_page.log_output.toPlainText()
    assert "Rendered PIN" not in production_page.log_output.toPlainText()

    production_page.cmb_log_filter.setCurrentIndex(0)
    assert "Rendered PIN" in production_page.log_output.toPlainText()


def test_a_run_without_a_template_is_refused(production_page: ProductionPage):
    """Without a template the run is refused with a hint."""
    production_page.set_generation_context(
        template=None,
        records=_records(2),
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
    )

    production_page._start_generation()
    assert not production_page.notice.isHidden()
    assert not production_page.btn_generate.is_busy


# ---------------------------------------------------------------------------
# The queue
# ---------------------------------------------------------------------------
@pytest.fixture
def review_page(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "id_card_generator.ui.production_page.get_staging_dir",
        lambda: tmp_path / "staging",
    )
    page = ProductionPage()
    qtbot.addWidget(page)
    page.show()
    return page


def _load_session(page: ProductionPage, records=None) -> list:
    records = records if records is not None else _records(6)
    results = [
        RenderResult(record_id=record.record_id, pin=record.pin, success=True)
        for record in records
    ]
    page.load_review_session(
        source_records=records,
        generation_results=results,
        template=_template(),
        match_results=_matches(records),
        column_mappings={},
    )
    return records


def test_the_queue_shows_every_record(review_page: ProductionPage):
    """The list is filled from the review session."""
    records = _load_session(review_page)

    assert review_page.record_model.rowCount() == len(records)
    assert review_page.lbl_list_info.text().startswith(f"{len(records)} of {len(records)}")


def test_the_quality_filters_split_the_records(review_page: ProductionPage):
    """A record with a warning is not counted as valid."""
    records = _records(4)
    records[1].validation_warnings.append("Department code is unknown")
    records[2].validation_errors.append("Missing PIN number")

    _load_session(review_page, records)

    counts = review_page._quality_counts()
    assert counts["all"] == 4
    assert counts["warn"] == 1
    assert counts["error"] == 1
    assert counts["valid"] == 2

    review_page._on_quality_filter("warn")
    assert review_page.record_model.rowCount() == 1
    assert review_page.record_model.entry(0).severity == SEVERITY_WARN

    review_page._on_quality_filter("error")
    assert review_page.record_model.rowCount() == 1
    assert review_page.record_model.entry(0).severity == SEVERITY_ERROR

    review_page._on_quality_filter("all")
    assert review_page.record_model.rowCount() == 4


def test_a_missing_photo_is_flagged(review_page: ProductionPage):
    """A record without a photo is reported as a warning."""
    records = _records(3)
    matches = _matches(records)
    matches[records[0].record_id] = PhotoMatchResult(
        pin=records[0].pin,
        record_id=records[0].record_id,
        status=MatchStatus.MISSING,
    )

    review_page.load_review_session(
        source_records=records,
        generation_results=[],
        template=_template(),
        match_results=matches,
        column_mappings={},
    )

    entry = review_page.record_model.entry(0)
    assert entry.severity == SEVERITY_WARN
    assert any("Missing photo" in flag for flag in entry.flags)


def test_picking_a_record_jumps_to_it(review_page: ProductionPage):
    """Clicking a row of the queue selects that record."""
    records = _load_session(review_page)

    review_page._on_record_selected(records[3].record_id)
    assert review_page.manager.current_index == 3
    assert review_page.lbl_nav_index.text() == "Card 4 of 6"


def test_the_preview_can_be_flipped_to_the_back_face(review_page: ProductionPage):
    """The back side is rendered live from the template."""
    _load_session(review_page)

    review_page._on_side_changed("back")
    assert review_page._side == "back"
    assert "Back side" in review_page.lbl_preview_meta.text()

    review_page._on_side_changed("front")
    assert review_page._side == "front"


def test_editing_a_field_re_renders_the_card(review_page: ProductionPage):
    """A changed field is written back and the card is rendered again."""
    records = _load_session(review_page)

    editor = review_page._field_editors["Name"]
    editor.setText("Edited Name")
    review_page._apply_field_edits()

    source = review_page.source_records_map[records[0].record_id]
    assert source.data["Name"] == "Edited Name"
    assert "Updated 1 field" in review_page.notice.text()


def test_the_search_narrows_the_queue(review_page: ProductionPage):
    """The search field filters the records."""
    records = _load_session(review_page)

    review_page.txt_search.setText("Person 3")
    assert review_page.record_model.rowCount() == 1
    assert review_page.record_model.entry(0).pin == records[3].pin


def test_approving_moves_to_the_next_record(review_page: ProductionPage):
    """A decision is stored and the inspector advances."""
    records = _load_session(review_page)

    review_page._set_current_status(ReviewStatus.APPROVED)

    assert review_page.manager.records[0].status == ReviewStatus.APPROVED
    assert review_page.manager.current_index == 1


def test_the_queue_can_approve_every_card(review_page: ProductionPage):
    """The button approves every card of the queue that is not rejected."""
    records = _records(5)
    results = [
        RenderResult(
            record_id=record.record_id,
            pin=record.pin,
            success=True,
            image_path=f"/tmp/{record.pin}.png",
        )
        for record in records
    ]
    review_page.load_review_session(
        source_records=records,
        generation_results=results,
        template=_template(),
        match_results=_matches(records),
        column_mappings={},
    )

    # One card is rejected, it stays rejected.
    review_page.manager.records[-1].status = ReviewStatus.REJECTED
    review_page._update_display()

    assert review_page.btn_approve_all.isEnabled() is True
    assert "4" in review_page.btn_approve_all.text()

    review_page.btn_approve_all.click()

    counts = review_page.manager.counts
    assert counts["approved"] == 4
    assert counts["pending"] == 0
    assert counts["rejected"] == 1
    assert "Approved 4" in review_page.notice.text()

    # Nothing is left to approve, so the button goes quiet.
    assert review_page.btn_approve_all.isEnabled() is False
