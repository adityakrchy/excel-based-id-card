//! Native mapping editor for binding template elements to arbitrary columns.

use std::collections::BTreeMap;

use eframe::egui::{self, Ui};

use crate::data::models::{CanvasElement, SourceRecord, TemplateDefinition};

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct ElementMapping {
    pub element_id: String,
    pub source_column: String,
    pub is_photo: bool,
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct MappingIssue {
    pub element_id: Option<String>,
    pub message: String,
}

#[derive(Debug, Clone, Default)]
pub struct MappingEditorState {
    pub bindings: BTreeMap<String, String>,
    pub sample_record: Option<SourceRecord>,
    pub issues: Vec<MappingIssue>,
    pub photo_key_column: Option<String>,
}

impl MappingEditorState {
    pub fn binding_for(&self, element_id: &str) -> Option<&str> {
        self.bindings
            .get(element_id)
            .map(String::as_str)
            .filter(|value| !value.trim().is_empty())
    }

    pub fn set_binding(&mut self, element_id: impl Into<String>, source_column: impl Into<String>) {
        self.bindings
            .insert(element_id.into(), source_column.into());
    }

    pub fn clear_binding(&mut self, element_id: &str) {
        self.bindings.remove(element_id);
    }

    fn effective_binding<'a>(&'a self, element: &'a CanvasElement) -> Option<&'a str> {
        self.binding_for(&element.id).or_else(|| {
            element
                .binding
                .as_deref()
                .filter(|value| !value.trim().is_empty())
        })
    }

    pub fn mappings(&self, template: &TemplateDefinition) -> Vec<ElementMapping> {
        template
            .elements
            .iter()
            .filter(|element| element.r#type == "dynamic_text" || element.r#type == "photo")
            .map(|element| ElementMapping {
                element_id: element.id.clone(),
                source_column: self
                    .effective_binding(element)
                    .unwrap_or_default()
                    .to_owned(),
                is_photo: element.r#type == "photo",
            })
            .collect()
    }

    pub fn validate(&mut self, template: &TemplateDefinition) -> &[MappingIssue] {
        self.issues.clear();
        let sample_columns = self.sample_record.as_ref().map(|record| &record.data);
        for element in template
            .elements
            .iter()
            .filter(|element| element.r#type == "dynamic_text" || element.r#type == "photo")
        {
            let binding = self.effective_binding(element);
            if let Some(binding) = binding {
                if let Some(columns) = sample_columns {
                    if element.r#type == "photo" && binding == "photo" {
                        let key_col = self.photo_key_column.as_deref().unwrap_or("PIN");
                        if !columns.contains_key(key_col)
                            && !columns.contains_key("PIN")
                            && !columns.contains_key("pin")
                            && !columns.contains_key("ID")
                            && !columns.contains_key("id")
                        {
                            self.issues.push(MappingIssue {
                                element_id: Some(element.id.clone()),
                                message: format!(
                                    "Photo element '{}' needs a lookup column (e.g. ID or PIN)",
                                    element.name
                                ),
                            });
                        }
                    } else if !columns.contains_key(binding) {
                        self.issues.push(MappingIssue {
                            element_id: Some(element.id.clone()),
                            message: format!(
                                "Source column '{}' is not present in the sample record",
                                binding
                            ),
                        });
                    }
                }
            } else {
                self.issues.push(MappingIssue {
                    element_id: Some(element.id.clone()),
                    message: format!("{} has no source column", element.name),
                });
            }
        }
        if template
            .elements
            .iter()
            .any(|element| element.r#type == "photo")
            && self.sample_record.is_none()
        {
            self.issues.push(MappingIssue {
                element_id: None,
                message: "Select a sample record to preview photo and text bindings".into(),
            });
        }
        &self.issues
    }

    pub fn preview_value(&self, element_id: &str, template: &TemplateDefinition) -> String {
        let Some(element) = template.get_element_by_id(element_id) else {
            return String::new();
        };
        let Some(binding) = self.effective_binding(element) else {
            return element.static_content.clone().unwrap_or_default();
        };
        if element.r#type == "photo" {
            let key_col = if binding == "photo" {
                self.photo_key_column.as_deref().unwrap_or("PIN")
            } else {
                binding
            };
            return self
                .sample_record
                .as_ref()
                .map(|record| {
                    let val = record.get_value(key_col);
                    if val.is_empty() {
                        record.pin_or_raw().to_owned()
                    } else {
                        val
                    }
                })
                .unwrap_or_else(|| format!("<photo:{key_col}>"));
        }
        self.sample_record
            .as_ref()
            .map(|record| record.get_value(binding))
            .unwrap_or_else(|| format!("<{binding}>"))
    }
}

/// Mapping editor widget.  `on_edit_template` is called by the real button,
/// leaving navigation/application integration with the host.
pub struct MappingEditor<'a> {
    pub template: &'a TemplateDefinition,
    pub state: &'a mut MappingEditorState,
    pub available_columns: &'a [String],
    pub photo_key_column: Option<&'a mut Option<String>>,
    pub photo_match_result: Option<&'a crate::data::models::PhotoMatchResult>,
}

impl<'a> MappingEditor<'a> {
    pub fn new(template: &'a TemplateDefinition, state: &'a mut MappingEditorState) -> Self {
        Self {
            template,
            state,
            available_columns: &[],
            photo_key_column: None,
            photo_match_result: None,
        }
    }

    pub fn with_context(
        template: &'a TemplateDefinition,
        state: &'a mut MappingEditorState,
        available_columns: &'a [String],
        photo_key_column: Option<&'a mut Option<String>>,
        photo_match_result: Option<&'a crate::data::models::PhotoMatchResult>,
    ) -> Self {
        Self {
            template,
            state,
            available_columns,
            photo_key_column,
            photo_match_result,
        }
    }

    pub fn show<F>(&mut self, ui: &mut Ui, mut on_edit_template: F) -> bool
    where
        F: FnMut(),
    {
        let before = self.state.bindings.clone();
        ui.horizontal(|ui| {
            ui.heading("Mapping Editor");
            if ui.button("✏ Edit Template").clicked() {
                on_edit_template();
            }
        });
        ui.label(
            "Bind each dynamic template element to a spreadsheet column. \
             For photo elements, choose the unique column (e.g. PIN, ID, Roll No) matching the image filename in your photo directory.",
        );
        ui.separator();
        egui::ScrollArea::vertical().show(ui, |ui| {
            let elements: Vec<_> = self
                .template
                .elements
                .iter()
                .filter(|element| element.r#type == "dynamic_text" || element.r#type == "photo")
                .map(|element| {
                    (
                        element.id.clone(),
                        element.name.clone(),
                        element.r#type.clone(),
                        element.binding.clone(),
                    )
                })
                .collect();
            if elements.is_empty() {
                ui.label("No dynamic text or photo elements are present in this template.");
            }
            for (id, name, kind, model_binding) in elements {
                ui.group(|ui| {
                    let is_photo = kind == "photo";
                    ui.horizontal(|ui| {
                        if is_photo {
                            ui.strong(format!("📷 {name}"));
                            ui.colored_label(
                                egui::Color32::from_rgb(56, 189, 248),
                                "Photo Placeholder",
                            );
                        } else {
                            ui.strong(format!("🔤 {name}"));
                            ui.small("Dynamic Text Field");
                        }
                    });

                    ui.horizontal(|ui| {
                        ui.label(if is_photo {
                            "Photo lookup key column:"
                        } else {
                            "Source column:"
                        });

                        let current_value = self
                            .state
                            .bindings
                            .get(&id)
                            .cloned()
                            .or_else(|| {
                                if is_photo {
                                    self.photo_key_column
                                        .as_ref()
                                        .and_then(|k| (**k).clone())
                                        .or(model_binding.clone())
                                } else {
                                    model_binding.clone()
                                }
                            })
                            .unwrap_or_default();

                        let display_text = if current_value.is_empty() {
                            "(Select a column…)".to_owned()
                        } else {
                            current_value.clone()
                        };

                        let mut selected_col = current_value.clone();
                        let combo_id = format!("col-combo-{}", id);
                        egui::ComboBox::from_id_salt(combo_id)
                            .selected_text(&display_text)
                            .width(220.0)
                            .show_ui(ui, |ui| {
                                if ui
                                    .selectable_value(
                                        &mut selected_col,
                                        String::new(),
                                        "— None (Unmapped) —",
                                    )
                                    .clicked()
                                {
                                    self.state.clear_binding(&id);
                                    if is_photo {
                                        if let Some(key_col) = self.photo_key_column.as_deref_mut()
                                        {
                                            *key_col = None;
                                        }
                                        self.state.photo_key_column = None;
                                    }
                                }
                                for col in self.available_columns {
                                    if ui
                                        .selectable_value(
                                            &mut selected_col,
                                            col.clone(),
                                            col.clone(),
                                        )
                                        .clicked()
                                    {
                                        self.state.set_binding(id.clone(), col.clone());
                                        if is_photo {
                                            if let Some(key_col) =
                                                self.photo_key_column.as_deref_mut()
                                            {
                                                *key_col = Some(col.clone());
                                            }
                                            self.state.photo_key_column = Some(col.clone());
                                        }
                                    }
                                }
                            });

                        // Fallback text input for typing custom column names
                        let mut manual_input = selected_col.clone();
                        ui.label("or type:");
                        if ui
                            .add(
                                egui::TextEdit::singleline(&mut manual_input)
                                    .desired_width(120.0)
                                    .hint_text("Column name…"),
                            )
                            .changed()
                        {
                            self.state.set_binding(id.clone(), manual_input.clone());
                            if is_photo {
                                if let Some(key_col) = self.photo_key_column.as_deref_mut() {
                                    *key_col = (!manual_input.trim().is_empty())
                                        .then_some(manual_input.clone());
                                }
                                self.state.photo_key_column = (!manual_input.trim().is_empty())
                                    .then_some(manual_input.clone());
                            }
                        }
                    });

                    // Live sample value readout
                    if is_photo {
                        let key_col = self
                            .state
                            .binding_for(&id)
                            .or_else(|| {
                                self.photo_key_column
                                    .as_ref()
                                    .and_then(|k| k.as_deref())
                            })
                            .unwrap_or("PIN");

                        let key_val = self
                            .state
                            .sample_record
                            .as_ref()
                            .map(|rec| {
                                let v = rec.get_value(key_col);
                                if v.is_empty() {
                                    rec.pin_or_raw().to_owned()
                                } else {
                                    v
                                }
                            })
                            .unwrap_or_else(|| "<no sample>".into());

                        ui.horizontal(|ui| {
                            ui.label(format!("Lookup Key [{key_col}]:"));
                            ui.monospace(&key_val);

                            if let Some(match_result) = self.photo_match_result {
                                match match_result.status {
                                    crate::data::models::MatchStatus::Matched => {
                                        ui.colored_label(
                                            egui::Color32::from_rgb(34, 197, 94),
                                            format!(
                                                "✓ Matched photo: {}",
                                                match_result
                                                    .photo_path
                                                    .as_ref()
                                                    .map(|p| std::path::Path::new(p)
                                                        .file_name()
                                                        .unwrap_or_default()
                                                        .to_string_lossy()
                                                        .into_owned())
                                                    .unwrap_or_else(|| "Yes".into())
                                            ),
                                        );
                                    }
                                    crate::data::models::MatchStatus::Overridden => {
                                        ui.colored_label(
                                            egui::Color32::from_rgb(56, 189, 248),
                                            "✓ Manually Overridden",
                                        );
                                    }
                                    crate::data::models::MatchStatus::Ambiguous => {
                                        ui.colored_label(
                                            egui::Color32::from_rgb(249, 115, 22),
                                            "⚠ Multiple files matched",
                                        );
                                    }
                                    crate::data::models::MatchStatus::Missing => {
                                        ui.colored_label(
                                            egui::Color32::from_rgb(239, 68, 68),
                                            format!("✗ No photo found named '{key_val}' in photos folder"),
                                        );
                                    }
                                }
                            } else {
                                ui.small("(Photos folder not indexed or no record selected)");
                            }
                        });
                    } else {
                        let preview = self.state.preview_value(&id, self.template);
                        ui.horizontal(|ui| {
                            ui.label("Preview Value:");
                            ui.monospace(preview);
                        });
                    }
                });
            }
            ui.separator();
            ui.heading("Sample record");
            if let Some(record) = &self.state.sample_record {
                ui.label(format!(
                    "Row {} · PIN: {}",
                    record.row_index + 1,
                    record.pin_or_raw()
                ));
                egui::Grid::new("sample_record_mapping_grid")
                    .striped(true)
                    .show(ui, |ui| {
                        for (col_name, val) in &record.data {
                            ui.monospace(col_name);
                            match val {
                                serde_json::Value::String(s) => ui.label(s),
                                serde_json::Value::Null => ui.label("—"),
                                other => ui.label(other.to_string()),
                            };
                            ui.end_row();
                        }
                    });
            } else {
                ui.label("No sample record selected.");
            }
            ui.separator();
            let issues = self.state.validate(self.template).to_vec();
            if issues.is_empty() {
                ui.colored_label(
                    egui::Color32::from_rgb(40, 150, 70),
                    "✓ All dynamic elements are bound to spreadsheet columns.",
                );
            } else {
                ui.heading("Validation warnings");
                for issue in issues {
                    ui.colored_label(
                        egui::Color32::from_rgb(190, 110, 25),
                        format!("⚠ {}", issue.message),
                    );
                }
            }
        });
        before != self.state.bindings
    }
}
