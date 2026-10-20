"""ID Studio specialized UI component library."""

from id_card_generator.ui.components.controls import normalize_control_heights
from id_card_generator.ui.components.elided_label import ElidedLabel
from id_card_generator.ui.components.layout_blocks import (
    Divider,
    OverflowMenu,
    Section,
    StatLine,
)
from id_card_generator.ui.components.numeric_well import NumericWell
from id_card_generator.ui.components.page_scaffold import (
    EmptyState,
    InlineNotice,
    PageFooter,
    PageHeader,
)
from id_card_generator.ui.components.spec_list import SpecList
from id_card_generator.ui.components.status_pill import StatusPill
from id_card_generator.ui.components.studio_header_bar import StudioHeaderBar
from id_card_generator.ui.components.studio_nav_bar import StudioNavBar, StudioTab
from id_card_generator.ui.components.surface import StatTile, SurfaceCard
from id_card_generator.ui.components.template_gallery import TemplateGalleryDelegate

__all__ = [
    "Divider",
    "ElidedLabel",
    "EmptyState",
    "OverflowMenu",
    "EmptyState",
    "InlineNotice",
    "NumericWell",
    "PageFooter",
    "PageHeader",
    "StatTile",
    "Section",
    "SpecList",
    "StatLine",
    "StatusPill",
    "StudioHeaderBar",
    "StudioNavBar",
    "StudioTab",
    "SurfaceCard",
    "TemplateGalleryDelegate",
    "normalize_control_heights",
]
