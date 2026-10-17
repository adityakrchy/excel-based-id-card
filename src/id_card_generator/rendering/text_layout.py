"""Text layout calculation, word wrapping, alignment, and auto-shrink fitting."""

import logging
from typing import List, Optional, Tuple
from PIL import ImageDraw, ImageFont
from id_card_generator.core.constants import DEFAULT_DPI, TextOverflowPolicy
from id_card_generator.core.geometry import points_to_document_pixels
from id_card_generator.rendering.font_manager import FontManager

logger = logging.getLogger(__name__)


class TextLayoutResult:
    """Contains calculated layout lines and layout metadata."""

    def __init__(self) -> None:
        self.lines: List[Tuple[str, float, float]] = []  # (text, x, y)
        self.font: Optional[ImageFont.ImageFont] = None
        self.overflow_detected: bool = False
        self.font_size_used: float = 0.0  # In typographic points (pt)
        self.font_size_px: float = 0.0    # In document pixels at target DPI


class TextLayout:
    """Computes exact positioning, line breaks, and auto-shrink fitting for text blocks."""

    @staticmethod
    def measure_text(font: ImageFont.ImageFont, text: str) -> Tuple[float, float]:
        """Return (width, height) bounding box of string with given font."""
        if not text:
            return 0.0, 0.0
        try:
            bbox = font.getbbox(text)
            return float(bbox[2] - bbox[0]), float(bbox[3] - bbox[1])
        except Exception:
            return float(len(text) * 10), 20.0

    @staticmethod
    def wrap_text(
        text: str,
        font: ImageFont.ImageFont,
        max_width: float,
    ) -> List[str]:
        """Wrap text into lines that do not exceed max_width."""
        if not text:
            return []

        words = text.split(" ")
        lines: List[str] = []
        current_line: List[str] = []

        for word in words:
            candidate = " ".join(current_line + [word])
            w, _ = TextLayout.measure_text(font, candidate)
            if w <= max_width or not current_line:
                current_line.append(word)
            else:
                lines.append(" ".join(current_line))
                current_line = [word]

        if current_line:
            lines.append(" ".join(current_line))

        return lines

    @classmethod
    def layout_text(
        cls,
        text: str,
        family: str,
        initial_font_size: float,
        bold: bool,
        italic: bool,
        target_width: float,
        target_height: float,
        target_x: float,
        target_y: float,
        text_align: str = "left",  # left, center, right
        vertical_align: str = "top",  # top, middle, bottom
        line_spacing: float = 1.2,
        wrap: bool = True,
        overflow_policy: TextOverflowPolicy = TextOverflowPolicy.AUTO_SHRINK,
        min_font_size: float = 4.0,  # in typographic points
        dpi: float = DEFAULT_DPI,
    ) -> TextLayoutResult:
        """Calculate layout lines for text within bounding box.

        Args:
            initial_font_size: Font size in typographic points (pt), matching Photoshop.
            min_font_size: Minimum font size in points for AUTO_SHRINK.
            dpi: Document resolution (dots/pixels per inch), default 300.
        """
        result = TextLayoutResult()
        if not text:
            return result

        font_size_pt = float(initial_font_size)
        min_font_size_pt = float(min_font_size)

        # 1. Handle AUTO_SHRINK
        if overflow_policy == TextOverflowPolicy.AUTO_SHRINK:
            while font_size_pt >= min_font_size_pt:
                font_size_px = points_to_document_pixels(font_size_pt, dpi)
                font = FontManager.get_font(family, font_size_px, bold, italic)
                lines = cls.wrap_text(text, font, target_width) if wrap else [text]
                line_height = font_size_px * line_spacing
                total_text_h = len(lines) * line_height
                max_line_w = max((cls.measure_text(font, l)[0] for l in lines), default=0)

                fits_single_line = (len(lines) <= 1) and ("\n" not in text) and (max_line_w <= target_width)
                if fits_single_line or (max_line_w <= target_width and total_text_h <= target_height):
                    break
                font_size_pt -= 0.5  # Fine-grained half-point reduction

            if font_size_pt < min_font_size_pt:
                font_size_pt = min_font_size_pt
                font_size_px = points_to_document_pixels(font_size_pt, dpi)
                font = FontManager.get_font(family, font_size_px, bold, italic)
                result.overflow_detected = True
        else:
            font_size_px = points_to_document_pixels(font_size_pt, dpi)
            font = FontManager.get_font(family, font_size_px, bold, italic)

        font_size_px = points_to_document_pixels(font_size_pt, dpi)
        result.font = font
        result.font_size_used = font_size_pt
        result.font_size_px = font_size_px

        # 2. Break lines using final font
        lines = cls.wrap_text(text, font, target_width) if wrap else [text]

        # Check for TRUNCATE policy
        if overflow_policy == TextOverflowPolicy.TRUNCATE:
            truncated_lines = []
            for line in lines:
                w, _ = cls.measure_text(font, line)
                if w > target_width:
                    result.overflow_detected = True
                    while line and cls.measure_text(font, line + "...")[0] > target_width:
                        line = line[:-1]
                    line = line + "..."
                truncated_lines.append(line)
            lines = truncated_lines

        line_height = font_size_px * line_spacing
        total_block_h = len(lines) * line_height

        # 3. Vertical alignment
        if vertical_align == "middle":
            start_y = target_y + max(0.0, (target_height - total_block_h) / 2.0)
        elif vertical_align == "bottom":
            start_y = target_y + max(0.0, target_height - total_block_h)
        else:
            start_y = target_y

        # 4. Horizontal alignment and position lines
        for i, line in enumerate(lines):
            line_w, _ = cls.measure_text(font, line)
            if text_align == "center":
                x = target_x + max(0.0, (target_width - line_w) / 2.0)
            elif text_align == "right":
                x = target_x + max(0.0, target_width - line_w)
            else:
                x = target_x

            y = start_y + (i * line_height)
            result.lines.append((line, x, y))

        return result
