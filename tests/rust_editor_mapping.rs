use std::collections::BTreeMap;

use eframe::egui::{pos2, vec2, Rect};
use excel_id_card_rust::{
    data::models::{CanvasElement, SourceRecord, TemplateDefinition},
    ui::{CanvasTransform, EditorCommand, EditorHistory, MappingEditorState},
};
use serde_json::json;

fn element(id: &str, kind: &str) -> CanvasElement {
    CanvasElement {
        id: id.into(),
        name: id.into(),
        r#type: kind.into(),
        x: 10.0,
        y: 20.0,
        width: 100.0,
        height: 40.0,
        z_index: 0,
        ..serde_json::from_value(json!({})).unwrap()
    }
}

#[test]
fn canvas_transform_round_trips_scene_coordinates() {
    let template = TemplateDefinition {
        width_px: 1000,
        height_px: 500,
        ..Default::default()
    };
    let transform = CanvasTransform::fit(
        Rect::from_min_size(pos2(20.0, 30.0), vec2(800.0, 600.0)),
        &template,
        1.0,
        vec2(12.0, -8.0),
    );
    let scene = pos2(250.0, 120.0);
    let screen = transform.scene_to_screen(scene);
    let round_trip = transform.screen_to_scene(screen);
    assert!((round_trip.x - scene.x).abs() < 0.001);
    assert!((round_trip.y - scene.y).abs() < 0.001);
}

#[test]
fn editor_commands_cover_move_duplicate_delete_and_z_order_with_undo_redo() {
    let mut template = TemplateDefinition {
        elements: vec![element("one", "dynamic_text"), element("two", "rect")],
        ..Default::default()
    };
    template.elements[1].z_index = 1;
    let mut history = EditorHistory::default();
    assert!(history.execute(
        &mut template,
        EditorCommand::Move {
            id: "one".into(),
            delta: vec2(5.0, -2.0)
        }
    ));
    assert_eq!(
        (template.elements[0].x, template.elements[0].y),
        (15.0, 18.0)
    );
    assert!(history.execute(&mut template, EditorCommand::Duplicate { id: "one".into() }));
    assert_eq!(template.elements.len(), 3);
    assert!(history.execute(
        &mut template,
        EditorCommand::BringToFront { id: "one".into() }
    ));
    assert!(
        template
            .elements
            .iter()
            .find(|item| item.id == "one")
            .unwrap()
            .z_index
            > 1
    );
    assert!(history.execute(&mut template, EditorCommand::Delete { id: "two".into() }));
    assert_eq!(template.elements.len(), 2);
    assert!(history.undo(&mut template));
    assert!(template.get_element_by_id("two").is_some());
    assert!(history.redo(&mut template));
    assert!(template.get_element_by_id("two").is_none());
}

#[test]
fn mapping_accepts_arbitrary_columns_previews_values_and_reports_warnings() {
    let template = TemplateDefinition {
        elements: vec![element("name", "dynamic_text"), element("photo", "photo")],
        ..Default::default()
    };
    let mut state = MappingEditorState::default();
    state.set_binding("name", "Employee Name");
    state.set_binding("photo", "Portrait File");
    state.sample_record = Some(SourceRecord {
        record_id: "r1".into(),
        row_index: 4,
        raw_pin: String::new(),
        pin: String::new(),
        data: BTreeMap::from([("Employee Name".into(), json!("Ada"))]),
        validation_errors: vec![],
        validation_warnings: vec![],
    });
    assert_eq!(state.preview_value("name", &template), "Ada");
    let issues = state.validate(&template).to_vec();
    assert_eq!(issues.len(), 1);
    assert!(issues[0].message.contains("Portrait File"));
    state.set_binding("photo", "Portrait File");
    state
        .sample_record
        .as_mut()
        .unwrap()
        .data
        .insert("Portrait File".into(), json!("ada.png"));
    assert!(state.validate(&template).is_empty());
}

#[test]
fn photoshop_editor_supports_alignment_swatches_and_history_action_stack() {
    use excel_id_card_rust::ui::{AlignmentType, SwatchTarget, SWATCHES};

    let mut template = TemplateDefinition {
        width_px: 1000,
        height_px: 600,
        elements: vec![element("badge", "rect")],
        ..Default::default()
    };
    template.elements[0].width = 200.0;
    template.elements[0].height = 100.0;
    template.elements[0].x = 50.0;
    template.elements[0].y = 50.0;

    let mut history = EditorHistory::default();

    // 1. Alignment command
    assert!(history.execute(
        &mut template,
        EditorCommand::Align {
            id: "badge".into(),
            alignment: AlignmentType::CenterOnCard,
        }
    ));
    assert_eq!(template.elements[0].x, 400.0);
    assert_eq!(template.elements[0].y, 250.0);
    assert_eq!(history.action_names.len(), 1);
    assert!(history.action_names[0].contains("Align"));

    // 2. Swatch color update
    let corporate_blue = SWATCHES[4].0;
    assert!(history.execute(
        &mut template,
        EditorCommand::UpdateColor {
            id: "badge".into(),
            target: SwatchTarget::Fill,
            color: corporate_blue.into(),
        }
    ));
    assert_eq!(template.elements[0].style.background_color, corporate_blue);
    assert_eq!(history.action_names.len(), 2);

    // 3. Undo both and verify restoration
    assert!(history.undo(&mut template));
    assert_ne!(template.elements[0].style.background_color, corporate_blue);
    assert!(history.undo(&mut template));
    assert_eq!(template.elements[0].x, 50.0);
    assert_eq!(template.elements[0].y, 50.0);

    // 4. Redo alignment
    assert!(history.redo(&mut template));
    assert_eq!(template.elements[0].x, 400.0);
}
