"""Unit tests for sequential step-by-step navigation, sidebar removal, canvas auto-enlargement, and dashboard settings."""

import pytest
from PySide6.QtCore import QRectF, Qt
from id_card_generator.core.constants import MissingPhotoPolicy, WorkflowStep
from id_card_generator.editor.canvas_view import CanvasView
from id_card_generator.ui.main_window import MainWindow


@pytest.fixture
def app_window(qtbot):
    """Fixture providing an instantiated MainWindow."""
    window = MainWindow()
    qtbot.addWidget(window)
    return window


def test_sidebar_removed_from_visual_layout(app_window: MainWindow):
    """Verify that the left sidebar menu is not in central layout."""
    central = app_window.centralWidget()
    assert central.layout() is not None
    # Ensure layout items are only workflow_nav and stack
    layout_widgets = [
        central.layout().itemAt(i).widget()
        for i in range(central.layout().count())
        if central.layout().itemAt(i).widget() is not None
    ]
    # The sidebar frame must not be added to central layout
    assert app_window.sidebar not in layout_widgets
    assert app_window.workflow_nav in layout_widgets
    assert app_window.stack in layout_widgets


def test_dashboard_embedded_settings(app_window: MainWindow):
    """Verify that settings are embedded directly into the dashboard page and trigger updates."""
    dash = app_window.page_dashboard

    # Theme switching from dashboard
    dash.cmb_theme.setCurrentIndex(dash.cmb_theme.findData("white"))
    # Missing photo policy
    dash.cmb_policy.setCurrentIndex(dash.cmb_policy.findData(MissingPhotoPolicy.SKIP_RECORD))
    assert app_window.settings.missing_photo_policy == MissingPhotoPolicy.SKIP_RECORD

    # DPI
    dash.spin_dpi.setValue(600)
    assert app_window.settings.dpi == 600


def test_step_by_step_sequential_navigation(app_window: MainWindow):
    """Verify clicking step navigation bars advances through the workflow sequentially."""
    # Start at Dashboard
    assert app_window.stack.currentIndex() == 0

    # 1. Start from Dashboard
    app_window.page_dashboard.btn_start_workflow.click()
    assert app_window.stack.currentIndex() == 1  # Data Source

    # 2. Advance to Photo Library
    app_window.page_data_source.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 2  # Photos

    # 3. Advance to Templates
    app_window.page_photos.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 3  # Templates

    # 4. Advance to Canvas Editor
    app_window.page_templates.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 4  # Canvas Editor

    # 5. Advance to Generate
    app_window.page_editor.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 5  # Generate

    # 6. Advance to Review
    app_window.page_generation.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 6  # Review

    # 7. Advance to Export
    app_window.page_review.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 7  # Export

    # 8. Complete and return to Dashboard
    app_window.page_export.nav_bar.btn_next.click()
    assert app_window.stack.currentIndex() == 0  # Dashboard


def test_canvas_view_auto_enlarge(qtbot):
    """Verify canvas view enlarged fit factor applies generous scale."""
    from id_card_generator.editor.canvas_scene import CanvasScene
    scene = CanvasScene()
    scene.setSceneRect(0, 0, 1012, 638)
    view = CanvasView(scene)
    qtbot.addWidget(view)
    view.resize(800, 600)
    view.show()

    # Fit with enlarge_factor=1.35
    view.fit_to_view(enlarge_factor=1.35)
    scale_135 = view._zoom_factor

    # Standard fit with enlarge_factor=1.0
    view.fit_to_view(enlarge_factor=1.0)
    scale_100 = view._zoom_factor

    assert scale_135 > scale_100
    assert abs(scale_135 / scale_100 - 1.35) < 0.05
