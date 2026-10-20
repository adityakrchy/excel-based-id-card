"""Shared Qt text measurement helpers for the canvas editor.

The canvas painter and the interactive resize guard must agree on *how* a text
element is laid out, otherwise the "minimum size" protection would guard a
size that does not match what is actually drawn.  This module is the single
source of truth for:

* resolving the text an element displays,
* building the effective ``QFont`` (including AUTO_SHRINK fitting),
* measuring the space a text block needs so that it is never clipped,
* deriving the minimum bounding-box size a text element may be resized to.

All sizes are returned in **document pixels** (the same space used by the
canvas scene), so they can be compared directly with ``element.width`` /
``element.height``.
"""

from typing import Optional, Tuple

from PySide6.QtCore import QRect, QRectF, Qt
from PySide6.QtGui import QFont, QFontMetrics

from id_card_generator.core.constants import DEFAULT_DPI, TextOverflowPolicy
from id_card_generator.core.geometry import points_to_document_pixels
from id_card_generator.core.models import CanvasElement, SourceRecord

# Element types that render text content.
TEXT_ELEMENT_TYPES = ("static_text", "dynamic_text", "pin_field")

# Smallest size any element may have (matches the historic hard floor).
ABSOLUTE_MIN_SIZE = 10.0

# Breathing room kept between the text and the bounding-box border.
TEXT_PADDING = 2.0

# Unicode fallbacks appended after the user's chosen family.
DEVANAGARI_FALLBACK_FONTS = (
    "Devanagari Sangam MN",
    "Mangal",
    "Nirmala UI",
    "Kohinoor Devanagari",
    "Noto Sans Devanagari",
)

# Lower bound used by the AUTO_SHRINK fitting loop.
MIN_AUTO_SHRINK_PT = 4.0

# Resize handles that keep the *right* edge anchored (left side handles).
LEFT_HANDLE_IDS = (0, 6, 7)
# Resize handles that keep the *bottom* edge anchored (top side handles).
TOP_HANDLE_IDS = (0, 1, 2)


def is_text_element(element: Optional[CanvasElement]) -> bool:
    """Return True when the element renders text content."""
    return element is not None and element.type in TEXT_ELEMENT_TYPES


def resolve_display_text(
    element: CanvasElement,
    record: Optional[SourceRecord] = None,
) -> str:
    """Return the text an element currently displays."""
    if element.type == "static_text":
        return element.static_content or element.name
    if element.type == "pin_field":
        if record is not None:
            return record.pin or (element.binding or "PIN-100001")
        return element.binding or "PIN-100001"

    column = element.binding or element.name
    if record is not None:
        return record.get_value(column, f"[{column}]")
    return f"[{column}]"


def build_font(element: CanvasElement) -> QFont:
    """Build the base font (family fallbacks, weight, slant) for an element."""
    chosen = element.style.font_family or "Arial"
    families = [chosen] + [f for f in DEVANAGARI_FALLBACK_FONTS if f != chosen] + ["Arial"]

    font = QFont(families[0])
    font.setFamilies(families)
    font.setBold(element.style.font_bold)
    font.setItalic(element.style.font_italic)
    font.setStyleStrategy(
        QFont.StyleStrategy(QFont.PreferAntialias | QFont.PreferMatch)
    )
    return font


def measurement_flags(element: CanvasElement) -> int:
    """Return the draw flags used when measuring an element's text."""
    flags = Qt.TextIncludeTrailingSpaces
    if element.style.wrap:
        flags |= Qt.TextWordWrap
    return flags


def resolve_font(
    element: CanvasElement,
    text: str,
    dpi: int,
    rect: QRectF,
) -> QFont:
    """Return the font actually used to paint ``text`` inside ``rect``.

    Mirrors the canvas painter exactly, including the AUTO_SHRINK fitting loop,
    so measurements taken with the returned font match what is drawn.
    """
    font = build_font(element)
    font_size_pt = float(element.style.font_size)

    if element.style.overflow_policy == TextOverflowPolicy.AUTO_SHRINK and text:
        flags = measurement_flags(element)
        cur_pt = font_size_pt
        while cur_pt >= MIN_AUTO_SHRINK_PT:
            font.setPixelSize(max(1, int(round(points_to_document_pixels(cur_pt, dpi)))))
            fm = QFontMetrics(font)
            bounding = fm.boundingRect(rect.toRect(), flags, text)
            single_w = fm.horizontalAdvance(text)
            fits_single_line = (single_w <= rect.width()) and ("\n" not in text)
            if fits_single_line:
                break
            if bounding.width() <= rect.width() and bounding.height() <= rect.height():
                break
            cur_pt -= 0.5

        if cur_pt < MIN_AUTO_SHRINK_PT:
            cur_pt = MIN_AUTO_SHRINK_PT
            font.setPixelSize(max(1, int(round(points_to_document_pixels(cur_pt, dpi)))))
    else:
        doc_px = points_to_document_pixels(font_size_pt, dpi)
        font.setPixelSize(max(1, int(round(doc_px))))

    return font


