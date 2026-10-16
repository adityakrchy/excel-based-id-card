//! Template compatibility and persistence-facing exports.

pub use crate::data::models::{CanvasElement, CanvasElementStyle, TemplateDefinition};

use serde_json::Error as JsonError;
use thiserror::Error;

const CLASSIC_PORTRAIT: &str =
    include_str!("../id_card_generator/templates/builtins/classic_portrait.json");
const MODERN_CORPORATE: &str =
    include_str!("../id_card_generator/templates/builtins/modern_corporate.json");
const OFFICE_ID_CARD: &str =
    include_str!("../id_card_generator/templates/builtins/office_id_card.json");

#[derive(Debug, Error)]
pub enum TemplateError {
    #[error("unknown built-in template: {0}")]
    UnknownBuiltin(String),
    #[error("could not parse built-in template {name}: {source}")]
    InvalidBuiltin {
        name: String,
        #[source]
        source: JsonError,
    },
}

/// Stable IDs for the templates shipped with the Python implementation.
pub const BUILTIN_TEMPLATE_IDS: &[&str] = &[
    "builtin-classic-portrait",
    "builtin-modern-corporate",
    "builtin-office-id-card",
];

pub fn builtin_template_json(id: &str) -> Option<&'static str> {
    match id {
        "builtin-classic-portrait" => Some(CLASSIC_PORTRAIT),
        "builtin-modern-corporate" => Some(MODERN_CORPORATE),
        "builtin-office-id-card" => Some(OFFICE_ID_CARD),
        _ => None,
    }
}

pub fn load_builtin_template(id: &str) -> Result<TemplateDefinition, TemplateError> {
    let json =
        builtin_template_json(id).ok_or_else(|| TemplateError::UnknownBuiltin(id.to_owned()))?;
    serde_json::from_str(json).map_err(|source| TemplateError::InvalidBuiltin {
        name: id.to_owned(),
        source,
    })
}

pub fn builtin_templates() -> Result<Vec<TemplateDefinition>, TemplateError> {
    BUILTIN_TEMPLATE_IDS
        .iter()
        .map(|id| load_builtin_template(id))
        .collect()
}
