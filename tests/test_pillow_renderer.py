"""Unit tests for the Pillow ID card renderer."""

from pathlib import Path
from PIL import Image
from id_card_generator.core.constants import MissingPhotoPolicy, OutputFormat
from id_card_generator.core.models import RenderSettings, SourceRecord
from id_card_generator.rendering.pillow_renderer import PillowRenderer
from id_card_generator.templates.template_manager import TemplateManager


def test_render_classic_portrait_with_photo(sample_photos_dir: Path):
    mgr = TemplateManager()
    tmpl = mgr.get_template("builtin-classic-portrait")
    assert tmpl is not None

    record = SourceRecord(
        row_index=1,
        raw_pin="100001",
        pin="100001",
        data={
            "Name": "Aditya Sharma",
            "Designation": "Senior Engineer",
            "Office Name": "Headquarters",
            "Constituency": "North Central",
            "Source PDF": "batch1.pdf",
        },
    )

    photo_path = str(sample_photos_dir / "100001.jpg")
    img, warnings = PillowRenderer.render_card(
        template=tmpl,
        record=record,
        photo_path=photo_path,
    )

    assert isinstance(img, Image.Image)
    assert img.size == (tmpl.width_px, tmpl.height_px)
    assert img.mode == "RGBA"
    assert len(warnings) == 0


def test_render_modern_corporate_jpeg(sample_photos_dir: Path):
    mgr = TemplateManager()
    tmpl = mgr.get_template("builtin-modern-corporate")
    assert tmpl is not None

    record = SourceRecord(
        row_index=2,
        raw_pin="100002",
        pin="100002",
        data={
            "Name": "Priya Patel",
            "Designation": "Product Manager",
            "Office Name": "Regional Office",
            "Constituency": "South Coast",
        },
    )

    photo_path = str(sample_photos_dir / "100002.png")
    settings = RenderSettings(output_format=OutputFormat.JPEG)

    img, warnings = PillowRenderer.render_card(
        template=tmpl,
        record=record,
        photo_path=photo_path,
        settings=settings,
    )

    assert isinstance(img, Image.Image)
    assert img.size == (tmpl.width_px, tmpl.height_px)
    assert img.mode == "RGB"  # JPEG is flattened to RGB


def test_render_missing_photo_placeholder():
    mgr = TemplateManager()
    tmpl = mgr.get_template("builtin-office-id-card")
    assert tmpl is not None

    record = SourceRecord(
        row_index=3,
        raw_pin="999000",
        pin="999000",
        data={"Name": "Unknown User"},
    )

    settings = RenderSettings(
        missing_photo_policy=MissingPhotoPolicy.GENERATE_WITH_PLACEHOLDER
    )

    img, warnings = PillowRenderer.render_card(
        template=tmpl,
        record=record,
        photo_path=None,
        settings=settings,
    )

    assert isinstance(img, Image.Image)
    assert any("Missing photograph" in w for w in warnings)
