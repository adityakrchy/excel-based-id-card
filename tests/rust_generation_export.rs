use std::{collections::BTreeMap, fs, path::PathBuf};

use excel_id_card_rust::{
    data::models::{
        ExportConfiguration, MissingPhotoPolicy, OutputFormat, RenderSettings, ReviewRecord,
        ReviewStatus, SourceRecord, TemplateDefinition, TextOverflowPolicy,
    },
    export::{ExportManager, ExportRequest},
    generation::{CancellationToken, GenerationEvent, GenerationOptions},
};
use serde_json::json;
use tempfile::tempdir;

fn record(id: &str, pin: &str, name: &str) -> SourceRecord {
    SourceRecord {
        record_id: id.into(),
        row_index: 1,
        raw_pin: pin.into(),
        pin: pin.into(),
        data: BTreeMap::from([
            ("Name".into(), json!(name)),
            ("Department".into(), json!("Engineering")),
        ]),
        validation_errors: Vec::new(),
        validation_warnings: Vec::new(),
    }
}

fn settings(policy: MissingPhotoPolicy) -> RenderSettings {
    RenderSettings {
        dpi: 300,
        output_format: OutputFormat::Png,
        jpeg_quality: 88,
        missing_photo_policy: policy,
        text_overflow_policy: TextOverflowPolicy::AutoShrink,
    }
}

fn config(directory: &std::path::Path) -> ExportConfiguration {
    ExportConfiguration {
        output_dir: directory.display().to_string(),
        format: OutputFormat::Png,
        jpeg_quality: 88,
        naming_pattern: "{PIN_NUMBER}_{NAME}".into(),
        approved_only: true,
        export_manifest: true,
        export_contact_sheet: false,
        open_output_dir_on_complete: false,
    }
}

#[test]
fn generation_sanitizes_names_and_resolves_existing_and_batch_collisions() {
    let directory = tempdir().unwrap();
    fs::write(directory.path().join("7_Ada_Smith.png"), b"existing").unwrap();
    let records = vec![
        record("one", "7", "Ada/Smith"),
        record("two", "7", "Ada/Smith"),
    ];
    let mut options = GenerationOptions::new(directory.path());
    options.settings = settings(MissingPhotoPolicy::GenerateWithPlaceholder);
    options.max_parallelism = 2;
    options.naming_pattern = "{PIN_NUMBER}_{NAME}".into();

    let summary = excel_id_card_rust::generation::generate_batch(
        &TemplateDefinition {
            width_px: 12,
            height_px: 12,
            ..Default::default()
        },
        &records,
        None,
        &options,
        &CancellationToken::new(),
    )
    .unwrap();

    assert_eq!(summary.completed_count, 2);
    let names: Vec<String> = summary
        .results
        .iter()
        .map(|result| {
            result
                .output_path
                .as_ref()
                .unwrap()
                .file_name()
                .unwrap()
                .to_string_lossy()
                .into_owned()
        })
        .collect();
    assert_eq!(names, vec!["7_Ada_Smith_2.png", "7_Ada_Smith_3.png"]);
    assert!(names.iter().all(|name| !name.contains('/')));
}

#[test]
fn generation_reports_cancellation_and_render_errors_in_source_order() {
    let directory = tempdir().unwrap();
    let records = vec![record("one", "1", "One"), record("two", "2", "Two")];
    let token = CancellationToken::new();
    token.cancel();
    let (sender, receiver) = std::sync::mpsc::channel();
    let mut options = GenerationOptions::new(directory.path());
    options.progress = Some(sender);
    let summary = excel_id_card_rust::generation::generate_batch(
        &TemplateDefinition::default(),
        &records,
        None,
        &options,
        &token,
    )
    .unwrap();
    assert!(summary.cancelled);
    assert_eq!(summary.cancelled_count, 2);
    assert_eq!(summary.results[0].record_id, "one");
    assert!(matches!(
        receiver.recv().unwrap(),
        GenerationEvent::Record { index: 0, .. }
    ));

    let failing = excel_id_card_rust::generation::generate_batch(
        &TemplateDefinition {
            width_px: 0,
            height_px: 12,
            ..Default::default()
        },
        &[record("bad", "3", "Bad")],
        None,
        &GenerationOptions::new(directory.path()),
        &CancellationToken::new(),
    )
    .unwrap();
    assert_eq!(failing.failed_count, 1);
    assert!(failing.results[0].error.is_some());
}

