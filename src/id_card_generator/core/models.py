"""Domain data models and schemas using Pydantic."""

from pathlib import Path
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field
import uuid

from id_card_generator.core.constants import (
    CR80_WIDTH_PX,
    CR80_HEIGHT_PX,
    DEFAULT_DPI,
    DEFAULT_FONT_SIZE_PT,
    MatchStatus,
    ReviewStatus,
    ImageFitMode,
    MissingPhotoPolicy,
    TextOverflowPolicy,
    OutputFormat,
)


class SourceRecord(BaseModel):
    """Represents a single imported row from Excel/CSV."""
    record_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    row_index: int
    raw_pin: str
    pin: str
    data: Dict[str, Any] = Field(default_factory=dict)
    validation_errors: List[str] = Field(default_factory=list)
    validation_warnings: List[str] = Field(default_factory=list)

    @property
    def is_valid(self) -> bool:
        return len(self.validation_errors) == 0

    def get_value(self, column: str, default: str = "") -> str:
        """Safely fetch string value for a column."""
        val = self.data.get(column)
        if val is None or (isinstance(val, float) and val != val):  # check NaN
            return default
        return str(val).strip()


class PhotoMatchResult(BaseModel):
    """Result of matching a photograph for a record."""
    pin: str
    key_value: Optional[str] = None
    record_id: Optional[str] = None
    status: MatchStatus = MatchStatus.MISSING
    photo_path: Optional[str] = None
    matched_filename: Optional[str] = None
    candidate_paths: List[str] = Field(default_factory=list)
    is_overridden: bool = False
    details: str = ""


class CanvasElementStyle(BaseModel):
    """Style attributes for a canvas/template element."""
    font_family: str = "Arial"
    font_size: float = DEFAULT_FONT_SIZE_PT  # Typographic font size in points (pt), default 10 pt
    font_bold: bool = False
    font_italic: bool = False
    font_color: str = "#1A1A1A"
    background_color: str = "transparent"
    border_color: str = "transparent"
    border_width: int = 0
    border_radius: int = 0
    text_align: str = "left"  # left, center, right
    vertical_align: str = "top"  # top, middle, bottom
    line_spacing: float = 1.2
    wrap: bool = True
    overflow_policy: TextOverflowPolicy = TextOverflowPolicy.AUTO_SHRINK
    fit_mode: ImageFitMode = ImageFitMode.COVER
    mask_shape: str = "rect"  # rect, circle, rounded
    opacity: float = 1.0


