//! Serde models matching the Python application's JSON field names.

use std::collections::BTreeMap;

use serde::{Deserialize, Serialize};
use serde_json::Value;
use uuid::Uuid;

pub const CURRENT_FORMAT_VERSION: &str = "1.0.0";

fn new_id() -> String {
    Uuid::new_v4().to_string()
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum MatchStatus {
    Matched,
    #[default]
    Missing,
    Ambiguous,
    Overridden,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq, Default)]
#[serde(rename_all = "snake_case")]
pub enum ReviewStatus {
    #[default]
    Pending,
    Approved,
    Rejected,
    Correction,
    Skipped,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum ImageFitMode {
    Cover,
    Contain,
    Stretch,
    Crop,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum MissingPhotoPolicy {
    #[serde(rename = "placeholder")]
    GenerateWithPlaceholder,
    #[serde(rename = "skip")]
    SkipRecord,
    #[serde(rename = "fail")]
    FailRecord,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "snake_case")]
pub enum TextOverflowPolicy {
    AutoShrink,
    Truncate,
    Wrap,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
pub enum OutputFormat {
    #[serde(rename = "PNG")]
    Png,
    #[serde(rename = "JPEG")]
    Jpeg,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Eq)]
#[serde(rename_all = "lowercase")]
pub enum ThemePreference {
    Black,
    White,
    System,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct SourceRecord {
    #[serde(default = "new_id")]
    pub record_id: String,
    pub row_index: usize,
    #[serde(default)]
    pub raw_pin: String,
    #[serde(default)]
    pub pin: String,
    #[serde(default)]
    pub data: BTreeMap<String, Value>,
    #[serde(default)]
    pub validation_errors: Vec<String>,
    #[serde(default)]
    pub validation_warnings: Vec<String>,
}

impl SourceRecord {
    pub fn is_valid(&self) -> bool {
        self.validation_errors.is_empty()
    }

    pub fn pin_or_raw(&self) -> &str {
        if self.pin.is_empty() {
            &self.raw_pin
        } else {
            &self.pin
        }
    }

