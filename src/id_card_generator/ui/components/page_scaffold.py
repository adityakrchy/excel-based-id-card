"""Reusable page scaffolding for the ID Studio workspaces.

Every workflow page is built from the same three pieces so the whole
application feels like one product:

* :class:`PageHeader` - step badge, title, subtitle and a slot for the
  contextual actions of the screen.
* :class:`PageFooter` - the step progress badge plus the Back / Next controls
  that drive the linear production pipeline.
* :class:`EmptyState` - a friendly placeholder for screens without data yet.
"""

from typing import Optional

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.ui.studio_tokens import (
    FONT_FAMILY_MONO,
    FONT_FAMILY_UI,
    PRIMARY,
    SURFACE,
    SURFACE_CONTAINER,
    TEXT_MUTED,
    TYPOGRAPHY,
)


class PageHeader(QFrame):
    """Title block for a workspace page."""

    def __init__(
        self,
        title: str = "",
        subtitle: str = "",
        badge: str = "",
        height: int = 64,
        parent=None,
    ):
        super().__init__(parent)
        self.setObjectName("page_header")
        self.setFixedHeight(height)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 10, 20, 10)
        layout.setSpacing(16)

        text_col = QVBoxLayout()
        text_col.setContentsMargins(0, 0, 0, 0)
        text_col.setSpacing(2)

        self.lbl_badge = QLabel(badge)
        self.lbl_badge.setStyleSheet(
            f"color: {PRIMARY}; font-family: {FONT_FAMILY_MONO}; "
            f"font-size: 10px; font-weight: 700; letter-spacing: 0.1em;"
        )
        self.lbl_badge.setVisible(bool(badge))
        text_col.addWidget(self.lbl_badge)

        self.lbl_title = QLabel(title)
        self.lbl_title.setStyleSheet(
            f"color: #FFFFFF; font-family: {FONT_FAMILY_UI}; "
            f"font-size: {TYPOGRAPHY.SIZE_DISPLAY}px; font-weight: 700;"
        )
        text_col.addWidget(self.lbl_title)

        self.lbl_subtitle = QLabel(subtitle)
        self.lbl_subtitle.setStyleSheet(f"color: {TEXT_MUTED}; font-size: 11px;")
        self.lbl_subtitle.setVisible(bool(subtitle))
        text_col.addWidget(self.lbl_subtitle)

        layout.addLayout(text_col)
        layout.addStretch(1)

        # Right hand side: contextual actions supplied by the page.
        self.actions_layout = QHBoxLayout()
        self.actions_layout.setContentsMargins(0, 0, 0, 0)
        self.actions_layout.setSpacing(8)
        layout.addLayout(self.actions_layout)

    # -- content ----------------------------------------------------
    def set_title(self, title: str) -> None:
        self.lbl_title.setText(title)

    def set_subtitle(self, subtitle: str) -> None:
        self.lbl_subtitle.setText(subtitle)
        self.lbl_subtitle.setVisible(bool(subtitle))

    def set_badge(self, badge: str) -> None:
        self.lbl_badge.setText(badge)
        self.lbl_badge.setVisible(bool(badge))

    def add_action(self, widget: QWidget) -> None:
        """Append a contextual action widget to the right of the header."""
        self.actions_layout.addWidget(widget)

    def add_action_stretch(self) -> None:
        """Push the actions that follow to the far right."""
        self.actions_layout.insertStretch(0, 1)


