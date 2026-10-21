"""Authoritative Pillow ID card renderer."""

import logging
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from PIL import Image, ImageDraw, ImageOps

from id_card_generator.core.constants import (
    DEFAULT_DPI,
    ImageFitMode,
    MissingPhotoPolicy,
    OutputFormat,
    TextOverflowPolicy,
)
from id_card_generator.core.models import (
    CanvasElement,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.rendering.image_processing import ImageProcessor
from id_card_generator.rendering.text_layout import TextLayout

logger = logging.getLogger(__name__)


class PillowRenderer:
    """Renders ID cards from a template, source record, and matched photograph."""

    @classmethod
    def render_card(
        cls,
        template: TemplateDefinition,
        record: Optional[SourceRecord] = None,
        photo_path: Optional[str] = None,
        column_mappings: Optional[Dict[str, str]] = None,
        settings: Optional[RenderSettings] = None,
        side: str = "front",
    ) -> Tuple[Image.Image, List[str]]:
        """Render a single card and return (PIL Image, List of warnings).

        ``side`` selects the face of the card: the elements that belong to the
        other face are skipped.  Existing templates only use the front, so
        the default renders exactly what it always did.
        """
        settings = settings or RenderSettings()
        column_mappings = column_mappings or {}
        warnings: List[str] = []
        side = (side or "front").lower()

        card_w = template.width_px
        card_h = template.height_px

        card_dpi = template.dpi if getattr(template, "dpi", None) else DEFAULT_DPI

        # 1. Base canvas
        card_img = Image.new("RGBA", (card_w, card_h), template.background_color or "#FFFFFF")
        card_img.info["dpi"] = (card_dpi, card_dpi)

        # 2. Background image if present
        if template.background_image_path:
            bg_path = Path(template.background_image_path)
            if bg_path.exists():
                bg_img = ImageProcessor.load_and_fit(
                    bg_path, card_w, card_h, fit_mode=ImageFitMode.COVER
                )
                card_img = Image.alpha_composite(card_img, bg_img)
            else:
                warnings.append(f"Template background image not found: {template.background_image_path}")

        # 3. Sort elements by z_index
        sorted_elements = sorted(template.elements, key=lambda el: el.z_index)

        # 4. Render elements
        for elem in sorted_elements:
            if not elem.visible:
                continue

            # Only the elements of the requested face are painted.
            if (getattr(elem, "side", "front") or "front").lower() != side:
                continue

            try:
                elem_warnings = cls._render_element(
                    card_img=card_img,
                    elem=elem,
                    record=record,
                    photo_path=photo_path,
                    column_mappings=column_mappings,
                    settings=settings,
                    dpi=card_dpi,
                )
                warnings.extend(elem_warnings)
            except Exception as e:
                logger.error("Failed to render element '%s' (%s): %s", elem.name, elem.id, e)
                warnings.append(f"Element '{elem.name}' render error: {e}")

        # 5. Format conversion if JPEG requested
        if settings.output_format == OutputFormat.JPEG:
            # Flatten RGBA onto RGB
            rgb_bg = Image.new("RGB", (card_w, card_h), template.background_color or "#FFFFFF")
            rgb_bg.paste(card_img, (0, 0), card_img)
            rgb_bg.info["dpi"] = (card_dpi, card_dpi)
            return rgb_bg, warnings

        return card_img, warnings

    @classmethod
    def _render_element(
        cls,
        card_img: Image.Image,
        elem: CanvasElement,
        record: Optional[SourceRecord],
        photo_path: Optional[str],
        column_mappings: Dict[str, str],
        settings: RenderSettings,
        dpi: int = DEFAULT_DPI,
    ) -> List[str]:
        """Render a single canvas element onto card_img. Returns warnings."""
        warnings: List[str] = []
        elem_x = int(elem.x)
        elem_y = int(elem.y)
        elem_w = int(elem.width)
        elem_h = int(elem.height)

        if elem_w <= 0 or elem_h <= 0:
            return warnings

        # --- SHAPES ---
        if elem.type in ("rect", "round_rect", "line"):
            cls._render_shape(card_img, elem, elem_x, elem_y, elem_w, elem_h)
            return warnings

        # --- STATIC TEXT ---
        if elem.type == "static_text":
            text = elem.static_content or ""
            warn = cls._render_text(card_img, elem, text, elem_x, elem_y, elem_w, elem_h, settings, dpi=dpi)
            if warn:
                warnings.extend(warn)
            return warnings

        # --- DYNAMIC TEXT ---
        if elem.type in ("dynamic_text", "pin_field"):
            text = cls._resolve_bound_text(elem, record, column_mappings)
            warn = cls._render_text(card_img, elem, text, elem_x, elem_y, elem_w, elem_h, settings, dpi=dpi)
            if warn:
                warnings.extend(warn)
            return warnings

        # --- PHOTO ---
        if elem.type == "photo":
            warn = cls._render_photo(card_img, elem, record, photo_path, elem_x, elem_y, elem_w, elem_h, settings)
            if warn:
                warnings.extend(warn)
            return warnings

        # --- STATIC IMAGE / LOGO ---
        if elem.type == "image":
            if elem.static_content:
                img_p = Path(elem.static_content)
                if img_p.exists():
                    fit_img = ImageProcessor.load_and_fit(
                        img_p, elem_w, elem_h, fit_mode=elem.style.fit_mode
                    )
                    masked = ImageProcessor.apply_mask_and_border(
                        fit_img,
                        mask_shape=elem.style.mask_shape,
                        border_radius=elem.style.border_radius,
                        border_width=elem.style.border_width,
                        border_color=elem.style.border_color,
                    )
                    card_img.alpha_composite(masked, (elem_x, elem_y))
                else:
                    warnings.append(f"Image element '{elem.name}' file not found: {elem.static_content}")
            return warnings

        return warnings

    @staticmethod
    def _render_shape(
        card_img: Image.Image,
        elem: CanvasElement,
        x: int,
        y: int,
        w: int,
        h: int,
    ) -> None:
        """Render rectangles, rounded rectangles, and divider lines."""
        draw = ImageDraw.Draw(card_img)
        bg_col = elem.style.background_color
        if bg_col == "transparent":
            bg_col = None

        border_col = elem.style.border_color
        if border_col == "transparent":
            border_col = None

        bw = elem.style.border_width

        if elem.type == "line":
            draw.line([(x, y), (x + w, y + h)], fill=bg_col or border_col or "#000000", width=max(1, h, bw))
        elif elem.type == "round_rect" or elem.style.border_radius > 0:
            radius = elem.style.border_radius
            draw.rounded_rectangle(
                [(x, y), (x + w - 1, y + h - 1)],
                radius=radius,
                fill=bg_col,
                outline=border_col,
                width=bw,
            )
        else:
            draw.rectangle(
                [(x, y), (x + w - 1, y + h - 1)],
                fill=bg_col,
                outline=border_col,
                width=bw,
            )

    @staticmethod
    def _resolve_bound_text(
        elem: CanvasElement,
        record: Optional[SourceRecord],
        column_mappings: Dict[str, str],
    ) -> str:
        """Resolve string value for dynamic element."""
        if not record:
            return f"[{elem.binding or elem.name}]"

        # Check explicit column mappings first
        col_name = column_mappings.get(elem.id) or elem.binding

        if elem.type == "pin_field" or (col_name and col_name.lower() in ("pin number", "pin", "id")):
            return record.pin or record.raw_pin

        if col_name:
            val = record.get_value(col_name)
            if val:
                return val

        # Fallback to element static content or name
        return elem.static_content or ""

    @classmethod
    def _render_text(
        cls,
        card_img: Image.Image,
        elem: CanvasElement,
        text: str,
        x: int,
        y: int,
        w: int,
        h: int,
        settings: RenderSettings,
        dpi: int = DEFAULT_DPI,
    ) -> List[str]:
        """Compute layout and draw text onto card_img."""
        warnings: List[str] = []
        if not text:
            return warnings

        # If text contains Devanagari characters, render using Qt's HarfBuzz complex shaping engine
        if any(0x0900 <= ord(c) <= 0x097F for c in text):
            rendered_layer = cls._render_devanagari_text_qt(
                text=text,
                family=elem.style.font_family,
                font_size_pt=elem.style.font_size,
                font_color=elem.style.font_color or "#000000",
                bold=elem.style.font_bold,
                italic=elem.style.font_italic,
                w=w,
                h=h,
                text_align=elem.style.text_align,
                vertical_align=elem.style.vertical_align,
                wrap=elem.style.wrap,
                overflow_policy=elem.style.overflow_policy,
                dpi=dpi,
            )
            if rendered_layer:
                card_img.alpha_composite(rendered_layer, (x, y))
                return warnings

        layout = TextLayout.layout_text(
            text=text,
            family=elem.style.font_family,
            initial_font_size=elem.style.font_size,
            bold=elem.style.font_bold,
            italic=elem.style.font_italic,
            target_width=w,
            target_height=h,
            target_x=x,
            target_y=y,
            text_align=elem.style.text_align,
            vertical_align=elem.style.vertical_align,
            line_spacing=elem.style.line_spacing,
            wrap=elem.style.wrap,
            overflow_policy=elem.style.overflow_policy,
            dpi=dpi,
        )

        if layout.overflow_detected:
            warnings.append(f"Text in element '{elem.name}' overflowed target dimensions ({w}x{h}).")

        draw = ImageDraw.Draw(card_img)
        font_color = elem.style.font_color or "#000000"

        for line_str, lx, ly in layout.lines:
            draw.text((int(lx), int(ly)), line_str, font=layout.font, fill=font_color)

        return warnings

    @classmethod
    def _render_devanagari_text_qt(
        cls,
        text: str,
        family: str,
        font_size_pt: float,
        font_color: str,
        bold: bool,
        italic: bool,
        w: int,
        h: int,
        text_align: str = "left",
        vertical_align: str = "top",
        wrap: bool = True,
        overflow_policy: TextOverflowPolicy = TextOverflowPolicy.AUTO_SHRINK,
        dpi: int = DEFAULT_DPI,
    ) -> Optional[Image.Image]:
        """Render Devanagari text using Qt's OpenType complex script shaping engine with HarfBuzz."""
        try:
            import sys
            from PySide6.QtCore import QRectF, Qt
            from PySide6.QtGui import QColor, QFont, QFontMetrics, QGuiApplication, QImage, QPainter
            from id_card_generator.core.geometry import points_to_document_pixels

            app = QGuiApplication.instance()
            if not app:
                app = QGuiApplication(sys.argv)

            qimg = QImage(max(1, w), max(1, h), QImage.Format_ARGB32_Premultiplied)
            qimg.fill(Qt.transparent)
            painter = QPainter(qimg)
            painter.setRenderHint(QPainter.TextAntialiasing)

            has_devanagari = any(0x0900 <= ord(c) <= 0x097F for c in text)
            is_latin_default = family.lower() in (
                "arial", "segoe ui", "helvetica", "helvetica neue", "sans-serif", "times new roman", "roboto", "inter"
            )
            if has_devanagari and is_latin_default:
                families = [
                    "Devanagari Sangam MN",
                    "Mangal",
                    "Nirmala UI",
                    "Kohinoor Devanagari",
                    "Noto Sans Devanagari",
                    family,
                ]
            else:
                families = [
                    family,
                    "Devanagari Sangam MN",
                    "Mangal",
                    "Nirmala UI",
                    "Kohinoor Devanagari",
                    "Noto Sans Devanagari",
                    "Arial",
                ]
            font = QFont(families[0])
            font.setFamilies(families)
            font.setBold(bold)
            font.setItalic(italic)
            font.setStyleStrategy(QFont.PreferAntialias)

            flags = Qt.TextIncludeTrailingSpaces
            if text_align == "center":
                flags |= Qt.AlignHCenter
            elif text_align == "right":
                flags |= Qt.AlignRight
            else:
                flags |= Qt.AlignLeft

            if vertical_align == "middle":
                flags |= Qt.AlignVCenter
            elif vertical_align == "bottom":
                flags |= Qt.AlignBottom
            else:
                flags |= Qt.AlignTop

            if wrap:
                flags |= Qt.TextWordWrap

            cur_pt = float(font_size_pt)
            rect = QRectF(0, 0, w, h)

            if overflow_policy == TextOverflowPolicy.AUTO_SHRINK and text:
                min_pt = 4.0
                while cur_pt >= min_pt:
                    doc_px = points_to_document_pixels(cur_pt, dpi)
                    font.setPixelSize(max(1, int(round(doc_px))))
                    fm = QFontMetrics(font)
                    bounding = fm.boundingRect(rect.toRect(), flags, text)
                    single_w = fm.horizontalAdvance(text)
                    fits_single_line = (single_w <= w) and ("\n" not in text)
                    if fits_single_line:
                        break
                    if bounding.width() <= w and bounding.height() <= h:
                        break
                    cur_pt -= 0.5
            else:
                doc_px = points_to_document_pixels(cur_pt, dpi)
                font.setPixelSize(max(1, int(round(doc_px))))

            painter.setFont(font)
            painter.setPen(QColor(font_color))
            painter.drawText(rect, flags, text)
            painter.end()

            ptr = qimg.bits()
            bytes_per_line = qimg.bytesPerLine()
            raw = bytes(ptr)
            return Image.frombuffer("RGBA", (qimg.width(), qimg.height()), raw, "raw", "BGRA", bytes_per_line, 1)
        except Exception as e:
            logger.warning("Qt Devanagari text rendering fallback to FreeType: %s", e)
            return None

    @staticmethod
    def _render_photo(
        card_img: Image.Image,
        elem: CanvasElement,
        record: Optional[SourceRecord],
        photo_path: Optional[str],
        x: int,
        y: int,
        w: int,
        h: int,
        settings: RenderSettings,
    ) -> List[str]:
        """Load and composite photo or placeholder."""
        warnings: List[str] = []
        resolved_img: Optional[Image.Image] = None

        if photo_path and Path(photo_path).exists():
            resolved_img = ImageProcessor.load_and_fit(
                Path(photo_path), w, h, fit_mode=elem.style.fit_mode
            )
        else:
            # Photo is missing
            if record:
                warnings.append(f"Missing photograph for PIN '{record.pin}'")

            if settings.missing_photo_policy == MissingPhotoPolicy.FAIL_RECORD:
                raise ValueError(f"Missing required photo for PIN {record.pin if record else 'unknown'}")

            resolved_img = ImageProcessor.generate_placeholder(w, h)

        # Apply mask and border
        masked_img = ImageProcessor.apply_mask_and_border(
            resolved_img,
            mask_shape=elem.style.mask_shape,
            border_radius=elem.style.border_radius,
            border_width=elem.style.border_width,
            border_color=elem.style.border_color,
        )

        card_img.alpha_composite(masked_img, (x, y))
        return warnings
