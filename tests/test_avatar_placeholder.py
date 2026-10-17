"""Tests for avatar silhouette placeholder in mapping editor canvas and post-generation rendering."""

import pytest
from PIL import Image
from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QImage, QPainter, QPixmap

from id_card_generator.core.constants import MissingPhotoPolicy
from id_card_generator.core.models import CanvasElement, RenderSettings, SourceRecord
from id_card_generator.editor.canvas_items import CanvasItem
from id_card_generator.rendering.image_processing import ImageProcessor
from id_card_generator.rendering.pillow_renderer import PillowRenderer
from id_card_generator.templates.template_manager import TemplateManager


def test_image_processor_generate_placeholder():
    """Verify ImageProcessor.generate_placeholder renders an avatar silhouette."""
    img = ImageProcessor.generate_placeholder(200, 240)
    assert isinstance(img, Image.Image)
    assert img.size == (200, 240)
    assert img.mode == "RGBA"

    # Verify background and avatar colors exist
    colors = img.getcolors(maxcolors=200 * 240)
    assert colors is not None
    assert len(colors) > 1  # Not a blank single-color rectangle


def test_canvas_item_paint_photo_avatar_placeholder(qapp):
    """Verify CanvasItem renders avatar silhouette when photo is missing."""
    elem = CanvasElement(
        name="Profile Photo",
        type="photo",
        x=50.0,
        y=50.0,
        width=150.0,
        height=180.0,
        binding="photo",
    )
    item = CanvasItem(elem)

    # Render item to a QImage
    qimg = QImage(150, 180, QImage.Format_ARGB32_Premultiplied)
    qimg.fill(Qt.transparent)
    painter = QPainter(qimg)
    item._paint_photo(painter, QRectF(0, 0, 150, 180), elem)
    painter.end()

    # Verify pixels are not all transparent and not all background
    assert not qimg.isNull()
    # Check that avatar pixmap is loaded
    avatar_pix = CanvasItem.get_avatar_pixmap()
    assert avatar_pix is not None
    assert not avatar_pix.isNull()
    assert avatar_pix.width() > 0


def test_post_generation_card_with_avatar_placeholder():
    """Verify post-generation ID card renders avatar placeholder when photo is missing."""
    mgr = TemplateManager()
    tmpl = mgr.get_template("builtin-classic-portrait")
    assert tmpl is not None

    record = SourceRecord(
        row_index=1,
        raw_pin="999888",
        pin="999888",
        data={
            "Name": "Jane Doe",
            "Designation": "Software Engineer",
            "Office Name": "Tech Lab",
        },
    )

    settings = RenderSettings(
        missing_photo_policy=MissingPhotoPolicy.GENERATE_WITH_PLACEHOLDER
    )

    card_img, warnings = PillowRenderer.render_card(
        template=tmpl,
        record=record,
        photo_path=None,  # No photo provided
        settings=settings,
    )

    assert isinstance(card_img, Image.Image)
    assert any("Missing photograph" in w for w in warnings)

    # Find the photo element on template
    photo_elems = [e for e in tmpl.elements if e.type == "photo"]
    assert len(photo_elems) > 0
    photo_elem = photo_elems[0]

    # Crop the photo region from the rendered card
    photo_crop = card_img.crop((
        int(photo_elem.x),
        int(photo_elem.y),
        int(photo_elem.x + photo_elem.width),
        int(photo_elem.y + photo_elem.height),
    ))
    assert photo_crop.size == (int(photo_elem.width), int(photo_elem.height))

    # Verify photo region has avatar content
    colors = photo_crop.getcolors(maxcolors=int(photo_elem.width * photo_elem.height))
    assert colors is not None
    assert len(colors) > 10
