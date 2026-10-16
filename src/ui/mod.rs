//! Native `egui` widgets for the template and mapping editors.
//!
//! The widgets deliberately operate on the typed persistence models instead of
//! introducing a second template format.  Their state is transient UI state;
//! callers retain ownership of the template and can persist it normally.

pub mod mapping_editor;
pub mod new_canvas_dialog;
pub mod template_editor;

pub use mapping_editor::{ElementMapping, MappingEditor, MappingEditorState, MappingIssue};
pub use new_canvas_dialog::{
    BackgroundType, BitDepth, CanvasPreset, CanvasUnit, ColorMode, DpiUnit, NewCanvasDialogState,
    OrientationOption, CANVAS_PRESETS,
};
pub use template_editor::{
    AlignmentType, CanvasTransform, CropAspectPreset, EditorCommand, EditorHistory, EditorTab,
    EditorTool, ShapeKind, SwatchTarget, TemplateEditor, TemplateEditorState, TransformHandle,
    SWATCHES,
};