#[test]
fn export_filters_review_state_and_writes_bom_manifest_with_arbitrary_columns() {
    let staging = tempdir().unwrap();
    let output = tempdir().unwrap();
    let records = vec![
        record("approved", "1", "Alice"),
        record("rejected", "2", "Bob"),
    ];
    let mut options = GenerationOptions::new(staging.path());
    options.settings = settings(MissingPhotoPolicy::GenerateWithPlaceholder);
    let generated = excel_id_card_rust::generation::generate_batch(
        &TemplateDefinition {
            width_px: 10,
            height_px: 10,
            ..Default::default()
        },
        &records,
        None,
        &options,
        &CancellationToken::new(),
    )
    .unwrap();
    let generated_map = generated
        .results
        .into_iter()
        .map(|result| (result.record_id.clone(), result))
        .collect();
    let reviews = vec![
        ReviewRecord {
            record_id: "approved".into(),
            pin: "1".into(),
            name: "Alice".into(),
            status: ReviewStatus::Approved,
            comments: None,
            rendered_image_path: None,
            last_reviewed_at: None,
        },
        ReviewRecord {
            record_id: "rejected".into(),
            pin: "2".into(),
            name: "Bob".into(),
            status: ReviewStatus::Rejected,
            comments: None,
            rendered_image_path: None,
            last_reviewed_at: None,
        },
    ];
    let source_map = records
        .into_iter()
        .map(|record| (record.record_id.clone(), record))
        .collect();
    let result = ExportManager::export_batch(ExportRequest {
        config: &config(output.path()),
        review_records: &reviews,
        source_records: &source_map,
        generated_results: &generated_map,
        match_results: None,
        template: None,
    })
    .unwrap();

    assert_eq!(result.total_records, 2);
    assert_eq!(result.exported_count, 1);
    assert_eq!(result.skipped_count, 1);
    assert_eq!(result.failed_count, 0);
    let manifest = PathBuf::from(result.manifest_path.unwrap());
    let bytes = fs::read(&manifest).unwrap();
    assert_eq!(&bytes[..3], b"\xEF\xBB\xBF");
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(true)
        .from_reader(&bytes[3..]);
    let headers = reader
        .headers()
        .unwrap()
        .iter()
        .map(str::to_owned)
        .collect::<Vec<_>>();
    assert!(headers.contains(&"Department".into()));
    assert!(headers.contains(&"Output Filename".into()));
    assert!(output.path().join("1_Alice.png").is_file());
    assert!(!output.path().join("2_Bob.png").exists());

    let jpeg_output = tempdir().unwrap();
    let mut jpeg_config = config(jpeg_output.path());
    jpeg_config.format = OutputFormat::Jpeg;
    jpeg_config.jpeg_quality = 72;
    jpeg_config.approved_only = false;
    jpeg_config.export_manifest = false;
    let jpeg_result = ExportManager::export_batch(ExportRequest {
        config: &jpeg_config,
        review_records: &reviews,
        source_records: &source_map,
        generated_results: &generated_map,
        match_results: None,
        template: None,
    })
    .unwrap();
    assert_eq!(jpeg_result.exported_count, 2);
    assert!(jpeg_output.path().join("1_Alice.jpg").is_file());
    assert!(jpeg_output.path().join("2_Bob.jpg").is_file());
}

#[test]
fn contact_sheet_export_arranges_cards_in_grid_and_writes_png() {
    use excel_id_card_rust::export::{
        ContactSheetCardItem, ContactSheetGenerator, ContactSheetOptions, PageSize,
    };

    let dir = tempdir().unwrap();
    let img1_path = dir.path().join("card1.png");
    let img2_path = dir.path().join("card2.png");
    let img3_path = dir.path().join("card3.png");

    // Write simple valid PNGs for test cards
    let sample = image::RgbaImage::from_pixel(300, 200, image::Rgba([40, 80, 160, 255]));
    sample.save(&img1_path).unwrap();
    sample.save(&img2_path).unwrap();
    sample.save(&img3_path).unwrap();

    let cards = vec![
        ContactSheetCardItem {
            image_path: img1_path,
            pin: "101".into(),
            name: "John Doe".into(),
        },
        ContactSheetCardItem {
            image_path: img2_path,
            pin: "102".into(),
            name: "Jane Smith".into(),
        },
        ContactSheetCardItem {
            image_path: img3_path,
            pin: "103".into(),
            name: "Alex Taylor".into(),
        },
    ];

    let out_dir = dir.path().join("sheets");
    let options = ContactSheetOptions {
        page_size: PageSize::Custom {
            width_px: 800,
            height_px: 1000,
        },
        dpi: 150,
        columns: 2,
        rows: 2,
        margin_px: 40,
        spacing_px: 20,
        title: "Test Contact Sheet".into(),
        draw_cut_marks: true,
        draw_card_borders: true,
        draw_labels: true,
    };

    let sheets = ContactSheetGenerator::generate_sheets(&cards, &out_dir, &options).unwrap();
    assert_eq!(sheets.len(), 1);
    assert!(sheets[0].is_file());

    // Verify generated sheet dimensions
    let sheet_img = image::open(&sheets[0]).unwrap();
    assert_eq!(sheet_img.width(), 800);
    assert_eq!(sheet_img.height(), 1000);
}
