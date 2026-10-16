//! Photoshop-inspired template editor widget with interactive rulers, floating HUD,
//! docking panels (Properties, Layers, Swatches, History, Align), and command-based undo/redo.

use eframe::egui::{
    self, Align2, Color32, FontId, Id, PointerButton, Pos2, Rect, Response, Sense, Stroke, Ui, Vec2,
};
use uuid::Uuid;

use crate::data::models::{CanvasElement, CanvasElementStyle, TemplateDefinition};

const MIN_ZOOM: f32 = 0.1;
const MAX_ZOOM: f32 = 4.0;
const RULER_THICKNESS: f32 = 22.0;

/// Curated 24-color ID badge palette inspired by professional badge design systems.
pub const SWATCHES: &[(&str, &str)] = &[
    ("#0F172A", "Deep Midnight"),
    ("#1E293B", "Slate 800"),
    ("#1E3A8A", "Navy Blue"),
    ("#1D4ED8", "Royal Blue"),
    ("#2563EB", "Corporate Blue"),
    ("#0284C7", "Sky Blue"),
    ("#06B6D4", "Cyan Accent"),
    ("#0D9488", "Teal"),
    ("#064E3B", "Dark Emerald"),
    ("#059669", "Emerald Green"),
    ("#10B981", "Bright Green"),
    ("#84CC16", "Lime"),
    ("#78350F", "Bronze"),
    ("#B45309", "Dark Amber"),
    ("#D97706", "Amber Gold"),
    ("#F59E0B", "Warning Yellow"),
    ("#DC2626", "Crimson Red"),
    ("#BE123C", "Ruby Accent"),
    ("#E11D48", "Rose"),
    ("#7C3AED", "Purple"),
    ("#000000", "Pitch Black"),
    ("#475569", "Slate Gray"),
    ("#94A3B8", "Silver"),
    ("#FFFFFF", "Pure White"),
];

/// A scene-to-screen transform for the template canvas.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct CanvasTransform {
    pub origin: Pos2,
    pub scale: f32,
}

impl CanvasTransform {
    /// Fit the whole template into `view`, preserving its aspect ratio.
    pub fn fit(view: Rect, template: &TemplateDefinition, zoom: f32, pan: Vec2) -> Self {
        let width = template.width_px.max(1) as f32;
        let height = template.height_px.max(1) as f32;
        let scale =
            (view.width() / width).min(view.height() / height) * zoom.clamp(MIN_ZOOM, MAX_ZOOM);
        let size = Vec2::new(width * scale, height * scale);
        Self {
            origin: view.center() - size / 2.0 + pan,
            scale,
        }
    }

    pub fn scene_to_screen(self, point: Pos2) -> Pos2 {
        self.origin + point.to_vec2() * self.scale
    }

    pub fn screen_to_scene(self, point: Pos2) -> Pos2 {
        let value = (point - self.origin) / self.scale.max(f32::EPSILON);
        Pos2::new(value.x, value.y)
    }

