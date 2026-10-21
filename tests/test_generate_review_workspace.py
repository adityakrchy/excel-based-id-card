"""Tests for the generate and review workstations.

The two screens were rebuilt as three column workstations:

* the generation engine reports the KPI telemetry of the plan (cards
  generated, elapsed / remaining time, disk throughput, thread pool and CPU
  load), runs a configurable batch scope and shows a multi-core progress ring
  next to the throughput graph,
* the review workstation pairs a virtual record list (with the data quality
  filters), a card preview that can be flipped to the back face and a record
  editor that can change a field and re-render the card.
"""

import pytest

from id_card_generator.core.constants import (
    MatchStatus,
    MissingPhotoPolicy,
    OutputFormat,
    ReviewStatus,
)
from id_card_generator.core.models import (
    CanvasElement,
    PhotoMatchResult,
    RenderResult,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.ui.components.progress_ring import ProgressRing
from id_card_generator.ui.components.record_list import (
    SEVERITY_ERROR,
    SEVERITY_WARN,
    RecordListEntry,
    RecordListModel,
)
from id_card_generator.ui.components.speed_graph import SpeedGraph
from id_card_generator.ui.generation_page import GenerationPage
from id_card_generator.ui.review_page import ReviewPage


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
# The reusable components
# ---------------------------------------------------------------------------
def test_progress_ring_tracks_the_progress(qtbot):
    """The ring clamps the progress and reports it back."""
    ring = ProgressRing(diameter=120, cores=2)
    qtbot.addWidget(ring)

    assert ring.value == 0.0
    assert ring.cores == 2

    ring.set_progress(0.5)
    assert ring.value == pytest.approx(0.5)

    ring.set_progress(2.0)
    assert ring.value == 1.0

    ring.set_progress(-1.0)
    assert ring.value == 0.0


def test_progress_ring_can_change_the_core_count(qtbot):
    """The ring adapts to the size of the thread pool."""
    ring = ProgressRing(cores=1)
    qtbot.addWidget(ring)

    ring.set_cores(8)
    assert ring.cores == 8

    ring.set_core_values([0.1, 0.2])
    assert ring.value == 0.0  # the overall progress is untouched


def test_speed_graph_keeps_the_peak(qtbot):
    """The graph remembers the highest rate that was recorded."""
    graph = SpeedGraph(capacity=10)
    qtbot.addWidget(graph)

    assert graph.peak == 0.0
    graph.push_sample(2.5)
    graph.push_sample(4.0)
    graph.push_sample(1.0)

    assert graph.peak == pytest.approx(4.0)
    assert graph.last_value == pytest.approx(1.0)

    graph.clear_samples()
    assert graph.peak == 0.0


def test_record_list_model_tracks_the_entries(qtbot):
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
# The generation workstation
# ---------------------------------------------------------------------------
@pytest.fixture
def generation_page(qtbot):
    page = GenerationPage()
    qtbot.addWidget(page)
    page.show()
    return page


def test_generation_reports_the_plan_telemetry(generation_page: GenerationPage):
    """Every KPI tile of the plan is on the screen."""
    tiles = {
        generation_page.lbl_kpi_rendered.text(),
        generation_page.lbl_kpi_time.text(),
        generation_page.lbl_kpi_throughput.text(),
        generation_page.lbl_kpi_workers.text(),
        generation_page.lbl_kpi_cpu.text(),
    }
    assert len(tiles) == 5

    # The captions name the metrics of the plan.
    captions = [
        generation_page.card_rendered.lbl_caption.text(),
        generation_page.card_time.lbl_caption.text(),
        generation_page.card_throughput.lbl_caption.text(),
        generation_page.card_workers.lbl_caption.text(),
        generation_page.card_cpu.lbl_caption.text(),
    ]
    assert captions == [
        "Cards Generated",
        "Elapsed / Remaining",
        "Disk Throughput",
        "Thread Pool",
        "CPU Load",
    ]


def test_generation_context_fills_the_configuration(generation_page: GenerationPage):
    """The run configuration mirrors the context of the project."""
    records = _records(6)
    generation_page.set_generation_context(
        template=_template(),
        records=records,
        match_results=_matches(records),
        column_mappings={},
        settings=RenderSettings(),
    )

    assert generation_page.lbl_cfg_template.text() == "Workstation Card"
    assert "6 records" in generation_page.lbl_cfg_dataset.text()
    assert "mm" in generation_page.lbl_cfg_card.text()
    assert generation_page.lbl_kpi_rendered.text() == "0 / 6"


def test_batch_scope_defaults_to_every_record(generation_page: GenerationPage):
    """Without a custom range the whole dataset is rendered."""
    records = _records(6)
    generation_page.set_generation_context(
        template=_template(),
        records=records,
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
    )

    assert generation_page.btn_scope_all.isChecked()
    assert len(generation_page._selected_records()) == 6


def test_batch_scope_limits_the_run_to_a_range(generation_page: GenerationPage):
    """A custom range renders only the selected records."""
    records = _records(10)
    generation_page.set_generation_context(
        template=_template(),
        records=records,
        match_results={},
        column_mappings={},
        settings=RenderSettings(),
    )

    generation_page.btn_scope_range.setChecked(True)
    generation_page.spin_range_start.setValue(3)
    generation_page.spin_range_end.setValue(6)

    selected = generation_page._selected_records()
    assert [r.pin for r in selected] == ["000002", "000003", "000004", "000005"]
    assert "4 cards" in generation_page.lbl_batch_scope.text()


def test_output_widgets_drive_the_render_settings(generation_page: GenerationPage):
    """The raster output of the panel reaches the render settings."""
    settings = RenderSettings()
    generation_page.set_generation_context(
        template=_template(),
        records=_records(3),
        match_results={},
        column_mappings={},
        settings=settings,
    )

    generation_page.cmb_format.setCurrentIndex(
        generation_page.cmb_format.findData(OutputFormat.JPEG)
    )
    generation_page.cmb_dpi.setCurrentIndex(generation_page.cmb_dpi.findData(600))

    assert settings.output_format.value == "JPEG"
    assert settings.dpi == 600
    assert generation_page.lbl_naming.text().endswith(".jpg")


def test_progress_moves_the_ring_and_the_tiles(generation_page: GenerationPage):
    """A progress report updates the ring, the bar and the counters."""
    generation_page._on_progress(3, 10, "000001", "Generated")

    assert generation_page.progress_ring.value == pytest.approx(0.3)
    assert generation_page.progress_bar.value() == 30
    assert generation_page.lbl_kpi_rendered.text() == "3 / 10"
    assert generation_page.lbl_status.text().startswith("Generating: 3 of 10")


def test_the_event_log_collects_the_failures(generation_page: GenerationPage):
    """Errors land in the inspector and the log can be filtered."""
    generation_page._on_status("[OK] Rendered PIN: 000001")
    generation_page._on_status("[ERROR] Failed PIN: 000002 - no photo")

    assert generation_page.error_list.count() == 1
    assert "1 failure" in generation_page.lbl_error_count.text()

    generation_page.cmb_log_filter.setCurrentIndex(1)
    assert "Failed PIN" in generation_page.log_output.toPlainText()
    assert "Rendered PIN" not in generation_page.log_output.toPlainText()

    generation_page.cmb_log_filter.setCurrentIndex(0)
    assert "Rendered PIN" in generation_page.log_output.toPlainText()


# ---------------------------------------------------------------------------
# The review workstation
# ---------------------------------------------------------------------------
@pytest.fixture
def review_page(qtbot, tmp_path, monkeypatch):
    monkeypatch.setattr(
        "id_card_generator.ui.review_page.get_staging_dir",
        lambda: tmp_path / "staging",
    )
    page = ReviewPage()
    qtbot.addWidget(page)
    page.show()
    return page


def _load_session(page: ReviewPage, records=None) -> list:
    records = records if records is not None else _records(6)
    results = [
        RenderResult(
            record_id=record.record_id,
            pin=record.pin,
            success=True,
            image_path="",
        )
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


def test_the_record_list_shows_every_record(review_page: ReviewPage):
    """The list is filled from the review session."""
    records = _load_session(review_page)

    assert review_page.record_model.rowCount() == len(records)
    assert review_page.lbl_list_info.text().startswith(f"{len(records)} of {len(records)}")


def test_the_quality_filters_split_the_records(review_page: ReviewPage):
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


def test_a_missing_photo_is_flagged(review_page: ReviewPage):
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


def test_picking_a_record_jumps_to_it(review_page: ReviewPage):
    """Clicking a row of the list selects that record."""
    records = _load_session(review_page)

    review_page._on_record_selected(records[3].record_id)
    assert review_page.manager.current_index == 3
    assert review_page.lbl_nav_index.text() == "Card 4 of 6"


def test_the_preview_can_be_flipped_to_the_back_face(review_page: ReviewPage):
    """The back side is rendered live from the template."""
    _load_session(review_page)

    review_page._on_side_changed("back")
    assert review_page._side == "back"
    assert "Back side" in review_page.lbl_preview_meta.text()

    review_page._on_side_changed("front")
    assert review_page._side == "front"


def test_editing_a_field_re_renders_the_card(review_page: ReviewPage):
    """A changed field is written back and the card is rendered again."""
    records = _load_session(review_page)

    editor = review_page._field_editors["Name"]
    editor.setText("Edited Name")
    review_page._apply_field_edits()

    source = review_page.source_records_map[records[0].record_id]
    assert source.data["Name"] == "Edited Name"
    assert "Updated 1 field" in review_page.notice.text()


def test_the_search_narrows_the_list(review_page: ReviewPage):
    """The search field filters the records."""
    records = _load_session(review_page)

    review_page.txt_search.setText("Person 3")
    assert review_page.record_model.rowCount() == 1
    assert review_page.record_model.entry(0).pin == records[3].pin


def test_approving_moves_to_the_next_record(review_page: ReviewPage):
    """A decision is stored and the inspector advances."""
    records = _load_session(review_page)

    review_page._set_current_status(ReviewStatus.APPROVED)

    assert review_page.manager.records[0].status == ReviewStatus.APPROVED
    assert review_page.manager.current_index == 1


# ---------------------------------------------------------------------------
# The renderer
# ---------------------------------------------------------------------------
def test_the_renderer_only_paints_the_requested_face():
    """Each face of the card only shows its own elements."""
    from id_card_generator.rendering.pillow_renderer import PillowRenderer

    template = _template()
    record = _records(1)[0]

    front, _ = PillowRenderer.render_card(template=template, record=record)
    back, _ = PillowRenderer.render_card(template=template, record=record, side="back")

    front_pixels = front.convert("RGB").tobytes()
    back_pixels = back.convert("RGB").tobytes()
    assert front_pixels != back_pixels
