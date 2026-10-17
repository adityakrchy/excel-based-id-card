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


# ============================================================================
# Typography & Point-to-Pixel Conversions (Photoshop Alignment)
# ============================================================================

POINTS_PER_INCH = 72.0
CSS_PIXELS_PER_INCH = 96.0


def points_to_inches(points: float) -> float:
    """Convert typographic points (pt) to physical inches (1 inch = 72 pt)."""
    return float(points) / POINTS_PER_INCH


def inches_to_points(inches: float) -> float:
    """Convert physical inches to typographic points (pt)."""
    return float(inches) * POINTS_PER_INCH


def points_to_mm(points: float) -> float:
    """Convert typographic points (pt) to millimeters."""
    return (float(points) / POINTS_PER_INCH) * MM_PER_INCH


def mm_to_points(mm: float) -> float:
    """Convert millimeters to typographic points (pt)."""
    return (float(mm) / MM_PER_INCH) * POINTS_PER_INCH


def points_to_document_pixels(points: float, dpi: float) -> float:
    """Convert typographic points (pt) to document pixels at the given document DPI.

    Matches Photoshop and standard digital publishing:
        nominal_size_px = points * (dpi / 72.0)

    Examples:
        10 pt @ 300 DPI = 41.6667 px
        10 pt @  72 DPI = 10.0 px
        10 pt @  96 DPI = 13.3333 px
        12 pt @ 300 DPI = 50.0 px
        24 pt @ 300 DPI = 100.0 px
    """
    return float(points) * (float(dpi) / POINTS_PER_INCH)


def document_pixels_to_points(pixels: float, dpi: float) -> float:
    """Convert document pixels at given document DPI to typographic points (pt)."""
    d = float(dpi) if float(dpi) > 0 else POINTS_PER_INCH
    return float(pixels) * (POINTS_PER_INCH / d)


def points_to_css_pixels(points: float) -> float:
    """Convert typographic points (pt) to W3C CSS reference pixels (1 pt = 96/72 CSS px)."""
    return float(points) * (CSS_PIXELS_PER_INCH / POINTS_PER_INCH)


def css_pixels_to_points(css_pixels: float) -> float:
    """Convert W3C CSS pixels to typographic points (pt)."""
    return float(css_pixels) * (POINTS_PER_INCH / CSS_PIXELS_PER_INCH)


class TypographyMetrics:
    """Canonical typography measurement and layout calculations matching Photoshop."""

    POINTS_PER_INCH: float = POINTS_PER_INCH
    CSS_PIXELS_PER_INCH: float = CSS_PIXELS_PER_INCH

    @staticmethod
    def points_to_pixels(points: float, dpi: float) -> float:
        return points_to_document_pixels(points, dpi)

    @staticmethod
    def pixels_to_points(pixels: float, dpi: float) -> float:
        return document_pixels_to_points(pixels, dpi)

    @staticmethod
    def calculate_line_height(points: float, dpi: float, line_spacing: float = 1.2) -> float:
        """Calculate nominal line leading matching Photoshop's auto leading (default 120%)."""
        em_px = points_to_document_pixels(points, dpi)
        return em_px * float(line_spacing)

