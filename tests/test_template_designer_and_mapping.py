"""Comprehensive tests for Advanced Template Designer, Streamlined Mapping Editor, and Export Improvements."""

import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication, QMessageBox

from id_card_generator.core.constants import ImageFitMode, WorkflowStep
from id_card_generator.core.models import (
    CanvasElement,
    ExportConfiguration,
    PhotoMatchResult,
    ProjectConfiguration,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.templates.template_manager import TemplateManager
from id_card_generator.templates.template_validator import TemplateValidator
from id_card_generator.ui.dialogs.blank_canvas_dialog import BlankCanvasDialog
from id_card_generator.ui.editor_page import EditorPage
from id_card_generator.ui.export_page import ExportPage
from id_card_generator.ui.main_window import MainWindow


@pytest.fixture
def sample_template() -> TemplateDefinition:
    """Fixture providing a standard ID card template with multiple element types."""
    elem1 = CanvasElement(id="e-name", name="Full Name", type="dynamic_text", x=40, y=80, width=300, height=45)
    elem2 = CanvasElement(id="e-dept", name="Department", type="dynamic_text", x=40, y=140, width=280, height=35)
    elem3 = CanvasElement(id="e-photo", name="Profile Photo", type="photo", x=400, y=80, width=160, height=200)
    elem4 = CanvasElement(id="e-logo", name="Company Logo", type="image", x=40, y=20, width=100, height=40)
    elem5 = CanvasElement(id="e-shape", name="Card Divider", type="line", x=40, y=260, width=520, height=2)
    return TemplateDefinition(
        id="tmpl-test-1",
        name="Corporate Badge",
        width_px=600,
        height_px=400,
        dpi=300,
        unit="mm",
        width_physical=50.8,
        height_physical=33.87,
        border_color="#0078D4",
        border_width=2,
        safe_area_margin_mm=3.0,
        elements=[elem1, elem2, elem3, elem4, elem5],
    )


@pytest.fixture
def sample_records(temp_dir: Path) -> tuple[list[SourceRecord], dict[str, PhotoMatchResult], list[str]]:
    """Fixture providing source records, photo matches, and columns."""
    img_path = temp_dir / "101.jpg"
    from PIL import Image
    im = Image.new("RGB", (100, 100), color=(50, 100, 150))
    im.save(img_path, format="JPEG")

    recs = [
        SourceRecord(row_index=1, raw_pin="101", pin="101", data={"Full Name": "Rahul Sharma", "Dept": "Engineering"}),
        SourceRecord(row_index=2, raw_pin="102", pin="102", data={"Full Name": "Anita Roy", "Dept": "Product"}),
    ]
    matches = {
        recs[0].record_id: PhotoMatchResult(pin="101", photo_path=str(img_path)),
        recs[1].record_id: PhotoMatchResult(pin="102", photo_path=None),
    }
    cols = ["PIN Number", "Full Name", "Dept", "Office"]
    return recs, matches, cols


# =========================================================================
# 1. Template Designer Tests
# =========================================================================

def test_template_designer_initial_layout(qtbot, sample_template):
    """Verify editor starts in Mode 0 (Template Designer) with Photoshop-style tools and header."""
    page = EditorPage()
    qtbot.addWidget(page)
    page.load_template(sample_template)

    # Initial mode must be Template Designer (0)
    assert page.mode_stack.currentIndex() == 0

    # Header components exist
    assert hasattr(page, "btn_new_canvas")
    assert hasattr(page, "btn_save_template")
    assert hasattr(page, "btn_preview_pil")
    assert hasattr(page, "btn_finalize_template")
    assert page.lbl_app_template_name.text() == f"<b>{sample_template.name}</b>"

    # Essential design tools present in vertical tool strip
    tool_buttons = [btn.toolTip() for btn in page.tool_group.buttons()]
    assert any("Select" in t for t in tool_buttons)
    assert any("Text Tool" in t for t in tool_buttons)
    assert any("Dynamic Field" in t for t in tool_buttons)
    assert any("Photo Tool" in t for t in tool_buttons)
    assert any("Image / Logo" in t for t in tool_buttons)
    assert any("Rectangle" in t for t in tool_buttons)
    assert any("Line Tool" in t for t in tool_buttons)


def test_blank_canvas_dialog_configuration(qtbot):
    """Verify BlankCanvasDialog configures dimensions, border, safe-area margin, and starts with empty elements."""
    dialog = BlankCanvasDialog()
    qtbot.addWidget(dialog)

    dialog.txt_name.setText("Custom ID Badge")
    dialog.spin_width.setValue(85.6)
    dialog.spin_height.setValue(54.0)
    dialog.spin_border_width.setValue(3)
    dialog.spin_margin.setValue(4.5)
    dialog._border_color = "#333333"
    dialog._on_accept()

    tmpl = dialog.template_definition
    assert tmpl.name == "Custom ID Badge"
    assert tmpl.width_physical == 85.6
    assert tmpl.height_physical == 54.0
    assert tmpl.border_width == 3
    assert tmpl.border_color == "#333333"
    assert tmpl.safe_area_margin_mm == 4.5
    assert len(tmpl.elements) == 0  # Blank canvas starts with 0 elements


def test_template_finalization_validation_blocks_invalid(qtbot):
    """Verify TemplateValidator blocks finalization when template has invalid geometry."""
    page = EditorPage()
    qtbot.addWidget(page)

    # Invalid template: negative dimensions and out-of-bounds element
    bad_elem = CanvasElement(name="Offscreen Element", type="static_text", x=-500, y=-500, width=50, height=20)
    bad_tmpl = TemplateDefinition(
        name="Bad Template",
        width_px=0,  # Invalid
        height_px=400,
        dpi=300,
        elements=[bad_elem],
    )
    page.load_template(bad_tmpl)

    with patch("PySide6.QtWidgets.QMessageBox.critical") as mock_crit:
        success = page.finalize_template()
        assert success is False
        mock_crit.assert_called_once()
        # Remains in designer mode
        assert page.mode_stack.currentIndex() == 0


def test_template_finalization_success_transitions_to_mapping(qtbot, sample_template, sample_records):
    """Verify successful template finalization transitions to Mapping Editor mode."""
    recs, matches, cols = sample_records
    page = EditorPage()
    qtbot.addWidget(page)
    page.load_template(sample_template)
    page.set_dataset(recs, matches, cols)

    assert page.mode_stack.currentIndex() == 0

    success = page.finalize_template()
    assert success is True
    assert page.mode_stack.currentIndex() == 1  # Switched to Mapping Editor
    assert page.mapping_view.isVisibleTo(page)


# =========================================================================
# 2. Mapping Editor Tests
# =========================================================================

def test_mapping_editor_streamlined_controls(qtbot, sample_template, sample_records):
    """Verify Mapping Editor provides only data-binding controls and no design drawing tools."""
    recs, matches, cols = sample_records
    page = EditorPage()
    qtbot.addWidget(page)
    page.load_template(sample_template)
    page.set_dataset(recs, matches, cols)
    page.finalize_template()

    m_view = page.mapping_view

    # Header and navigation
    assert hasattr(m_view, "btn_edit_template")
    assert hasattr(m_view, "btn_goto_generate")

    # Elements list exists and populated with sample template elements
    assert m_view.list_elements.count() == len(sample_template.elements)

    # Elements list items show type and status
    item_texts = [m_view.list_elements.item(i).text() for i in range(m_view.list_elements.count())]
    assert any("Full Name" in t for t in item_texts)
    assert any("Profile Photo" in t for t in item_texts)
    assert any("Company Logo" in t for t in item_texts)
    assert any("Card Divider" in t for t in item_texts)

    # Binding controls present
    assert hasattr(m_view, "combo_columns")
    assert hasattr(m_view, "lbl_sample_val")
    assert hasattr(m_view, "chk_required")
    assert hasattr(m_view, "txt_fallback")
    assert hasattr(m_view, "btn_clear_binding")


def test_mapping_editor_arbitrary_column_binding(qtbot, sample_template, sample_records):
    """Verify dynamic text elements can be mapped to any spreadsheet column and preview bound value."""
    recs, matches, cols = sample_records
    page = EditorPage()
    qtbot.addWidget(page)
    page.load_template(sample_template)
    page.set_dataset(recs, matches, cols)
    page.finalize_template()

    m_view = page.mapping_view

    # Select "Full Name" item (row 0)
    m_view.list_elements.setCurrentRow(0)
    assert m_view.selected_element.name == "Full Name"

    # Map to "Full Name" column
    idx = m_view.combo_columns.findData("Full Name")
    assert idx >= 0
    m_view.combo_columns.setCurrentIndex(idx)

    # Mapping recorded
    assert m_view.column_mappings.get("e-name") == "Full Name"
    assert m_view.lbl_sample_val.text() == "Rahul Sharma"

    # Select "Department" item (row 1)
    m_view.list_elements.setCurrentRow(1)
    assert m_view.selected_element.name == "Department"

    # Map to arbitrary "Dept" column
    idx_dept = m_view.combo_columns.findData("Dept")
    assert idx_dept >= 0
    m_view.combo_columns.setCurrentIndex(idx_dept)
    assert m_view.column_mappings.get("e-dept") == "Dept"
    assert m_view.lbl_sample_val.text() == "Engineering"


def test_mapping_editor_sample_record_switching(qtbot, sample_template, sample_records):
    """Verify sample record next/prev updates bound values and photo resolution."""
    recs, matches, cols = sample_records
    page = EditorPage()
    qtbot.addWidget(page)
    page.load_template(sample_template)
    page.set_dataset(recs, matches, cols)
    page.finalize_template()

    m_view = page.mapping_view
    m_view.list_elements.setCurrentRow(0)
    idx = m_view.combo_columns.findData("Full Name")
    assert idx >= 0
    m_view.combo_columns.setCurrentIndex(idx)

    # Record 1
    assert "Rahul Sharma" in m_view.lbl_sample_val.text()
    assert "Record 1 of 2" in m_view.lbl_record_info.text()
    assert "Photo matched" in m_view.lbl_photo_info.text()

    # Next record
    m_view.btn_next.click()
    assert "Anita Roy" in m_view.lbl_sample_val.text()
    assert "Record 2 of 2" in m_view.lbl_record_info.text()
    assert "Photo missing" in m_view.lbl_photo_info.text()


def test_preserve_bindings_when_returning_to_designer(qtbot, sample_template, sample_records):
    """Verify valid bindings are preserved when returning to Template Designer and re-finalizing."""
    recs, matches, cols = sample_records
    page = EditorPage()
    qtbot.addWidget(page)
    page.load_template(sample_template)
    page.set_dataset(recs, matches, cols)
    page.finalize_template()

    m_view = page.mapping_view
    m_view.list_elements.setCurrentRow(0)
    idx = m_view.combo_columns.findData("Full Name")
    m_view.combo_columns.setCurrentIndex(idx)
    assert m_view.column_mappings.get("e-name") == "Full Name"

    # User clicks "◀ Edit Template" to return to designer
    m_view.btn_edit_template.click()
    assert page.mode_stack.currentIndex() == 0  # Back in designer

    # Modify designer: add a new element, but "e-name" remains intact
    new_el = CanvasElement(id="e-empcode", name="Emp Code", type="dynamic_text", x=40, y=200, width=150, height=30)
    page.scene.add_element(new_el)

    # Re-finalize template
    success = page.finalize_template()
    assert success is True
    assert page.mode_stack.currentIndex() == 1  # Back in mapping editor

    # The mapping for "e-name" must STILL BE PRESERVED
    assert page.column_mappings.get("e-name") == "Full Name"
    assert page.mapping_view.column_mappings.get("e-name") == "Full Name"


# =========================================================================
# 3. Export Improvements Tests
# =========================================================================

def test_export_configuration_and_auto_open_setting(temp_dir: Path):
    """Verify ExportConfiguration and ProjectConfiguration support open_output_dir_on_complete."""
    cfg = ExportConfiguration(
        output_dir=str(temp_dir),
        open_output_dir_on_complete=True,
    )
    assert cfg.open_output_dir_on_complete is True

    proj = ProjectConfiguration(
        name="Test Project",
        last_export_dir=str(temp_dir),
        open_output_dir_on_export=True,
    )
    assert proj.open_output_dir_on_export is True


def test_export_page_auto_open_checkbox_and_manual_button(qtbot, temp_dir: Path):
    """Verify ExportPage has chk_auto_open checkbox and btn_open_dest manual button."""
    page = ExportPage()
    qtbot.addWidget(page)

    assert hasattr(page, "chk_auto_open")
    assert hasattr(page, "btn_open_dest")
    assert page.chk_auto_open.text() == "Open output directory automatically when export completes"
    assert page.btn_open_dest.text() == "Open Output Folder"
    assert page.btn_open_dest.isEnabled()


def test_export_page_manual_open_nonexistent_handled(qtbot, temp_dir: Path):
    """Verify clicking Open Output Folder when directory is nonexistent prompts gracefully."""
    page = ExportPage()
    qtbot.addWidget(page)

    nonexistent = temp_dir / "does_not_exist_yet"
    page.set_destination_dir(nonexistent)

    # User answers No to creation prompt
    with patch("PySide6.QtWidgets.QMessageBox.question", return_value=QMessageBox.No) as mock_q:
        page.btn_open_dest.click()
        mock_q.assert_called_once()
        assert not nonexistent.exists()


def test_export_auto_open_triggers_only_on_successful_export(qtbot, temp_dir: Path):
    """Verify automatic folder opening is called only when enabled and export succeeded with >0 files."""
    page = ExportPage()
    qtbot.addWidget(page)

    out_dir = temp_dir / "cards"
    out_dir.mkdir(parents=True, exist_ok=True)
    page.set_destination_dir(out_dir)

    # Mock _open_in_explorer
    page._open_in_explorer = MagicMock()

    # Case 1: Checkbox disabled -> does not open
    page.chk_auto_open.setChecked(False)
    page._on_export_finished(exported_count=5, failed_count=0)
    page._open_in_explorer.assert_not_called()

    # Case 2: Checkbox enabled, but 0 exported files -> does not open
    page.chk_auto_open.setChecked(True)
    page._on_export_finished(exported_count=0, failed_count=2)
    page._open_in_explorer.assert_not_called()

    # Case 3: Checkbox enabled and successful export (>0) -> opens directory
    page._on_export_finished(exported_count=10, failed_count=0)
    page._open_in_explorer.assert_called_once()