class CanvasElement(BaseModel):
    """An element placed on the ID card canvas."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Element"
    type: str = "dynamic_text"  # dynamic_text, static_text, photo, pin_field, rect, round_rect, line, image
    x: float = 0.0
    y: float = 0.0
    width: float = 200.0
    height: float = 50.0
    z_index: int = 0
    visible: bool = True
    locked: bool = False
    # Which face of the card the element belongs to ("front" or "back").
    side: str = "front"
    binding: Optional[str] = None  # Excel column name, or special: 'photo', 'pin'
    static_content: Optional[str] = None  # Text or asset path for static elements
    style: CanvasElementStyle = Field(default_factory=CanvasElementStyle)


class TemplateDefinition(BaseModel):
    """Complete specification of an ID card template."""
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Custom Template"
    version: str = "1.0.0"
    description: str = ""
    width_px: int = CR80_WIDTH_PX
    height_px: int = CR80_HEIGHT_PX
    dpi: int = DEFAULT_DPI
    unit: str = "mm"
    width_physical: Optional[float] = None
    height_physical: Optional[float] = None
    orientation: str = "portrait"
    background_color: str = "#FFFFFF"
    background_image_path: Optional[str] = None
    elements: List[CanvasElement] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

    @property
    def is_landscape(self) -> bool:
        return self.width_px >= self.height_px

    def get_element_by_id(self, elem_id: str) -> Optional[CanvasElement]:
        for el in self.elements:
            if el.id == elem_id:
                return el
        return None


class RenderSettings(BaseModel):
    """Configuration for rendering engine."""
    dpi: int = DEFAULT_DPI
    output_format: OutputFormat = OutputFormat.PNG
    jpeg_quality: int = 95
    missing_photo_policy: MissingPhotoPolicy = MissingPhotoPolicy.GENERATE_WITH_PLACEHOLDER
    text_overflow_policy: TextOverflowPolicy = TextOverflowPolicy.AUTO_SHRINK


class RenderResult(BaseModel):
    """Output of rendering an individual ID card."""
    record_id: str
    pin: str
    success: bool
    image_path: Optional[str] = None
    warnings: List[str] = Field(default_factory=list)
    error_message: Optional[str] = None


class ReviewRecord(BaseModel):
    """State of an individual record during sequential review."""
    record_id: str
    pin: str
    name: str = ""
    status: ReviewStatus = ReviewStatus.PENDING
    comments: Optional[str] = None
    rendered_image_path: Optional[str] = None
    last_reviewed_at: Optional[str] = None


class ExportConfiguration(BaseModel):
    """Export parameters chosen by user.

    The export always writes one file per card.  The printable contact sheet
    is an optional extra.
    """
    output_dir: str
    format: OutputFormat = OutputFormat.PNG
    jpeg_quality: int = 95
    naming_pattern: str = "{PIN_NUMBER}_{NAME}"
    approved_only: bool = True
    export_manifest: bool = True
    export_contact_sheet: bool = False
    # Layout of the optional printable contact sheet
    sheet_columns: int = 2
    sheet_rows: int = 3
    sheet_margin_mm: float = 12.7


class ExportResult(BaseModel):
    """Summary of batch export operation."""
    total_records: int = 0
    exported_count: int = 0
    skipped_count: int = 0
    failed_count: int = 0
    manifest_path: Optional[str] = None
    contact_sheet_path: Optional[str] = None
    exported_files: List[str] = Field(default_factory=list)
    errors: List[Dict[str, str]] = Field(default_factory=list)


class ProjectConfiguration(BaseModel):
    """Serializable application project file model."""
    project_name: str = "Untitled Project"
    version: str = "1.0.0"
    workspace_dir: Optional[str] = None
    excel_file_path: Optional[str] = None
    sheet_name: Optional[str] = None
    header_row: int = 0
    photo_dir_path: Optional[str] = None
    photo_key_column: Optional[str] = None
    photo_prefix: str = ""
    photo_suffix: str = ""
    theme: str = "system"
    template: Optional[TemplateDefinition] = None
    column_mappings: Dict[str, str] = Field(default_factory=dict)  # element_id -> column_name
    photo_overrides: Dict[str, str] = Field(default_factory=dict)  # record_id or key -> photo_path
    missing_photo_policy: MissingPhotoPolicy = MissingPhotoPolicy.GENERATE_WITH_PLACEHOLDER
    review_states: Dict[str, ReviewStatus] = Field(default_factory=dict)  # record_id -> ReviewStatus
    last_export_dir: Optional[str] = None

    @property
    def workspace_path(self) -> Optional[Path]:
        return Path(self.workspace_dir).resolve() if self.workspace_dir else None

    @property
    def data_dir(self) -> Optional[Path]:
        return (Path(self.workspace_dir) / "data").resolve() if self.workspace_dir else None

    @property
    def photos_dir(self) -> Optional[Path]:
        return (Path(self.workspace_dir) / "photos").resolve() if self.workspace_dir else None

    @property
    def exports_dir(self) -> Optional[Path]:
        return (Path(self.workspace_dir) / "exports").resolve() if self.workspace_dir else None

    @property
    def project_file_path(self) -> Optional[Path]:
        return (Path(self.workspace_dir) / "project.json").resolve() if self.workspace_dir else None
