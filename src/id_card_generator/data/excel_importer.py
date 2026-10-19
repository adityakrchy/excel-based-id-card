"""Excel and CSV data source importer supporting .xlsx, .xls, and .csv."""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
import pandas as pd

from id_card_generator.core.exceptions import DataSourceError, SheetNotFoundError
from id_card_generator.core.models import SourceRecord
from id_card_generator.data.data_normalizer import DataNormalizer
from id_card_generator.data.hindi_converter import HindiConverter

logger = logging.getLogger(__name__)


class ExcelImporter:
    """Imports spreadsheets and CSV files with sheet selection, header configuration, and Hindi font processing."""

    @staticmethod
    def get_sheet_names(file_path: Path) -> List[str]:
        """Return list of sheet names in an Excel file. Returns ['Default'] for CSV."""
        if not file_path.exists():
            raise DataSourceError(f"File not found: {file_path}")

        suffix = file_path.suffix.lower()
        if suffix == ".csv":
            return ["Default"]

        try:
            engine = "xlrd" if suffix == ".xls" else "openpyxl"
            with pd.ExcelFile(file_path, engine=engine) as excel_file:
                return list(excel_file.sheet_names)
        except Exception as e:
            logger.error("Failed to inspect sheets in %s: %s", file_path, e)
            raise DataSourceError(f"Could not read spreadsheet sheets: {e}") from e

    @staticmethod
    def import_data(
        file_path: Path,
        sheet_name: Optional[str] = None,
        header_row: int = 0,
        pin_column_hint: Optional[str] = None,
        hindi_font_mode: str = "auto",
    ) -> Tuple[List[str], List[SourceRecord]]:
        """Import records from file.
        
        Args:
            file_path: Path to .xlsx, .xls, or .csv
            sheet_name: Specific sheet name (for Excel workbooks)
            header_row: 0-indexed row number containing column headers
            pin_column_hint: Specific column name to treat as PIN Number (optional)
            hindi_font_mode: 'auto' (detect Kruti Dev / DevLys / Unicode),
                             'kruti_to_unicode' (force conversion), or
                             'none' (preserve raw strings).

        Returns:
            Tuple of (columns_list, source_records_list)
        """
        if not file_path.exists():
            raise DataSourceError(f"File does not exist: {file_path}")

        suffix = file_path.suffix.lower()

        # Extract font metadata if available (for .xlsx)
        header_fonts: Dict[int, str] = {}
        cell_fonts: Dict[Tuple[int, int], str] = {}
        if suffix == ".xlsx":
            try:
                import openpyxl
                wb = openpyxl.load_workbook(file_path, data_only=True)
                ws = wb[sheet_name] if sheet_name and sheet_name in wb.sheetnames else wb.active
                excel_header_row = header_row + 1
                for c_idx in range(1, ws.max_column + 1):
                    cell = ws.cell(excel_header_row, c_idx)
                    if cell.font and cell.font.name:
                        header_fonts[c_idx - 1] = cell.font.name

                for r_idx in range(excel_header_row + 1, ws.max_row + 1):
                    df_r = r_idx - (excel_header_row + 1)
                    for c_idx in range(1, ws.max_column + 1):
                        cell = ws.cell(r_idx, c_idx)
                        if cell.font and cell.font.name:
                            cell_fonts[(df_r, c_idx - 1)] = cell.font.name
            except Exception as e:
                logger.debug("Could not read openpyxl font metadata from %s: %s", file_path, e)

        try:
            # dtype=object preserves original representations (like leading zeros)
            if suffix == ".csv":
                df = pd.read_csv(file_path, header=header_row, dtype=object)
            elif suffix in (".xls", ".xlsx"):
                engine = "xlrd" if suffix == ".xls" else "openpyxl"
                sheet = sheet_name or 0
                with pd.ExcelFile(file_path, engine=engine) as excel_file:
                    df = pd.read_excel(excel_file, sheet_name=sheet, header=header_row, dtype=object)
            else:
                raise DataSourceError(f"Unsupported file format: {suffix}")
        except SheetNotFoundError:
            raise
        except Exception as e:
            logger.error("Failed to import spreadsheet %s: %s", file_path, e)
            raise DataSourceError(f"Failed to read file: {e}") from e

        # Clean and convert column names
        converted_columns: List[str] = []
        for c_idx, raw_col in enumerate(df.columns):
            c_str = str(raw_col).strip()
            # If the column was auto-generated unnamed index, keep as is
            if c_str.startswith("Unnamed:"):
                converted_columns.append(c_str)
            else:
                font_name = header_fonts.get(c_idx)
                conv_col = HindiConverter.convert_value(c_str, font_name=font_name, mode=hindi_font_mode)
                converted_columns.append(conv_col.strip())

        df.columns = converted_columns

        # Identify candidate PIN column
        pin_col = ExcelImporter._detect_pin_column(df.columns.tolist(), pin_column_hint)

        records: List[SourceRecord] = []
        for idx, row in df.iterrows():
            row_dict: Dict[str, Any] = {}
            for c_idx, col in enumerate(df.columns):
                val = row[col]
                # Convert NaN to empty string
                if pd.isna(val):
                    row_dict[col] = ""
                else:
                    font_name = cell_fonts.get((int(idx), c_idx))
                    conv_val = HindiConverter.convert_value(val, font_name=font_name, mode=hindi_font_mode)
                    row_dict[col] = conv_val

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
            "Imported %d records with %d columns from %s (sheet: %s, hindi_mode: %s)",
            len(records),
            len(df.columns),
            file_path.name,
            sheet_name or "default",
            hindi_font_mode,
        )
        return list(df.columns), records

    @staticmethod
    def _detect_pin_column(columns: List[str], hint: Optional[str] = None) -> Optional[str]:
        """Detect which column represents the PIN Number."""
        if hint and hint in columns:
            return hint

        # Common variants in English and Hindi
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
            "sl.no",
            "sl no",
            "s.no",
            "s no",
            "क्रम",
            "क्रम संख्या",
            "क्र0सं0",
            "क्र०सं०",
            "क्र.सं.",
            "आईडी",
            "पिन",
            "रोल नंबर",
        ]

        # Case-insensitive match
        col_lower_map = {c.lower(): c for c in columns}
        for cand in candidates:
            if cand in col_lower_map:
                return col_lower_map[cand]

        # Partial match
        for cand in ["pin", "id", "क्रम"]:
            for col in columns:
                if cand in col.lower():
                    return col

        return columns[0] if columns else None
