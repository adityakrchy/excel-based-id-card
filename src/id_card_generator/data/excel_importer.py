"""Excel and CSV data source importer supporting .xlsx, .xls, and .csv."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from id_card_generator.core.exceptions import DataSourceError, SheetNotFoundError
from id_card_generator.core.models import SourceRecord
from id_card_generator.data.data_normalizer import DataNormalizer

logger = logging.getLogger(__name__)


class ExcelImporter:
    """Imports spreadsheets and CSV files with sheet selection and header configuration."""

    @staticmethod
    def get_sheet_names(file_path: Path) -> List[str]:
        """Return list of sheet names in an Excel file. Returns ['Default'] for CSV."""
        if not file_path.exists():
            raise DataSourceError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            return ["Default"]

        try:
            if suffix == ".xls":
                excel_file = pd.ExcelFile(file_path, engine="xlrd")
            else:
                excel_file = pd.ExcelFile(file_path, engine="openpyxl")
            return excel_file.sheet_names
        except Exception as e:
            logger.error("Failed to inspect sheets in %s: %s", file_path, e)
            raise DataSourceError(f"Could not read spreadsheet sheets: {e}") from e

    @staticmethod
    def import_data(
        file_path: Path,
        sheet_name: Optional[str] = None,
        header_row: int = 0,
        pin_column_hint: Optional[str] = None,
    ) -> Tuple[List[str], List[SourceRecord]]:
        """Import records from file.
        
        Args:
            file_path: Path to .xlsx, .xls, or .csv
            sheet_name: Specific sheet name (for Excel workbooks)
            header_row: 0-indexed row number containing column headers
            pin_column_hint: Specific column name to treat as PIN Number (optional)

        Returns:
            Tuple of (columns_list, source_records_list)
        """
        if not file_path.exists():
            raise DataSourceError(f"File does not exist: {file_path}")

        suffix = file_path.suffix.lower()

        try:
            # dtype=object preserves original representations (like leading zeros)
            if suffix == ".csv":
                df = pd.read_csv(file_path, header=header_row, dtype=object)
            elif suffix == ".xls":
                sheet = sheet_name or 0
                df = pd.read_excel(file_path, sheet_name=sheet, header=header_row, engine="xlrd", dtype=object)
            elif suffix == ".xlsx":
                sheet = sheet_name or 0
                df = pd.read_excel(file_path, sheet_name=sheet, header=header_row, engine="openpyxl", dtype=object)
            else:
                raise DataSourceError(f"Unsupported file format: {suffix}")
        except SheetNotFoundError:
            raise
        except Exception as e:
            logger.error("Failed to import spreadsheet %s: %s", file_path, e)
            raise DataSourceError(f"Failed to read file: {e}") from e

        # Clean column names
        raw_columns = [str(c).strip() for c in df.columns if not str(c).startswith("Unnamed:")]
        # Ensure all columns are converted to clean strings
        df.columns = [str(c).strip() for c in df.columns]

        # Identify candidate PIN column
        pin_col = ExcelImporter._detect_pin_column(df.columns.tolist(), pin_column_hint)

        records: List[SourceRecord] = []
        for idx, row in df.iterrows():
            row_dict: Dict[str, Any] = {}
            for col in df.columns:
                val = row[col]
                # Convert NaN to empty string
                if pd.isna(val):
                    row_dict[col] = ""
                else:
                    row_dict[col] = str(val)

            raw_pin_val = row_dict.get(pin_col, "") if pin_col else ""
            raw_pin, normalized_pin = DataNormalizer.normalize_pin(raw_pin_val)

            rec = SourceRecord(
                row_index=int(idx) + header_row + 1,
                raw_pin=raw_pin,
                pin=normalized_pin,
                data=row_dict,
            )
            records.append(rec)

        logger.info(
            "Imported %d records with %d columns from %s (sheet: %s)",
            len(records),
            len(df.columns),
            file_path.name,
            sheet_name or "default",
        )
        return list(df.columns), records

    @staticmethod
    def _detect_pin_column(columns: List[str], hint: Optional[str] = None) -> Optional[str]:
        """Detect which column represents the PIN Number."""
        if hint and hint in columns:
            return hint

        # Common variants
        candidates = [
            "pin number",
            "pin_number",
            "pin",
            "id",
            "emp id",
            "employee id",
            "roll no",
            "roll number",
            "badge number",
        ]

        # Case-insensitive match
        col_lower_map = {c.lower(): c for c in columns}
        for cand in candidates:
            if cand in col_lower_map:
                return col_lower_map[cand]

        # Partial match
        for cand in ["pin", "id"]:
            for col in columns:
                if cand in col.lower():
                    return col

        return columns[0] if columns else None
