"""Canonical physical geometry and DPI conversion utilities.

Supports conversion between physical units (mm, cm, inch) and pixels
at any custom DPI without loss of precision.
"""

from enum import Enum
from typing import Tuple


class MeasurementUnit(str, Enum):
    """Supported physical measurement units."""
    MM = "mm"
    CM = "cm"
    INCH = "inch"
    PIXELS = "px"


MM_PER_INCH = 25.4
CM_PER_INCH = 2.54


def to_inches(value: float, unit: str) -> float:
    """Convert any supported unit to inches."""
    u = unit.lower().strip()
    if u in ("mm", "millimeter", "millimeters"):
        return value / MM_PER_INCH
    elif u in ("cm", "centimeter", "centimeters"):
        return value / CM_PER_INCH
    elif u in ("in", "inch", "inches"):
        return value
    elif u in ("px", "pixel", "pixels"):
        # Assume standard 96 DPI if no DPI provided
        return value / 96.0
    return value


def from_inches(inches: float, target_unit: str) -> float:
    """Convert inches to any supported physical unit."""
    u = target_unit.lower().strip()
    if u in ("mm", "millimeter", "millimeters"):
        return inches * MM_PER_INCH
    elif u in ("cm", "centimeter", "centimeters"):
        return inches * CM_PER_INCH
    elif u in ("in", "inch", "inches"):
        return inches
    elif u in ("px", "pixel", "pixels"):
        return inches * 96.0
    return inches


def convert_unit(value: float, from_unit: str, to_unit: str) -> float:
    """Convert between physical units without cumulative rounding errors."""
    if from_unit.lower() == to_unit.lower():
        return value
    inches = to_inches(value, from_unit)
    return from_inches(inches, to_unit)


def physical_to_pixels(val: float, unit: str, dpi: int) -> int:
    """Convert a physical measurement in given unit to output pixels at specified DPI."""
    inches = to_inches(val, unit)
    return max(1, int(round(inches * dpi)))


def pixels_to_physical(pixels: int, dpi: int, target_unit: str) -> float:
    """Convert pixels at given DPI back to physical measurement."""
    inches = pixels / max(1, dpi)
    return round(from_inches(inches, target_unit), 3)


def calculate_card_dimensions(
    width: float,
    height: float,
    unit: str,
    dpi: int,
    orientation: str = "landscape",
) -> Tuple[int, int, float, float]:
    """Calculate (width_px, height_px, width_mm, height_mm).
    
    Returns:
        Tuple of (width_px, height_px, width_mm, height_mm)
    """
    w_in = to_inches(width, unit)
    h_in = to_inches(height, unit)

    if orientation.lower() == "portrait" and w_in > h_in:
        w_in, h_in = h_in, w_in
    elif orientation.lower() == "landscape" and h_in > w_in:
        w_in, h_in = h_in, w_in

    width_px = max(1, int(round(w_in * dpi)))
    height_px = max(1, int(round(h_in * dpi)))

    width_mm = round(w_in * MM_PER_INCH, 2)
    height_mm = round(h_in * MM_PER_INCH, 2)

    return width_px, height_px, width_mm, height_mm