    pub fn get_value(&self, column: &str) -> String {
        self.data
            .get(column)
            .and_then(|value| match value {
                Value::Null => None,
                Value::String(value) => Some(value.trim().to_owned()),
                value => Some(value.to_string()),
            })
            .unwrap_or_default()
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CanvasElementStyle {
    #[serde(default = "default_font_family")]
    pub font_family: String,
    #[serde(default = "default_font_size")]
    pub font_size: u32,
    #[serde(default)]
    pub font_bold: bool,
    #[serde(default)]
    pub font_italic: bool,
    #[serde(default = "default_font_color")]
    pub font_color: String,
    #[serde(default = "default_transparent")]
    pub background_color: String,
    #[serde(default = "default_transparent")]
    pub border_color: String,
    #[serde(default)]
    pub border_width: u32,
    #[serde(default)]
    pub border_radius: u32,
    #[serde(default = "default_left")]
    pub text_align: String,
    #[serde(default = "default_top")]
    pub vertical_align: String,
    #[serde(default = "default_line_spacing")]
    pub line_spacing: f32,
    #[serde(default = "default_true")]
    pub wrap: bool,
    #[serde(default = "default_overflow_policy")]
    pub overflow_policy: TextOverflowPolicy,
    #[serde(default = "default_fit_mode")]
    pub fit_mode: ImageFitMode,
    #[serde(default = "default_rect")]
    pub mask_shape: String,
    #[serde(default = "default_opacity")]
    pub opacity: f32,
    #[serde(default)]
    pub rotation: f32,
    #[serde(default)]
    pub lock_aspect_ratio: bool,
    #[serde(default = "default_min_font_size")]
    pub min_font_size: u32,
    #[serde(default = "default_max_font_size")]
    pub max_font_size: u32,
}

impl Default for CanvasElementStyle {
    fn default() -> Self {
        Self {
            font_family: default_font_family(),
            font_size: default_font_size(),
            font_bold: false,
            font_italic: false,
            font_color: default_font_color(),
            background_color: default_transparent(),
            border_color: default_transparent(),
            border_width: 0,
            border_radius: 0,
            text_align: default_left(),
            vertical_align: default_top(),
            line_spacing: default_line_spacing(),
            wrap: true,
            overflow_policy: default_overflow_policy(),
            fit_mode: default_fit_mode(),
            mask_shape: default_rect(),
            opacity: default_opacity(),
            rotation: 0.0,
            lock_aspect_ratio: false,
            min_font_size: default_min_font_size(),
            max_font_size: default_max_font_size(),
        }
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CanvasElement {
    #[serde(default = "new_id")]
    pub id: String,
    #[serde(default = "default_element_name")]
    pub name: String,
    #[serde(rename = "type", default = "default_element_type")]
    pub r#type: String,
    #[serde(default)]
    pub x: f64,
    #[serde(default)]
    pub y: f64,
    #[serde(default = "default_element_width")]
    pub width: f64,
    #[serde(default = "default_element_height")]
    pub height: f64,
    #[serde(default)]
    pub z_index: i32,
    #[serde(default = "default_true")]
    pub visible: bool,
    #[serde(default)]
    pub locked: bool,
    #[serde(default)]
    pub binding: Option<String>,
    #[serde(default)]
    pub static_content: Option<String>,
    #[serde(default)]
    pub style: CanvasElementStyle,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct TemplateDefinition {
    #[serde(default = "new_id")]
    pub id: String,
    #[serde(default = "default_template_name")]
    pub name: String,
    #[serde(default = "default_version")]
    pub version: String,
    #[serde(default)]
    pub description: String,
    #[serde(default = "default_width_px")]
    pub width_px: u32,
    #[serde(default = "default_height_px")]
    pub height_px: u32,
    #[serde(default = "default_dpi")]
    pub dpi: u32,
    #[serde(default = "default_unit")]
    pub unit: String,
    #[serde(default)]
    pub width_physical: Option<f64>,
    #[serde(default)]
    pub height_physical: Option<f64>,
    #[serde(default = "default_portrait")]
    pub orientation: String,
    #[serde(default = "default_background")]
    pub background_color: String,
    #[serde(default)]
    pub background_image_path: Option<String>,
    #[serde(default)]
    pub border_color: Option<String>,
    #[serde(default)]
    pub border_width: u32,
    #[serde(default = "default_safe_margin")]
    pub safe_area_margin_mm: f64,
    #[serde(default)]
    pub elements: Vec<CanvasElement>,
    #[serde(default)]
    pub metadata: BTreeMap<String, Value>,
}

impl Default for TemplateDefinition {
    fn default() -> Self {
        Self {
            id: new_id(),
            name: default_template_name(),
            version: default_version(),
            description: String::new(),
            width_px: default_width_px(),
            height_px: default_height_px(),
            dpi: default_dpi(),
            unit: default_unit(),
            width_physical: None,
            height_physical: None,
            orientation: default_portrait(),
            background_color: default_background(),
            background_image_path: None,
            border_color: None,
            border_width: 0,
            safe_area_margin_mm: default_safe_margin(),
            elements: Vec::new(),
            metadata: BTreeMap::new(),
        }
    }
}

impl TemplateDefinition {
    pub fn is_landscape(&self) -> bool {
        self.width_px >= self.height_px
    }

    pub fn get_element_by_id(&self, id: &str) -> Option<&CanvasElement> {
        self.elements.iter().find(|element| element.id == id)
    }
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct RenderSettings {
    #[serde(default = "default_dpi")]
    pub dpi: u32,
    #[serde(default = "default_output_format")]
    pub output_format: OutputFormat,
    #[serde(default = "default_jpeg_quality")]
    pub jpeg_quality: u8,
    #[serde(default = "default_missing_photo_policy")]
    pub missing_photo_policy: MissingPhotoPolicy,
    #[serde(default = "default_overflow_policy")]
    pub text_overflow_policy: TextOverflowPolicy,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ReviewRecord {
    pub record_id: String,
    pub pin: String,
    #[serde(default)]
    pub name: String,
    #[serde(default)]
    pub status: ReviewStatus,
    #[serde(default)]
    pub comments: Option<String>,
    #[serde(default)]
    pub rendered_image_path: Option<String>,
    #[serde(default)]
    pub last_reviewed_at: Option<String>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ExportConfiguration {
    pub output_dir: String,
    #[serde(default = "default_output_format")]
    pub format: OutputFormat,
    #[serde(default = "default_jpeg_quality")]
    pub jpeg_quality: u8,
    #[serde(default = "default_naming_pattern")]
    pub naming_pattern: String,
    #[serde(default = "default_true")]
    pub approved_only: bool,
    #[serde(default = "default_true")]
    pub export_manifest: bool,
    #[serde(default)]
    pub export_contact_sheet: bool,
    #[serde(default)]
    pub open_output_dir_on_complete: bool,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq, Default)]
pub struct ExportResult {
    #[serde(default)]
    pub total_records: usize,
    #[serde(default)]
    pub exported_count: usize,
    #[serde(default)]
    pub skipped_count: usize,
    #[serde(default)]
    pub failed_count: usize,
    #[serde(default)]
    pub manifest_path: Option<String>,
    #[serde(default)]
    pub contact_sheet_path: Option<String>,
    #[serde(default)]
    pub exported_files: Vec<String>,
    #[serde(default)]
    pub errors: Vec<BTreeMap<String, String>>,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PhotoMatchResult {
    pub pin: String,
    #[serde(default)]
    pub key_value: Option<String>,
    #[serde(default)]
    pub record_id: Option<String>,
    #[serde(default = "default_missing_status")]
    pub status: MatchStatus,
    #[serde(default)]
    pub photo_path: Option<String>,
    #[serde(default)]
    pub candidate_paths: Vec<String>,
    #[serde(default)]
    pub is_overridden: bool,
    #[serde(default)]
    pub details: String,
}

#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct ProjectConfiguration {
    #[serde(default = "default_project_name")]
    pub project_name: String,
    #[serde(default = "default_version")]
    pub version: String,
    #[serde(default)]
    pub excel_file_path: Option<String>,
    #[serde(default)]
    pub sheet_name: Option<String>,
    #[serde(default)]
    pub header_row: usize,
    #[serde(default)]
    pub photo_dir_path: Option<String>,
    #[serde(default)]
    pub photo_key_column: Option<String>,
    #[serde(default)]
    pub photo_prefix: String,
    #[serde(default)]
    pub photo_suffix: String,
    #[serde(default = "default_theme")]
    pub theme: String,
    #[serde(default)]
    pub template: Option<TemplateDefinition>,
    #[serde(default)]
    pub column_mappings: BTreeMap<String, String>,
    #[serde(default)]
    pub photo_overrides: BTreeMap<String, String>,
    #[serde(default = "default_missing_photo_policy")]
    pub missing_photo_policy: MissingPhotoPolicy,
    #[serde(default)]
    pub review_states: BTreeMap<String, ReviewStatus>,
    #[serde(default)]
    pub review_comments: BTreeMap<String, String>,
    #[serde(default)]
    pub last_export_dir: Option<String>,
    #[serde(default = "default_output_format")]
    pub export_format: OutputFormat,
    #[serde(default = "default_jpeg_quality")]
    pub export_jpeg_quality: u8,
    #[serde(default = "default_naming_pattern")]
    pub export_naming_pattern: String,
    #[serde(default = "default_true")]
    pub export_approved_only: bool,
    #[serde(default = "default_true")]
    pub export_manifest: bool,
    #[serde(default)]
    pub export_contact_sheet: bool,
    #[serde(default)]
    pub open_output_dir_on_export: bool,
}

impl Default for ProjectConfiguration {
    fn default() -> Self {
        Self {
            project_name: default_project_name(),
            version: default_version(),
            excel_file_path: None,
            sheet_name: None,
            header_row: 0,
            photo_dir_path: None,
            photo_key_column: None,
            photo_prefix: String::new(),
            photo_suffix: String::new(),
            theme: default_theme(),
            template: None,
            column_mappings: BTreeMap::new(),
            photo_overrides: BTreeMap::new(),
            missing_photo_policy: default_missing_photo_policy(),
            review_states: BTreeMap::new(),
            review_comments: BTreeMap::new(),
            last_export_dir: None,
            export_format: default_output_format(),
            export_jpeg_quality: default_jpeg_quality(),
            export_naming_pattern: default_naming_pattern(),
            export_approved_only: true,
            export_manifest: true,
            export_contact_sheet: false,
            open_output_dir_on_export: false,
        }
    }
}

fn default_font_family() -> String {
    "Arial".into()
}
fn default_font_size() -> u32 {
    24
}
fn default_font_color() -> String {
    "#1A1A1A".into()
}
fn default_transparent() -> String {
    "transparent".into()
}
fn default_left() -> String {
    "left".into()
}
fn default_top() -> String {
    "top".into()
}
fn default_line_spacing() -> f32 {
    1.2
}
fn default_true() -> bool {
    true
}
fn default_overflow_policy() -> TextOverflowPolicy {
    TextOverflowPolicy::AutoShrink
}
fn default_fit_mode() -> ImageFitMode {
    ImageFitMode::Cover
}
fn default_rect() -> String {
    "rect".into()
}
fn default_opacity() -> f32 {
    1.0
}
fn default_min_font_size() -> u32 {
    8
}
fn default_max_font_size() -> u32 {
    72
}
fn default_element_name() -> String {
    "Element".into()
}
fn default_element_type() -> String {
    "dynamic_text".into()
}
fn default_element_width() -> f64 {
    200.0
}
fn default_element_height() -> f64 {
    50.0
}
fn default_template_name() -> String {
    "Custom Template".into()
}
fn default_version() -> String {
    CURRENT_FORMAT_VERSION.into()
}
fn default_width_px() -> u32 {
    638
}
fn default_height_px() -> u32 {
    1012
}
fn default_dpi() -> u32 {
    300
}
fn default_unit() -> String {
    "mm".into()
}
fn default_portrait() -> String {
    "portrait".into()
}
fn default_background() -> String {
    "#FFFFFF".into()
}
fn default_safe_margin() -> f64 {
    3.0
}
fn default_output_format() -> OutputFormat {
    OutputFormat::Png
}
fn default_jpeg_quality() -> u8 {
    95
}
fn default_missing_photo_policy() -> MissingPhotoPolicy {
    MissingPhotoPolicy::GenerateWithPlaceholder
}
fn default_naming_pattern() -> String {
    "{PIN_NUMBER}_{NAME}".into()
}
fn default_missing_status() -> MatchStatus {
    MatchStatus::Missing
}
fn default_project_name() -> String {
    "Untitled Project".into()
}
fn default_theme() -> String {
    "system".into()
}
