"""Tests for template section visual canvas preview and canvas properties editing."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QApplication

from id_card_generator.core.models import TemplateDefinition, CanvasElement
from id_card_generator.ui.dialogs.blank_canvas_dialog import CanvasPropertiesDialog, BlankCanvasDialog
from id_card_generator.ui.template_page import TemplatePage


@pytest.fixture
def template_page(qtbot):
    """Fixture providing initialized TemplatePage."""
    page = TemplatePage()
    qtbot.addWidget(page)
    return page


def test_template_page_loads_and_previews(template_page: TemplatePage):
    """Verify selecting a template loads details and renders a live canvas preview."""
    assert template_page.list_widget.count() > 0
    assert template_page.active_template is not None

    # Verify preview card exists and has a rendered pixmap
    assert template_page.preview_card is not None
    assert template_page.preview_card._original_pixmap is not None
    assert not template_page.preview_card._original_pixmap.isNull()
    assert template_page.preview_card._original_pixmap.width() > 0
    assert template_page.preview_card._original_pixmap.height() > 0

    # Verify specs badge is set
    badge_text = template_page.preview_card.lbl_badge.text()
    assert "px" in badge_text
    assert "DPI" in badge_text


def test_template_page_inline_property_editing(template_page: TemplatePage, qtbot):
    """Verify editing canvas properties inline updates preview and saves changes."""
    first_item = template_page.list_widget.item(0)
    template_page.list_widget.setCurrentItem(first_item)
    orig_tmpl = template_page.active_template
    assert orig_tmpl is not None

    # 1. Edit name inline
    template_page.txt_tmpl_name.setText("Customized Preview Test Card")
    assert "Customized Preview Test Card" in template_page.lbl_tmpl_title.text()

    # 2. Change background color
    template_page._current_bg_color = "#123456"
    template_page._update_prop_color_btn()
    assert template_page.lbl_prop_bg_hex.text() == "#123456"

    # 3. Save inline properties
    template_page._save_inline_properties()

    # Verify the updated template is loaded and active
    assert template_page.active_template is not None
    assert "Customized Preview Test Card" in template_page.active_template.name
    assert template_page.active_template.background_color == "#123456"


def test_canvas_properties_dialog_edit_existing(qtbot):
    """Verify CanvasPropertiesDialog pre-fills and preserves elements for an existing template."""
    sample_elem = CanvasElement(name="Badge Photo", type="photo", x=10, y=20, width=100, height=120)
    tmpl = TemplateDefinition(
        name="Conference Badge",
        width_px=800,
        height_px=500,
        dpi=300,
        unit="mm",
        width_physical=85.6,
        height_physical=54.0,
        orientation="landscape",
        background_color="#ABCDEF",
        elements=[sample_elem],
    )

    dialog = CanvasPropertiesDialog(existing_template=tmpl)
    qtbot.addWidget(dialog)

    # Verify dialog pre-populated fields
    assert dialog.txt_name.text() == "Conference Badge"
    assert dialog.spin_dpi.value() == 300
    assert dialog.radio_landscape.isChecked()
    assert dialog._bg_color == "#ABCDEF"
    assert dialog.spin_width.value() == 85.6
    assert dialog.spin_height.value() == 54.0

    # Modify properties
    dialog.txt_name.setText("Updated Conference Badge")
    dialog._bg_color = "#FEDCBA"
    dialog.spin_dpi.setValue(600)

    # Accept dialog
    dialog._on_accept()

    result_tmpl = dialog.template_definition
    assert result_tmpl is not None
    assert result_tmpl.name == "Updated Conference Badge"
    assert result_tmpl.background_color == "#FEDCBA"
    assert result_tmpl.dpi == 600
    # Verify existing elements are preserved!
    assert len(result_tmpl.elements) == 1
    assert result_tmpl.elements[0].name == "Badge Photo"


def test_template_page_double_click_signal(template_page: TemplatePage, monkeypatch):
    """Verify double-clicking an item in the left menu opens the template property editor."""
    first_item = template_page.list_widget.item(0)
    assert first_item is not None

    called_with_template = []

    def mock_edit(tmpl=None):
        called_with_template.append(tmpl or template_page.active_template)

    monkeypatch.setattr(template_page, "_edit_canvas_properties", mock_edit)

    # Double-click the list item
    template_page._on_item_double_clicked(first_item)

    assert len(called_with_template) == 1
    assert called_with_template[0] is not None
