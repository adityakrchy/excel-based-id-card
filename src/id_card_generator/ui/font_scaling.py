"""Screen aware typography scaling for the whole UI chrome.

The workstation ships with a compact 10-12 px type scale. On dense or
large displays that reads too small, so every stylesheet the app applies
is routed through a scale factor derived from the main screen: taller
displays and dense (retina) panels raise the type, small panels keep the
base size. Card (canvas) rendering is deliberately untouched - document
text is typographic geometry in points, not UI chrome.

Set the ``ID_CARD_FONT_SCALE`` environment variable to force a specific
factor (0.75-2.0) and bypass the screen detection.
"""

import logging
import os
import re

from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import QWidget

logger = logging.getLogger(__name__)

#: Matches every ``font-size: Npx`` rule of a stylesheet.
_FONT_SIZE_RULE = re.compile(r"(font-size\s*:\s*)(\d+(?:\.\d+)?)px")

#: The screen height (logical pixels) the base type was designed for.
REFERENCE_LOGICAL_HEIGHT = 900.0

#: The comfort bump applied on every screen.
BASE_SCALE = 1.15

#: The scale is clamped so the interface never becomes comic or cramped.
MIN_SCALE = 1.0
MAX_SCALE = 1.6

#: Environment variable override for the scale.
SCALE_ENV_VAR = "ID_CARD_FONT_SCALE"

_scale: float | None = None
_installed = False


def compute_font_scale() -> float:
    """Derive the UI type scale from the main screen.

    The reference is a ~900 logical px tall display. Taller screens get
    proportionally larger type (a 4K desktop reads its labels from across
    the room), and every density step of the screen (retina = 2x) nudges
    the scale up a little more, because a dense panel draws smaller
    physical glyphs at the same logical size.
    """
    override = os.environ.get(SCALE_ENV_VAR)
    if override:
        try:
            return round(min(max(float(override), 0.75), 2.0), 2)
        except ValueError:
            logger.warning("Ignoring invalid %s=%r", SCALE_ENV_VAR, override)

    scale = BASE_SCALE
    try:
        screen = QGuiApplication.primaryScreen()
    except RuntimeError:  # pragma: no cover - application gone
        screen = None
    if screen is not None:
        logical_height = float(screen.geometry().height())
        scale *= min(max(logical_height / REFERENCE_LOGICAL_HEIGHT, 1.0), 1.35)
        density_steps = round(screen.devicePixelRatio()) - 1
        scale *= 1.0 + 0.05 * density_steps
    return round(min(max(scale, MIN_SCALE), MAX_SCALE), 2)


def font_scale() -> float:
    """The scale in effect (computed once per session and cached)."""
    global _scale
    if _scale is None:
        _scale = compute_font_scale()
    return _scale


def scale_stylesheet_text(stylesheet: str, scale: float | None = None) -> str:
    """Scale every ``font-size: Npx`` rule of the given stylesheet.

    Point sizes, widths, heights and colors pass through untouched, so
    control metrics keep their layout while the glyphs grow.
    """
    if not stylesheet:
        return stylesheet
    factor = font_scale() if scale is None else scale
    if factor == 1.0:
        return stylesheet
    return _FONT_SIZE_RULE.sub(
        lambda m: f"{m.group(1)}{max(1, round(float(m.group(2)) * factor))}px",
        stylesheet,
    )


def scaled_point_size(base_pt: float) -> int:
    """The application font size in points for the current screen."""
    return max(8, round(base_pt * font_scale()))


def scaled_point(base_pt: float) -> float:
    """A painter-drawn point size adjusted for the current screen.

    Custom painted components (the record list, the export preview, the
    gallery delegate) draw their text with :class:`QFont` directly, so the
    stylesheet patch cannot reach them - their pinned point sizes go
    through this helper instead. Half point steps keep the type metrics
    quiet.
    """
    return max(6.0, round(base_pt * font_scale() * 2.0) / 2.0)


def install_font_scaling() -> float:
    """Route every stylesheet applied from now on through the font scale.

    Call once, right after the :class:`QApplication` exists and before the
    main window is built. The patch is a no-op when the screen keeps the
    base scale.
    """
    global _installed
    scale = font_scale()
    if scale == 1.0:
        logger.info("UI font scale 1.0 - no scaling needed")
        return scale
    if _installed:
        return scale
    _installed = True

    original_set_stylesheet = QWidget.setStyleSheet

    def scaled_set_stylesheet(self: QWidget, stylesheet) -> None:
        if stylesheet:
            # Remember the unscaled source so a stylesheet that is read
            # back and re-applied (theme retargeting) never compounds.
            self.setProperty("unscaled_stylesheet", stylesheet)
            stylesheet = scale_stylesheet_text(stylesheet, scale)
        original_set_stylesheet(self, stylesheet)

    QWidget.setStyleSheet = scaled_set_stylesheet  # type: ignore[method-assign]
    logger.info("UI font scale: %.2fx", scale)
    return scale
