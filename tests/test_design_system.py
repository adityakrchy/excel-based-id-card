"""Tests for the ID Studio design system and the structured workflow.

Covers:
* the token driven stylesheet (both themes expose the same vocabulary),
* the workflow model (order, badges, footer labels, gating),
* the page scaffolding (every workflow page has a matching header + footer),
* the workspace ribbon progress states,
* the non blocking notice banners.
"""

import pytest
from PySide6.QtCore import Qt

from id_card_generator.core.constants import WorkflowStep
from id_card_generator.ui import workflow
from id_card_generator.ui.components import (
    EmptyState,
    InlineNotice,
    PageFooter,
    PageHeader,
    StatTile,
    SurfaceCard,
)
from id_card_generator.ui.components.studio_nav_bar import TabState
from id_card_generator.ui.main_window import MainWindow
from id_card_generator.ui.theme_manager import ThemeManager


# ---------------------------------------------------------------------------
# Design tokens & stylesheet
# ---------------------------------------------------------------------------
def test_stylesheet_is_generated_from_tokens():
    """The global stylesheet is derived from the design tokens."""
    stylesheet = ThemeManager.build_stylesheet("black")
    assert "QPushButton" in stylesheet
    assert "QFrame#page_header" in stylesheet
    assert "QFrame#page_footer" in stylesheet
    assert "QFrame#surface_card" in stylesheet
    assert "QLabel#notice_banner" in stylesheet
    # No unresolved template placeholders.
    assert "$" not in stylesheet
    assert "{{" not in stylesheet


def test_both_themes_expose_the_same_widget_vocabulary():
    """Dark and light theme are generated from the same template."""
    dark = ThemeManager.build_stylesheet("black")
    light = ThemeManager.build_stylesheet("white")

    selectors = [
        "QPushButton",
        "QLineEdit",
        "QComboBox",
        "QTableWidget",
        "QTabBar::tab",
        "QStatusBar",
        "QProgressBar",
        "QSplitter::handle",
        "QGroupBox",
        "QFrame#page_header",
        "QFrame#page_footer",
        "QLabel#notice_banner",
    ]
    for selector in selectors:
        assert selector in dark
        assert selector in light

    # The palettes must actually differ.
    assert dark != light


def test_light_theme_uses_the_light_palette():
    """The light theme picks up the light surface colours."""
    from id_card_generator.ui.studio_tokens import COLORS, LIGHT_COLORS

    light = ThemeManager.build_stylesheet("white")
    assert LIGHT_COLORS.SURFACE in light
    assert COLORS.SURFACE not in light


# ---------------------------------------------------------------------------
# Workflow model
# ---------------------------------------------------------------------------
def test_pipeline_order_is_linear():
    """The production pipeline is a single, linear sequence."""
    assert workflow.PIPELINE == (
        WorkflowStep.DATA_SOURCE,
        WorkflowStep.PHOTOS,
        WorkflowStep.TEMPLATES,
        WorkflowStep.CANVAS_EDITOR,
        WorkflowStep.GENERATE,
        WorkflowStep.REVIEW,
        WorkflowStep.EXPORT,
    )


def test_step_badges_are_consistent():
    """Every stage reports a 1-based position inside the pipeline."""
    assert workflow.step_badge(WorkflowStep.DATA_SOURCE) == "Step 1 of 7"
    assert workflow.step_badge(WorkflowStep.EXPORT) == "Step 7 of 7"
    assert workflow.step_badge(WorkflowStep.DASHBOARD) == "Project Hub"


def test_footer_labels_follow_the_pipeline():
    """Back / next labels are derived from the pipeline, not hard coded."""
    back, next_, badge = workflow.footer_labels(WorkflowStep.PHOTOS)
    assert back == "Data Source"
    assert next_ == "Templates"
    assert badge == "Step 2 of 7"

    # The first step still offers a way back to the hub.
    back, next_, _ = workflow.footer_labels(WorkflowStep.DATA_SOURCE)
    assert back == "Hub"
    assert next_ == "Photo Library"

    # The last step returns to the hub.
    back, next_, _ = workflow.footer_labels(WorkflowStep.EXPORT)
    assert back == "Review"
    assert next_ == "Back to Hub"


def test_gating_reports_missing_prerequisites():
    """A stage knows which prerequisites are still missing."""
    completed = {stage.step: False for stage in workflow.STAGES}

    missing = workflow.missing_requirements(WorkflowStep.GENERATE, completed)
    assert {m.step for m in missing} == {
        WorkflowStep.DATA_SOURCE,
        WorkflowStep.CANVAS_EDITOR,
    }

    completed[WorkflowStep.DATA_SOURCE] = True
    completed[WorkflowStep.CANVAS_EDITOR] = True
    assert workflow.missing_requirements(WorkflowStep.GENERATE, completed) == []
    assert workflow.step_completed(WorkflowStep.GENERATE, completed) is False


