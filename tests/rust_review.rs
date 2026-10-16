use std::collections::BTreeMap;

use excel_id_card_rust::{
    data::models::{ProjectConfiguration, ReviewRecord, ReviewStatus, SourceRecord},
    projects::ProjectStore,
    review::ReviewManager,
};
use serde_json::json;
use tempfile::tempdir;

fn source(record_id: &str, pin: &str, name: &str, row_index: usize) -> SourceRecord {
    SourceRecord {
        record_id: record_id.into(),
        row_index,
        raw_pin: pin.into(),
        pin: pin.into(),
        data: BTreeMap::from([(String::from("Name"), json!(name))]),
        validation_errors: Vec::new(),
        validation_warnings: Vec::new(),
    }
}

fn manager() -> ReviewManager {
    ReviewManager::from_sources(
        &[
            source("r-1", "1001", "Alice", 1),
            source("r-2", "1002", "Bob", 2),
            source("r-3", "1003", "Charlie", 3),
        ],
        &BTreeMap::new(),
    )
    .unwrap()
}

#[test]
fn navigation_follows_source_order_and_search_finds_stable_records() {
    let mut manager = manager();

    assert_eq!(manager.current_record().unwrap().record_id, "r-1");
    assert_eq!(manager.next().unwrap().record_id, "r-2");
    assert_eq!(manager.last().unwrap().record_id, "r-3");
    assert_eq!(manager.previous().unwrap().record_id, "r-2");
    assert_eq!(manager.first().unwrap().record_id, "r-1");

    let matches = manager.search("boB");
    assert_eq!(matches.len(), 1);
    assert_eq!(matches[0].record_id, "r-2");

    manager.set_search_query("1003");
    assert_eq!(manager.current_record().unwrap().record_id, "r-3");
    assert_eq!(manager.current_index(), Some(0));
}

#[test]
fn status_transitions_and_comments_are_typed_and_keyed_by_record_id() {
    let mut manager = manager();

    manager.approve("r-1").unwrap();
    manager
        .set_comment("r-1", Some("Looks good".into()))
        .unwrap();
    manager.reject("r-2").unwrap();
    manager.mark_correction("r-3").unwrap();
    manager.skip("r-2").unwrap();

    assert_eq!(
        manager.record("r-1").unwrap().status,
        ReviewStatus::Approved
    );
    assert_eq!(manager.comment("r-1"), Some("Looks good"));
    assert_eq!(manager.record("r-2").unwrap().status, ReviewStatus::Skipped);
    assert_eq!(
        manager.record("r-3").unwrap().status,
        ReviewStatus::Correction
    );
    assert!(manager.record("missing").is_none());
}

#[test]
fn regeneration_invalidates_approval_and_replaces_or_clears_image_path() {
    let records = vec![ReviewRecord {
        record_id: "r-1".into(),
        pin: "1001".into(),
        name: "Alice".into(),
        status: ReviewStatus::Approved,
        comments: Some("old review".into()),
        rendered_image_path: Some("/staging/old.png".into()),
        last_reviewed_at: Some("123".into()),
    }];
    let mut manager = ReviewManager::new(records);

    manager
        .regenerate("r-1", Some("/staging/new.png".into()))
        .unwrap();
    assert_eq!(manager.record("r-1").unwrap().status, ReviewStatus::Pending);
    assert_eq!(
        manager
            .record("r-1")
            .unwrap()
            .rendered_image_path
            .as_deref(),
        Some("/staging/new.png")
    );

    manager.invalidate_regeneration("r-1").unwrap();
    assert_eq!(manager.record("r-1").unwrap().status, ReviewStatus::Pending);
    assert!(manager.record("r-1").unwrap().rendered_image_path.is_none());
}

#[test]
fn review_states_and_review_records_round_trip_through_project_json() {
    let directory = tempdir().unwrap();
    let project_path = directory.path().join("review-project.json");
    let mut manager = manager();
    manager.approve("r-1").unwrap();
    manager
        .set_comment("r-1", Some("Use the corrected department name".into()))
        .unwrap();
    manager.mark_correction("r-2").unwrap();
    manager.skip("r-3").unwrap();

    let review_records = manager.to_review_records();
    assert_eq!(review_records[0].record_id, "r-1");
    assert_eq!(review_records[1].status, ReviewStatus::Correction);

    let mut project = ProjectConfiguration::default();
    manager.apply_to_project_configuration(&mut project);
    ProjectStore::save_project(&project_path, &project).unwrap();
    let loaded = ProjectStore::load_project(&project_path).unwrap();

    assert_eq!(loaded.review_states["r-1"], ReviewStatus::Approved);
    assert_eq!(loaded.review_states["r-2"], ReviewStatus::Correction);
    assert_eq!(loaded.review_states["r-3"], ReviewStatus::Skipped);
    assert_eq!(
        loaded.review_comments["r-1"],
        "Use the corrected department name"
    );

    let restored = ReviewManager::from_project_configuration(&loaded, review_records).unwrap();
    assert_eq!(
        restored.record("r-1").unwrap().status,
        ReviewStatus::Approved
    );
    assert_eq!(
        restored.record("r-2").unwrap().status,
        ReviewStatus::Correction
    );
    assert_eq!(
        restored.comment("r-1"),
        Some("Use the corrected department name")
    );
    assert_eq!(restored.to_review_states(), loaded.review_states);
}

#[test]
fn approve_all_and_selection_work_consistently() {
    let mut manager = manager();
    assert_eq!(manager.pending_count(), 3);
    assert_eq!(manager.pending_records().len(), 3);

    assert!(manager.select_record("r-2"));
    assert_eq!(manager.current_record().unwrap().record_id, "r-2");
    assert!(!manager.select_record("nonexistent"));

    manager.approve_all();
    assert_eq!(manager.pending_count(), 0);
    assert_eq!(manager.approved_count(), 3);
    assert_eq!(
        manager.record("r-1").unwrap().status,
        ReviewStatus::Approved
    );
    assert_eq!(
        manager.record("r-2").unwrap().status,
        ReviewStatus::Approved
    );
    assert_eq!(
        manager.record("r-3").unwrap().status,
        ReviewStatus::Approved
    );
}
