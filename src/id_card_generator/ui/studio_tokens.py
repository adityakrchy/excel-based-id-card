"""Design tokens for the ID Studio workstation design system.

Everything visual in the application derives from this module:

* ``COLORS`` / ``LIGHT_COLORS`` - surface ramp, hairlines, accents and text tones
  for the dark and light themes.
* ``SPACING`` / ``RADII`` / ``SIZES`` - the spacing, corner and control metrics
  that give every screen the same rhythm.
* ``TYPOGRAPHY`` - font stacks and type scale.

The theme manager renders the global stylesheet from these tokens, and the
reusable widgets in :mod:`id_card_generator.ui.components` consume the same
values, so a change here propagates to the whole application.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class StudioColors:
    """Dark workstation palette (charcoal value ramp)."""

    # Surfaces & depth hierarchy
    SURFACE_LOWEST: str = "#0c0e12"     # Recessed canvas / artboard backdrop
    SURFACE: str = "#111317"            # Application shell
    SURFACE_DIM: str = "#0f1115"        # Header bar / chrome
    SURFACE_BRIGHT: str = "#37393e"
    SURFACE_LOW: str = "#1a1c20"        # Docked drawers, sidebars, context ribbons
    SURFACE_CONTAINER: str = "#1e2024"  # Cards, tool wells, toolbar base
    SURFACE_HIGH: str = "#282a2e"       # Hover / elevated panels / active tabs
    SURFACE_HIGHEST: str = "#333539"    # Active selections, popovers

    # Hairlines & dividers
    OUTLINE: str = "#8e909f"
    OUTLINE_VARIANT: str = "#383d47"
    BORDER_HAIRLINE: str = "#383d47"
    BORDER_SUBTLE: str = "#282a2e"

    # Primary accent & selection
    PRIMARY: str = "#b6c4ff"
    PRIMARY_CONTAINER: str = "#6c8cff"
    ON_PRIMARY: str = "#002780"
    ON_PRIMARY_CONTAINER: str = "#002376"

    # Secondary muted accents
    SECONDARY: str = "#c4c6d1"
    SECONDARY_CONTAINER: str = "#464952"
    ON_SECONDARY: str = "#2d3038"

    # Semantic accents
    TERTIARY: str = "#6edba3"           # Success / valid / ready
    TERTIARY_CONTAINER: str = "#34a673"
    ON_TERTIARY: str = "#003822"
    ON_TERTIARY_CONTAINER: str = "#00341f"

    WARNING: str = "#e8b65b"
    WARNING_CONTAINER: str = "#3a2c10"
    ON_WARNING: str = "#241a05"
    ERROR: str = "#ffb4ab"
    ERROR_CONTAINER: str = "#93000a"
    ON_ERROR: str = "#690005"
    INFO: str = "#9ecbff"
    INFO_CONTAINER: str = "#12325c"
    ON_INFO: str = "#cce5ff"

    # Typography tones
    ON_SURFACE: str = "#e2e2e8"
    ON_SURFACE_VARIANT: str = "#c4c5d5"
    TEXT_MUTED: str = "#8e909f"

    # Canvas
    CANVAS_BACKDROP: str = "#0c0e12"
    CANVAS_SURFACE: str = "#ffffff"


@dataclass(frozen=True)
class LightStudioColors:
    """Light "paper" palette used by the white theme."""

    SURFACE_LOWEST: str = "#f3f4f6"
    SURFACE: str = "#f7f8fa"
    SURFACE_DIM: str = "#ffffff"
    SURFACE_BRIGHT: str = "#d1d5db"
    SURFACE_LOW: str = "#f3f4f6"
    SURFACE_CONTAINER: str = "#ffffff"
    SURFACE_HIGH: str = "#e9ebef"
    SURFACE_HIGHEST: str = "#dfe2e7"

    OUTLINE: str = "#9ca3af"
    OUTLINE_VARIANT: str = "#e5e7eb"
    BORDER_HAIRLINE: str = "#dfe3e8"
    BORDER_SUBTLE: str = "#eef0f3"

    PRIMARY: str = "#1b3fa8"
    PRIMARY_CONTAINER: str = "#0067c0"
    ON_PRIMARY: str = "#ffffff"
    ON_PRIMARY_CONTAINER: str = "#ffffff"

    SECONDARY: str = "#374151"
    SECONDARY_CONTAINER: str = "#e5e7eb"
    ON_SECONDARY: str = "#111827"

    TERTIARY: str = "#0f7a4d"
    TERTIARY_CONTAINER: str = "#34a673"
    ON_TERTIARY: str = "#ffffff"
    ON_TERTIARY_CONTAINER: str = "#00341f"

    WARNING: str = "#8a5a00"
    WARNING_CONTAINER: str = "#fdf1d8"
    ON_WARNING: str = "#241a05"
    ERROR: str = "#b3261e"
    ERROR_CONTAINER: str = "#fde3e1"
    ON_ERROR: str = "#690005"
    INFO: str = "#0b4a8f"
    INFO_CONTAINER: str = "#e3f0ff"
    ON_INFO: str = "#0a2a52"

    ON_SURFACE: str = "#111827"
    ON_SURFACE_VARIANT: str = "#374151"
    TEXT_MUTED: str = "#6b7280"

    CANVAS_BACKDROP: str = "#e9ebef"
    CANVAS_SURFACE: str = "#ffffff"


@dataclass(frozen=True)
class StudioSpacing:
    """Spacing scale (4 px base)."""

    XXS: int = 2
    XS: int = 4
    SM: int = 8
    MD: int = 12
    LG: int = 16
    XL: int = 24
    XXL: int = 32


@dataclass(frozen=True)
class StudioRadii:
    """Corner radius scale."""

    XS: int = 2
    SM: int = 4
    MD: int = 6
    LG: int = 8
    PILL: int = 999


@dataclass(frozen=True)
class StudioSizes:
    """Control metrics shared by every screen."""

    HEADER_HEIGHT: int = 36
    NAV_HEIGHT: int = 44
    FOOTER_HEIGHT: int = 52
    CONTROL_HEIGHT: int = 28
    CONTROL_HEIGHT_SM: int = 24
    BUTTON_HEIGHT: int = 30
    ICON_BUTTON: int = 28
    PANEL_TITLE_HEIGHT: int = 34


@dataclass(frozen=True)
class StudioTypography:
    """Typography stacks and font hierarchies."""

    FONT_FAMILY_UI: str = 'Inter, -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif'
    FONT_FAMILY_MONO: str = '"JetBrains Mono", "SF Mono", Menlo, Monaco, Consolas, monospace'

    SIZE_DISPLAY: int = 16
    SIZE_TITLE: int = 13
    SIZE_BODY: int = 12
    SIZE_LABEL: int = 11
    SIZE_NUMERIC: int = 11
    SIZE_MICRO: int = 9


COLORS = StudioColors()
LIGHT_COLORS = LightStudioColors()
SPACING = StudioSpacing()
RADII = StudioRadii()
SIZES = StudioSizes()
TYPOGRAPHY = StudioTypography()

# Convenience top-level constants (dark theme defaults)
SURFACE_LOWEST = COLORS.SURFACE_LOWEST
SURFACE = COLORS.SURFACE
SURFACE_LOW = COLORS.SURFACE_LOW
SURFACE_CONTAINER = COLORS.SURFACE_CONTAINER
SURFACE_HIGH = COLORS.SURFACE_HIGH
SURFACE_HIGHER = COLORS.SURFACE_HIGHEST
BORDER_DEFAULT = COLORS.BORDER_HAIRLINE
BORDER_SUBTLE = COLORS.BORDER_SUBTLE
PRIMARY = COLORS.PRIMARY_CONTAINER
PRIMARY_LIGHT = COLORS.PRIMARY
SEMANTIC_SUCCESS = COLORS.TERTIARY
SEMANTIC_WARNING = COLORS.WARNING
SEMANTIC_ERROR = COLORS.ERROR
SEMANTIC_INFO = COLORS.INFO
TEXT_PRIMARY = COLORS.ON_SURFACE
TEXT_SECONDARY = COLORS.ON_SURFACE_VARIANT
TEXT_MUTED = COLORS.TEXT_MUTED

FONT_FAMILY_UI = TYPOGRAPHY.FONT_FAMILY_UI
FONT_FAMILY_MONO = TYPOGRAPHY.FONT_FAMILY_MONO


def palette_for(theme: str) -> StudioColors:
    """Return the color palette for a theme name (``"black"``/``"white"``)."""
    return LIGHT_COLORS if str(theme).lower().strip() == "white" else COLORS


def active_palette() -> StudioColors:
    """Return the palette of the theme that is currently applied.

    The hand painted widgets (progress ring, speed graph, list delegates)
    cannot be styled with a stylesheet, so they resolve the palette at
    paint time instead of baking the colours in.
    """
    try:
        # Imported lazily: the theme manager builds on these tokens.
        from id_card_generator.ui.theme_manager import ThemeManager

        return palette_for(ThemeManager.instance().active_effective_theme)
    except Exception:  # pragma: no cover - the fallback is defensive
        return COLORS
