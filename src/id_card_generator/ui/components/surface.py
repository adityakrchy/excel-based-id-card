"""Surface containers and metric tiles used across the ID Studio pages."""

from typing import Optional

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.ui.studio_tokens import (
    FONT_FAMILY_MONO,
    FONT_FAMILY_UI,
    SURFACE_CONTAINER,
    SURFACE_HIGH,
    TEXT_MUTED,
    TYPOGRAPHY,
)


class SurfaceCard(QFrame):
    """A titled panel used to group related controls on a page."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("surface_card")
        self.setFrameShape(QFrame.NoFrame)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # The header row is a real widget so it can be shown / hidden.
        self.header_widget = QWidget()
        self.header = QHBoxLayout(self.header_widget)
        self.header.setContentsMargins(14, 10, 14, 8)
        self.header.setSpacing(8)
        self.header_widget.setVisible(bool(title or subtitle))

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(1)

        self.lbl_title = QLabel(title)
        self.lbl_title.setProperty("role", "cardTitle")
        text_col.addWidget(self.lbl_title)

        self.lbl_subtitle = QLabel(subtitle)
        self.lbl_subtitle.setProperty("role", "cardSubtitle")
        self.lbl_subtitle.setVisible(bool(subtitle))
        text_col.addWidget(self.lbl_subtitle)

        self.header.addLayout(text_col)
        self.header.addStretch(1)

        # Optional header actions (added via add_header_action).
        self.header_actions = QHBoxLayout()
        self.header_actions.setContentsMargins(0, 0, 0, 0)
        self.header_actions.setSpacing(6)
        self.header.addLayout(self.header_actions)

        outer.addWidget(self.header_widget)

        self.divider = QFrame()
        self.divider.setFixedHeight(1)
        self.divider.setStyleSheet(f"background-color: {SURFACE_HIGH};")
        self.divider.setVisible(bool(title or subtitle))
        outer.addWidget(self.divider)

        self.content = QVBoxLayout()
        self.content.setContentsMargins(14, 12, 14, 12)
        self.content.setSpacing(10)
        outer.addLayout(self.content)

    # -- content ----------------------------------------------------
    def add_header_action(self, widget: QWidget) -> None:
        self.header_actions.addWidget(widget)

    def add(self, widget: QWidget, stretch: int = 0) -> None:
        """Add a widget to the card body."""
        self.content.addWidget(widget, stretch)

    def add_layout(self, layout) -> None:
        """Add a layout to the card body."""
        self.content.addLayout(layout)

    def set_title(self, title: str) -> None:
        self.lbl_title.setText(title)
        self._sync_header_visibility()

    def set_subtitle(self, subtitle: str) -> None:
        self.lbl_subtitle.setText(subtitle)
        self.lbl_subtitle.setVisible(bool(subtitle))
        self._sync_header_visibility()

    def _sync_header_visibility(self) -> None:
        visible = bool(self.lbl_title.text() or self.lbl_subtitle.text())
        self.header_widget.setVisible(visible)
        self.divider.setVisible(visible)


class StatTile(QFrame):
    """Compact metric tile (caption + value) used on dashboards."""

    def __init__(
        self,
        caption: str = "",
        value: str = "0",
        accent: Optional[str] = None,
        hint: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("surface_card")
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.setMinimumHeight(76)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        self.lbl_caption = QLabel(caption)
        self.lbl_caption.setProperty("role", "metricCaption")
        layout.addWidget(self.lbl_caption)

        self.lbl_value = QLabel(value)
        self.lbl_value.setProperty("role", "metricValue")
        if accent:
            self.lbl_value.setStyleSheet(f"color: {accent};")
        layout.addWidget(self.lbl_value)

        self.lbl_hint = QLabel(hint)
        self.lbl_hint.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 10px;")
        self.lbl_hint.setVisible(bool(hint))
        layout.addWidget(self.lbl_hint)

    def set_value(self, value) -> None:
        self.lbl_value.setText(str(value))

    def set_hint(self, hint: str) -> None:
        self.lbl_hint.setText(hint)
        self.lbl_hint.setVisible(bool(hint))

    def set_accent(self, accent: Optional[str]) -> None:
        self.lbl_value.setStyleSheet(f"color: {accent};" if accent else "")
