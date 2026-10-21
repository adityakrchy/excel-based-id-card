"""Virtual record list used by the review workstation.

The list is backed by a real model/view pair, so a project with thousands of
records scrolls without building a widget per row.  Each row shows the PIN,
the name and a short flag for the problems the operator has to look at.
"""

from dataclasses import dataclass, field
from typing import List, Optional, Sequence, Tuple

from PySide6.QtCore import QAbstractListModel, QModelIndex, QRectF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QFontMetrics, QPainter, QPen
from PySide6.QtWidgets import QListView, QStyle, QStyledItemDelegate

from id_card_generator.ui.font_scaling import font_scale, scaled_point
from id_card_generator.ui.studio_tokens import (
    FONT_FAMILY_MONO,
    FONT_FAMILY_UI,
    active_palette,
)

# Record severities.
SEVERITY_OK = "ok"
SEVERITY_WARN = "warn"
SEVERITY_ERROR = "error"


@dataclass(frozen=True)
class RecordListEntry:
    """One row of the record list."""

    record_id: str
    pin: str = ""
    name: str = ""
    status: str = ""
    severity: str = SEVERITY_OK
    flags: Tuple[str, ...] = field(default_factory=tuple)


class RecordListModel(QAbstractListModel):
    """Model holding the records that are shown in the list."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._entries: List[RecordListEntry] = []

    # -- Qt model API ------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._entries)

    def data(self, index: QModelIndex, role: int = Qt.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._entries)):
            return None

        entry = self._entries[index.row()]

        if role == Qt.DisplayRole:
            return entry.pin or entry.name or entry.record_id
        if role == Qt.UserRole:
            return entry.record_id
        if role == Qt.ToolTipRole:
            if entry.flags:
                return "\n".join(entry.flags)
            return entry.name
        return None

    # -- content ------------------------------------------------------
    def set_entries(self, entries: Sequence[RecordListEntry]) -> None:
        """Replace the content of the list."""
        self.beginResetModel()
        self._entries = list(entries)
        self.endResetModel()

    def entries(self) -> List[RecordListEntry]:
        """Return the current entries."""
        return list(self._entries)

    def entry(self, row: int) -> Optional[RecordListEntry]:
        """Return the entry at a row (None when the row is out of range)."""
        if 0 <= row < len(self._entries):
            return self._entries[row]
        return None

    def row_for_record(self, record_id: str) -> int:
        """Return the row of a record (-1 when it is not in the list)."""
        for index, entry in enumerate(self._entries):
            if entry.record_id == record_id:
                return index
        return -1


class RecordListDelegate(QStyledItemDelegate):
    """Paints a record row: status stripe, PIN, name and a problem flag."""

    # The base design row height; grows with the screen font scale so the
    # larger glyphs keep their breathing room.
    ROW_HEIGHT = 46

    def __init__(self, parent=None):
        super().__init__(parent)

    def sizeHint(self, option, index) -> QSize:  # noqa: N802 - Qt naming
        return QSize(option.rect.width(), round(self.ROW_HEIGHT * font_scale()))

    def paint(self, painter: QPainter, option, index) -> None:  # noqa: N802
        painter.setRenderHint(QPainter.Antialiasing)
        painter.setRenderHint(QPainter.TextAntialiasing)

        palette = active_palette()
        rect = QRectF(option.rect)

        selected = bool(option.state & QStyle.State_Selected)
        hovered = bool(option.state & QStyle.State_MouseOver)

        # Row surface.
        if selected:
            surface = QColor(palette.SURFACE_HIGH)
        elif hovered:
            surface = QColor(palette.SURFACE_CONTAINER)
        else:
            surface = QColor(palette.SURFACE_LOW)
        painter.setPen(Qt.NoPen)
        painter.setBrush(surface)
        painter.drawRect(rect)

        entry = index.data(Qt.UserRole)
        pin = index.data(Qt.DisplayRole) or ""
        name = index.data(Qt.ToolTipRole) or ""
        severity = SEVERITY_OK
        status = ""
        flags: Tuple[str, ...] = ()

        # The text bands grow with the screen font scale.
        s = font_scale()

        # The delegate works on a plain model, so the richer fields are read
        # from the model itself when it is available.
        model = index.model()
        if isinstance(model, RecordListModel):
            row = model.entry(index.row())
            if row is not None:
                entry = row.record_id
                pin = row.pin or row.name
                name = row.name
                severity = row.severity
                status = row.status
                flags = row.flags

        # Status stripe on the left edge.
        stripe = self._status_color(status, palette)
        if stripe is not None:
            painter.setPen(Qt.NoPen)
            painter.setBrush(stripe)
            painter.drawRect(
                QRectF(rect.left(), rect.top(), 3.0, rect.height())
            )

        text_left = rect.left() + 12.0
        text_width = rect.width() - 36.0

        # PIN - the identity of the card.
        font = QFont()
        font.setFamily(FONT_FAMILY_MONO)
        font.setPointSizeF(scaled_point(10.0))
        font.setBold(True)
        painter.setFont(font)
        painter.setPen(QColor(palette.ON_SURFACE))
        metrics = QFontMetrics(font)
        painter.drawText(
            QRectF(text_left, rect.top() + 6.0 * s, text_width, 16.0 * s),
            Qt.AlignLeft | Qt.AlignVCenter,
            metrics.elidedText(str(pin), Qt.ElideRight, int(text_width)),
        )

        # Name - what the card is about.
        font = QFont()
        font.setFamily(FONT_FAMILY_UI)
        font.setPointSizeF(scaled_point(9.0))
        painter.setFont(font)
        painter.setPen(QColor(palette.TEXT_MUTED))
        metrics = QFontMetrics(font)
        painter.drawText(
            QRectF(text_left, rect.top() + 22.0 * s, text_width, 16.0 * s),
            Qt.AlignLeft | Qt.AlignVCenter,
            metrics.elidedText(str(name), Qt.ElideRight, int(text_width)),
        )

        # Problem flag on the right.
        if severity != SEVERITY_OK:
            color = (
                QColor(palette.WARNING)
                if severity == SEVERITY_WARN
                else QColor(palette.ERROR)
            )
            badge = "!" if severity == SEVERITY_WARN else "✕"
            painter.setPen(color)
            font = QFont()
            font.setFamily(FONT_FAMILY_UI)
            font.setPointSizeF(scaled_point(10.0))
            font.setBold(True)
            painter.setFont(font)
            painter.drawText(
                QRectF(rect.right() - 26.0 * s, rect.top(), 18.0 * s, rect.height()),
                Qt.AlignCenter,
                badge,
            )

        # Hairline between the rows.
        painter.setPen(QPen(QColor(palette.OUTLINE_VARIANT), 1))
        painter.drawLine(
            int(rect.left()),
            int(rect.bottom()),
            int(rect.right()),
            int(rect.bottom()),
        )

    @staticmethod
    def _status_color(status: str, palette):
        """Return the stripe colour for a review status."""
        name = str(status).lower()
        if name == "approved":
            return QColor(palette.TERTIARY)
        if name == "rejected":
            return QColor(palette.ERROR)
        if name == "correction":
            return QColor(palette.WARNING)
        if name == "skipped":
            return QColor(palette.TEXT_MUTED)
        return None


class RecordListView(QListView):
    """The list view that shows the records of a review session."""

    record_selected = Signal(str)  # record_id

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("record_list")
        self.setUniformItemSizes(True)
        self.setSelectionMode(QListView.SingleSelection)
        self.setVerticalScrollMode(QListView.ScrollPerPixel)
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.setMouseTracking(True)

        self._delegate = RecordListDelegate(self)
        self.setItemDelegate(self._delegate)

        self.doubleClicked.connect(self._on_double_clicked)
        self.clicked.connect(self._on_clicked)

    def _on_clicked(self, index: QModelIndex) -> None:
        record_id = index.data(Qt.UserRole)
        if record_id:
            self.record_selected.emit(str(record_id))

    def _on_double_clicked(self, index: QModelIndex) -> None:
        self._on_clicked(index)