def measure_required_size(
    text: str,
    font: QFont,
    wrap: bool,
    avail_width: Optional[float] = None,
) -> Tuple[float, float]:
    """Return the ``(width, height)`` needed to render ``text`` completely.

    * When ``wrap`` is False the text is never re-flowed, so the full single
      line width is required.
    * When ``wrap`` is True the text is re-flowed inside ``avail_width``; the
      returned height is the wrapped height and the returned width is the
      longest unbreakable word (so words are never cut in half).
    """
    if not text:
        return (0.0, 0.0)

    fm = QFontMetrics(font)

    if wrap:
        width = int(max(1.0, avail_width)) if avail_width else 32767
        br = fm.boundingRect(
            QRect(0, 0, width, 32767),
            Qt.TextWordWrap | Qt.TextIncludeTrailingSpaces,
            text,
        )
        needed_h = float(br.height())

        longest_word = 0.0
        for word in text.replace("\n", " ").split(" "):
            if word:
                longest_word = max(longest_word, float(fm.horizontalAdvance(word)))
        needed_w = longest_word
    else:
        br = fm.boundingRect(
            QRect(0, 0, 32767, 32767),
            Qt.TextIncludeTrailingSpaces,
            text,
        )
        needed_w = float(br.width())
        needed_h = float(br.height())

    return (needed_w, needed_h)


def natural_text_size(
    element: CanvasElement,
    text: str,
    font: QFont,
) -> Tuple[float, float]:
    """Return the natural (unwrapped) size of the text content."""
    return measure_required_size(text, font, wrap=False)


def minimum_text_size(
    element: CanvasElement,
    text: str,
    font: QFont,
    avail_width: Optional[float] = None,
) -> Tuple[float, float]:
    """Return the minimum ``(width, height)`` a text box may be resized to.

    The result guarantees that the rendered text is never clipped by the
    element's bounding box:

    * non-wrapped text keeps its full single-line width,
    * wrapped text may become narrower (down to its longest word) but the
      height grows with it, giving Figma/Illustrator style auto-height.
    """
    if not text:
        return (ABSOLUTE_MIN_SIZE, ABSOLUTE_MIN_SIZE)

    wrap = bool(element.style.wrap)
    needed_w, needed_h = measure_required_size(text, font, wrap, avail_width)

    min_w = max(ABSOLUTE_MIN_SIZE, needed_w + TEXT_PADDING)
    min_h = max(ABSOLUTE_MIN_SIZE, needed_h + TEXT_PADDING)
    return (min_w, min_h)


def constrain_rect_to_min(
    rect: QRectF,
    min_w: float,
    min_h: float,
    handle: Optional[int] = None,
) -> QRectF:
    """Clamp ``rect`` so it is never smaller than ``min_w`` x ``min_h``.

    The edge opposite to the dragged handle stays anchored so the element
    does not jump around while it is being resized.
    """
    out = QRectF(rect)

    if out.width() < min_w:
        if handle in LEFT_HANDLE_IDS:
            out.setLeft(out.right() - min_w)
        else:
            out.setWidth(min_w)

    if out.height() < min_h:
        if handle in TOP_HANDLE_IDS:
            out.setTop(out.bottom() - min_h)
        else:
            out.setHeight(min_h)

    return out


def fit_element_to_text(
    element: CanvasElement,
    record: Optional[SourceRecord] = None,
    dpi: int = DEFAULT_DPI,
    max_width: Optional[float] = None,
) -> Tuple[float, float]:
    """Resize a text element so its box hugs its text content.

    Returns the applied ``(width, height)``.  The width never exceeds
    ``max_width``; when the text is wider the content is wrapped and the
    height grows accordingly.
    """
    if not is_text_element(element):
        return (element.width, element.height)

    text = resolve_display_text(element, record)
    if not text:
        return (element.width, element.height)

    # Measure with an unbounded canvas so an AUTO_SHRINK policy does not
    # shrink the font because of the current (possibly too small) box.
    probe = QRectF(0, 0, 32767, 32767)
    font = resolve_font(element, text, dpi, probe)

    single_w, single_h = natural_text_size(element, text, font)
    if single_w <= 0:
        return (element.width, element.height)

    target_w = single_w
    if max_width and single_w > max_width:
        target_w = max_width

    if element.style.wrap and target_w < single_w:
        _, wrapped_h = measure_required_size(text, font, True, target_w)
        height = max(single_h, wrapped_h)
    else:
        height = single_h

    width = max(ABSOLUTE_MIN_SIZE, target_w + TEXT_PADDING)
    height = max(ABSOLUTE_MIN_SIZE, height + TEXT_PADDING)

    element.width = width
    element.height = height
    return (width, height)
