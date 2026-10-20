"""Tests for the redesigned template browser.

The page used to be a plain list with a dense inspector.  It is now a gallery
of card thumbnails next to a quiet details rail, and these tests lock the
new behaviour in.
"""

import pytest
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QListView

from id_card_generator.ui.template_page import TemplatePage


@pytest.fixture
def template_page(qtbot):
    page = TemplatePage()
    qtbot.addWidget(page)
    page.show()
    return page


def test_gallery_shows_card_thumbnails(template_page: TemplatePage):
    """The list is a gallery of cards, not a list of names."""
    assert template_page.list_widget.viewMode() == QListView.IconMode
    assert template_page.list_widget.flow() == QListView.LeftToRight
    assert template_page.list_widget.isWrapping()

    first = template_page.list_widget.item(0)
    assert first.sizeHint().width() > 120
    assert first.sizeHint().height() > 120


def test_gallery_items_carry_the_plain_name(template_page: TemplatePage):
    """The type tag is drawn by the delegate, not baked into the label."""
    first = template_page.list_widget.item(0)
    assert "[Built-in]" not in first.text()
    assert "[Custom]" not in first.text()


def test_gallery_renders_a_thumbnail(template_page: TemplatePage):
    """Every template gets a real preview of the card."""
    template_id = template_page.list_widget.item(0).data(Qt.UserRole)
    thumbnail = template_page._template_thumbnail(template_id)
    assert thumbnail is not None
    assert not thumbnail.isNull()


def test_details_rail_lists_the_specifications(template_page: TemplatePage):
    """The specifications are a scannable list, not a monospace blob."""
    from PySide6.QtWidgets import QLabel

    template_page.list_widget.setCurrentRow(0)
    labels = template_page.spec_list.findChildren(QLabel)
    assert len(labels) >= 10, "the specification list is empty"

    values = [label.text() for label in labels if label.property("role") == "specValue"]
    assert any("mm" in value for value in values)
    assert any("DPI" in value for value in values)


def test_only_one_primary_action(template_page: TemplatePage):
    """The details rail has a single primary action."""
    assert template_page.btn_use.objectName() == "btn_primary"
    assert template_page.btn_use.isVisibleTo(template_page)

    # The secondary actions live in the overflow menu.
    assert template_page.btn_more.menu() is not None
    actions = [a.text() for a in template_page.btn_more.menu().actions() if a.text()]
    assert "Duplicate" in actions
    assert "Export JSON" in actions


def test_save_action_appears_only_when_edited(template_page: TemplatePage):
    """The save action is hidden until something was changed."""
    template_page.list_widget.setCurrentRow(0)
    assert template_page.btn_save_prop.isHidden()

    template_page.txt_tmpl_name.setText("Renamed template")
    assert not template_page.btn_save_prop.isHidden()


def test_type_tag_is_plain_text(template_page: TemplatePage):
    """The type tag reads 'Built-in' or 'Custom Saved'."""
    template_page.list_widget.setCurrentRow(0)
    assert template_page.lbl_tmpl_badge.text() in ("Built-in", "Custom Saved")
