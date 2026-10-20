"""End-to-end tests for the structured ID Studio workflow.

The application must keep the user moving: no modal dialog may block the
pipeline, every step reports its position, and the shell remembers what has
been finished.
"""

import pytest

from id_card_generator.core.constants import WorkflowStep
from id_card_generator.ui.components.studio_nav_bar import StudioTab, TabState
from id_card_generator.ui.main_window import MainWindow


@pytest.fixture
def app_window(qtbot):
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def test_pipeline_navigation_walks_forward(app_window: MainWindow):
    """The footers walk the user through the whole pipeline."""
    app_window.switch_page(WorkflowStep.DATA_SOURCE)
    app_window.page_data_source.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 2  # Photo Library

    app_window.page_photos.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 3  # Templates

    app_window.page_templates.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 4  # Designer

    app_window.page_editor.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 5  # Generate

    app_window.page_generation.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 6  # Review

    app_window.page_review.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 7  # Export

    # The last step closes the loop back on the hub.
    app_window.page_export.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 0  # Dashboard


def test_pipeline_navigation_walks_back(app_window: MainWindow):
    """Every step offers a way back to the previous one."""
    app_window.switch_page(WorkflowStep.REVIEW)
    app_window.page_review.nav_bar.btn_back.click()
    assert app_window.stack.currentIndex() == 5  # Generate

    app_window.switch_page(WorkflowStep.DATA_SOURCE)
    app_window.page_data_source.nav_bar.btn_back.click()
    assert app_window.stack.currentIndex() == 0  # Dashboard


def test_step_progress_is_tracked(app_window: MainWindow):
    """Finishing a step is remembered and reflected in the ribbon."""
    app_window.switch_page(WorkflowStep.DASHBOARD)
    assert app_window.studio_nav._states[StudioTab.DATA_MAPPING] == TabState.IDLE

    app_window._mark_step_completed(WorkflowStep.DATA_SOURCE, True)
    assert app_window.studio_nav._states[StudioTab.DATA_MAPPING] == TabState.PARTIAL

    app_window._mark_step_completed(WorkflowStep.PHOTOS, True)
    assert app_window.studio_nav._states[StudioTab.DATA_MAPPING] == TabState.DONE

    # A workspace whose prerequisites are missing is blocked, not available.
    assert app_window.studio_nav._states[StudioTab.EXPORT_PRINT] == TabState.BLOCKED


def test_broken_spreadsheet_is_reported_inline(qtbot, tmp_path):
    """A failing import must not open a modal dialog (it would stall the flow)."""
    from id_card_generator.ui.data_source_page import DataSourcePage

    page = DataSourcePage()
    qtbot.addWidget(page)

    broken = tmp_path / "broken.xlsx"
    broken.write_text("this is not a spreadsheet")

    # Must return without blocking on a message box.
    page.load_file(broken)

    assert not page.notice.isHidden()
    assert page.notice.severity == "error"
    assert "spreadsheet" in page.notice.text().lower()


def test_saving_a_project_is_non_blocking(app_window: MainWindow, tmp_path):
    """Saving reports through the status bar instead of a modal dialog."""
    from id_card_generator.core.models import ProjectConfiguration

    app_window.set_project(ProjectConfiguration(project_name="Flow Test"))
    target = tmp_path / "flow.idcrt"

    app_window._save_to_path(target)

    assert target.exists()
    assert "flow.idcrt" in app_window.status_bar.currentMessage()


def test_page_headers_track_the_active_step(app_window: MainWindow):
    """The shell keeps the ribbon and the page header in sync."""
    app_window.switch_page(WorkflowStep.CANVAS_EDITOR)

    assert app_window.studio_nav._buttons[StudioTab.DESIGNER].isChecked()
    assert app_window.page_editor.page_header.lbl_badge.text() == "Step 4 of 7"
    assert app_window.page_editor.nav_bar.lbl_badge.text() == "Step 4 of 7"
