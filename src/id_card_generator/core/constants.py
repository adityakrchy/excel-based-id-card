"""Application-wide constants and enumerations."""

from enum import Enum
from pathlib import Path

APP_NAME = "Excel ID Card Generator"
APP_SLUG = "excel-id-card-generator"
APP_ORG = "CardForge"
APP_VERSION = "1.0.5"

# File extensions
SUPPORTED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp", ".tiff", ".tif"}
SUPPORTED_EXCEL_EXTENSIONS = {".xlsx", ".xls", ".csv"}

# Default DPI & standard card sizes in pixels (at 300 DPI)
# CR80 standard credit/ID card: 85.60 mm x 53.98 mm (approx 3.370" x 2.125") -> 1011 x 638 px (landscape) or 638 x 1011 px (portrait)
DEFAULT_DPI = 300
DEFAULT_FONT_SIZE_PT = 10.0
CR80_WIDTH_PX = 638
CR80_HEIGHT_PX = 1012

# Standard columns expected in typical Excel files (not mandatory, used for suggestions)
STANDARD_COLUMNS = [
    "PIN Number",
    "Name",
    "Office Name",
    "Designation",
    "Constituency",
    "Source PDF",
    "Page",
]


class WorkflowStep(str, Enum):
    """Guided workflow steps."""
    DASHBOARD = "dashboard"
    DATA_SOURCE = "data_source"
    PHOTOS = "photos"
    TEMPLATES = "templates"
    CANVAS_EDITOR = "canvas_editor"
    GENERATE = "generate"
    REVIEW = "review"
    EXPORT = "export"
    SETTINGS = "settings"


class MatchStatus(str, Enum):
    """Photo matching statuses."""
    MATCHED = "matched"
    MISSING = "missing"
    AMBIGUOUS = "ambiguous"
    OVERRIDDEN = "overridden"


class ReviewStatus(str, Enum):
    """Card review approval statuses."""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    CORRECTION = "correction"
    SKIPPED = "skipped"


class ImageFitMode(str, Enum):
    """Fit mode for images rendered on card."""
    COVER = "cover"
    CONTAIN = "contain"
    STRETCH = "stretch"
    CROP = "crop"


class MissingPhotoPolicy(str, Enum):
    """Policy when generating cards without matched photo."""
    GENERATE_WITH_PLACEHOLDER = "placeholder"
    SKIP_RECORD = "skip"
    FAIL_RECORD = "fail"


class TextOverflowPolicy(str, Enum):
    """Policy for text overflow."""
    CLIP = "clip"          # Render at full pt size, clip to box (default)
    AUTO_SHRINK = "auto_shrink"
    TRUNCATE = "truncate"
    WRAP = "wrap"


class OutputFormat(str, Enum):
    """Export output format."""
    PNG = "PNG"
    JPEG = "JPEG"