    pub fn scene_rect(self, template: &TemplateDefinition) -> Rect {
        Rect::from_min_size(
            self.origin,
            Vec2::new(
                template.width_px as f32 * self.scale,
                template.height_px as f32 * self.scale,
            ),
        )
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum AlignmentType {
    Left,
    CenterHorizontal,
    Right,
    Top,
    CenterVertical,
    Bottom,
    CenterOnCard,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SwatchTarget {
    Fill,
    Font,
    Border,
    Background,
}

/// Commands are intentionally independent of egui so they can be used by a
/// host application's keyboard shortcuts or command palette as well.
#[derive(Debug, Clone, PartialEq)]
#[allow(clippy::large_enum_variant)]
pub enum EditorCommand {
    Add(CanvasElement),
    Delete {
        id: String,
    },
    Duplicate {
        id: String,
    },
    Move {
        id: String,
        delta: Vec2,
    },
    SetVisibility {
        id: String,
        visible: bool,
    },
    SetLocked {
        id: String,
        locked: bool,
    },
    Raise {
        id: String,
    },
    Lower {
        id: String,
    },
    BringToFront {
        id: String,
    },
    SendToBack {
        id: String,
    },
    Align {
        id: String,
        alignment: AlignmentType,
    },
    UpdateColor {
        id: String,
        target: SwatchTarget,
        color: String,
    },
}

impl EditorCommand {
    pub fn description(&self) -> String {
        match self {
            Self::Add(elem) => format!("Add {}", elem.name),
            Self::Delete { .. } => "Delete element".into(),
            Self::Duplicate { .. } => "Duplicate element".into(),
            Self::Move { .. } => "Move element".into(),
            Self::SetVisibility { visible, .. } => if *visible {
                "Show element"
            } else {
                "Hide element"
            }
            .into(),
            Self::SetLocked { locked, .. } => if *locked {
                "Lock element"
            } else {
                "Unlock element"
            }
            .into(),
            Self::Raise { .. } => "Bring forward".into(),
            Self::Lower { .. } => "Send backward".into(),
            Self::BringToFront { .. } => "Bring to front".into(),
            Self::SendToBack { .. } => "Send to back".into(),
            Self::Align { alignment, .. } => format!("Align {:?}", alignment),
            Self::UpdateColor { target, .. } => format!("Set {:?} color", target),
        }
    }
}

/// Snapshot history for template edits with action stack names for the Photoshop History panel.
#[derive(Debug, Clone, Default)]
pub struct EditorHistory {
    pub undo: Vec<TemplateDefinition>,
    pub redo: Vec<TemplateDefinition>,
    pub action_names: Vec<String>,
}

impl EditorHistory {
    pub fn execute(&mut self, template: &mut TemplateDefinition, command: EditorCommand) -> bool {
        let before = template.clone();
        let desc = command.description();
        if !apply_command(template, command) || *template == before {
            return false;
        }
        self.undo.push(before);
        self.action_names.push(desc);
        self.redo.clear();
        true
    }

    /// Record a direct property edit whose mutation has already been applied.
    pub fn record_change(&mut self, before: TemplateDefinition, after: &TemplateDefinition) {
        if before != *after {
            self.undo.push(before);
            self.action_names.push("Edit properties".into());
            self.redo.clear();
        }
    }

    pub fn undo(&mut self, template: &mut TemplateDefinition) -> bool {
        let Some(snapshot) = self.undo.pop() else {
            return false;
        };
        self.redo.push(template.clone());
        *template = snapshot;
        true
    }

    pub fn redo(&mut self, template: &mut TemplateDefinition) -> bool {
        let Some(snapshot) = self.redo.pop() else {
            return false;
        };
        self.undo.push(template.clone());
        *template = snapshot;
        true
    }

    pub fn can_undo(&self) -> bool {
        !self.undo.is_empty()
    }

    pub fn can_redo(&self) -> bool {
        !self.redo.is_empty()
    }
}

fn apply_command(template: &mut TemplateDefinition, command: EditorCommand) -> bool {
    match command {
        EditorCommand::Add(mut element) => {
            if template.get_element_by_id(&element.id).is_some() {
                element.id = Uuid::new_v4().to_string();
            }
            template.elements.push(element);
            true
        }
        EditorCommand::Delete { id } => remove_element(template, &id),
        EditorCommand::Duplicate { id } => {
            let Some(mut copy) = template.get_element_by_id(&id).cloned() else {
                return false;
            };
            copy.id = Uuid::new_v4().to_string();
            copy.name = format!("{} copy", copy.name);
            copy.x += 20.0;
            copy.y += 20.0;
            template.elements.push(copy);
            true
        }
        EditorCommand::Move { id, delta } => {
            let Some(element) = template
                .elements
                .iter_mut()
                .find(|element| element.id == id && !element.locked)
            else {
                return false;
            };
            element.x += f64::from(delta.x);
            element.y += f64::from(delta.y);
            true
        }
        EditorCommand::SetVisibility { id, visible } => {
            let Some(element) = template
                .elements
                .iter_mut()
                .find(|element| element.id == id)
            else {
                return false;
            };
            if element.visible == visible {
                return false;
            }
            element.visible = visible;
            true
        }
        EditorCommand::SetLocked { id, locked } => {
            let Some(element) = template
                .elements
                .iter_mut()
                .find(|element| element.id == id)
            else {
                return false;
            };
            if element.locked == locked {
                return false;
            }
            element.locked = locked;
            true
        }
        EditorCommand::Raise { id } => shift_z(template, &id, 1),
        EditorCommand::Lower { id } => shift_z(template, &id, -1),
        EditorCommand::BringToFront { id } => set_extreme_z(template, &id, true),
        EditorCommand::SendToBack { id } => set_extreme_z(template, &id, false),
        EditorCommand::Align { id, alignment } => align_element(template, &id, alignment),
        EditorCommand::UpdateColor { id, target, color } => {
            update_element_color(template, &id, target, &color)
        }
    }
}

fn align_element(template: &mut TemplateDefinition, id: &str, alignment: AlignmentType) -> bool {
    let t_w = template.width_px as f64;
    let t_h = template.height_px as f64;
    let Some(elem) = template
        .elements
        .iter_mut()
        .find(|e| e.id == id && !e.locked)
    else {
        return false;
    };
    match alignment {
        AlignmentType::Left => elem.x = 0.0,
        AlignmentType::CenterHorizontal => elem.x = ((t_w - elem.width) / 2.0).max(0.0),
        AlignmentType::Right => elem.x = (t_w - elem.width).max(0.0),
        AlignmentType::Top => elem.y = 0.0,
        AlignmentType::CenterVertical => elem.y = ((t_h - elem.height) / 2.0).max(0.0),
        AlignmentType::Bottom => elem.y = (t_h - elem.height).max(0.0),
        AlignmentType::CenterOnCard => {
            elem.x = ((t_w - elem.width) / 2.0).max(0.0);
            elem.y = ((t_h - elem.height) / 2.0).max(0.0);
        }
    }
    true
}

fn update_element_color(
    template: &mut TemplateDefinition,
    id: &str,
    target: SwatchTarget,
    color: &str,
) -> bool {
    if target == SwatchTarget::Background {
        template.background_color = color.to_owned();
        return true;
    }
    let Some(elem) = template
        .elements
        .iter_mut()
        .find(|e| e.id == id && !e.locked)
    else {
        return false;
    };
    match target {
        SwatchTarget::Fill => elem.style.background_color = color.to_owned(),
        SwatchTarget::Font => elem.style.font_color = color.to_owned(),
        SwatchTarget::Border => elem.style.border_color = color.to_owned(),
        SwatchTarget::Background => {}
    }
    true
}

fn remove_element(template: &mut TemplateDefinition, id: &str) -> bool {
    let before = template.elements.len();
    template.elements.retain(|element| element.id != id);
    template.elements.len() != before
}

fn shift_z(template: &mut TemplateDefinition, id: &str, delta: i32) -> bool {
    let Some(element) = template
        .elements
        .iter_mut()
        .find(|element| element.id == id)
    else {
        return false;
    };
    let old = element.z_index;
    element.z_index = element.z_index.saturating_add(delta);
    old != element.z_index
}

fn set_extreme_z(template: &mut TemplateDefinition, id: &str, front: bool) -> bool {
    let target = if front {
        template
            .elements
            .iter()
            .map(|element| element.z_index)
            .max()
            .unwrap_or(0)
            + 1
    } else {
        template
            .elements
            .iter()
            .map(|element| element.z_index)
            .min()
            .unwrap_or(0)
            - 1
    };
    let Some(element) = template
        .elements
        .iter_mut()
        .find(|element| element.id == id)
    else {
        return false;
    };
    if element.z_index == target {
        return false;
    }
    element.z_index = target;
    true
}

#[derive(Debug, Clone)]
struct DragState {
    id: String,
    last_delta: Vec2,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum EditorTab {
    Properties,
    Layers,
    Swatches,
    History,
    Align,
}

/// Transient state for [`TemplateEditor`].
#[derive(Debug, Clone)]
pub struct TemplateEditorState {
    pub zoom: f32,
    pub pan: Vec2,
    pub selected_id: Option<String>,
    pub show_grid: bool,
    pub show_safe_area: bool,
    pub show_rulers: bool,
    pub ruler_unit: String,
    pub show_crosshairs: bool,
    pub snap_to_grid: bool,
    pub active_tab: EditorTab,
    pub swatch_target: SwatchTarget,
    pub custom_hex_color: String,
    pub cursor_scene_pos: Option<Pos2>,
    pub history: EditorHistory,
    drag: Option<DragState>,
}

impl Default for TemplateEditorState {
    fn default() -> Self {
        Self {
            zoom: 1.0,
            pan: Vec2::ZERO,
            selected_id: None,
            show_grid: true,
            show_safe_area: true,
            show_rulers: true,
            ruler_unit: "px".into(),
            show_crosshairs: true,
            snap_to_grid: true,
            active_tab: EditorTab::Properties,
            swatch_target: SwatchTarget::Fill,
            custom_hex_color: "#2563EB".into(),
            cursor_scene_pos: None,
            history: EditorHistory::default(),
            drag: None,
        }
    }
}

impl TemplateEditorState {
    pub fn execute(&mut self, template: &mut TemplateDefinition, command: EditorCommand) -> bool {
        self.history.execute(template, command)
    }

    pub fn undo(&mut self, template: &mut TemplateDefinition) -> bool {
        let changed = self.history.undo(template);
        if changed
            && self
                .selected_id
                .as_ref()
                .is_some_and(|id| template.get_element_by_id(id).is_none())
        {
            self.selected_id = None;
        }
        changed
    }

    pub fn redo(&mut self, template: &mut TemplateDefinition) -> bool {
        self.history.redo(template)
    }

    pub fn fit_canvas(&mut self) {
        self.zoom = 1.0;
        self.pan = Vec2::ZERO;
    }
}

/// Native template editor with Photoshop-inspired rulers, dock panels, and HUD.
pub struct TemplateEditor<'a> {
    pub template: &'a mut TemplateDefinition,
    pub state: &'a mut TemplateEditorState,
    pub available_columns: &'a [String],
    pub photo_key_column: Option<&'a mut Option<String>>,
    pub sample_photo_match: Option<&'a crate::data::models::PhotoMatchResult>,
}

impl<'a> TemplateEditor<'a> {
    pub fn new(template: &'a mut TemplateDefinition, state: &'a mut TemplateEditorState) -> Self {
        Self {
            template,
            state,
            available_columns: &[],
            photo_key_column: None,
            sample_photo_match: None,
        }
    }

    pub fn with_context(
        template: &'a mut TemplateDefinition,
        state: &'a mut TemplateEditorState,
        available_columns: &'a [String],
        photo_key_column: Option<&'a mut Option<String>>,
        sample_photo_match: Option<&'a crate::data::models::PhotoMatchResult>,
    ) -> Self {
        Self {
            template,
            state,
            available_columns,
            photo_key_column,
            sample_photo_match,
        }
    }

    pub fn show(&mut self, ui: &mut Ui) -> bool {
        let before = self.template.clone();
        self.top_toolbar(ui);
        ui.separator();

        egui::SidePanel::right(Id::new("photoshop-dock-panel"))
            .resizable(true)
            .default_width(280.0)
            .show_inside(ui, |ui| self.right_dock_panel(ui));

        egui::CentralPanel::default().show_inside(ui, |ui| self.canvas_viewport(ui));

        *self.template != before
    }

    fn top_toolbar(&mut self, ui: &mut Ui) {
        ui.horizontal(|ui| {
            if ui.button("↶ Undo").clicked() {
                self.state.undo(self.template);
            }
            if ui.button("↷ Redo").clicked() {
                self.state.redo(self.template);
            }
            ui.separator();
            ui.label("Add Element:");
            for (label, kind) in [
                ("🔤 Text", "text"),
                ("🗄 Dynamic", "dynamic_text"),
                ("🖼 Photo", "photo"),
                ("▭ Rect", "rect"),
                ("▢ Round Rect", "round_rect"),
                ("─ Line", "line"),
            ] {
                if ui.small_button(label).clicked() {
                    self.add_element(kind);
                }
            }
            ui.separator();
            ui.label(format!(
                "Canvas: {} × {} px @ {} DPI",
                self.template.width_px, self.template.height_px, self.template.dpi
            ));
        });
    }

    fn right_dock_panel(&mut self, ui: &mut Ui) {
        // Tab switcher
        ui.horizontal(|ui| {
            for (tab, label) in [
                (EditorTab::Properties, "Properties"),
                (EditorTab::Layers, "Layers"),
                (EditorTab::Swatches, "Swatches"),
                (EditorTab::History, "History"),
                (EditorTab::Align, "Align"),
            ] {
                if ui
                    .selectable_label(self.state.active_tab == tab, label)
                    .clicked()
                {
                    self.state.active_tab = tab;
                }
            }
        });
        ui.separator();

        match self.state.active_tab {
            EditorTab::Properties => self.properties_tab(ui),
            EditorTab::Layers => self.layers_tab(ui),
            EditorTab::Swatches => self.swatches_tab(ui),
            EditorTab::History => self.history_tab(ui),
            EditorTab::Align => self.align_tab(ui),
        }
    }

    fn properties_tab(&mut self, ui: &mut Ui) {
        ui.heading("Properties Inspector");
        let Some(id) = self.state.selected_id.clone() else {
            ui.label("Select an element on the canvas to inspect its properties.");
            return;
        };
        if self.template.get_element_by_id(&id).is_none() {
            self.state.selected_id = None;
            return;
        }
        let before = self.template.clone();
        if let Some(element) = self
            .template
            .elements
            .iter_mut()
            .find(|element| element.id == id)
        {
            ui.strong(format!("{} · {}", element.name, element.r#type));
            ui.horizontal(|ui| {
                ui.label("Name");
                ui.text_edit_singleline(&mut element.name);
            });
            ui.horizontal(|ui| {
                ui.label("X");
                ui.add(egui::DragValue::new(&mut element.x).speed(1.0));
                ui.label("Y");
                ui.add(egui::DragValue::new(&mut element.y).speed(1.0));
            });
            ui.horizontal(|ui| {
                ui.label("W");
                ui.add(
                    egui::DragValue::new(&mut element.width)
                        .speed(1.0)
                        .range(1.0..=10000.0),
                );
                ui.label("H");
                ui.add(
                    egui::DragValue::new(&mut element.height)
                        .speed(1.0)
                        .range(1.0..=10000.0),
                );
            });
            ui.horizontal(|ui| {
                ui.checkbox(&mut element.visible, "Visible");
                ui.checkbox(&mut element.locked, "Locked");
            });
            if element.r#type == "photo" {
                ui.group(|ui| {
                    ui.strong("📷 Photo Settings");
                    ui.horizontal(|ui| {
                        ui.label("Key Column:");
                        let mut current_col = element.binding.clone().unwrap_or_else(|| {
                            self.photo_key_column
                                .as_ref()
                                .and_then(|k| (**k).clone())
                                .unwrap_or_else(|| "PIN".into())
                        });
                        let combo_id = format!("te-photo-col-{}", element.id);
                        egui::ComboBox::from_id_salt(combo_id)
                            .selected_text(&current_col)
                            .width(130.0)
                            .show_ui(ui, |ui| {
                                for col in self.available_columns {
                                    if ui
                                        .selectable_value(
                                            &mut current_col,
                                            col.clone(),
                                            col.clone(),
                                        )
                                        .clicked()
                                    {
                                        element.binding = Some(col.clone());
                                        if let Some(key_col) = self.photo_key_column.as_deref_mut()
                                        {
                                            *key_col = Some(col.clone());
                                        }
                                    }
                                }
                            });
                        if ui
                            .text_edit_singleline(element.binding.get_or_insert_with(String::new))
                            .changed()
                        {
                            if let Some(key_col) = self.photo_key_column.as_deref_mut() {
                                *key_col = element.binding.clone();
                            }
                        }
                    });
                    if let Some(match_result) = self.sample_photo_match {
                        match match_result.status {
                            crate::data::models::MatchStatus::Matched => {
                                ui.colored_label(
                                    egui::Color32::from_rgb(34, 197, 94),
                                    format!(
                                        "✓ Found: {}",
                                        match_result
                                            .photo_path
                                            .as_ref()
                                            .map(|p| std::path::Path::new(p)
                                                .file_name()
                                                .unwrap_or_default()
                                                .to_string_lossy()
                                                .into_owned())
                                            .unwrap_or_default()
                                    ),
                                );
                            }
                            crate::data::models::MatchStatus::Missing => {
                                ui.colored_label(
                                    egui::Color32::from_rgb(239, 68, 68),
                                    "✗ No photo matched for sample row",
                                );
                            }
                            crate::data::models::MatchStatus::Ambiguous => {
                                ui.colored_label(
                                    egui::Color32::from_rgb(249, 115, 22),
                                    "⚠ Ambiguous matches",
                                );
                            }
                            crate::data::models::MatchStatus::Overridden => {
                                ui.colored_label(
                                    egui::Color32::from_rgb(56, 189, 248),
                                    "✓ Manually overridden",
                                );
                            }
                        }
                    }
                    ui.horizontal(|ui| {
                        ui.label("Fit");
                        let fit_label = match element.style.fit_mode {
                            crate::data::models::ImageFitMode::Cover => "cover",
                            crate::data::models::ImageFitMode::Contain => "contain",
                            crate::data::models::ImageFitMode::Stretch => "stretch",
                            crate::data::models::ImageFitMode::Crop => "crop",
                        };
                        egui::ComboBox::from_id_salt(format!("photo-fit-{}", element.id))
                            .selected_text(fit_label)
                            .show_ui(ui, |ui| {
                                ui.selectable_value(
                                    &mut element.style.fit_mode,
                                    crate::data::models::ImageFitMode::Cover,
                                    "cover",
                                );
                                ui.selectable_value(
                                    &mut element.style.fit_mode,
                                    crate::data::models::ImageFitMode::Contain,
                                    "contain",
                                );
                                ui.selectable_value(
                                    &mut element.style.fit_mode,
                                    crate::data::models::ImageFitMode::Stretch,
                                    "stretch",
                                );
                                ui.selectable_value(
                                    &mut element.style.fit_mode,
                                    crate::data::models::ImageFitMode::Crop,
                                    "crop",
                                );
                            });
                        ui.label("Mask");
                        egui::ComboBox::from_id_salt(format!("photo-mask-{}", element.id))
                            .selected_text(&element.style.mask_shape)
                            .show_ui(ui, |ui| {
                                for mask in ["rect", "rounded", "circle"] {
                                    ui.selectable_value(
                                        &mut element.style.mask_shape,
                                        mask.into(),
                                        mask,
                                    );
                                }
                            });
                    });
                });
            } else if element.r#type == "dynamic_text" {
                ui.horizontal(|ui| {
                    ui.label("Source Column");
                    let mut current_col = element.binding.clone().unwrap_or_default();
                    let combo_id = format!("te-dyn-col-{}", element.id);
                    egui::ComboBox::from_id_salt(combo_id)
                        .selected_text(if current_col.is_empty() {
                            "(Select…)"
                        } else {
                            &current_col
                        })
                        .width(130.0)
                        .show_ui(ui, |ui| {
                            for col in self.available_columns {
                                if ui
                                    .selectable_value(&mut current_col, col.clone(), col.clone())
                                    .clicked()
                                {
                                    element.binding = Some(col.clone());
                                }
                            }
                        });
                    ui.text_edit_singleline(element.binding.get_or_insert_with(String::new));
                });
            }
            if element.r#type == "text" || element.r#type == "dynamic_text" {
                ui.horizontal(|ui| {
                    ui.label("Text");
                    ui.text_edit_singleline(element.static_content.get_or_insert_with(String::new));
                });
                ui.horizontal(|ui| {
                    ui.label("Font Size");
                    ui.add(egui::DragValue::new(&mut element.style.font_size).range(6..=200));
                    ui.checkbox(&mut element.style.font_bold, "Bold");
                    ui.checkbox(&mut element.style.font_italic, "Italic");
                });
                ui.horizontal(|ui| {
                    ui.label("Font Color");
                    ui.text_edit_singleline(&mut element.style.font_color);
                });
            }
            ui.horizontal(|ui| {
                ui.label("Fill Color");
                ui.text_edit_singleline(&mut element.style.background_color);
            });
            ui.horizontal(|ui| {
                ui.label("Border");
                ui.add(egui::DragValue::new(&mut element.style.border_width).range(0..=50));
                ui.text_edit_singleline(&mut element.style.border_color);
            });
            if element.r#type == "round_rect" {
                ui.horizontal(|ui| {
                    ui.label("Corner Radius");
                    ui.add(egui::DragValue::new(&mut element.style.border_radius).range(0..=100));
                });
            }
        }
        self.state.history.record_change(before, self.template);

        ui.separator();
        ui.horizontal(|ui| {
            if ui.button("Duplicate").clicked() {
                self.state
                    .execute(self.template, EditorCommand::Duplicate { id: id.clone() });
            }
            if ui.button("Delete").clicked() {
                self.state
                    .execute(self.template, EditorCommand::Delete { id: id.clone() });
                self.state.selected_id = None;
            }
        });
    }

    fn layers_tab(&mut self, ui: &mut Ui) {
        ui.heading("Layers Stack");
        let mut ids: Vec<(String, i32, String, bool, bool)> = self
            .template
            .elements
            .iter()
            .map(|element| {
                (
                    element.id.clone(),
                    element.z_index,
                    element.name.clone(),
                    element.visible,
                    element.locked,
                )
            })
            .collect();
        ids.sort_by_key(|left| std::cmp::Reverse(left.1));

        let scroll_height = (ui.available_height() - 60.0).max(350.0);
        egui::ScrollArea::vertical()
            .max_height(scroll_height)
            .show(ui, |ui| {
                for (id, _, name, visible, locked) in ids {
                    ui.horizontal(|ui| {
                        if ui
                            .selectable_label(
                                self.state.selected_id.as_deref() == Some(id.as_str()),
                                name,
                            )
                            .clicked()
                        {
                            self.state.selected_id = Some(id.clone());
                        }
                        if ui.small_button(if visible { "◉" } else { "○" }).clicked() {
                            self.state.execute(
                                self.template,
                                EditorCommand::SetVisibility {
                                    id: id.clone(),
                                    visible: !visible,
                                },
                            );
                        }
                        if ui.small_button(if locked { "🔒" } else { "🔓" }).clicked() {
                            self.state.execute(
                                self.template,
                                EditorCommand::SetLocked {
                                    id: id.clone(),
                                    locked: !locked,
                                },
                            );
                        }
                    });
                }
            });

        if let Some(id) = self.state.selected_id.clone() {
            ui.separator();
            ui.horizontal(|ui| {
                for (label, command) in [
                    ("⤓ Bottom", EditorCommand::SendToBack { id: id.clone() }),
                    ("↓ Lower", EditorCommand::Lower { id: id.clone() }),
                    ("↑ Raise", EditorCommand::Raise { id: id.clone() }),
                    ("⤒ Top", EditorCommand::BringToFront { id: id.clone() }),
                ] {
                    if ui.small_button(label).clicked() {
                        self.state.execute(self.template, command);
                    }
                }
            });
        }
    }

    fn swatches_tab(&mut self, ui: &mut Ui) {
        ui.heading("Swatches Palette");
        ui.label("Apply curated colors to the selected element or canvas.");

        ui.horizontal(|ui| {
            ui.label("Target:");
            ui.selectable_value(&mut self.state.swatch_target, SwatchTarget::Fill, "Fill");
            ui.selectable_value(&mut self.state.swatch_target, SwatchTarget::Font, "Font");
            ui.selectable_value(
                &mut self.state.swatch_target,
                SwatchTarget::Border,
                "Border",
            );
            ui.selectable_value(
                &mut self.state.swatch_target,
                SwatchTarget::Background,
                "Card BG",
            );
        });

        ui.add_space(4.0);
        let selected_id = self.state.selected_id.clone();
        let target = self.state.swatch_target;

        // 6x4 Grid of 24 curated swatches
        egui::Grid::new("swatches_grid")
            .spacing([6.0, 6.0])
            .show(ui, |ui| {
                for (idx, (hex, name)) in SWATCHES.iter().enumerate() {
                    let col = parse_color(hex, Color32::WHITE);
                    let (rect, resp) = ui.allocate_exact_size(Vec2::splat(26.0), Sense::click());
                    let painter = ui.painter_at(rect);
                    painter.rect_filled(rect, 4.0, col);
                    painter.rect_stroke(rect, 4.0, Stroke::new(1.0_f32, Color32::from_gray(100)));

                    if resp.on_hover_text(format!("{} ({})", name, hex)).clicked() {
                        if target == SwatchTarget::Background {
                            self.state.execute(
                                self.template,
                                EditorCommand::UpdateColor {
                                    id: String::new(),
                                    target,
                                    color: (*hex).to_owned(),
                                },
                            );
                        } else if let Some(id) = &selected_id {
                            self.state.execute(
                                self.template,
                                EditorCommand::UpdateColor {
                                    id: id.clone(),
                                    target,
                                    color: (*hex).to_owned(),
                                },
                            );
                        }
                    }

                    if (idx + 1) % 6 == 0 {
                        ui.end_row();
                    }
                }
            });

        ui.separator();
        ui.label("Custom Hex Color:");
        ui.horizontal(|ui| {
            ui.text_edit_singleline(&mut self.state.custom_hex_color);
            if ui.button("Apply Color").clicked() {
                let hex = self.state.custom_hex_color.clone();
                if target == SwatchTarget::Background {
                    self.state.execute(
                        self.template,
                        EditorCommand::UpdateColor {
                            id: String::new(),
                            target,
                            color: hex,
                        },
                    );
                } else if let Some(id) = &selected_id {
                    self.state.execute(
                        self.template,
                        EditorCommand::UpdateColor {
                            id: id.clone(),
                            target,
                            color: hex,
                        },
                    );
                }
            }
        });
    }

    fn history_tab(&mut self, ui: &mut Ui) {
        ui.heading("Action History");
        ui.horizontal(|ui| {
            if ui.button("↶ Step Backward").clicked() {
                self.state.undo(self.template);
            }
            if ui.button("↷ Step Forward").clicked() {
                self.state.redo(self.template);
            }
        });
        ui.separator();

        let scroll_height = (ui.available_height() - 60.0).max(350.0);
        egui::ScrollArea::vertical()
            .max_height(scroll_height)
            .show(ui, |ui| {
                ui.label("📄 Document Opened");
                for (idx, name) in self.state.history.action_names.iter().enumerate() {
                    let is_current = idx + 1 == self.state.history.undo.len();
                    let text = format!("⚡ {name}");
                    if is_current {
                        ui.strong(text);
                    } else {
                        ui.label(text);
                    }
                }
            });
    }

    fn align_tab(&mut self, ui: &mut Ui) {
        ui.heading("Alignment & Distribution");
        let Some(id) = self.state.selected_id.clone() else {
            ui.label("Select an element to align on the card canvas.");
            return;
        };

        ui.label("Align to Card Bounds:");
        ui.horizontal(|ui| {
            if ui.button("Left").clicked() {
                self.state.execute(
                    self.template,
                    EditorCommand::Align {
                        id: id.clone(),
                        alignment: AlignmentType::Left,
                    },
                );
            }
            if ui.button("Center H").clicked() {
                self.state.execute(
                    self.template,
                    EditorCommand::Align {
                        id: id.clone(),
                        alignment: AlignmentType::CenterHorizontal,
                    },
                );
            }
            if ui.button("Right").clicked() {
                self.state.execute(
                    self.template,
                    EditorCommand::Align {
                        id: id.clone(),
                        alignment: AlignmentType::Right,
                    },
                );
            }
        });
        ui.horizontal(|ui| {
            if ui.button("Top").clicked() {
                self.state.execute(
                    self.template,
                    EditorCommand::Align {
                        id: id.clone(),
                        alignment: AlignmentType::Top,
                    },
                );
            }
            if ui.button("Center V").clicked() {
                self.state.execute(
                    self.template,
                    EditorCommand::Align {
                        id: id.clone(),
                        alignment: AlignmentType::CenterVertical,
                    },
                );
            }
            if ui.button("Bottom").clicked() {
                self.state.execute(
                    self.template,
                    EditorCommand::Align {
                        id: id.clone(),
                        alignment: AlignmentType::Bottom,
                    },
                );
            }
        });
        if ui.button("⊡ Center on Entire Card").clicked() {
            self.state.execute(
                self.template,
                EditorCommand::Align {
                    id: id.clone(),
                    alignment: AlignmentType::CenterOnCard,
                },
            );
        }
    }

    fn canvas_viewport(&mut self, ui: &mut Ui) {
        let full_size = ui.available_size();
        let (view_rect, response) = ui.allocate_exact_size(full_size, Sense::click_and_drag());
        let painter = ui.painter_at(view_rect);

        // Fill background
        painter.rect_filled(view_rect, 0.0, Color32::from_rgb(28, 28, 30));

        let ruler_offset = if self.state.show_rulers {
            RULER_THICKNESS
        } else {
            0.0
        };
        let canvas_area = Rect::from_min_max(
            view_rect.min + Vec2::new(ruler_offset, ruler_offset),
            view_rect.max - Vec2::new(0.0, 36.0), // Reserve bottom HUD
        );

        let transform = CanvasTransform::fit(
            canvas_area.shrink(16.0),
            self.template,
            self.state.zoom,
            self.state.pan,
        );
        let scene_rect = transform.scene_rect(self.template);

        // Draw card shadow and white canvas
        painter.rect_filled(
            scene_rect.translate(Vec2::new(3.0, 4.0)),
            2.0,
            Color32::from_black_alpha(100),
        );
        painter.rect_filled(
            scene_rect,
            2.0,
            parse_color(&self.template.background_color, Color32::WHITE),
        );

        // Draw guides & elements
        self.draw_guides(&painter, scene_rect, transform);
        let mut ordered: Vec<&CanvasElement> = self
            .template
            .elements
            .iter()
            .filter(|element| element.visible)
            .collect();
        ordered.sort_by(|left, right| {
            left.z_index
                .cmp(&right.z_index)
                .then_with(|| left.id.cmp(&right.id))
        });
        for element in ordered {
            self.draw_element(&painter, element, transform);
        }

        // Track cursor position
        let pointer_pos = response
            .hover_pos()
            .or_else(|| response.interact_pointer_pos());
        if let Some(pos) = pointer_pos {
            let scene_pt = transform.screen_to_scene(pos);
            self.state.cursor_scene_pos = Some(scene_pt);

            // Draw crosshairs on canvas
            if self.state.show_crosshairs && scene_rect.contains(pos) {
                let crosshair_stroke =
                    Stroke::new(0.8_f32, Color32::from_rgba_unmultiplied(6, 182, 212, 140));
                painter.line_segment(
                    [
                        Pos2::new(scene_rect.left(), pos.y),
                        Pos2::new(scene_rect.right(), pos.y),
                    ],
                    crosshair_stroke,
                );
                painter.line_segment(
                    [
                        Pos2::new(pos.x, scene_rect.top()),
                        Pos2::new(pos.x, scene_rect.bottom()),
                    ],
                    crosshair_stroke,
                );
            }
        } else {
            self.state.cursor_scene_pos = None;
        }

        // Draw Photoshop Rulers
        if self.state.show_rulers {
            self.draw_rulers(&painter, view_rect, canvas_area, transform, pointer_pos);
        }

        // Floating bottom HUD overlay
        self.draw_floating_hud(ui, view_rect);

        // Handle canvas interaction
        self.handle_canvas_input(response, canvas_area, transform);
    }

    fn draw_rulers(
        &mut self,
        painter: &egui::Painter,
        view_rect: Rect,
        canvas_area: Rect,
        transform: CanvasTransform,
        pointer_pos: Option<Pos2>,
    ) {
        let bg_color = Color32::from_rgb(30, 30, 34);
        let border_stroke = Stroke::new(1.0_f32, Color32::from_rgb(58, 58, 62));
        let tick_stroke = Stroke::new(1.0_f32, Color32::from_gray(120));
        let sub_tick_stroke = Stroke::new(0.8_f32, Color32::from_gray(80));
        let text_color = Color32::from_gray(160);
        let hairline_stroke = Stroke::new(1.0_f32, Color32::from_rgb(239, 68, 68));

        let corner_rect = Rect::from_min_size(view_rect.min, Vec2::splat(RULER_THICKNESS));
        painter.rect_filled(corner_rect, 0.0, bg_color);
        painter.line_segment(
            [corner_rect.right_top(), corner_rect.right_bottom()],
            border_stroke,
        );
        painter.line_segment(
            [corner_rect.left_bottom(), corner_rect.right_bottom()],
            border_stroke,
        );
        painter.text(
            corner_rect.center(),
            Align2::CENTER_CENTER,
            &self.state.ruler_unit,
            FontId::proportional(9.0),
            text_color,
        );

        let dpi = self.template.dpi.max(72) as f32;
        let is_mm = self.state.ruler_unit == "mm";
        let base_step = if is_mm { 10.0 * dpi / 25.4 } else { 100.0 };
        let step = if transform.scale > 2.5 {
            base_step / 2.0
        } else if transform.scale < 0.6 {
            base_step * 2.0
        } else {
            base_step
        };

        // Horizontal Ruler
        let h_ruler_rect = Rect::from_min_max(
            Pos2::new(view_rect.min.x + RULER_THICKNESS, view_rect.min.y),
            Pos2::new(view_rect.max.x, view_rect.min.y + RULER_THICKNESS),
        );
        painter.rect_filled(h_ruler_rect, 0.0, bg_color);
        painter.line_segment(
            [h_ruler_rect.left_bottom(), h_ruler_rect.right_bottom()],
            border_stroke,
        );

        let scene_left = transform.screen_to_scene(h_ruler_rect.left_top()).x;
        let scene_right = transform.screen_to_scene(h_ruler_rect.right_top()).x;
        let mut val = (scene_left / step).floor() * step;
        while val <= scene_right + step {
            let screen_x = transform.scene_to_screen(Pos2::new(val, 0.0)).x;
            if screen_x >= h_ruler_rect.left() && screen_x <= h_ruler_rect.right() {
                // Major tick
                painter.line_segment(
                    [
                        Pos2::new(screen_x, h_ruler_rect.bottom() - 7.0),
                        Pos2::new(screen_x, h_ruler_rect.bottom()),
                    ],
                    tick_stroke,
                );
                let label_val = if is_mm {
                    (val / dpi * 25.4).round() as i32
                } else {
                    val.round() as i32
                };
                painter.text(
                    Pos2::new(screen_x + 3.0, h_ruler_rect.top() + 3.0),
                    Align2::LEFT_TOP,
                    label_val.to_string(),
                    FontId::proportional(8.0),
                    text_color,
                );

                // Sub-ticks
                for i in 1..5 {
                    let sub_val = val + (step * i as f32 / 5.0);
                    let sub_x = transform.scene_to_screen(Pos2::new(sub_val, 0.0)).x;
                    if sub_x >= h_ruler_rect.left() && sub_x <= h_ruler_rect.right() {
                        let tick_h = if i == 2 || i == 3 { 5.0 } else { 3.0 };
                        painter.line_segment(
                            [
                                Pos2::new(sub_x, h_ruler_rect.bottom() - tick_h),
                                Pos2::new(sub_x, h_ruler_rect.bottom()),
                            ],
                            sub_tick_stroke,
                        );
                    }
                }
            }
            val += step;
        }

        // Vertical Ruler
        let v_ruler_rect = Rect::from_min_max(
            Pos2::new(view_rect.min.x, view_rect.min.y + RULER_THICKNESS),
            Pos2::new(view_rect.min.x + RULER_THICKNESS, canvas_area.bottom()),
        );
        painter.rect_filled(v_ruler_rect, 0.0, bg_color);
        painter.line_segment(
            [v_ruler_rect.right_top(), v_ruler_rect.right_bottom()],
            border_stroke,
        );

        let scene_top = transform.screen_to_scene(v_ruler_rect.left_top()).y;
        let scene_bottom = transform.screen_to_scene(v_ruler_rect.left_bottom()).y;
        let mut y_val = (scene_top / step).floor() * step;
        while y_val <= scene_bottom + step {
            let screen_y = transform.scene_to_screen(Pos2::new(0.0, y_val)).y;
            if screen_y >= v_ruler_rect.top() && screen_y <= v_ruler_rect.bottom() {
                // Major tick
                painter.line_segment(
                    [
                        Pos2::new(v_ruler_rect.right() - 7.0, screen_y),
                        Pos2::new(v_ruler_rect.right(), screen_y),
                    ],
                    tick_stroke,
                );
                let label_val = if is_mm {
                    (y_val / dpi * 25.4).round() as i32
                } else {
                    y_val.round() as i32
                };
                painter.text(
                    Pos2::new(v_ruler_rect.left() + 2.0, screen_y - 2.0),
                    Align2::LEFT_BOTTOM,
                    label_val.to_string(),
                    FontId::proportional(8.0),
                    text_color,
                );

                // Sub-ticks
                for i in 1..5 {
                    let sub_val = y_val + (step * i as f32 / 5.0);
                    let sub_y = transform.scene_to_screen(Pos2::new(0.0, sub_val)).y;
                    if sub_y >= v_ruler_rect.top() && sub_y <= v_ruler_rect.bottom() {
                        let tick_w = if i == 2 || i == 3 { 5.0 } else { 3.0 };
                        painter.line_segment(
                            [
                                Pos2::new(v_ruler_rect.right() - tick_w, sub_y),
                                Pos2::new(v_ruler_rect.right(), sub_y),
                            ],
                            sub_tick_stroke,
                        );
                    }
                }
            }
            y_val += step;
        }

        // Hairlines on rulers
        if let Some(pos) = pointer_pos {
            if pos.x >= h_ruler_rect.left() && pos.x <= h_ruler_rect.right() {
                painter.line_segment(
                    [
                        Pos2::new(pos.x, h_ruler_rect.top()),
                        Pos2::new(pos.x, h_ruler_rect.bottom()),
                    ],
                    hairline_stroke,
                );
            }
            if pos.y >= v_ruler_rect.top() && pos.y <= v_ruler_rect.bottom() {
                painter.line_segment(
                    [
                        Pos2::new(v_ruler_rect.left(), pos.y),
                        Pos2::new(v_ruler_rect.right(), pos.y),
                    ],
                    hairline_stroke,
                );
            }
        }
    }

    fn draw_floating_hud(&mut self, ui: &mut Ui, view_rect: Rect) {
        let hud_rect = Rect::from_min_size(
            Pos2::new(view_rect.min.x + 8.0, view_rect.max.y - 32.0),
            Vec2::new(view_rect.width() - 16.0, 28.0),
        );

        let mut child_ui = ui.new_child(egui::UiBuilder::new().max_rect(hud_rect));
        child_ui.horizontal(|ui| {
            ui.visuals_mut().override_text_color = Some(Color32::from_gray(230));

            // Zoom controls
            if ui.small_button("−").clicked() {
                self.state.zoom = (self.state.zoom / 1.15).max(MIN_ZOOM);
            }
            ui.add(egui::Slider::new(&mut self.state.zoom, MIN_ZOOM..=MAX_ZOOM).show_value(false));
            if ui.small_button("+").clicked() {
                self.state.zoom = (self.state.zoom * 1.15).min(MAX_ZOOM);
            }
            ui.label(format!("{}%", (self.state.zoom * 100.0).round() as i32));

            ui.separator();
            if ui.small_button("⊡ Fit Card").clicked() {
                self.state.fit_canvas();
            }
            if ui.small_button("1:1 Actual").clicked() {
                self.state.zoom = 1.0;
                self.state.pan = Vec2::ZERO;
            }

            ui.separator();
            if ui
                .small_button(if self.state.show_rulers {
                    "📏 Rulers ✓"
                } else {
                    "📏 Rulers"
                })
                .clicked()
            {
                self.state.show_rulers = !self.state.show_rulers;
            }
            if ui
                .small_button(if self.state.show_grid {
                    "▦ Grid ✓"
                } else {
                    "▦ Grid"
                })
                .clicked()
            {
                self.state.show_grid = !self.state.show_grid;
            }
            if ui
                .small_button(if self.state.snap_to_grid {
                    "🧲 Snap ✓"
                } else {
                    "🧲 Snap"
                })
                .clicked()
            {
                self.state.snap_to_grid = !self.state.snap_to_grid;
            }
            if ui
                .small_button(if self.state.show_safe_area {
                    "⛶ Safe ✓"
                } else {
                    "⛶ Safe"
                })
                .clicked()
            {
                self.state.show_safe_area = !self.state.show_safe_area;
            }
            if ui
                .small_button(if self.state.show_crosshairs {
                    "✛ Crosshairs ✓"
                } else {
                    "✛ Crosshairs"
                })
                .clicked()
            {
                self.state.show_crosshairs = !self.state.show_crosshairs;
            }

            // Unit toggle in HUD
            if ui
                .small_button(format!("Unit: {}", self.state.ruler_unit))
                .clicked()
            {
                self.state.ruler_unit = if self.state.ruler_unit == "px" {
                    "mm".into()
                } else {
                    "px".into()
                };
            }
        });
    }

    fn draw_guides(&self, painter: &egui::Painter, canvas: Rect, transform: CanvasTransform) {
        if self.state.show_grid {
            let spacing = (50.0 * transform.scale).max(8.0);
            let mut x = canvas.left() + spacing;
            while x < canvas.right() {
                painter.line_segment(
                    [Pos2::new(x, canvas.top()), Pos2::new(x, canvas.bottom())],
                    Stroke::new(0.5_f32, Color32::from_gray(220)),
                );
                x += spacing;
            }
            let mut y = canvas.top() + spacing;
            while y < canvas.bottom() {
                painter.line_segment(
                    [Pos2::new(canvas.left(), y), Pos2::new(canvas.right(), y)],
                    Stroke::new(0.5_f32, Color32::from_gray(220)),
                );
                y += spacing;
            }
        }
        if self.state.show_safe_area {
            let margin = (self.template.safe_area_margin_mm / 25.4 * f64::from(self.template.dpi))
                as f32
                * transform.scale;
            painter.rect_stroke(
                canvas.shrink(margin),
                0.0,
                Stroke::new(1.0_f32, Color32::from_rgb(80, 160, 220)),
            );
        }
    }

    fn draw_element(
        &self,
        painter: &egui::Painter,
        element: &CanvasElement,
        transform: CanvasTransform,
    ) {
        let rect = Rect::from_min_size(
            transform.scene_to_screen(Pos2::new(element.x as f32, element.y as f32)),
            Vec2::new(
                element.width as f32 * transform.scale,
                element.height as f32 * transform.scale,
            ),
        );
        let fill = parse_color(
            &element.style.background_color,
            Color32::from_white_alpha(20),
        );
        let stroke_color = parse_color(&element.style.border_color, Color32::from_gray(100));
        let stroke = Stroke::new(
            (element.style.border_width.max(1) as f32 * transform.scale).max(1.0),
            stroke_color,
        );
        match element.r#type.as_str() {
            "line" => {
                painter.line_segment(
                    [rect.left_top(), rect.right_bottom()],
                    Stroke::new(2.0_f32, stroke_color),
                );
            }
            "photo" => {
                let bg_color = Color32::from_rgb(226, 232, 240);
                painter.rect_filled(rect, 4.0, bg_color);
                painter.rect_stroke(rect, 4.0, stroke);
                // Draw soft crosshairs
                let soft_stroke = Stroke::new(1.0_f32, Color32::from_rgb(203, 213, 225));
                painter.line_segment([rect.left_top(), rect.right_bottom()], soft_stroke);
                painter.line_segment([rect.right_top(), rect.left_bottom()], soft_stroke);

                let center = rect.center();
                let icon_size = (28.0 * transform.scale).clamp(14.0, 36.0);
                painter.text(
                    center - Vec2::new(0.0, icon_size * 0.35),
                    Align2::CENTER_CENTER,
                    "📷",
                    FontId::proportional(icon_size),
                    Color32::from_rgb(100, 116, 139),
                );

                let key_hint = element
                    .binding
                    .as_deref()
                    .or_else(|| {
                        self.photo_key_column
                            .as_ref()
                            .and_then(|k| (**k).as_deref())
                    })
                    .unwrap_or("PIN");
                let label_text = format!("Photo [{key_hint}]");
                painter.text(
                    center + Vec2::new(0.0, icon_size * 0.5),
                    Align2::CENTER_CENTER,
                    label_text,
                    FontId::proportional((11.0 * transform.scale).clamp(8.0, 14.0)),
                    Color32::from_rgb(71, 85, 105),
                );
            }
            "round_rect" => {
                painter.rect_filled(rect, element.style.border_radius.max(8) as f32, fill);
                painter.rect_stroke(rect, element.style.border_radius.max(8) as f32, stroke);
            }
            _ => {
                painter.rect_filled(rect, 0.0, fill);
                painter.rect_stroke(rect, 0.0, stroke);
            }
        }
        let label = element
            .static_content
            .as_deref()
            .or(element.binding.as_deref())
            .unwrap_or(&element.name);
        if element.r#type != "line" {
            painter.text(
                rect.left_top() + Vec2::splat(5.0),
                Align2::LEFT_TOP,
                label,
                FontId::proportional((element.style.font_size as f32 * transform.scale).max(8.0)),
                parse_color(&element.style.font_color, Color32::DARK_GRAY),
            );
        }
        if self.state.selected_id.as_deref() == Some(element.id.as_str()) {
            painter.rect_stroke(
                rect.expand(2.0),
                0.0,
                Stroke::new(2.0_f32, Color32::from_rgb(35, 120, 235)),
            );
        }
    }

    fn handle_canvas_input(&mut self, response: Response, view: Rect, transform: CanvasTransform) {
        let pointer = response.interact_pointer_pos();
        let hit = pointer.and_then(|pos| self.hit_test(transform.screen_to_scene(pos)));

        // Unit corner click
        if response.clicked() {
            if let Some(pos) = response.hover_pos() {
                let corner_rect = Rect::from_min_size(
                    view.min - Vec2::splat(RULER_THICKNESS),
                    Vec2::splat(RULER_THICKNESS),
                );
                if corner_rect.contains(pos) {
                    self.state.ruler_unit = if self.state.ruler_unit == "px" {
                        "mm".into()
                    } else {
                        "px".into()
                    };
                    return;
                }
            }
            self.state.selected_id = hit.clone();
        }

        if response.drag_started() {
            if let Some(id) = hit.clone() {
                if self
                    .template
                    .get_element_by_id(&id)
                    .is_some_and(|element| !element.locked)
                {
                    self.state.selected_id = Some(id.clone());
                    self.state.history.undo.push(self.template.clone());
                    self.state.history.action_names.push("Move element".into());
                    self.state.history.redo.clear();
                    self.state.drag = Some(DragState {
                        id,
                        last_delta: Vec2::ZERO,
                    });
                }
            }
        }
        if response.dragged() {
            if let Some(drag) = self.state.drag.as_mut() {
                let total = response.drag_delta();
                let delta = total - drag.last_delta;
                drag.last_delta = total;
                if let Some(element) = self
                    .template
                    .elements
                    .iter_mut()
                    .find(|element| element.id == drag.id)
                {
                    let mut new_x =
                        element.x + f64::from(delta.x / transform.scale.max(f32::EPSILON));
                    let mut new_y =
                        element.y + f64::from(delta.y / transform.scale.max(f32::EPSILON));
                    if self.state.snap_to_grid {
                        new_x = (new_x / 10.0).round() * 10.0;
                        new_y = (new_y / 10.0).round() * 10.0;
                    }
                    element.x = new_x;
                    element.y = new_y;
                }
            } else if response.dragged_by(PointerButton::Primary) && hit.is_none() {
                self.state.pan += response.drag_motion();
            }
        }
        let middle_down = response.hovered()
            && response
                .ctx
                .input(|input| input.pointer.button_down(PointerButton::Middle));
        if middle_down {
            self.state.pan += response.ctx.input(|input| input.pointer.delta());
        }
        if response.drag_stopped() {
            self.state.drag = None;
        }
        if response.hovered() {
            let scroll = response.ctx.input(|input| input.smooth_scroll_delta.y);
            if scroll != 0.0 && response.ctx.input(|input| input.modifiers.ctrl) {
                self.state.zoom =
                    (self.state.zoom * (1.0 + scroll * 0.001)).clamp(MIN_ZOOM, MAX_ZOOM);
            }
        }
    }

    fn hit_test(&self, point: Pos2) -> Option<String> {
        self.template
            .elements
            .iter()
            .filter(|element| {
                element.visible
                    && element.x <= f64::from(point.x)
                    && element.y <= f64::from(point.y)
                    && element.x + element.width >= f64::from(point.x)
                    && element.y + element.height >= f64::from(point.y)
            })
            .max_by(|left, right| {
                left.z_index
                    .cmp(&right.z_index)
                    .then_with(|| left.id.cmp(&right.id))
            })
            .map(|element| element.id.clone())
    }

    fn add_element(&mut self, kind: &str) {
        let index = self.template.elements.len();
        let is_line = kind == "line";
        let element = CanvasElement {
            id: Uuid::new_v4().to_string(),
            name: format!("{} {}", kind.replace('_', " "), index + 1),
            r#type: kind.to_owned(),
            x: 40.0 + (index as f64 * 12.0) % 200.0,
            y: 40.0 + (index as f64 * 12.0) % 180.0,
            width: if is_line { 220.0 } else { 200.0 },
            height: if is_line { 2.0 } else { 60.0 },
            z_index: self
                .template
                .elements
                .iter()
                .map(|element| element.z_index)
                .max()
                .unwrap_or(-1)
                + 1,
            visible: true,
            locked: false,
            binding: (kind == "dynamic_text" || kind == "photo").then(|| "Column".to_owned()),
            static_content: (kind == "text").then(|| "Text".to_owned()),
            style: CanvasElementStyle::default(),
        };
        let id = element.id.clone();
        if self
            .state
            .execute(self.template, EditorCommand::Add(element))
        {
            self.state.selected_id = Some(id);
        }
    }
}

fn parse_color(value: &str, fallback: Color32) -> Color32 {
    let value = value.trim().trim_start_matches('#');
    let bytes = match value.len() {
        6 | 8 => (0..value.len())
            .step_by(2)
            .map(|index| u8::from_str_radix(&value[index..index + 2], 16).ok())
            .collect::<Option<Vec<_>>>(),
        _ => None,
    };
    match bytes.as_deref() {
        Some([r, g, b]) => Color32::from_rgb(*r, *g, *b),
        Some([r, g, b, a]) => Color32::from_rgba_unmultiplied(*r, *g, *b, *a),
        _ if value.eq_ignore_ascii_case("transparent") => Color32::TRANSPARENT,
        _ => fallback,
    }
}