class PageFooter(QFrame):
    """Bottom navigation bar driving the linear production pipeline."""

    back_requested = Signal()
    next_requested = Signal()

    def __init__(
        self,
        prev_label: Optional[str] = None,
        next_label: Optional[str] = None,
        step_badge: Optional[str] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self.setObjectName("page_footer")
        self.setFixedHeight(52)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(20, 8, 20, 8)
        layout.setSpacing(12)

        self.btn_back = QPushButton(f"◀  {prev_label}" if prev_label else "◀  Back")
        self.btn_back.setCursor(Qt.PointingHandCursor)
        self.btn_back.setObjectName("btn_ghost")
        self.btn_back.clicked.connect(self.back_requested.emit)
        self.btn_back.setVisible(bool(prev_label))
        layout.addWidget(self.btn_back)

        layout.addStretch(1)

        self.lbl_badge = QLabel(step_badge or "")
        self.lbl_badge.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: {FONT_FAMILY_MONO}; "
            f"font-size: 11px; letter-spacing: 0.06em;"
        )
        self.lbl_badge.setVisible(bool(step_badge))
        layout.addWidget(self.lbl_badge)

        layout.addStretch(1)

        self.btn_next = QPushButton(f"{next_label}  ➔" if next_label else "Next  ➔")
        self.btn_next.setObjectName("btn_primary")
        self.btn_next.setCursor(Qt.PointingHandCursor)
        self.btn_next.clicked.connect(self.next_requested.emit)
        self.btn_next.setVisible(bool(next_label))
        layout.addWidget(self.btn_next)

    # -- content ----------------------------------------------------
    def set_step_badge(self, text: str) -> None:
        self.lbl_badge.setText(text)
        self.lbl_badge.setVisible(bool(text))

    def set_back_visible(self, visible: bool) -> None:
        self.btn_back.setVisible(visible)

    def set_next_visible(self, visible: bool) -> None:
        self.btn_next.setVisible(visible)

    def set_next_enabled(self, enabled: bool) -> None:
        self.btn_next.setEnabled(enabled)

    def set_next_text(self, text: str) -> None:
        self.btn_next.setText(f"{text}  ➔")

    def set_back_text(self, text: str) -> None:
        self.btn_back.setText(f"◀  {text}")

    def set_next_tooltip(self, text: str) -> None:
        self.btn_next.setToolTip(text)


class EmptyState(QWidget):
    """Friendly placeholder used when a screen has nothing to show yet."""

    def __init__(
        self,
        title: str = "Nothing here yet",
        description: str = "",
        icon: str = "◌",
        action_text: str = "",
        parent=None,
    ):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 32, 32, 32)
        layout.setSpacing(8)
        layout.addStretch(1)

        self.lbl_icon = QLabel(icon)
        self.lbl_icon.setAlignment(Qt.AlignCenter)
        self.lbl_icon.setStyleSheet("font-size: 26px; color: #4A4D57;")
        layout.addWidget(self.lbl_icon)

        self.lbl_title = QLabel(title)
        self.lbl_title.setAlignment(Qt.AlignCenter)
        self.lbl_title.setStyleSheet(
            f"color: {TEXT_MUTED}; font-family: {FONT_FAMILY_UI}; "
            f"font-size: 13px; font-weight: 600;"
        )
        layout.addWidget(self.lbl_title)

        self.lbl_description = QLabel(description)
        self.lbl_description.setAlignment(Qt.AlignCenter)
        self.lbl_description.setWordWrap(True)
        self.lbl_description.setStyleSheet(f"color: #6C7280; font-size: 11px;")
        self.lbl_description.setVisible(bool(description))
        layout.addWidget(self.lbl_description)

        self.btn_action = QPushButton(action_text)
        self.btn_action.setObjectName("btn_primary")
        self.btn_action.setVisible(bool(action_text))
        self.btn_action.setCursor(Qt.PointingHandCursor)
        layout.addWidget(self.btn_action, 0, Qt.AlignCenter)

        layout.addStretch(1)

    def set_title(self, title: str) -> None:
        self.lbl_title.setText(title)

    def set_description(self, description: str) -> None:
        self.lbl_description.setText(description)
        self.lbl_description.setVisible(bool(description))

    def set_action_text(self, text: str) -> None:
        self.btn_action.setText(text)
        self.btn_action.setVisible(bool(text))


class InlineNotice(QLabel):
    """Non-blocking banner used to report errors, warnings and confirmations.

    Modal dialogs are avoided on purpose: they block the workflow and stall
    automated runs.  The banner keeps the information visible in context.
    """

    SEVERITIES = ("info", "success", "warning", "error")

    def __init__(self, message: str = "", severity: str = "info", parent=None):
        super().__init__(parent)
        self.setObjectName("notice_banner")
        self.setWordWrap(True)
        self.setVisible(False)
        self._severity = "info"
        self.set_message(message, severity)

    @property
    def severity(self) -> str:
        """The severity of the message currently shown."""
        return self._severity

    def set_message(self, message: str, severity: str = "info") -> None:
        """Show (or hide, when the message is empty) the banner."""
        severity = severity if severity in self.SEVERITIES else "info"
        self._severity = severity
        self.setProperty("severity", severity)
        # Re-polish so the severity specific styling is applied.
        self.style().unpolish(self)
        self.style().polish(self)
        self.setText(message)
        self.setVisible(bool(message))

    def clear_message(self) -> None:
        self._severity = "info"
        self.setText("")
        self.setVisible(False)
