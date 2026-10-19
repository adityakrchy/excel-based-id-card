"""Design tokens and visual constants for the ID Studio workstation design system."""

from dataclasses import dataclass


@dataclass(frozen=True)
class StudioColors:
    """ID Studio Dark Workstation Color Tokens (Charcoal Value Ramp)."""
    # Surfaces & Depth Hierarchy
    SURFACE_LOWEST: str = "#0c0e12"     # Level 0 (Recessed canvas / Artboard backdrop)
    SURFACE: str = "#111317"            # Level 1 (Main application shell)
    SURFACE_DIM: str = "#111317"        # Dim background
    SURFACE_BRIGHT: str = "#37393e"     # Bright surface
    SURFACE_LOW: str = "#1a1c20"        # Level 1.5 (Docked drawers, sidebars, context ribbons)
    SURFACE_CONTAINER: str = "#1e2024"  # Level 2 (Inspector cards, tool wells, toolbar base)
    SURFACE_HIGH: str = "#282a2e"       # Level 2.5 (Hover states, elevated panels, active tabs)
    SURFACE_HIGHEST: str = "#333539"    # Level 3 (Active button selections, popovers, highlights)

    # Hairline Borders & Dividers (1px tactile precision)
    OUTLINE: str = "#8e909f"
    OUTLINE_VARIANT: str = "#383d47"
    BORDER_HAIRLINE: str = "#383d47"
    BORDER_SUBTLE: str = "#282a2e"

    # Primary Accent & Selection
    PRIMARY: str = "#b6c4ff"
    PRIMARY_CONTAINER: str = "#6c8cff"  # Core vibrant Studio Blue
    ON_PRIMARY: str = "#002780"
    ON_PRIMARY_CONTAINER: str = "#002376"

    # Secondary Muted Accents
    SECONDARY: str = "#c4c6d1"
    SECONDARY_CONTAINER: str = "#464952"
    ON_SECONDARY: str = "#2d3038"

    # Semantic Status Accents
    TERTIARY: str = "#6edba3"            # Success / Valid / Ready / Bleed Guideline
    TERTIARY_CONTAINER: str = "#34a673"
    ON_TERTIARY: str = "#003822"
    ON_TERTIARY_CONTAINER: str = "#00341f"

    WARNING: str = "#e8b65b"             # Warning / Overflow / Fallback Notice
    ERROR: str = "#ffb4ab"               # Error / Missing Photo
    ERROR_CONTAINER: str = "#93000a"
    ON_ERROR: str = "#690005"

    # Typography Tones
    ON_SURFACE: str = "#e2e2e8"          # Primary text / Labels / Metrics
    ON_SURFACE_VARIANT: str = "#c4c5d5"  # Secondary text / Inactive icons / Units
    TEXT_MUTED: str = "#8e909f"          # Muted hint text / Disabled tokens


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
TYPOGRAPHY = StudioTypography()

# Convenience top-level constants
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
TEXT_PRIMARY = COLORS.ON_SURFACE
TEXT_SECONDARY = COLORS.ON_SURFACE_VARIANT
TEXT_MUTED = COLORS.TEXT_MUTED

FONT_FAMILY_UI = TYPOGRAPHY.FONT_FAMILY_UI
FONT_FAMILY_MONO = TYPOGRAPHY.FONT_FAMILY_MONO
