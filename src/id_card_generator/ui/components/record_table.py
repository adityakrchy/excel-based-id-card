"""Virtual table model for the records of the sheet.

The table of the connector shows the records of the imported sheet.  Every
column can be filtered by the values it holds, and the filter of the columns
is combined with the search of the records.

The machinery of the filter lives in :class:`FilterableTableModel`, so the
table of the export can filter the cards the same way.
"""

from typing import Dict, List, Optional, Sequence, Set

from PySide6.QtCore import QAbstractTableModel, QModelIndex, Qt
from PySide6.QtGui import QColor, QFont

from id_card_generator.core.models import CanvasElement, SourceRecord
from id_card_generator.ui.studio_tokens import active_palette

# The fixed columns in front of the spreadsheet columns.
COL_ROW = 0
COL_STATUS = 1
COL_PIN = 2
COL_FIRST_DATA = 3


class FilterableTableModel(QAbstractTableModel):
    """A table whose rows can be filtered by the values of a column."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._column_filters: Dict[int, Set[str]] = {}
        self._query: str = ""
        self._visible: List[int] = []

    # -- the content, provided by the subclass -------------------------
    def _row_count(self) -> int:
        """The number of the rows of the table."""
        raise NotImplementedError

    def _row_value(self, row: int, column: int) -> str:
        """The value of a row in a column."""
        raise NotImplementedError

    def _row_matches(self, row: int, query: str) -> bool:
        """True when the row matches the search."""
        return True

    # -- the filter ------------------------------------------------------
    def set_filter(self, query: str) -> None:
        """Only keep the records that match the query."""
        self.beginResetModel()
        self._query = (query or "").lower().strip()
        self._rebuild_visible()
        self.endResetModel()

    def set_column_filter(self, column: int, values) -> None:
        """Only keep the records whose column has one of the given values.

        ``None`` removes the filter of the column, an empty set keeps the
        records that have no value in it - so every value can be unpicked.
        """
        if values is None:
            self._column_filters.pop(column, None)
        else:
            self._column_filters[column] = {str(value) for value in values}

        self.beginResetModel()
        self._rebuild_visible()
        self.endResetModel()

    def clear_column_filter(self, column: int) -> None:
        """Remove the filter of a column."""
        self.set_column_filter(column, None)

    def reset_filters(self) -> None:
        """Remove the filter of every column and the search."""
        self.beginResetModel()
        self._column_filters.clear()
        self._query = ""
        self._rebuild_visible()
        self.endResetModel()

    def column_filter(self, column: int) -> Set[str]:
        """The values a column is filtered by (an empty set when it is free)."""
        return set(self._column_filters.get(column, set()))

    def filtered_columns(self) -> List[int]:
        """The columns that carry a filter."""
        return sorted(self._column_filters)

    def is_filtered(self, column: int) -> bool:
        """True when the column carries a filter."""
        return column in self._column_filters

    def distinct_values(self, column: int) -> List[str]:
        """The values a column has, with the empty value at the end."""
        seen: Dict[str, int] = {}
        for row in range(self._row_count()):
            value = self._row_value(row, column)
            seen[value] = seen.get(value, 0) + 1
        return sorted(seen, key=lambda v: (v == "", v.lower()))

    def value_counts(self, column: int) -> Dict[str, int]:
        """How often every value of a column occurs."""
        counts: Dict[str, int] = {}
        for row in range(self._row_count()):
            value = self._row_value(row, column)
            counts[value] = counts.get(value, 0) + 1
        return counts

    def _rebuild_visible(self) -> None:
        """Apply the search and the filters of the columns."""
        self._visible = [
            row
            for row in range(self._row_count())
            if self._passes_filters(row)
        ]

    def _passes_filters(self, row: int) -> bool:
        """True when the row passes the search and every column filter."""
        if self._query and not self._row_matches(row, self._query):
            return False
        for column, allowed in self._column_filters.items():
            if self._row_value(row, column) not in allowed:
                return False
        return True

    # -- Qt model API --------------------------------------------------
    def rowCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else len(self._visible)

    def headerData(self, section, orientation, role=Qt.DisplayRole):  # noqa: N802
        """The header of the table, the filtered columns carry their state."""
        if orientation == Qt.Horizontal and role == Qt.ForegroundRole:
            palette = active_palette()
            if section in self._column_filters:
                return QColor(palette.PRIMARY_CONTAINER)
            return QColor(palette.ON_SURFACE_VARIANT)

        if orientation == Qt.Horizontal and role == Qt.ToolTipRole:
            if section in self._column_filters:
                allowed = self._column_filters[section]
                return (
                    f"Filtered: {len(allowed)} of "
                    f"{len(self.distinct_values(section))} values"
                )
            return "Click to filter the records by this column"

        if role != Qt.DisplayRole:
            return None

        if orientation == Qt.Horizontal:
            return self._column_title(section)

        return str(section + 1)

    def _column_title(self, section: int) -> Optional[str]:
        """The name of a column."""
        raise NotImplementedError


class RecordTableModel(FilterableTableModel):
    """Shows the imported records with the PIN state of every row."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._records: List[SourceRecord] = []
        self._columns: List[str] = []
        self._data_columns: List[str] = []

    # -- content ------------------------------------------------------
    def set_records(
        self,
        records: Sequence[SourceRecord],
        columns: Sequence[str],
        keep_filters: bool = False,
    ) -> None:
        """Replace the content of the table."""
        self.beginResetModel()
        self._records = list(records)
        self._columns = list(columns)
        self._data_columns = [c for c in self._columns if c.lower() != "pin number"]
        if not keep_filters:
            self._column_filters.clear()
            self._query = ""
        self._rebuild_visible()
        self.endResetModel()

    def set_columns(self, columns: Sequence[str]) -> None:
        """Adopt the column names before the records stream in."""
        self.beginResetModel()
        self._columns = list(columns)
        self._data_columns = [c for c in self._columns if c.lower() != "pin number"]
        self.endResetModel()

    def append_records(self, records: Sequence[SourceRecord]) -> None:
        """Append a chunk of records without resetting the whole table.

        The streaming path appends consecutive chunks while the filters are
        already cleared, so the visible mapping grows by plain identity. When
        a search/filter is active anyway, a rebuild keeps the mapping sound.
        """
        if not records:
            return
        total = self._row_count()
        if self._query or self._column_filters:
            self._records.extend(records)
            self._rebuild_visible()
            if total != len(self._records):
                self.beginResetModel()
                self.endResetModel()
            return
        self.beginInsertRows(
            QModelIndex(), total, total + len(records) - 1
        )
        self._records.extend(records)
        self._visible.extend(range(total, len(self._records)))
        self.endInsertRows()

    def _row_count(self) -> int:
        return len(self._records)

    def _row_value(self, row: int, column: int) -> str:
        record = self._records[row]
        if column == COL_STATUS:
            return self._pin_status(record)[0]
        if column == COL_PIN:
            return record.pin or record.raw_pin or ""
        if column == COL_ROW:
            return str(record.row_index + 1)
        index = column - COL_FIRST_DATA
        if 0 <= index < len(self._data_columns):
            return record.get_value(self._data_columns[index])
        return ""

    def _row_matches(self, row: int, query: str) -> bool:
        """True when the query is found in the record."""
        record = self._records[row]
        if query in (record.pin or "").lower():
            return True
        if query in (record.raw_pin or "").lower():
            return True
        for value in record.data.values():
            if query in str(value).lower():
                return True
        return False

    def record_at(self, row: int) -> Optional[SourceRecord]:
        """Return the record of a table row."""
        if 0 <= row < len(self._visible):
            return self._records[self._visible[row]]
        return None

    # -- the header -----------------------------------------------------
    def _column_title(self, section: int) -> Optional[str]:
        if section == COL_ROW:
            return "Row"
        if section == COL_STATUS:
            return "Status"
        if section == COL_PIN:
            return "PIN"
        index = section - COL_FIRST_DATA
        if 0 <= index < len(self._data_columns):
            name = self._data_columns[index]
            if section in self._column_filters:
                # The header shows how many of the values are picked.
                allowed = self._column_filters[section]
                total = len(self.distinct_values(section))
                return f"{name} ({len(allowed)}/{total})"
            return name
        return None

    # -- the model API ---------------------------------------------------
    def columnCount(self, parent: QModelIndex = QModelIndex()) -> int:  # noqa: N802
        return 0 if parent.isValid() else COL_FIRST_DATA + len(self._data_columns)

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
                font.setFamily("JetBrains Mono")
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
