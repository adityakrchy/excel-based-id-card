"""Virtual table model for the imported records.

A spreadsheet can hold thousands of rows, so the preview table is backed by a
model instead of a :class:`QTableWidget`: the rows are painted on demand and
only the visible ones cost anything.
"""

from typing import Dict, List, Optional, Sequence

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from id_card_generator.core.models import SourceRecord
from id_card_generator.ui.studio_tokens import (
    FONT_FAMILY_MONO,
    active_palette,
)

# The fixed columns in front of the spreadsheet columns.
COL_ROW = 0
COL_STATUS = 1
COL_PIN = 2
COL_FIRST_DATA = 3


class RecordTableModel(QAbstractTableModel):
    """Shows the imported records with the PIN state of every row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records: List[SourceRecord] = []
        self._columns: List[str] = []
        self._data_columns: List[str] = []
        self._visible: List[int] = []

    # -- content ------------------------------------------------------
    def set_records(
        self,
        records: Sequence[SourceRecord],
        columns: Sequence[str],
    ) -> None:
        """Replace the content of the table."""
        self.beginResetModel()
        self._records = list(records)
        self._columns = list(columns)
        self._data_columns = [c for c in self._columns if c.lower() != "pin number"]
        self._visible = list(range(len(self._records)))
        self.endResetModel()

    def set_filter(self, query: str) -> None:
        """Only keep the records that match the query."""
        query = (query or "").lower().strip()
        self.beginResetModel()
        if not query:
            self._visible = list(range(len(self._records)))
        else:
            self._visible = [
                index
                for index, record in enumerate(self._records)
                if self._matches(record, query)
            ]
        self.endResetModel()

    def record_at(self, row: int) -> Optional[SourceRecord]:
        """Return the record of a table row."""
        if 0 <= row < len(self._visible):
            return self._records[self._visible[row]]
        return None

    @staticmethod
    def _matches(record: SourceRecord, query: str) -> bool:
        """True when the query is found in the record."""
        if query in (record.pin or "").lower():
            return True
        if query in (record.raw_pin or "").lower():
            return True
        for value in record.data.values():
            if query in str(value).lower():
                return True
        return False

    # -- Qt model API --------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._visible)

    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else COL_FIRST_DATA + len(self._data_columns)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        if role != Qt.DisplayRole:
            return None

        if orientation == Qt.Horizontal:
            if section == COL_ROW:
                return "Row"
            if section == COL_STATUS:
                return "Status"
            if section == COL_PIN:
                return "PIN"
            index = section - COL_FIRST_DATA
            if 0 <= index < len(self._data_columns):
                return self._data_columns[index]
            return None

        return str(section + 1)

    def data(self, index: QModelIndex, role=Qt.DisplayRole):
        if not index.isValid():
            return None

        row = index.row()
        column = index.column()
        if row >= len(self._visible):
            return None

        record = self._records[self._visible[row]]
        palette = active_palette()

        if column == COL_ROW:
            if role == Qt.DisplayRole:
                return str(record.row_index + 1)
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            if role == Qt.ForegroundRole:
                return QColor(palette.TEXT_MUTED)
            return None

        if column == COL_STATUS:
            status, colour = self._pin_status(record)
            if role == Qt.DisplayRole:
                return status
            if role == Qt.ForegroundRole:
                return QColor(colour)
            if role == Qt.BackgroundRole:
                # A soft tint of the state colour.
                tint = QColor(colour)
                tint.setAlpha(48)
                return tint
            if role == Qt.TextAlignmentRole:
                return int(Qt.AlignCenter)
            if role == Qt.FontRole:
                font = QFont()
                font.setBold(True)
                return font
            return None

        if column == COL_PIN:
            value = record.pin or record.raw_pin
            if role == Qt.DisplayRole:
                return value
            if role == Qt.FontRole:
                font = QFont()
                font.setFamily(FONT_FAMILY_MONO)
                return font
            if role == Qt.ForegroundRole:
                if not record.pin:
                    return QColor(palette.ERROR)
                return QColor(palette.ON_SURFACE)
            return None

        data_index = column - COL_FIRST_DATA
        if not (0 <= data_index < len(self._data_columns)):
            return None

        value = record.get_value(self._data_columns[data_index])
        if role == Qt.DisplayRole:
            return value
        if role == Qt.BackgroundRole and not value:
            # Empty cells are dimmed so the gaps are easy to spot.
            return QColor(palette.SURFACE_LOW)
        if role == Qt.ToolTipRole:
            return value
        return None

    @staticmethod
    def _pin_status(record: SourceRecord):
        """Return the label and the colour of the PIN state of a record."""
        palette = active_palette()
        if not record.pin:
            return "MISSING PIN", palette.ERROR
        if any("Duplicate" in warning for warning in record.validation_warnings):
            return "DUPLICATE", palette.WARNING
        return "VALID", palette.TERTIARY
