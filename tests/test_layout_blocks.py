"""Tests for the shared layout blocks of the design system.

Every screen follows the same rules: one obvious action, the rest in an
overflow menu, statistics on a single quiet line and sections instead of
boxed groups.  These tests lock the blocks that make that possible.
"""

import pytest
from PySide6.QtWidgets import QLabel

from id_card_generator.ui.components.layout_blocks import (
    Divider,
    OverflowMenu,
    Section,
    StatLine,
)


def test_overflow_menu_holds_actions(qtbot):
    """The overflow menu collects the secondary actions."""
    menu = OverflowMenu()
    qtbot.addWidget(menu)

    clicked = []
    menu.add_action("Duplicate", lambda: clicked.append("duplicate"))
    menu.add_action("Export", lambda: clicked.append("export"))
    menu.add_separator()

    labels = [action.text() for action in menu.menu().actions() if action.text()]
    assert labels == ["Duplicate", "Export"]

    menu.menu().actions()[0].trigger()
    assert clicked == ["duplicate"]


def test_overflow_menu_can_disable_an_action(qtbot):
    """An action can be greyed out (e.g. delete for a built-in)."""
    menu = OverflowMenu()
    qtbot.addWidget(menu)
    menu.add_action("Delete template")

    menu.set_action_enabled("Delete template", False)
    assert menu.menu().actions()[0].isEnabled() is False


def test_stat_line_shows_numbers_without_pills(qtbot):
    """The statistics are one quiet line of caption / value pairs."""
    line = StatLine()
    qtbot.addWidget(line)

    line.set_stats([
        ("Records", 120),
        ("Errors", 3, "#ff0000"),
    ])

    captions = [w.text() for w in line.findChildren(QLabel) if w.property("role") == "statCaption"]
    values = [w.text() for w in line.findChildren(QLabel) if w.property("role") == "statValue"]

    assert captions == ["RECORDS", "ERRORS"]
    assert values == ["120", "3"]


def test_stat_line_updates_a_single_value(qtbot):
    """A single value can be updated in place."""
    line = StatLine()
    qtbot.addWidget(line)
    line.set_stats([("Records", 0)])

    line.set_value(0, 42)
    values = [w.text() for w in line.findChildren(QLabel) if w.property("role") == "statValue"]
    assert values == ["42"]


def test_section_has_a_title_and_content(qtbot):
    """A section carries a title and hosts widgets."""
    section = Section("appearance")
    qtbot.addWidget(section)

    assert section.lbl_title.text() == "APPEARANCE"

    label = QLabel("hello")
    section.add(label)
    assert section.content.count() == 1


def test_divider_is_a_hairline(qtbot):
    """The divider is a single pixel line."""
    line = Divider()
    qtbot.addWidget(line)
    assert line.height() == 1
