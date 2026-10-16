use std::collections::BTreeMap;

use eframe::egui::{pos2, vec2, Rect};
use excel_id_card_rust::{
    data::models::{CanvasElement, SourceRecord, TemplateDefinition},
    ui::{
        CanvasTransform, EditorCommand, EditorHistory, MappingEditorState, TemplateEditor,
        TemplateEditorState,
    },
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

#[test]
fn new_canvas_dialog_converts_units_and_computes_exact_pixel_dimensions() {
    use excel_id_card_rust::ui::{
        BitDepth, CanvasUnit, ColorMode, NewCanvasDialogState, OrientationOption,
    };

    let mut state = NewCanvasDialogState::default();
    // Default is CR80: 85.60 x 53.98 mm @ 300 DPI Landscape
    let (w, h) = state.compute_pixel_dimensions();
    assert_eq!(w, 1011);
    assert_eq!(h, 638);

    // Switch orientation to Portrait
    state.set_orientation(OrientationOption::Portrait);
    assert_eq!(state.orientation, OrientationOption::Portrait);
    let (pw, ph) = state.compute_pixel_dimensions();
    assert_eq!(pw, 638);
    assert_eq!(ph, 1011);

    // Convert unit to Inches
    state.convert_unit(CanvasUnit::Inches);
    assert_eq!(state.unit, CanvasUnit::Inches);
    let (iw, ih) = state.compute_pixel_dimensions();
    assert!((iw as i32 - 638).abs() <= 2);
    assert!((ih as i32 - 1011).abs() <= 2);

    // Check color mode and bit depth build
    state.color_mode = ColorMode::Cmyk;
    state.bit_depth = BitDepth::SixteenBit;
    let template = state.build_template();
    assert_eq!(template.dpi, 300);
    assert_eq!(
        template.metadata.get("color_mode").and_then(|v| v.as_str()),
        Some("CMYK")
    );
    assert_eq!(
        template.metadata.get("bit_depth").and_then(|v| v.as_str()),
        Some("16 bit")
    );
}

#[test]
fn photoshop_editor_toolbox_and_transform_handles_support_tools_and_resizing() {
    use excel_id_card_rust::ui::{EditorTool, TemplateEditorState};

    let mut state = TemplateEditorState::default();
    assert_eq!(state.active_tool, EditorTool::Move);
    assert_eq!(state.active_tool.shortcut(), "V");
    assert_eq!(EditorTool::Text.shortcut(), "T");
    assert_eq!(EditorTool::Crop.shortcut(), "C");
    assert_eq!(EditorTool::Eyedropper.shortcut(), "I");

    // Dual color swatches
    let fg = state.foreground_color;
    let bg = state.background_color;
    state.swap_colors();
    assert_eq!(state.foreground_color, bg);
    assert_eq!(state.background_color, fg);
    state.reset_default_colors();
    assert_eq!(state.foreground_color, eframe::egui::Color32::BLACK);
    assert_eq!(state.background_color, eframe::egui::Color32::WHITE);

    // Resize command for TBox
    let mut template = TemplateDefinition {
        width_px: 1000,
        height_px: 600,
        elements: vec![element("box1", "rect")],
        ..Default::default()
    };
    let mut history = EditorHistory::default();
    assert!(history.execute(
        &mut template,
        EditorCommand::Resize {
            id: "box1".into(),
            new_x: 25.0,
            new_y: 35.0,
            new_width: 320.0,
            new_height: 180.0,
        }
    ));
    assert_eq!(template.elements[0].x, 25.0);
    assert_eq!(template.elements[0].y, 35.0);
    assert_eq!(template.elements[0].width, 320.0);
    assert_eq!(template.elements[0].height, 180.0);
}

#[test]
fn crop_canvas_command_updates_dimensions_shifts_elements_and_supports_undo_redo() {
    let mut template = TemplateDefinition {
        width_px: 1000,
        height_px: 600,
        elements: vec![element("card_photo", "photo"), element("card_text", "text")],
        ..Default::default()
    };
    template.elements[0].x = 100.0;
    template.elements[0].y = 150.0;
    template.elements[1].x = 300.0;
    template.elements[1].y = 150.0;

    let mut history = EditorHistory::default();

    // Crop: trim 50px from left, 60px from top, new size 800x500
    assert!(history.execute(
        &mut template,
        EditorCommand::CropCanvas {
            new_width: 800,
            new_height: 500,
            offset_x: 50.0,
            offset_y: 60.0,
        }
    ));

    assert_eq!(template.width_px, 800);
    assert_eq!(template.height_px, 500);
    assert_eq!(template.elements[0].x, 50.0);
    assert_eq!(template.elements[0].y, 90.0);
    assert_eq!(template.elements[1].x, 250.0);
    assert_eq!(template.elements[1].y, 90.0);

    // Undo restores original dimensions and coordinates
    assert!(history.undo(&mut template));
    assert_eq!(template.width_px, 1000);
    assert_eq!(template.height_px, 600);
    assert_eq!(template.elements[0].x, 100.0);
    assert_eq!(template.elements[0].y, 150.0);

    // Redo re-applies crop
    assert!(history.redo(&mut template));
    assert_eq!(template.width_px, 800);
    assert_eq!(template.height_px, 500);
    assert_eq!(template.elements[0].x, 50.0);
}

#[test]
fn background_color_and_gradient_commands_support_undo_redo() {
    let mut template = TemplateDefinition {
        background_color: "#FFFFFF".into(),
        ..Default::default()
    };
    let mut history = EditorHistory::default();

    // 1. Set background color (Paint Bucket on canvas)
    assert!(history.execute(
        &mut template,
        EditorCommand::SetBackgroundColor {
            color: "#1E3A8A".into()
        }
    ));
    assert_eq!(template.background_color, "#1E3A8A");

    // 2. Set background gradient
    assert!(history.execute(
        &mut template,
        EditorCommand::SetBackgroundGradient {
            from_color: "#1E3A8A".into(),
            to_color: "#0284C7".into(),
            angle: 90.0,
        }
    ));
    assert!(template.metadata.contains_key("background_gradient"));

    // Undo gradient -> back to solid color
    assert!(history.undo(&mut template));
    assert_eq!(template.background_color, "#1E3A8A");

    // Undo solid color -> back to white
    assert!(history.undo(&mut template));
    assert_eq!(template.background_color, "#FFFFFF");

    // Redo back to gradient
    assert!(history.redo(&mut template));
    assert!(history.redo(&mut template));
    assert!(template.metadata.contains_key("background_gradient"));
}

#[test]
fn batch_delete_removes_multiple_elements_with_undo() {
    let mut template = TemplateDefinition {
        elements: vec![
            element("b1", "brush"),
            element("b2", "brush"),
            element("t1", "text"),
            element("s1", "ellipse"),
        ],
        ..Default::default()
    };
    let mut history = EditorHistory::default();

    assert!(history.execute(
        &mut template,
        EditorCommand::BatchDelete {
            ids: vec!["b1".into(), "b2".into()]
        }
    ));
    assert_eq!(template.elements.len(), 2);
    assert_eq!(template.elements[0].id, "t1");
    assert_eq!(template.elements[1].id, "s1");

    assert!(history.undo(&mut template));
    assert_eq!(template.elements.len(), 4);
}

#[test]
fn renderer_handles_brush_ellipse_and_gradient_elements() {
    use excel_id_card_rust::rendering::NativeRenderer;

    let points = json!([[10.0, 10.0], [25.0, 40.0], [50.0, 30.0], [80.0, 70.0]]);
    let mut brush_elem = element("brush_1", "brush");
    brush_elem.static_content = Some(points.to_string());
    brush_elem.style.border_width = 4;
    brush_elem.style.font_color = "#DC2626".into();

    let mut ellipse_elem = element("circle_1", "ellipse");
    ellipse_elem.x = 20.0;
    ellipse_elem.y = 20.0;
    ellipse_elem.width = 60.0;
    ellipse_elem.height = 40.0;
    ellipse_elem.style.background_color = "#2563EB".into();
    ellipse_elem.style.border_color = "#1D4ED8".into();
    ellipse_elem.style.border_width = 2;

    let mut grad_elem = element("grad_1", "gradient");
    grad_elem.x = 0.0;
    grad_elem.y = 0.0;
    grad_elem.width = 100.0;
    grad_elem.height = 100.0;
    grad_elem.style.background_color = "#0F172A".into();
    grad_elem.style.border_color = "#38BDF8".into();

    let template = TemplateDefinition {
        width_px: 200,
        height_px: 150,
        dpi: 300,
        elements: vec![grad_elem, ellipse_elem, brush_elem],
        ..Default::default()
    };

    let rendered = NativeRenderer::render(&template, None, None);
    assert!(rendered.is_ok(), "Render must succeed without errors");
    let result = rendered.unwrap();
    assert_eq!(result.image.width(), 200);
    assert_eq!(result.image.height(), 150);
}

#[test]
fn text_editing_and_update_text_command_support_undo_redo_and_helpers() {
    let mut template = TemplateDefinition {
        elements: vec![element("heading", "text")],
        ..Default::default()
    };
    template.elements[0].static_content = Some("Initial Text".into());

    let mut state = TemplateEditorState::default();
    let mut editor = TemplateEditor::new(&mut template, &mut state);

    // Start editing text
    editor.start_editing_text("heading".into());
    assert_eq!(editor.state.editing_text_id.as_deref(), Some("heading"));
    assert_eq!(editor.state.editing_text_buffer, "Initial Text");

    // Modify buffer and commit
    editor.state.editing_text_buffer = "Updated Title".into();
    editor.commit_editing_text();
    assert_eq!(editor.state.editing_text_id, None);
    assert_eq!(
        editor.template.elements[0].static_content.as_deref(),
        Some("Updated Title")
    );

    // Undo should restore initial text
    assert!(editor.state.undo(editor.template));
    assert_eq!(
        editor.template.elements[0].static_content.as_deref(),
        Some("Initial Text")
    );

    // Redo should restore updated title
    assert!(editor.state.history.redo(editor.template));
    assert_eq!(
        editor.template.elements[0].static_content.as_deref(),
        Some("Updated Title")
    );
}

#[test]
fn resize_enforces_minimum_bounds_for_text_and_shapes_to_prevent_overlap() {
    let mut template = TemplateDefinition {
        elements: vec![element("txt1", "text"), element("rect1", "rect")],
        ..Default::default()
    };
    let mut history = EditorHistory::default();

    // Attempt to reduce text box to 2.0 x 2.0 px
    assert!(history.execute(
        &mut template,
        EditorCommand::Resize {
            id: "txt1".into(),
            new_x: 10.0,
            new_y: 10.0,
            new_width: 2.0,
            new_height: 2.0,
        }
    ));
    // Text elements must enforce min width >= 40.0 and min height >= 20.0
    assert!(template.elements[0].width >= 40.0);
    assert!(template.elements[0].height >= 20.0);

    // Attempt to reduce rectangle shape to 2.0 x 2.0 px
    assert!(history.execute(
        &mut template,
        EditorCommand::Resize {
            id: "rect1".into(),
            new_x: 50.0,
            new_y: 50.0,
            new_width: 2.0,
            new_height: 2.0,
        }
    ));
    // Shapes must enforce min width >= 24.0 and min height >= 24.0
    assert!(template.elements[1].width >= 24.0);
    assert!(template.elements[1].height >= 24.0);
}

#[test]
fn crop_tool_custom_dimensions_and_drag_selection_support() {
    use excel_id_card_rust::ui::{CanvasUnit, CropAspectPreset, EditorTool, TemplateEditor};

    let mut template = TemplateDefinition {
        width_px: 1200,
        height_px: 800,
        dpi: 300,
        ..Default::default()
    };

    let mut state = TemplateEditorState::default();
    let mut editor = TemplateEditor::new(&mut template, &mut state);

    // Initial state
    assert_eq!(editor.state.crop_aspect_preset, CropAspectPreset::Free);
    assert_eq!(editor.state.crop_unit, CanvasUnit::Pixels);
    assert_eq!(editor.template.dpi, 300);

    // Apply custom crop dimensions
    editor.apply_crop_dimensions(600.0, 400.0);
    assert_eq!(editor.state.crop_width, 600.0);
    assert_eq!(editor.state.crop_height, 400.0);
    let rect = editor.state.crop_rect.expect("crop_rect should be Some");
    assert_eq!(rect.width(), 600.0);
    assert_eq!(rect.height(), 400.0);

    // Setting custom aspect preset
    editor.state.crop_aspect_preset = CropAspectPreset::Custom;
    assert_eq!(
        editor.state.crop_aspect_preset.label(),
        "Custom Size (W × H)"
    );

    // Verify unit switching (mm, cm, in, px)
    editor.state.crop_unit = CanvasUnit::Millimeters;
    assert_eq!(editor.state.crop_unit.short_code(), "mm");
    editor.state.crop_unit = CanvasUnit::Centimeters;
    assert_eq!(editor.state.crop_unit.short_code(), "cm");
    editor.state.crop_unit = CanvasUnit::Inches;
    assert_eq!(editor.state.crop_unit.short_code(), "in");
    editor.state.crop_unit = CanvasUnit::Pixels;
    assert_eq!(editor.state.crop_unit.short_code(), "px");

    // Commit crop modifies template dimensions
    editor.commit_crop();
    assert_eq!(editor.template.width_px, 600);
    assert_eq!(editor.template.height_px, 400);
    assert_eq!(editor.state.active_tool, EditorTool::Move);
    assert!(editor.state.crop_rect.is_none());
}

#[test]
fn eraser_carves_brush_stroke_section_without_deleting_entire_object() {
    use eframe::egui::Pos2;
    use excel_id_card_rust::ui::template_editor::parse_brush_paths;

    let points = json!([
        [10.0, 50.0],
        [20.0, 50.0],
        [30.0, 50.0],
        [40.0, 50.0],
        [50.0, 50.0],
        [60.0, 50.0],
        [70.0, 50.0],
        [80.0, 50.0],
        [90.0, 50.0],
        [100.0, 50.0]
    ]);
    let mut brush_elem = element("brush_1", "brush");
    brush_elem.x = 10.0;
    brush_elem.y = 50.0;
    brush_elem.width = 90.0;
    brush_elem.height = 2.0;
    brush_elem.static_content = Some(points.to_string());
    brush_elem.style.border_width = 4;

    let mut template = TemplateDefinition {
        elements: vec![brush_elem],
        ..Default::default()
    };

    // Erase across the middle at x=50.0, y=50.0 with radius 8.0
    let modified = TemplateEditor::erase_brush_strokes(
        &mut template,
        Pos2::new(50.0, 50.0),
        Pos2::new(50.0, 50.0),
        8.0,
    );
    assert!(modified, "Eraser should have modified the brush stroke");

    // The brush element must NOT be deleted!
    assert_eq!(
        template.elements.len(),
        1,
        "Brush element must survive when only a section is erased"
    );
    let elem = &template.elements[0];
    assert_eq!(elem.id, "brush_1");

    // Static content should now contain 2 separate sub-paths (before x=50 and after x=50)
    let content = elem.static_content.as_deref().unwrap();
    let paths = parse_brush_paths(content);
    assert_eq!(paths.len(), 2, "Stroke should be split into 2 sub-paths");

    // First subpath should be on the left (x < 50)
    for pt in &paths[0] {
        assert!(
            pt[0] < 45.0,
            "Left segment point x={} should be < 45.0",
            pt[0]
        );
    }
    // Second subpath should be on the right (x > 50)
    for pt in &paths[1] {
        assert!(
            pt[0] > 55.0,
            "Right segment point x={} should be > 55.0",
            pt[0]
        );
    }
}

#[test]
fn eraser_deletes_brush_stroke_only_when_fully_erased() {
    use eframe::egui::Pos2;

    let points = json!([[10.0, 10.0], [20.0, 20.0], [30.0, 30.0]]);
    let mut brush_elem = element("brush_small", "brush");
    brush_elem.x = 10.0;
    brush_elem.y = 10.0;
    brush_elem.width = 20.0;
    brush_elem.height = 20.0;
    brush_elem.static_content = Some(points.to_string());
    brush_elem.style.border_width = 4;

    let mut template = TemplateDefinition {
        elements: vec![brush_elem],
        ..Default::default()
    };

    // Erase with huge radius covering the entire stroke
    let modified = TemplateEditor::erase_brush_strokes(
        &mut template,
        Pos2::new(20.0, 20.0),
        Pos2::new(20.0, 20.0),
        50.0,
    );
    assert!(modified);
    assert_eq!(
        template.elements.len(),
        0,
        "Stroke should only be removed when all its points are erased"
    );
}

#[test]
fn eraser_undo_and_redo_works_seamlessly_for_carved_brush_strokes() {
    use eframe::egui::Pos2;
    use excel_id_card_rust::ui::template_editor::parse_brush_paths;

    let points = json!([
        [10.0, 10.0],
        [30.0, 10.0],
        [50.0, 10.0],
        [70.0, 10.0],
        [90.0, 10.0]
    ]);
    let mut brush_elem = element("stroke_undo", "brush");
    brush_elem.x = 10.0;
    brush_elem.y = 10.0;
    brush_elem.width = 80.0;
    brush_elem.height = 4.0;
    brush_elem.static_content = Some(points.to_string());
    brush_elem.style.border_width = 4;

    let mut template = TemplateDefinition {
        elements: vec![brush_elem],
        ..Default::default()
    };
    let mut state = TemplateEditorState::default();

    // Snapshot before erase
    let before = template.clone();

    // Erase section around (50.0, 10.0)
    let modified = TemplateEditor::erase_brush_strokes(
        &mut template,
        Pos2::new(50.0, 10.0),
        Pos2::new(50.0, 10.0),
        8.0,
    );
    assert!(modified);
    state
        .history
        .record_action(before, &template, "Erase Brush Stroke".into());

    let paths_after_erase =
        parse_brush_paths(template.elements[0].static_content.as_deref().unwrap());
    assert_eq!(paths_after_erase.len(), 2);

    // Undo should restore single contiguous stroke
    assert!(state.history.undo(&mut template));
    let paths_after_undo =
        parse_brush_paths(template.elements[0].static_content.as_deref().unwrap());
    assert_eq!(paths_after_undo.len(), 1);

    // Redo should carve it back to 2 sub-paths
    assert!(state.history.redo(&mut template));
    let paths_after_redo =
        parse_brush_paths(template.elements[0].static_content.as_deref().unwrap());
    assert_eq!(paths_after_redo.len(), 2);
}

#[test]
fn eraser_preserves_untouched_stroke_boundaries_and_non_brush_elements() {
    use eframe::egui::Pos2;
    use excel_id_card_rust::ui::template_editor::parse_brush_paths;

    // Stroke 1: From x=10 to x=50 at y=20
    let points1 = json!([
        [10.0, 20.0],
        [20.0, 20.0],
        [30.0, 20.0],
        [40.0, 20.0],
        [50.0, 20.0]
    ]);
    let mut brush1 = element("brush_far", "brush");
    brush1.x = 10.0;
    brush1.y = 20.0;
    brush1.width = 40.0;
    brush1.height = 2.0;
    brush1.static_content = Some(points1.to_string());

    // Stroke 2: From x=100 to x=200 at y=20
    let points2 = json!([[100.0, 20.0], [150.0, 20.0], [200.0, 20.0]]);
    let mut brush2 = element("brush_cut", "brush");
    brush2.x = 100.0;
    brush2.y = 20.0;
    brush2.width = 100.0;
    brush2.height = 2.0;
    brush2.static_content = Some(points2.to_string());

    // Card background rectangle element
    let mut card_bg = element("card_boundary", "rect");
    card_bg.x = 0.0;
    card_bg.y = 0.0;
    card_bg.width = 300.0;
    card_bg.height = 200.0;

    let mut template = TemplateDefinition {
        elements: vec![card_bg, brush1, brush2],
        ..Default::default()
    };

    // Erase across brush2 at (150.0, 20.0) with radius 5.0
    let modified = TemplateEditor::erase_brush_strokes(
        &mut template,
        Pos2::new(150.0, 20.0),
        Pos2::new(150.0, 20.0),
        5.0,
    );
    assert!(modified);

    // Card boundary rectangle MUST still exist!
    assert_eq!(
        template.elements[0].id, "card_boundary",
        "Non-brush boundary element must never be deleted by eraser"
    );

    // Untouched brush1 MUST still have identical endpoints and content
    assert_eq!(template.elements[1].id, "brush_far");
    let paths1 = parse_brush_paths(template.elements[1].static_content.as_deref().unwrap());
    assert_eq!(paths1.len(), 1);
    assert_eq!(paths1[0].len(), 5);
    assert_eq!(
        paths1[0][0],
        [10.0, 20.0],
        "Start boundary point must not be reduced"
    );
    assert_eq!(
        paths1[0][4],
        [50.0, 20.0],
        "End boundary point must not be reduced"
    );

    // Contacted brush2 MUST have its outer boundaries preserved (100.0 and 200.0)
    assert_eq!(template.elements[2].id, "brush_cut");
    let paths2 = parse_brush_paths(template.elements[2].static_content.as_deref().unwrap());
    assert_eq!(paths2.len(), 2);
    assert_eq!(
        paths2[0][0],
        [100.0, 20.0],
        "Left boundary must be preserved"
    );
    assert_eq!(
        paths2[1].last().copied().unwrap(),
        [200.0, 20.0],
        "Right boundary must be preserved"
    );
}
