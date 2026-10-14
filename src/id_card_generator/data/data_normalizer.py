"""Data normalization utilities for spreadsheet values and PIN identifiers."""

from typing import Any, Tuple


class DataNormalizer:
    """Normalizes raw Excel/CSV values without destroying leading zeros or corrupting numeric keys."""

    @staticmethod
    def normalize_pin(val: Any) -> Tuple[str, str]:
        """Normalize a PIN identifier.
        
        Returns:
            Tuple of (raw_pin_str, normalized_pin_str)
        """
        if val is None:
            return "", ""

        # Check for pandas NaN / float NaN
        if isinstance(val, float):
            if val != val:  # NaN check
                return "", ""
            # If float represents an exact integer (e.g. 100001.0), strip .0 to avoid corrupting ID
            if val.is_integer():
                raw = str(int(val))
                return raw, raw
            raw = str(val)
            return raw, raw.strip()

        if isinstance(val, int):
            raw = str(val)
            return raw, raw

        # String or other types
        raw_str = str(val)
        cleaned = raw_str.strip()

        # If string looks like a float with .0 (e.g., "100001.0"), convert to clean integer string
        if cleaned.endswith(".0") and cleaned[:-2].replace("-", "", 1).isdigit():
            normalized = cleaned[:-2]
        else:
            normalized = cleaned

        return raw_str, normalized

    @staticmethod
    def normalize_text(val: Any) -> str:
        """Clean standard string value by trimming whitespace and normalizing None."""
        if val is None:
            return ""
        if isinstance(val, float) and val != val:  # NaN
            return ""
        if isinstance(val, float) and val.is_integer():
            return str(int(val))
        return str(val).strip()

    @staticmethod
    def sanitize_filename(name: str) -> str:
        """Sanitize a string to be safely used as a filename component on Windows.
        
        Removes invalid characters: < > : " / \\ | ? * and control chars.
        """
        invalid_chars = '<>:"/\\|?*\n\r\t\0'
        sanitized = "".join(c if c not in invalid_chars else "_" for c in name)
        # Collapse multiple underscores
        while "__" in sanitized:
            sanitized = sanitized.replace("__", "_")
        sanitized = sanitized.strip(" ._")
        return sanitized or "card"
