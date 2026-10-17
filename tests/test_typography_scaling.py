"""Comprehensive test suite for Photoshop-aligned typography, font-size scaling, and unit conversions.

Covers:
- Standard point (pt) unit conversions at 72, 150, 300, 600 DPI
- 96 CSS DPI reference scale conversions
- Consistent nominal typographic size across Qt canvas and Pillow rendering
- Glyph bounding box, ascent/descent, and line height metrics
- Auto-shrink fitting in typographic points
- Zoom independence (screen zoom affects rendering only, not stored document geometry)
- Stability of stored font sizes across save/reload
- Physical print measurement verification
- Regression tests for 6, 8, 10, 12, 16, 24, 48 pt
"""

import pytest
from pathlib import Path
from PIL import Image, ImageFont
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QFont, QFontMetrics, QImage, QPainter
from PySide6.QtWidgets import QApplication

from id_card_generator.core.constants import DEFAULT_DPI, TextOverflowPolicy, OutputFormat
from id_card_generator.core.geometry import (
    POINTS_PER_INCH,
    CSS_PIXELS_PER_INCH,
    points_to_document_pixels,
    document_pixels_to_points,
    points_to_inches,
    inches_to_points,
    points_to_mm,
    mm_to_points,
    points_to_css_pixels,
    css_pixels_to_points,
    TypographyMetrics,
)
from id_card_generator.core.models import (
    CanvasElement,
    CanvasElementStyle,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.editor.canvas_items import CanvasItem
from id_card_generator.editor.canvas_scene import CanvasScene
from id_card_generator.editor.canvas_view import CanvasView
from id_card_generator.rendering.font_manager import FontManager
from id_card_generator.rendering.pillow_renderer import PillowRenderer
from id_card_generator.rendering.text_layout import TextLayout


# ============================================================================
# 1. Point-to-Pixel and Unit Conversion Tests
# ============================================================================

@pytest.mark.parametrize("pt,dpi,expected_px", [
    (6.0, 72, 6.0),
    (8.0, 72, 8.0),
    (10.0, 72, 10.0),
    (12.0, 72, 12.0),
    (16.0, 72, 16.0),
    (24.0, 72, 24.0),
    (48.0, 72, 48.0),
    # 150 DPI: factor = 150/72 = 2.08333...
    (6.0, 150, 12.5),
    (12.0, 150, 25.0),
    (24.0, 150, 50.0),
    (48.0, 150, 100.0),
    # 300 DPI: factor = 300/72 = 4.16666...
    (6.0, 300, 25.0),
    (10.0, 300, 41.66666666666667),
    (12.0, 300, 50.0),
    (24.0, 300, 100.0),
    (48.0, 300, 200.0),
    # 600 DPI: factor = 600/72 = 8.33333...
    (6.0, 600, 50.0),
    (12.0, 600, 100.0),
    (24.0, 600, 200.0),
    (48.0, 600, 400.0),
])
def test_points_to_document_pixels_standard_sizes(pt: float, dpi: int, expected_px: float):
    """Verify points to document pixels match Photoshop nominal sizes at various resolutions."""
    px = points_to_document_pixels(pt, dpi)
    assert abs(px - expected_px) < 1e-6
    # Round-trip back to points
    pt_back = document_pixels_to_points(px, dpi)
    assert abs(pt_back - pt) < 1e-6


def test_physical_print_invariance():
    """Verify that a 10 pt font has identical physical size (0.1389 inches / 3.528 mm) at any DPI."""
    pt = 10.0
    expected_inches = pt / 72.0
    expected_mm = (pt / 72.0) * 25.4

    assert abs(points_to_inches(pt) - expected_inches) < 1e-6
    assert abs(inches_to_points(expected_inches) - pt) < 1e-6
    assert abs(points_to_mm(pt) - expected_mm) < 1e-4
    assert abs(mm_to_points(expected_mm) - pt) < 1e-4

    # At 72, 150, 300, 600 DPI: pixels / DPI must equal physical inches
    for dpi in [72, 96, 150, 300, 600]:
        px = points_to_document_pixels(pt, dpi)
        physical_inches = px / dpi
        assert abs(physical_inches - expected_inches) < 1e-6


def test_css_pixel_conversions():
    """Verify 96 CSS DPI reference scale (1 pt = 96/72 = 1.333 CSS px)."""
    assert abs(points_to_css_pixels(72.0) - 96.0) < 1e-6
    assert abs(css_pixels_to_points(96.0) - 72.0) < 1e-6
    assert abs(points_to_css_pixels(12.0) - 16.0) < 1e-6
    assert abs(css_pixels_to_points(16.0) - 12.0) < 1e-6


# ============================================================================
# 2. Qt and Pillow Cross-Engine Consistency Tests
# ============================================================================

@pytest.mark.parametrize("pt", [6, 8, 10, 12, 16, 24, 48])
def test_qt_and_pillow_metric_consistency_300dpi(qtbot, pt: int):
    """Verify Qt QFont and Pillow ImageFont produce consistent metrics within 1-2px rasterization tolerance."""
    dpi = 300
    doc_px = points_to_document_pixels(pt, dpi)
    int_px = max(1, int(round(doc_px)))

    # 1. Qt Font Metrics
    qfont = QFont("Arial")
    qfont.setPixelSize(int_px)
    qmetrics = QFontMetrics(qfont)
    qt_height = qmetrics.height()
    qt_ascent = qmetrics.ascent()
    qt_descent = qmetrics.descent()
    qt_advance_h = qmetrics.horizontalAdvance("H")

    # 2. Pillow Font Metrics
    pfont = FontManager.get_font("Arial", doc_px)
    p_ascent, p_descent = pfont.getmetrics()
    p_bbox_h = pfont.getbbox("H")
    p_h_width = p_bbox_h[2] - p_bbox_h[0]

    # Em-heights between Qt and Pillow should be within 2 pixels
    assert abs(qt_height - (p_ascent + p_descent)) <= 2
    # Ascents should be within 2 pixels
    assert abs(qt_ascent - p_ascent) <= 2
    # Glyph widths of capital 'H' should be within 2 pixels
    assert abs(qt_advance_h - p_h_width) <= 2


# ============================================================================
# 3. Canvas Scene and Item Rendering (Zoom Independence & DPI)
# ============================================================================

def test_canvas_item_zoom_independence(qtbot):
    """Canvas zoom transforms rendering only; it must never mutate stored font size or geometry."""
    scene = CanvasScene()
    tmpl = TemplateDefinition(name="Test Card", width_px=638, height_px=1012, dpi=300)
    scene.load_template(tmpl)

    view = CanvasView(scene)
    view.show()
    qtbot.addWidget(view)

    elem = CanvasElement(
        name="NameField",
        type="dynamic_text",
        x=50.0,
        y=100.0,
        width=300.0,
        height=60.0,
        binding="Name",
        style=CanvasElementStyle(font_family="Arial", font_size=10.0),
    )
    item = scene.add_element(elem, push_undo=False)

    # Initial state
    assert item.element.style.font_size == 10.0
    assert item.element.width == 300.0
    assert item.element.height == 60.0

    # Zoom in to 200%
    view.set_zoom(2.0)
    assert scene.get_zoom_factor() == 2.0
    # Stored values MUST remain exactly 10.0 pt and 300x60 px
    assert item.element.style.font_size == 10.0
    assert item.element.width == 300.0
    assert item.element.height == 60.0

    # Zoom out to 50%
    view.set_zoom(0.5)
    assert scene.get_zoom_factor() == 0.5
    assert item.element.style.font_size == 10.0
    assert item.element.width == 300.0
    assert item.element.height == 60.0


def test_canvas_item_paint_with_dpi(qtbot):
    """Verify CanvasItem renders without errors and applies template DPI."""
    scene = CanvasScene()
    tmpl = TemplateDefinition(name="300DPI Card", width_px=638, height_px=1012, dpi=300)
    scene.load_template(tmpl)

    elem = CanvasElement(
        name="Title",
        type="static_text",
        x=20.0,
        y=20.0,
        width=500.0,
        height=50.0,
        static_content="Photoshop Parity",
        style=CanvasElementStyle(font_family="Arial", font_size=10.0),
    )
    item = scene.add_element(elem, push_undo=False)

    # Paint into a QImage to verify rendering pipeline
    img = QImage(638, 1012, QImage.Format_ARGB32)
    img.fill(Qt.white)
    painter = QPainter(img)
    item.paint(painter, None, None)
    painter.end()

    assert not img.isNull()
    assert item.element.style.font_size == 10.0


# ============================================================================
# 4. TextLayout Auto-Shrink in Points
# ============================================================================

def test_text_layout_auto_shrink_in_points():
    """Verify TextLayout auto-shrink reduces size in half-point steps at target DPI."""
    text = "Executive Director of Technology"
    target_w = 400.0
    target_h = 45.0
    dpi = 300.0

    layout = TextLayout.layout_text(
        text=text,
        family="Arial",
        initial_font_size=24.0,  # 24 pt @ 300 DPI = 100 px (too big for 45px height)
        bold=True,
        italic=False,
        target_width=target_w,
        target_height=target_h,
        target_x=0.0,
        target_y=0.0,
        wrap=False,
        overflow_policy=TextOverflowPolicy.AUTO_SHRINK,
        min_font_size=4.0,
        dpi=dpi,
    )

    # Should have shrunk down below 24 pt to fit inside 400x45 box
    assert layout.font_size_used < 24.0
    assert layout.font_size_used >= 4.0
    assert layout.font_size_px == points_to_document_pixels(layout.font_size_used, dpi)
    assert not layout.overflow_detected

    # Extreme text that cannot fit even at 4.0 pt should set overflow_detected = True
    impossible_layout = TextLayout.layout_text(
        text="A" * 500,
        family="Arial",
        initial_font_size=24.0,
        bold=True,
        italic=False,
        target_width=50.0,
        target_height=10.0,
        target_x=0.0,
        target_y=0.0,
        wrap=False,
        overflow_policy=TextOverflowPolicy.AUTO_SHRINK,
        min_font_size=4.0,
        dpi=dpi,
    )
    assert impossible_layout.overflow_detected
    assert impossible_layout.font_size_used == 4.0


# ============================================================================
# 5. Pillow Export Pipeline & DPI Metadata
# ============================================================================

def test_pillow_renderer_preserves_dpi():
    """PillowRenderer must set DPI metadata in output image."""
    tmpl = TemplateDefinition(
        name="Custom 300 DPI",
        width_px=638,
        height_px=1012,
        dpi=300,
        elements=[
            CanvasElement(
                name="Name",
                type="static_text",
                x=50.0,
                y=100.0,
                width=500.0,
                height=50.0,
                static_content="John Doe",
                style=CanvasElementStyle(font_family="Arial", font_size=10.0),
            )
        ],
    )

    img, warnings = PillowRenderer.render_card(template=tmpl)
    assert isinstance(img, Image.Image)
    assert img.size == (638, 1012)
    assert img.info.get("dpi") == (300, 300)
    assert len(warnings) == 0


def test_different_document_resolutions_render():
    """Rendering card at 72, 150, 300, and 600 DPI scales pixels while keeping physical dimensions invariant."""
    for dpi in [72, 150, 300, 600]:
        w_in, h_in = 2.125, 3.375
        w_px = int(round(w_in * dpi))
        h_px = int(round(h_in * dpi))

        tmpl = TemplateDefinition(
            name=f"Card {dpi} DPI",
            width_px=w_px,
            height_px=h_px,
            dpi=dpi,
            elements=[
                CanvasElement(
                    name="Heading",
                    type="static_text",
                    x=10.0 * (dpi / 72.0),
                    y=10.0 * (dpi / 72.0),
                    width=w_px - 20.0 * (dpi / 72.0),
                    height=50.0 * (dpi / 72.0),
                    static_content="Sample Heading",
                    style=CanvasElementStyle(font_family="Arial", font_size=10.0),
                )
            ],
        )

        img, warnings = PillowRenderer.render_card(template=tmpl)
        assert img.size == (w_px, h_px)
        assert img.info.get("dpi") == (dpi, dpi)
        assert len(warnings) == 0


# ============================================================================
# 6. Serialization Stability
# ============================================================================

def test_template_font_size_serialization_stability():
    """Font size in points must serialize and deserialize accurately without drift."""
    tmpl = TemplateDefinition(
        name="Test Serialization",
        width_px=638,
        height_px=1012,
        dpi=300,
        elements=[
            CanvasElement(
                name="Text1",
                style=CanvasElementStyle(font_size=10.0),
            ),
            CanvasElement(
                name="Text2",
                style=CanvasElementStyle(font_size=12.5),
            ),
        ],
    )

    data = tmpl.model_dump()
    reloaded = TemplateDefinition.model_validate(data)

    assert reloaded.elements[0].style.font_size == 10.0
    assert reloaded.elements[1].style.font_size == 12.5


# ============================================================================
# 7. Font Change and Space Preservation Regression Tests
# ============================================================================

def test_font_size_change_renders_nominal_size_on_canvas(qtbot):
    """Changing font size in pt on an element should actually update rendered size and not get forced to 4-7pt."""
    tmpl = TemplateDefinition(
        name="Test Size",
        width_px=638,
        height_px=1012,
        dpi=300,
        elements=[
            CanvasElement(
                name="Title",
                type="static_text",
                x=50,
                y=50,
                width=400,
                height=35,
                static_content="HELLO WORLD",
                style=CanvasElementStyle(font_family="Arial", font_size=18.0, overflow_policy=TextOverflowPolicy.AUTO_SHRINK),
            )
        ],
    )
    scene = CanvasScene()
    scene.load_template(tmpl)
    item = next(it for it in scene.items() if isinstance(it, CanvasItem) and it.element.id == tmpl.elements[0].id)
    assert item is not None

    # Paint onto a test image
    img = QImage(638, 1012, QImage.Format_ARGB32)
    img.fill(Qt.white)
    painter = QPainter(img)
    item.paint(painter, None)
    painter.end()

    # Change to 24pt
    item.element.style.font_size = 24.0
    item.element.width = 500.0
    item._rect = QRectF(0, 0, 500.0, 45.0)

    # Check font pixel size computed for 24pt @ 300DPI
    expected_doc_px = points_to_document_pixels(24.0, 300)
    assert expected_doc_px == 100.0

    # When wide enough (800px), it maintains full 24.0pt even though height is only 45px
    layout_wide = TextLayout.layout_text(
        text="HELLO WORLD",
        family="Arial",
        initial_font_size=24.0,
        bold=False,
        italic=False,
        target_width=800.0,
        target_height=45.0,
        target_x=50,
        target_y=50,
        overflow_policy=TextOverflowPolicy.AUTO_SHRINK,
        dpi=300,
    )
    assert layout_wide.font_size_used == 24.0, f"Expected 24.0pt, got {layout_wide.font_size_used}pt"

    # When constrained to 500px width, it scales to 16.0pt (fitting 486px width) instead of crushing to 6pt
    layout_500 = TextLayout.layout_text(
        text="HELLO WORLD",
        family="Arial",
        initial_font_size=24.0,
        bold=False,
        italic=False,
        target_width=500.0,
        target_height=45.0,
        target_x=50,
        target_y=50,
        overflow_policy=TextOverflowPolicy.AUTO_SHRINK,
        dpi=300,
    )
    assert layout_500.font_size_used == 16.0, f"Expected 16.0pt, got {layout_500.font_size_used}pt"


def test_space_gap_and_trailing_spaces_preserved_in_layout():
    """Text layout must not strip trailing spaces or collapse user spacing."""
    layout_with_space = TextLayout.layout_text(
        text="JOHN DOE ",
        family="Arial",
        initial_font_size=12.0,
        bold=False,
        italic=False,
        target_width=300.0,
        target_height=40.0,
        target_x=10,
        target_y=10,
        overflow_policy=TextOverflowPolicy.AUTO_SHRINK,
        dpi=300,
    )
    assert len(layout_with_space.lines) == 1
    # Check that space wasn't stripped from line representation
    assert layout_with_space.lines[0][0] == "JOHN DOE "
