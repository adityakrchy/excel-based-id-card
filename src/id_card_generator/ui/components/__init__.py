"""ID Studio specialized UI component library."""

from id_card_generator.ui.components.numeric_well import NumericWell
from id_card_generator.ui.components.page_scaffold import (
    EmptyState,
    InlineNotice,
    PageFooter,
    PageHeader,
)
from id_card_generator.ui.components.status_pill import StatusPill
from id_card_generator.ui.components.studio_header_bar import StudioHeaderBar
from id_card_generator.ui.components.studio_nav_bar import StudioNavBar, StudioTab
from id_card_generator.ui.components.surface import StatTile, SurfaceCard

__all__ = [
    "EmptyState",
    "InlineNotice",
    "NumericWell",
    "PageFooter",
    "PageHeader",
    "StatTile",
    "StatusPill",
    "StudioHeaderBar",
    "StudioNavBar",
    "StudioTab",
    "SurfaceCard",
]
