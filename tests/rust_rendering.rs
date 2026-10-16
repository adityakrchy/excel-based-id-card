use std::{collections::BTreeMap, io::Cursor, path::Path};

use excel_id_card_rust::{
    data::models::{
        CanvasElement, CanvasElementStyle, MissingPhotoPolicy, OutputFormat, RenderSettings,
        SourceRecord, TemplateDefinition, TextOverflowPolicy,
    },
    rendering::{NativeRenderer, RenderWarning},
};
use serde_json::json;

fn settings() -> RenderSettings {
    RenderSettings {
        dpi: 300,
        output_format: OutputFormat::Png,
        jpeg_quality: 95,
        missing_photo_policy: MissingPhotoPolicy::GenerateWithPlaceholder,
        text_overflow_policy: TextOverflowPolicy::AutoShrink,
    }
}

fn element(element_type: &str, x: f64, y: f64, width: f64, height: f64) -> CanvasElement {
    CanvasElement {
        id: element_type.into(),
        name: element_type.into(),
        r#type: element_type.into(),
        x,
        y,
        width,
        height,
        z_index: 0,
        visible: true,
        locked: false,
        binding: None,
        static_content: None,
        style: CanvasElementStyle::default(),
    }
}

fn record() -> SourceRecord {
    SourceRecord {
        record_id: "record-1".into(),
        row_index: 1,
        raw_pin: "0007".into(),
        pin: "0007".into(),
        data: BTreeMap::from([("Name".into(), json!("Ada Lovelace"))]),
        validation_errors: Vec::new(),
        validation_warnings: Vec::new(),
    }
}

#[test]
fn renderer_uses_template_pixel_dimensions() {
    let template = TemplateDefinition {
        width_px: 37,
        height_px: 23,
        ..Default::default()
    };

    let rendered = NativeRenderer::render(&template, None, None).unwrap();

    assert_eq!(rendered.dimensions(), (37, 23));
    assert_eq!(rendered.image.get_pixel(0, 0).0, [255, 255, 255, 255]);
}

#[test]
fn renderer_draws_background_shapes_and_respects_z_order() {
    let mut back = element("rect", 2.0, 2.0, 18.0, 12.0);
    back.z_index = 1;
    back.style.background_color = "#0000FF".into();

    let mut front = element("rect", 5.0, 5.0, 8.0, 6.0);
    front.z_index = 2;
    front.style.background_color = "#FF0000".into();

    let mut rounded = element("round_rect", 22.0, 2.0, 12.0, 12.0);
    rounded.style.background_color = "#00FF00".into();
    rounded.style.border_radius = 4;

    let template = TemplateDefinition {
        width_px: 40,
        height_px: 20,
        background_color: "#112233".into(),
        elements: vec![front, rounded, back],
        ..Default::default()
    };
    let rendered = NativeRenderer::render(&template, None, None).unwrap();

    assert_eq!(rendered.image.get_pixel(0, 0).0, [17, 34, 51, 255]);
    assert_eq!(rendered.image.get_pixel(6, 6).0, [255, 0, 0, 255]);
    assert_eq!(rendered.image.get_pixel(3, 3).0, [0, 0, 255, 255]);
    assert_eq!(rendered.image.get_pixel(22, 2).0, [17, 34, 51, 255]);
    assert_eq!(rendered.image.get_pixel(27, 7).0, [0, 255, 0, 255]);
}

#[test]
fn renderer_binds_dynamic_text_from_source_record() {
    let mut text = element("dynamic_text", 2.0, 2.0, 116.0, 28.0);
    text.binding = Some("Name".into());
    text.style.font_size = 18;
    text.style.font_color = "#000000".into();
    text.style.wrap = false;
    let template = TemplateDefinition {
        width_px: 120,
        height_px: 32,
        elements: vec![text],
        ..Default::default()
    };

    let rendered = NativeRenderer::render(&template, Some(&record()), None).unwrap();

    assert!(!rendered
        .warnings
        .iter()
        .any(|warning| matches!(warning, RenderWarning::MissingFont { .. })));
    let non_white_pixels = rendered
        .image
        .pixels()
        .filter(|pixel| pixel.0[0] < 240 || pixel.0[1] < 240 || pixel.0[2] < 240)
        .count();
    assert!(
        non_white_pixels > 0,
        "dynamic text should affect the rendered image"
    );
}

#[test]
fn renderer_warns_and_generates_safe_placeholder_for_missing_photo() {
    let photo = element("photo", 2.0, 2.0, 16.0, 16.0);
    let template = TemplateDefinition {
        width_px: 24,
        height_px: 24,
        elements: vec![photo],
        ..Default::default()
    };

    let rendered =
        NativeRenderer::render(&template, Some(&record()), Some(Path::new("missing.jpg"))).unwrap();

    assert!(rendered
        .warnings
        .iter()
        .any(|warning| matches!(warning, RenderWarning::MissingPhoto { pin } if pin == "0007")));
    assert_eq!(rendered.dimensions(), (24, 24));
}

#[test]
fn renderer_encodes_png_with_template_dimensions_and_dpi_chunk() {
    let template = TemplateDefinition {
        width_px: 12,
        height_px: 9,
        dpi: 300,
        ..Default::default()
    };
    let rendered = NativeRenderer::render(&template, None, None).unwrap();
    let mut bytes = Cursor::new(Vec::new());

    rendered.encode(&template, &settings(), &mut bytes).unwrap();

    assert_eq!(&bytes.get_ref()[..8], b"\x89PNG\r\n\x1a\n");
    assert!(bytes.get_ref().windows(4).any(|chunk| chunk == b"IHDR"));
    assert!(bytes.get_ref().windows(4).any(|chunk| chunk == b"pHYs"));
}
