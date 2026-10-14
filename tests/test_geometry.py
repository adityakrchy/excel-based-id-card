"""Unit tests for physical dimensions and DPI conversions."""

from id_card_generator.core.geometry import (
    calculate_card_dimensions,
    convert_unit,
    physical_to_pixels,
    pixels_to_physical,
    to_inches,
)


def test_standard_cr80_dimensions():
    """Verify standard CR80 card: 85.6 mm x 54.0 mm at 300 DPI."""
    # 85.6 mm / 25.4 * 300 = 1011.02 -> 1011 px
    # 54.0 mm / 25.4 * 300 = 637.795 -> 638 px
    w_px = physical_to_pixels(85.6, "mm", 300)
    h_px = physical_to_pixels(54.0, "mm", 300)

    assert w_px in (1011, 1012)
    assert h_px in (637, 638)


def test_unit_conversions():
    """Test conversions between mm, cm, inch."""
    assert round(convert_unit(25.4, "mm", "inch"), 4) == 1.0
    assert round(convert_unit(1.0, "inch", "mm"), 2) == 25.4
    assert round(convert_unit(10.0, "cm", "mm"), 1) == 100.0
    assert round(convert_unit(100.0, "mm", "cm"), 1) == 10.0


def test_custom_dpi_scaling():
    """Changing DPI must scale output pixels while physical size remains invariant."""
    w_300 = physical_to_pixels(85.6, "mm", 300)
    w_600 = physical_to_pixels(85.6, "mm", 600)

    # 600 DPI should have ~2x pixels of 300 DPI
    assert abs(w_600 - (2 * w_300)) <= 2


def test_calculate_card_dimensions_orientation():
    """Verify portrait vs landscape orientation adjustment."""
    # Landscape: width >= height
    w_px, h_px, w_mm, h_mm = calculate_card_dimensions(85.6, 54.0, "mm", 300, orientation="landscape")
    assert w_px > h_px
    assert w_mm > h_mm

    # Portrait: height >= width
    w_px_p, h_px_p, w_mm_p, h_mm_p = calculate_card_dimensions(85.6, 54.0, "mm", 300, orientation="portrait")
    assert h_px_p > w_px_p
    assert h_mm_p > w_mm_p
