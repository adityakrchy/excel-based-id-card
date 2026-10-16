//! Photoshop-style "New Document / Canvas" modal dialog.
//!
//! Provides presets (CR80 ID card, business card, visitor badge, A4, custom),
//! units (mm, cm, in, pixels), DPI (pixels/inch, pixels/cm), color modes (RGB, Grayscale, CMYK),
//! bit depths (8-bit, 16-bit, 32-bit), background colors/images, and orientation controls.

use std::collections::BTreeMap;

use eframe::egui::{self, Color32, RichText, Vec2};
use serde_json::json;

use crate::data::models::TemplateDefinition;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum CanvasUnit {
    Millimeters,
    Centimeters,
    Inches,
    Pixels,
}

impl CanvasUnit {
    pub fn label(self) -> &'static str {
        match self {
            Self::Millimeters => "Millimeters (mm)",
            Self::Centimeters => "Centimeters (cm)",
            Self::Inches => "Inches (in)",
            Self::Pixels => "Pixels (px)",
        }
    }

    pub fn short_code(self) -> &'static str {
        match self {
            Self::Millimeters => "mm",
            Self::Centimeters => "cm",
            Self::Inches => "in",
            Self::Pixels => "px",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum DpiUnit {
    PixelsPerInch,
    PixelsPerCentimeter,
}

impl DpiUnit {
    pub fn label(self) -> &'static str {
        match self {
            Self::PixelsPerInch => "Pixels / Inch (DPI)",
            Self::PixelsPerCentimeter => "Pixels / Centimeter (DPCM)",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum OrientationOption {
    Portrait,
    Landscape,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum ColorMode {
    Rgb,
    Grayscale,
    Cmyk,
}

impl ColorMode {
    pub fn label(self) -> &'static str {
        match self {
            Self::Rgb => "RGB Color",
            Self::Grayscale => "Grayscale",
            Self::Cmyk => "CMYK Color",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BitDepth {
    EightBit,
    SixteenBit,
    ThirtyTwoBit,
}

impl BitDepth {
    pub fn label(self) -> &'static str {
        match self {
            Self::EightBit => "8 bit",
            Self::SixteenBit => "16 bit",
            Self::ThirtyTwoBit => "32 bit",
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum BackgroundType {
    White,
    Black,
    CustomColor,
    Transparent,
    Image,
}

impl BackgroundType {
    pub fn label(self) -> &'static str {
        match self {
            Self::White => "White",
            Self::Black => "Black",
            Self::CustomColor => "Custom Color",
            Self::Transparent => "Transparent",
            Self::Image => "Background Image",
        }
    }
}

#[derive(Debug, Clone)]
pub struct CanvasPreset {
    pub name: &'static str,
    pub description: &'static str,
    pub width: f64,
    pub height: f64,
    pub unit: CanvasUnit,
    pub dpi: u32,
    pub orientation: OrientationOption,
}

pub const CANVAS_PRESETS: &[CanvasPreset] = &[
    CanvasPreset {
        name: "CR80 ID Card (Standard)",
        description: "Standard PVC badge: 85.60 × 53.98 mm @ 300 DPI",
        width: 85.60,
        height: 53.98,
        unit: CanvasUnit::Millimeters,
        dpi: 300,
        orientation: OrientationOption::Landscape,
    },
    CanvasPreset {
        name: "CR80 ID Card (Portrait)",
        description: "Vertical PVC badge: 53.98 × 85.60 mm @ 300 DPI",
        width: 53.98,
        height: 85.60,
        unit: CanvasUnit::Millimeters,
        dpi: 300,
        orientation: OrientationOption::Portrait,
    },
    CanvasPreset {
        name: "CR79 ID Card (Adhesive)",
        description: "Smaller sticky-back badge: 83.90 × 52.10 mm @ 300 DPI",
        width: 83.90,
        height: 52.10,
        unit: CanvasUnit::Millimeters,
        dpi: 300,
        orientation: OrientationOption::Landscape,
    },
    CanvasPreset {
        name: "Standard Visitor Badge",
        description: "Conferences & events: 4.0 × 3.0 in (101.6 × 76.2 mm)",
        width: 4.0,
        height: 3.0,
        unit: CanvasUnit::Inches,
        dpi: 300,
        orientation: OrientationOption::Landscape,
    },
    CanvasPreset {
        name: "Business Card",
        description: "US standard card: 3.5 × 2.0 in (88.9 × 50.8 mm)",
        width: 3.5,
        height: 2.0,
        unit: CanvasUnit::Inches,
        dpi: 300,
        orientation: OrientationOption::Landscape,
    },
    CanvasPreset {
        name: "A4 Document Sheet",
        description: "Printable sheet: 210 × 297 mm @ 300 DPI",
        width: 210.0,
        height: 297.0,
        unit: CanvasUnit::Millimeters,
        dpi: 300,
        orientation: OrientationOption::Portrait,
    },
    CanvasPreset {
        name: "Square 1000 × 1000",
        description: "Web / social media avatar: 1000 × 1000 px @ 72 DPI",
        width: 1000.0,
        height: 1000.0,
        unit: CanvasUnit::Pixels,
        dpi: 72,
        orientation: OrientationOption::Landscape,
    },
];

/// Transient state for the "New Document / Canvas" modal dialog.
#[derive(Debug, Clone)]
pub struct NewCanvasDialogState {
    pub is_open: bool,
    pub name: String,
    pub selected_preset: Option<usize>,
    pub unit: CanvasUnit,
    pub width: f64,
    pub height: f64,
    pub dpi: u32,
    pub dpi_unit: DpiUnit,
    pub orientation: OrientationOption,
    pub color_mode: ColorMode,
    pub bit_depth: BitDepth,
    pub background_type: BackgroundType,
    pub background_color: Color32,
    pub custom_hex: String,
    pub background_image_path: Option<String>,
    pub safe_area_margin_mm: f64,
}

impl Default for NewCanvasDialogState {
    fn default() -> Self {
        Self {
            is_open: false,
            name: "Untitled Canvas".into(),
            selected_preset: Some(0), // Default to CR80 Landscape
            unit: CanvasUnit::Millimeters,
            width: 85.60,
            height: 53.98,
            dpi: 300,
            dpi_unit: DpiUnit::PixelsPerInch,
            orientation: OrientationOption::Landscape,
            color_mode: ColorMode::Rgb,
            bit_depth: BitDepth::EightBit,
            background_type: BackgroundType::White,
            background_color: Color32::WHITE,
            custom_hex: "#FFFFFF".into(),
            background_image_path: None,
            safe_area_margin_mm: 3.0,
        }
    }
}

impl NewCanvasDialogState {
    pub fn open(&mut self) {
        self.is_open = true;
    }

    pub fn close(&mut self) {
        self.is_open = false;
    }

    pub fn apply_preset(&mut self, index: usize) {
        if let Some(preset) = CANVAS_PRESETS.get(index) {
            self.selected_preset = Some(index);
            self.name = preset.name.to_string();
            self.unit = preset.unit;
            self.width = preset.width;
            self.height = preset.height;
            self.dpi = preset.dpi;
            self.orientation = preset.orientation;
        }
    }

    /// Convert current width and height when user switches measurement unit.
    pub fn convert_unit(&mut self, new_unit: CanvasUnit) {
        if self.unit == new_unit {
            return;
        }
        let effective_dpi = match self.dpi_unit {
            DpiUnit::PixelsPerInch => self.dpi as f64,
            DpiUnit::PixelsPerCentimeter => (self.dpi as f64) * 2.54,
        };

        // Convert current (width, height) to inches first
        let (width_in_inches, height_in_inches) = match self.unit {
            CanvasUnit::Inches => (self.width, self.height),
            CanvasUnit::Millimeters => (self.width / 25.4, self.height / 25.4),
            CanvasUnit::Centimeters => (self.width / 2.54, self.height / 2.54),
            CanvasUnit::Pixels => (self.width / effective_dpi, self.height / effective_dpi),
        };

        // Convert inches to target unit
        let (new_w, new_h) = match new_unit {
            CanvasUnit::Inches => (width_in_inches, height_in_inches),
            CanvasUnit::Millimeters => (width_in_inches * 25.4, height_in_inches * 25.4),
            CanvasUnit::Centimeters => (width_in_inches * 2.54, height_in_inches * 2.54),
            CanvasUnit::Pixels => (
                (width_in_inches * effective_dpi).round(),
                (height_in_inches * effective_dpi).round(),
            ),
        };

        self.unit = new_unit;
        self.width = (new_w * 100.0).round() / 100.0;
        self.height = (new_h * 100.0).round() / 100.0;
    }

    /// Toggle or set orientation and flip width/height if needed.
    pub fn set_orientation(&mut self, orientation: OrientationOption) {
        if self.orientation == orientation {
            return;
        }
        self.orientation = orientation;
        match orientation {
            OrientationOption::Portrait => {
                if self.width > self.height {
                    std::mem::swap(&mut self.width, &mut self.height);
                }
            }
            OrientationOption::Landscape => {
                if self.height > self.width {
                    std::mem::swap(&mut self.width, &mut self.height);
                }
            }
        }
    }

    /// Compute pixel dimensions from unit, width, height, and DPI.
    pub fn compute_pixel_dimensions(&self) -> (u32, u32) {
        let effective_dpi = match self.dpi_unit {
            DpiUnit::PixelsPerInch => self.dpi as f64,
            DpiUnit::PixelsPerCentimeter => (self.dpi as f64) * 2.54,
        };

        let (w_px, h_px) = match self.unit {
            CanvasUnit::Pixels => (self.width.round() as u32, self.height.round() as u32),
            CanvasUnit::Inches => (
                (self.width * effective_dpi).round() as u32,
                (self.height * effective_dpi).round() as u32,
            ),
            CanvasUnit::Millimeters => (
                (self.width / 25.4 * effective_dpi).round() as u32,
                (self.height / 25.4 * effective_dpi).round() as u32,
            ),
            CanvasUnit::Centimeters => (
                (self.width / 2.54 * effective_dpi).round() as u32,
                (self.height / 2.54 * effective_dpi).round() as u32,
            ),
        };

        (w_px.max(10), h_px.max(10))
    }

    /// Build a complete TemplateDefinition from dialog settings.
    pub fn build_template(&self) -> TemplateDefinition {
        let (width_px, height_px) = self.compute_pixel_dimensions();

        let bg_color_hex = match self.background_type {
            BackgroundType::White => "#FFFFFF".to_string(),
            BackgroundType::Black => "#000000".to_string(),
            BackgroundType::Transparent => "#00000000".to_string(),
            BackgroundType::CustomColor => {
                format!(
                    "#{:02X}{:02X}{:02X}",
                    self.background_color.r(),
                    self.background_color.g(),
                    self.background_color.b()
                )
            }
            BackgroundType::Image => "#FFFFFF".to_string(),
        };

        let mut metadata = BTreeMap::new();
        metadata.insert(
            "color_mode".into(),
            json!(match self.color_mode {
                ColorMode::Rgb => "RGB",
                ColorMode::Grayscale => "Grayscale",
                ColorMode::Cmyk => "CMYK",
            }),
        );
        metadata.insert(
            "bit_depth".into(),
            json!(match self.bit_depth {
                BitDepth::EightBit => "8 bit",
                BitDepth::SixteenBit => "16 bit",
                BitDepth::ThirtyTwoBit => "32 bit",
            }),
        );
        metadata.insert(
            "dpi_unit".into(),
            json!(match self.dpi_unit {
                DpiUnit::PixelsPerInch => "Pixels/Inch",
                DpiUnit::PixelsPerCentimeter => "Pixels/Centimeter",
            }),
        );
        if let Some(preset_idx) = self.selected_preset {
            if let Some(p) = CANVAS_PRESETS.get(preset_idx) {
                metadata.insert("preset_name".into(), json!(p.name));
            }
        }

        TemplateDefinition {
            name: if self.name.trim().is_empty() {
                "Untitled Template".into()
            } else {
                self.name.trim().to_string()
            },
            width_px,
            height_px,
            dpi: self.dpi,
            unit: self.unit.short_code().to_string(),
            width_physical: Some(self.width),
            height_physical: Some(self.height),
            orientation: match self.orientation {
                OrientationOption::Portrait => "portrait".into(),
                OrientationOption::Landscape => "landscape".into(),
            },
            background_color: bg_color_hex,
            background_image_path: if self.background_type == BackgroundType::Image {
                self.background_image_path.clone()
            } else {
                None
            },
            safe_area_margin_mm: self.safe_area_margin_mm,
            elements: Vec::new(),
            metadata,
            ..Default::default()
        }
    }

    /// Render the modal window. Returns `Some(TemplateDefinition)` if user clicked "Create Canvas".
    pub fn show(&mut self, ctx: &egui::Context) -> Option<TemplateDefinition> {
        if !self.is_open {
            return None;
        }

        let mut created_template = None;
        let mut should_close = false;

        let modal_response = egui::Window::new("🖼 New Document / Blank Canvas")
            .id(egui::Id::new("photoshop_new_canvas_modal"))
            .collapsible(false)
            .resizable(false)
            .default_width(620.0)
            .anchor(egui::Align2::CENTER_CENTER, Vec2::ZERO)
            .show(ctx, |ui| {
                ui.add_space(4.0);

                ui.columns(2, |cols| {
                    // LEFT COLUMN: Presets List
                    let left_ui = &mut cols[0];
                    left_ui.group(|ui| {
                        ui.heading("Document Presets");
                        ui.label(
                            RichText::new("Choose a standard ID badge or custom format:")
                                .small()
                                .color(Color32::from_gray(160)),
                        );
                        ui.add_space(4.0);

                        egui::ScrollArea::vertical()
                            .max_height(340.0)
                            .show(ui, |ui| {
                                for (idx, preset) in CANVAS_PRESETS.iter().enumerate() {
                                    let is_selected = self.selected_preset == Some(idx);
                                    let resp = ui.selectable_label(
                                        is_selected,
                                        RichText::new(preset.name).strong(),
                                    );
                                    if resp.clicked() {
                                        self.apply_preset(idx);
                                    }
                                    ui.small(
                                        RichText::new(preset.description)
                                            .color(Color32::from_gray(140)),
                                    );
                                    ui.separator();
                                }
                            });
                    });

                    // RIGHT COLUMN: Detailed Parameters
                    let right_ui = &mut cols[1];
                    right_ui.group(|ui| {
                        ui.heading("Canvas Details");
                        ui.add_space(2.0);

                        // Document Name
                        ui.horizontal(|ui| {
                            ui.label("Name:");
                            ui.add(egui::TextEdit::singleline(&mut self.name).desired_width(170.0));
                        });

                        ui.separator();

                        // Measurement Unit
                        ui.horizontal(|ui| {
                            ui.label("Unit:");
                            let current_unit = self.unit;
                            egui::ComboBox::from_id_salt("canvas_unit_select")
                                .selected_text(current_unit.label())
                                .show_ui(ui, |ui| {
                                    for unit in [
                                        CanvasUnit::Millimeters,
                                        CanvasUnit::Centimeters,
                                        CanvasUnit::Inches,
                                        CanvasUnit::Pixels,
                                    ] {
                                        if ui
                                            .selectable_label(self.unit == unit, unit.label())
                                            .clicked()
                                        {
                                            self.convert_unit(unit);
                                        }
                                    }
                                });
                        });

                        // Width & Height
                        ui.horizontal(|ui| {
                            ui.label("Width:");
                            let w_resp = ui.add(
                                egui::DragValue::new(&mut self.width)
                                    .speed(0.1)
                                    .range(1.0..=10000.0),
                            );
                            if w_resp.changed() {
                                self.selected_preset = None;
                            }
                            ui.small(self.unit.short_code());

                            ui.add_space(8.0);
                            ui.label("Height:");
                            let h_resp = ui.add(
                                egui::DragValue::new(&mut self.height)
                                    .speed(0.1)
                                    .range(1.0..=10000.0),
                            );
                            if h_resp.changed() {
                                self.selected_preset = None;
                            }
                            ui.small(self.unit.short_code());
                        });

                        // Orientation
                        ui.horizontal(|ui| {
                            ui.label("Orientation:");
                            let is_portrait = self.orientation == OrientationOption::Portrait;
                            let is_landscape = self.orientation == OrientationOption::Landscape;

                            if ui
                                .selectable_label(is_portrait, "▯ Portrait")
                                .on_hover_text("Flip to vertical portrait orientation")
                                .clicked()
                            {
                                self.set_orientation(OrientationOption::Portrait);
                            }
                            if ui
                                .selectable_label(is_landscape, "▭ Landscape")
                                .on_hover_text("Flip to horizontal landscape orientation")
                                .clicked()
                            {
                                self.set_orientation(OrientationOption::Landscape);
                            }
                        });

                        ui.separator();

                        // Resolution / DPI
                        ui.horizontal(|ui| {
                            ui.label("Resolution:");
                            ui.add(egui::DragValue::new(&mut self.dpi).range(36..=2400));
                            egui::ComboBox::from_id_salt("dpi_unit_select")
                                .selected_text(self.dpi_unit.label())
                                .show_ui(ui, |ui| {
                                    ui.selectable_value(
                                        &mut self.dpi_unit,
                                        DpiUnit::PixelsPerInch,
                                        DpiUnit::PixelsPerInch.label(),
                                    );
                                    ui.selectable_value(
                                        &mut self.dpi_unit,
                                        DpiUnit::PixelsPerCentimeter,
                                        DpiUnit::PixelsPerCentimeter.label(),
                                    );
                                });
                        });

                        // DPI quick presets
                        ui.horizontal(|ui| {
                            ui.small("Quick DPI:");
                            for preset_dpi in [72, 150, 300, 600] {
                                if ui.small_button(format!("{preset_dpi}")).clicked() {
                                    self.dpi = preset_dpi;
                                }
                            }
                        });

                        ui.separator();

                        // Color Mode & Bit Depth
                        ui.horizontal(|ui| {
                            ui.label("Color Mode:");
                            egui::ComboBox::from_id_salt("color_mode_select")
                                .selected_text(self.color_mode.label())
                                .show_ui(ui, |ui| {
                                    ui.selectable_value(
                                        &mut self.color_mode,
                                        ColorMode::Rgb,
                                        "RGB Color",
                                    );
                                    ui.selectable_value(
                                        &mut self.color_mode,
                                        ColorMode::Grayscale,
                                        "Grayscale",
                                    );
                                    ui.selectable_value(
                                        &mut self.color_mode,
                                        ColorMode::Cmyk,
                                        "CMYK Color",
                                    );
                                });

                            egui::ComboBox::from_id_salt("bit_depth_select")
                                .selected_text(self.bit_depth.label())
                                .show_ui(ui, |ui| {
                                    ui.selectable_value(
                                        &mut self.bit_depth,
                                        BitDepth::EightBit,
                                        "8 bit",
                                    );
                                    ui.selectable_value(
                                        &mut self.bit_depth,
                                        BitDepth::SixteenBit,
                                        "16 bit",
                                    );
                                    ui.selectable_value(
                                        &mut self.bit_depth,
                                        BitDepth::ThirtyTwoBit,
                                        "32 bit",
                                    );
                                });
                        });

                        ui.separator();

                        // Background Contents
                        ui.horizontal(|ui| {
                            ui.label("Background:");
                            egui::ComboBox::from_id_salt("bg_type_select")
                                .selected_text(self.background_type.label())
                                .show_ui(ui, |ui| {
                                    ui.selectable_value(
                                        &mut self.background_type,
                                        BackgroundType::White,
                                        "White",
                                    );
                                    ui.selectable_value(
                                        &mut self.background_type,
                                        BackgroundType::Black,
                                        "Black",
                                    );
                                    ui.selectable_value(
                                        &mut self.background_type,
                                        BackgroundType::CustomColor,
                                        "Custom Color",
                                    );
                                    ui.selectable_value(
                                        &mut self.background_type,
                                        BackgroundType::Transparent,
                                        "Transparent",
                                    );
                                    ui.selectable_value(
                                        &mut self.background_type,
                                        BackgroundType::Image,
                                        "Background Image",
                                    );
                                });

                            if self.background_type == BackgroundType::CustomColor {
                                ui.color_edit_button_srgba(&mut self.background_color);
                            }
                        });

                        if self.background_type == BackgroundType::Image {
                            ui.horizontal(|ui| {
                                ui.label(
                                    self.background_image_path
                                        .as_deref()
                                        .unwrap_or("No image selected"),
                                );
                                if ui.small_button("Choose Image…").clicked() {
                                    if let Some(path) = rfd::FileDialog::new()
                                        .add_filter(
                                            "Image Files",
                                            &["png", "jpg", "jpeg", "webp", "bmp"],
                                        )
                                        .pick_file()
                                    {
                                        self.background_image_path =
                                            Some(path.display().to_string());
                                    }
                                }
                            });
                        }

                        // Safe Margin
                        ui.horizontal(|ui| {
                            ui.label("Safe Margin:");
                            ui.add(
                                egui::DragValue::new(&mut self.safe_area_margin_mm)
                                    .range(0.0..=50.0)
                                    .speed(0.5),
                            );
                            ui.small("mm (cut line tolerance)");
                        });
                    });
                });

                ui.add_space(8.0);
                ui.separator();

                // Live Resolution Summary
                let (w_px, h_px) = self.compute_pixel_dimensions();
                ui.horizontal(|ui| {
                    ui.strong(format!(
                        "⚡ Output Size: {} × {} pixels @ {} DPI · Mode: {} · {}",
                        w_px,
                        h_px,
                        self.dpi,
                        self.color_mode.label(),
                        self.bit_depth.label()
                    ));
                });

                ui.add_space(8.0);

                // Action Buttons
                ui.horizontal(|ui| {
                    if ui
                        .add(
                            egui::Button::new(
                                RichText::new("✓ Create Canvas")
                                    .strong()
                                    .color(Color32::WHITE),
                            )
                            .fill(Color32::from_rgb(37, 99, 235)),
                        )
                        .clicked()
                    {
                        created_template = Some(self.build_template());
                        should_close = true;
                    }

                    if ui.button("Cancel").clicked() {
                        should_close = true;
                    }
                });
            });

        if modal_response.is_none() || should_close {
            self.is_open = false;
        }

        created_template
    }
}
