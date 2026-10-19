"""Tests for Mapping Editor text tool properties: complete system font loading, spacing, and segmented alignment buttons."""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QFontComboBox

from id_card_generator.core.models import TemplateDefinition, CanvasElement
from id_card_generator.rendering.font_manager import FontManager
from id_card_generator.ui.editor_page import EditorPage


@pytest.fixture
def editor_page(qtbot):
    """Fixture providing initialized EditorPage."""
    page = EditorPage()
    qtbot.addWidget(page)
    tmpl = TemplateDefinition(name="Font Test Template", width_px=800, height_px=500)
    page.load_template(tmpl)
    return page


def test_system_fonts_registration_and_dropdown(editor_page: EditorPage):
    """Verify system fonts are registered with Qt and QFontComboBox has all fonts enabled."""
    FontManager.register_system_fonts_with_qt()
    combo = editor_page.ctx_font_family

    assert combo.fontFilters() == QFontComboBox.FontFilter.AllFonts
    assert combo.writingSystem() == QFontDatabase.WritingSystem.Any
    # Should contain system fonts (standard Qt font database has > 100 fonts, registering system dirs yields > 250)
    assert combo.count() > 100


def test_alignment_segmented_rectangle_buttons(editor_page: EditorPage):
    """Verify Left / Center / Right alignment buttons inside the rectangle."""
    # 1. Add static text
    editor_page._add_static_text()
    item = editor_page.scene.get_selected_item()
    assert item is not None

    # Initial default is left
    assert editor_page.ctx_btn_align_left.isChecked()
    assert not editor_page.ctx_btn_align_center.isChecked()
    assert not editor_page.ctx_btn_align_right.isChecked()
    assert item.element.style.text_align == "left"

    # 2. Click Center
    editor_page.ctx_btn_align_center.click()
    assert not editor_page.ctx_btn_align_left.isChecked()
    assert editor_page.ctx_btn_align_center.isChecked()
    assert not editor_page.ctx_btn_align_right.isChecked()
    assert item.element.style.text_align == "center"
    assert editor_page.ctx_cmb_align.currentText() == "center"

    # 3. Click Right
    editor_page.ctx_btn_align_right.click()
    assert not editor_page.ctx_btn_align_left.isChecked()
    assert not editor_page.ctx_btn_align_center.isChecked()
    assert editor_page.ctx_btn_align_right.isChecked()
    assert item.element.style.text_align == "right"
    assert editor_page.ctx_cmb_align.currentText() == "right"

    # 4. Click Left
    editor_page.ctx_btn_align_left.click()
    assert editor_page.ctx_btn_align_left.isChecked()
    assert not editor_page.ctx_btn_align_center.isChecked()
    assert not editor_page.ctx_btn_align_right.isChecked()
    assert item.element.style.text_align == "left"
    assert editor_page.ctx_cmb_align.currentText() == "left"


def test_inspector_alignment_buttons_sync(editor_page: EditorPage):
    """Verify ElementInspector alignment buttons work and synchronize with canvas and context bar."""
    editor_page._add_static_text()
    item = editor_page.scene.get_selected_item()
    assert item is not None

    # Click Center on Inspector
    editor_page.inspector.btn_align_center.click()
    assert item.element.style.text_align == "center"
    assert editor_page.inspector.btn_align_center.isChecked()
    assert editor_page.ctx_btn_align_center.isChecked()

    # Click Right on Inspector
    editor_page.inspector.btn_align_right.click()
    assert item.element.style.text_align == "right"
    assert editor_page.inspector.btn_align_right.isChecked()
    assert editor_page.ctx_btn_align_right.isChecked()


def test_bold_italic_toggle_buttons(editor_page: EditorPage):
    """Verify bold and italic toggle buttons update element styling."""
    editor_page._add_static_text()
    item = editor_page.scene.get_selected_item()
    assert item is not None

    # Initial state
    assert not editor_page.ctx_chk_bold.isChecked()
    assert not editor_page.ctx_chk_italic.isChecked()

    # Toggle bold
    editor_page.ctx_chk_bold.click()
    assert editor_page.ctx_chk_bold.isChecked()
    assert item.element.style.font_bold is True

    # Toggle italic
    editor_page.ctx_chk_italic.click()
    assert editor_page.ctx_chk_italic.isChecked()
    assert item.element.style.font_italic is True

    # Toggle bold off
    editor_page.ctx_chk_bold.click()
    assert not editor_page.ctx_chk_bold.isChecked()
    assert item.element.style.font_bold is False


def test_selection_syncs_alignment_and_font(editor_page: EditorPage):
    """Verify selecting an element with custom font and alignment updates the context bar correctly."""
    elem = CanvasElement(
        name="Custom Text",
        type="static_text",
        static_content="Sample",
        x=50,
        y=50,
        width=200,
        height=40,
    )
    elem.style.text_align = "center"
    elem.style.font_bold = True
    elem.style.font_italic = True
    elem.style.font_size = 18.0

    editor_page.scene.add_element(elem)
    item = editor_page.scene._items_by_id.get(elem.id)
    assert item is not None
    editor_page.scene.clearSelection()
    item.setSelected(True)
    editor_page._on_element_selected(item)

    assert editor_page.ctx_btn_align_center.isChecked()
    assert not editor_page.ctx_btn_align_left.isChecked()
    assert editor_page.ctx_chk_bold.isChecked()
    assert editor_page.ctx_chk_italic.isChecked()
    assert editor_page.ctx_font_size.value() == 18
    assert editor_page.ctx_btn_color.width() == 28
    assert editor_page.ctx_btn_color.height() == 28
    assert not editor_page.ctx_btn_color.icon().isNull()


def test_text_color_button_compact_icon(editor_page: EditorPage):
    """Verify the color button is a 28x28 square button with icon indicator."""
    btn = editor_page.ctx_btn_color
    assert btn.width() == 28
    assert btn.height() == 28
    assert btn.toolTip() == "Text Color"

    # Add text element and change color
    editor_page._add_static_text()
    item = editor_page.scene.get_selected_item()
    assert item is not None

    item.element.style.font_color = "#3B82F6"
    editor_page._update_context_options(item)
    assert getattr(editor_page, "_current_font_color", None) == "#3B82F6"
    assert not btn.icon().isNull()

