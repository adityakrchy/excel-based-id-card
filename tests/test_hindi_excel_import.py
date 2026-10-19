"""Integration tests for importing Excel files containing Hindi (Kruti Dev / Mangal) fonts."""

from pathlib import Path
import pytest
from id_card_generator.core.models import (
    CanvasElement,
    CanvasElementStyle,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.data.excel_importer import ExcelImporter
from id_card_generator.rendering.pillow_renderer import PillowRenderer


@pytest.fixture
def video_grapher_excel_path() -> Path:
    p = Path(__file__).resolve().parent.parent / "Video Grapher 15-10-2026.xlsx"
    assert p.exists(), f"Reference file {p} must exist in repository root"
    return p


def test_import_video_grapher_sheet_tc(video_grapher_excel_path: Path):
    """Test importing Sheet 'tc' where Row 2 has English headers and data rows have Kruti Dev Hindi."""
    cols, records = ExcelImporter.import_data(
        video_grapher_excel_path,
        sheet_name="tc",
        header_row=1,  # 0-indexed row 1 is row 2 ('SL.NO', 'BLOCK', 'NAME', etc.)
        hindi_font_mode="auto",
    )

    assert "SL.NO" in cols
    assert "NAME" in cols
    assert "BLOCK" in cols

    # Should detect SL.NO as the PIN Number column
    rec0 = records[0]
    assert rec0.pin == "1"
    assert rec0.get_value("NAME") == "श्री अंकित कुमार"
    assert rec0.get_value("BLOCK") == "जाले"
    assert rec0.get_value("MOBILE") == "6299109865"
    assert rec0.get_value("DUTY") == "VIDEOGRAPHER"

    # Second record
    rec1 = records[1]
    assert rec1.pin == "2"
    assert rec1.get_value("NAME") == "श्री पिन्टु"
    assert rec1.get_value("BLOCK") == "सिंहवाड़ा"

    # Third record
    rec2 = records[2]
    assert rec2.pin == "3"
    assert rec2.get_value("NAME") == "श्री अविनाश कुमार मिश्र"
    assert rec2.get_value("BLOCK") == "केवटी"


def test_import_video_grapher_sheet_gc(video_grapher_excel_path: Path):
    """Test importing Sheet 'gc' where headers themselves are in Kruti Dev ('Øe', 'iz[kaM dk uke', etc.)."""
    cols, records = ExcelImporter.import_data(
        video_grapher_excel_path,
        sheet_name="gc",
        header_row=1,
        hindi_font_mode="auto",
    )

    # Converted headers
    assert "क्रम" in cols
    assert "प्रखंड का नाम" in cols

    # 'क्रम' should be automatically recognized as the candidate PIN column
    # Record 1 corresponds to Row 4 in Excel (PIN 1)
    rec_pin1 = [r for r in records if r.pin == "1"]
    assert len(rec_pin1) == 1
    r1 = rec_pin1[0]
    assert r1.get_value("प्रखंड का नाम") == "जाले"
    assert "श्री प्रवीण कुमार" in r1.data.values()


def test_pillow_render_card_with_hindi():
    """Verify that PillowRenderer renders ID cards containing Devanagari Hindi text cleanly."""
    template = TemplateDefinition(
        name="Hindi Test Card",
        width_px=600,
        height_px=400,
        dpi=300,
        background_color="#FFFFFF",
        elements=[
            CanvasElement(
                id="el_name",
                name="Employee Name",
                type="dynamic_text",
                binding="Name",
                x=50,
                y=50,
                width=500,
                height=60,
                style=CanvasElementStyle(
                    font_family="Mangal",
                    font_size=18,
                    font_color="#1E293B",
                    font_bold=True,
                ),
            ),
            CanvasElement(
                id="el_block",
                name="Block Name",
                type="dynamic_text",
                binding="Block",
                x=50,
                y=120,
                width=500,
                height=50,
                style=CanvasElementStyle(
                    font_family="Arial",  # Test Devanagari fallback when font_family is Arial
                    font_size=14,
                    font_color="#475569",
                ),
            ),
        ],
    )

    record = SourceRecord(
        row_index=1,
        raw_pin="1",
        pin="1",
        data={
            "Name": "श्री अंकित कुमार",
            "Block": "जाले (दरभंगा)",
        },
    )

    card_img, warnings = PillowRenderer.render_card(
        template=template,
        record=record,
        column_mappings={"el_name": "Name", "el_block": "Block"},
        settings=RenderSettings(),
    )

    assert card_img is not None
    assert card_img.size == (600, 400)
    # Check that pixels were drawn (not all white)
    if hasattr(card_img, "get_flattened_data"):
        pixels = card_img.get_flattened_data()
        non_white = sum(1 for i in range(0, len(pixels), 4) if (pixels[i], pixels[i+1], pixels[i+2]) != (255, 255, 255))
    else:
        pixels = list(card_img.getdata())
        non_white = sum(1 for p in pixels if p[:3] != (255, 255, 255))
    assert non_white > 500, "Hindi text should be drawn onto the canvas"