def test_every_step_has_a_ribbon_entry():
    """Each stage maps to one entry of the workspace ribbon."""
    from id_card_generator.ui.components.studio_nav_bar import StudioTab

    tabs = {tab.value for tab in StudioTab}
    for stage in workflow.STAGES:
        assert stage.tab in tabs
        assert stage.title
        assert stage.subtitle


# ---------------------------------------------------------------------------
# Page scaffolding
# ---------------------------------------------------------------------------
@pytest.fixture
def app_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def test_every_workflow_page_has_a_matching_header_and_footer(app_window: MainWindow):
    """Header and footer always report the same step of the pipeline."""
    pages = {
        WorkflowStep.DATA_SOURCE: app_window.page_data_source,
        WorkflowStep.PHOTOS: app_window.page_photos,
        WorkflowStep.TEMPLATES: app_window.page_templates,
        WorkflowStep.CANVAS_EDITOR: app_window.page_editor,
        WorkflowStep.GENERATE: app_window.page_generation,
        WorkflowStep.REVIEW: app_window.page_review,
        WorkflowStep.EXPORT: app_window.page_export,
    }

    for step, page in pages.items():
        header = page.page_header
        footer = page.nav_bar
        assert header.lbl_badge.text() == workflow.step_badge(step)
        assert header.lbl_title.text() == workflow.title_for(step)
        assert footer.lbl_badge.text() == workflow.step_badge(step)
        assert not footer.btn_next.isHidden()


def test_page_header_exposes_contextual_actions(qtbot):
    """Pages can host their own actions in the header."""
    header = PageHeader("Title", "Subtitle", "Step 1 of 7")
    assert header.lbl_title.text() == "Title"
    assert header.lbl_badge.text() == "Step 1 of 7"

    from PySide6.QtWidgets import QPushButton

    button = QPushButton("Do it")
    header.add_action(button)
    assert header.actions_layout.count() == 1


def test_page_footer_navigates(qtbot):
    """The footer emits back / next requests."""
    footer = PageFooter(prev_label="Hub", next_label="Photos", step_badge="Step 1 of 7")

    seen = []
    footer.back_requested.connect(lambda: seen.append("back"))
    footer.next_requested.connect(lambda: seen.append("next"))

    footer.btn_back.click()
    footer.btn_next.click()
    assert seen == ["back", "next"]

    footer.set_next_enabled(False)
    assert not footer.btn_next.isEnabled()


def test_inline_notice_is_non_blocking(qtbot):
    """The notice banner shows a message and a severity without a dialog."""
    notice = InlineNotice()
    assert not notice.isVisible()

    notice.set_message("Something failed", severity="error")
    assert notice.isVisible()
    assert notice.severity == "error"
    assert "Something failed" in notice.text()

    notice.clear_message()
    assert not notice.isVisible()
    assert notice.severity == "info"


def test_surface_card_and_stat_tile(qtbot):
    """The reusable surface helpers expose their content."""
    card = SurfaceCard("Title", "Subtitle")
    assert card.lbl_title.text() == "Title"

    tile = StatTile("Records", "42")
    assert tile.lbl_caption.text() == "Records"
    tile.set_value(43)
    assert tile.lbl_value.text() == "43"


def test_empty_state(qtbot):
    """The empty state can carry a call to action."""
    state = EmptyState("Nothing yet", "Import a spreadsheet to begin.")
    assert state.lbl_title.text() == "Nothing yet"
    assert state.btn_action.isVisible() is False


# ---------------------------------------------------------------------------
# Shell & ribbon state
# ---------------------------------------------------------------------------
def test_ribbon_reflects_step_progress(app_window: MainWindow):
    """The ribbon badges every pipeline step with its progress state."""
    from id_card_generator.ui.components.studio_nav_bar import StudioTab

    app_window.switch_page(WorkflowStep.DASHBOARD)

    # A finished step is badged as done.
    app_window._mark_step_completed(WorkflowStep.DATA_SOURCE, True)
    assert app_window.studio_nav._states[StudioTab.DATA_SOURCE] == TabState.DONE

    # The step the user is in is always marked active.
    app_window.switch_page(WorkflowStep.CANVAS_EDITOR)
    assert app_window.studio_nav._states[StudioTab.DESIGNER] == TabState.ACTIVE


def test_header_actions_are_reachable(app_window: MainWindow):
    """The document actions live in the visible header bar."""
    for name in ("btn_new", "btn_open", "btn_save", "btn_undo", "btn_redo"):
        button = getattr(app_window.header_bar, name)
        assert not button.isHidden(), f"{name} should be visible in the header"
