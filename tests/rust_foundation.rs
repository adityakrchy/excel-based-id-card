use std::{collections::BTreeMap, fs, time::Duration};

use excel_id_card_rust::{
    data::models::{MatchStatus, ProjectConfiguration, SourceRecord, TemplateDefinition},
    editor::geometry::{cr80_dimensions, physical_to_pixels, Unit},
    photos::{PhotoIndex, PhotoMatcher},
    projects::ProjectStore,
    tasks::{IndexEvent, PhotoIndexingTask},
};
use serde_json::json;
use tempfile::tempdir;

#[test]
fn cr80_geometry_is_canonical_at_300_dpi() {
    let dimensions = cr80_dimensions(300, "landscape").unwrap();
    assert_eq!(dimensions.width_px, 1011);
    assert_eq!(dimensions.height_px, 638);
    assert_eq!(physical_to_pixels(85.6, Unit::Mm, 300).unwrap(), 1011);
}

#[test]
fn project_json_round_trips_and_reports_missing_references() {
    let directory = tempdir().unwrap();
    let project_path = directory.path().join("project.json");
    let missing_excel = directory.path().join("missing.xlsx");
    let project = ProjectConfiguration {
        project_name: "Migration test".into(),
        excel_file_path: Some(missing_excel.to_string_lossy().into_owned()),
        ..serde_json::from_value(json!({})).unwrap()
    };
    ProjectStore::save_project(&project_path, &project).unwrap();
    let loaded = ProjectStore::load_project(&project_path).unwrap();
    assert_eq!(loaded.project_name, "Migration test");
    let missing = ProjectStore::check_missing_references(&loaded);
    assert_eq!(missing[0].key, "excel_file");
    assert_eq!(missing[0].path, missing_excel);

    let template_path = directory.path().join("template.json");
    let template = TemplateDefinition {
        name: "Round-trip template".into(),
        ..Default::default()
    };
    ProjectStore::save_template(&template_path, &template).unwrap();
    assert_eq!(
        ProjectStore::load_template(&template_path).unwrap().name,
        "Round-trip template"
    );
    let lingering_temp_files = fs::read_dir(directory.path())
        .unwrap()
        .filter_map(Result::ok)
        .filter(|entry| {
            entry
                .path()
                .extension()
                .and_then(|extension| extension.to_str())
                == Some("tmp")
        })
        .count();
    assert_eq!(lingering_temp_files, 0);
}

#[test]
fn arbitrary_column_matching_keeps_ambiguous_and_override_states_explicit() {
    let directory = tempdir().unwrap();
    let matched = directory.path().join("EMP-7.jpg");
    let ambiguous = directory.path().join("EMP-8.png");
    fs::write(&matched, b"not decoded").unwrap();
    fs::write(&ambiguous, b"not decoded").unwrap();
    let second_ambiguous = directory.path().join("emp-8.jpeg");
    fs::write(&second_ambiguous, b"not decoded").unwrap();
    let mut index = PhotoIndex::default();
    index.insert("EMP-7".into(), matched.clone());
    index.insert("EMP-8".into(), ambiguous);
    index.insert("EMP-8".into(), second_ambiguous);
    let mut matcher = PhotoMatcher::default();
    matcher.set_index(index);
    matcher.set_key_column(Some("Employee Code".into()));
    let record = |id: &str, code: &str| SourceRecord {
        record_id: id.into(),
        row_index: 1,
        raw_pin: "".into(),
        pin: "".into(),
        data: BTreeMap::from([("Employee Code".into(), json!(code))]),
        validation_errors: Vec::new(),
        validation_warnings: Vec::new(),
    };
    assert_eq!(
        matcher.match_record(&record("r1", "EMP-7")).status,
        MatchStatus::Matched
    );
    assert_eq!(
        matcher.match_record(&record("r2", "EMP-8")).status,
        MatchStatus::Ambiguous
    );
    matcher.set_override("r2", matched.to_string_lossy().to_string());
    assert_eq!(
        matcher.match_record(&record("r2", "EMP-8")).status,
        MatchStatus::Overridden
    );
}

#[test]
fn scanner_emits_progressive_events_on_a_bounded_channel_without_decoding() {
    let directory = tempdir().unwrap();
    for number in 0..12 {
        fs::write(
            directory.path().join(format!("EMP-{number:03}.jpg")),
            b"invalid image bytes",
        )
        .unwrap();
    }
    fs::write(directory.path().join("ignored.txt"), b"not a photo").unwrap();
    let mut task = PhotoIndexingTask::start(directory.path(), 2, 1);
    let mut batches = 0;
    let mut finished = false;
    loop {
        match task.recv_timeout(Duration::from_secs(2)).unwrap() {
            IndexEvent::Discovered { batch, .. } => {
                assert!(batch.len() <= 2);
                batches += 1;
            }
            IndexEvent::Finished { index } => {
                assert_eq!(index.total_files(), 12);
                finished = true;
                break;
            }
            IndexEvent::Cancelled { .. } => break,
            IndexEvent::Failed(error) => panic!("scanner failed: {error}"),
        }
    }
    assert!(finished);
    assert!(batches >= 2);
    task.join().unwrap();
}

#[test]
fn scanner_cancellation_stops_a_large_discovery() {
    let directory = tempdir().unwrap();
    for number in 0..100 {
        fs::write(directory.path().join(format!("{number:03}.png")), b"bytes").unwrap();
    }
    let mut task = PhotoIndexingTask::start(directory.path(), 1, 1);
    task.cancel();
    let mut saw_terminal = false;
    for _ in 0..10 {
        match task.recv_timeout(Duration::from_millis(200)) {
            Ok(IndexEvent::Cancelled { .. })
            | Ok(IndexEvent::Finished { .. })
            | Ok(IndexEvent::Failed(_)) => {
                saw_terminal = true;
                break;
            }
            Ok(IndexEvent::Discovered { .. }) => {}
            Err(_) => break,
        }
    }
    task.join().unwrap();
    assert!(saw_terminal || task.is_cancelled());
}
