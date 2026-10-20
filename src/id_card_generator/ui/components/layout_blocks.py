"""Small building blocks that give every screen the same quiet rhythm."""

from typing import Iterable, List, Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QMenu,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.ui.studio_tokens import BORDER_DEFAULT, SIZES, TEXT_MUTED


class OverflowMenu(QToolButton):
    """A "⋯" button that holds the secondary actions of a screen.

    Every screen keeps exactly one obvious action and moves the rest into
    this menu, so the interface stays calm.
    """

    def __init__(self, tooltip: str = "More actions", parent=None):
        super().__init__(parent)
        self.setText("⋯")
        self.setObjectName("btn_ghost")
        self.setFixedSize(SIZES.CONTROL_HEIGHT, SIZES.CONTROL_HEIGHT)
        self.setToolTip(tooltip)
        self.setPopupMode(QToolButton.InstantPopup)
        self.setCursor(Qt.PointingHandCursor)

        self._menu = QMenu(self)
        self.setMenu(self._menu)

    def add_action(self, text: str, triggered=None, shortcut: str = "") -> QAction:
        """Add an entry to the menu and return the action."""
        action = self._menu.addAction(text)
        if shortcut:
            action.setShortcut(shortcut)
        if triggered is not None:
            action.triggered.connect(triggered)
        return action

    def add_separator(self) -> None:
        self._menu.addSeparator()

    def add_actions(self, entries: Iterable) -> None:
        """Add several (text, callback) pairs at once."""
        for text, callback in entries:
            self.add_action(text, callback)

    def set_action_enabled(self, text: str, enabled: bool) -> None:
        """Enable or disable an entry by its label."""
        for action in self._menu.actions():
            if action.text() == text:
                action.setEnabled(enabled)
                return

    def menu(self) -> QMenu:
        return self._menu


class Section(QWidget):
    """A titled block of content with a hairline separator."""

    def __init__(self, title: str = "", parent=None):
        super().__init__(parent)
        self._layout = QVBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(8)

        self.lbl_title = QLabel(title.upper() if title else "")
        self.lbl_title.setProperty("role", "sectionLabel")
        self.lbl_title.setVisible(bool(title))
        self._layout.addWidget(self.lbl_title)

        self.content = QVBoxLayout()
        self.content.setContentsMargins(0, 0, 0, 0)
        self.content.setSpacing(8)
        self._layout.addLayout(self.content)

    def add(self, widget: QWidget) -> None:
        self.content.addWidget(widget)

    def add_layout(self, layout) -> None:
        self.content.addLayout(layout)

    def set_title(self, title: str) -> None:
        self.lbl_title.setText(title.upper())
        self.lbl_title.setVisible(bool(title))


class Divider(QFrame):
    """A one pixel hairline."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedHeight(1)
        self.setStyleSheet(f"background-color: {BORDER_DEFAULT};")


class StatLine(QWidget):
    """A single, quiet line of statistics.

    Replaces the rows of coloured pills that used to sit above every table.
    """

    def __init__(self, parent=None):
        super().__init__(parent)
        self._layout = QHBoxLayout(self)
        self._layout.setContentsMargins(0, 0, 0, 0)
        self._layout.setSpacing(14)
        self._labels: List[QLabel] = []

    def set_stats(self, stats: Iterable) -> None:
        """Set the statistics from (label, value, colour) tuples."""
        while self._layout.count():
            item = self._layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._labels.clear()

        for stat in stats:
            label, value = stat[0], stat[1]
            colour = stat[2] if len(stat) > 2 else None

            caption = QLabel(str(label).upper())
            caption.setProperty("role", "statCaption")
            self._layout.addWidget(caption)

            figure = QLabel(str(value))
            figure.setProperty("role", "statValue")
            if colour:
                figure.setStyleSheet(f"color: {colour};")
            self._layout.addWidget(figure)
            self._labels.append(figure)

        self._layout.addStretch()

    def set_value(self, index: int, value) -> None:
        """Update one of the values."""
        if 0 <= index < len(self._labels):
            self._labels[index].setText(str(value))
