use std::fs;

use excel_id_card_rust::{
    data::models::ProjectConfiguration,
    projects::{AssetPathError, PersistenceError, ProjectStore},
};
use serde_json::json;
use tempfile::tempdir;

fn project(name: &str) -> ProjectConfiguration {
    serde_json::from_value(json!({
        "project_name": name,
        "version": "1.0.0"
    }))
    .unwrap()
}

#[test]
fn save_keeps_the_previous_primary_as_an_atomic_backup() {
    let directory = tempdir().unwrap();
    let path = directory.path().join("project.json");

    ProjectStore::save_project(&path, &project("first")).unwrap();
    assert_eq!(
        ProjectStore::load_project(&ProjectStore::backup_path(&path))
            .unwrap()
            .project_name,
        "first"
    );

    ProjectStore::save_project(&path, &project("second")).unwrap();
    let backup = ProjectStore::backup_path(&path);
    assert_eq!(
        ProjectStore::load_project(&backup).unwrap().project_name,
        "first"
    );
    assert_eq!(
        ProjectStore::load_project(&path).unwrap().project_name,
        "second"
    );
    assert!(!directory.path().read_dir().unwrap().any(|entry| entry
        .unwrap()
        .file_name()
        .to_string_lossy()
        .contains(".tmp")));
}

#[test]
fn corrupt_primary_recovers_with_explicit_metadata_and_primary_context() {
    let directory = tempdir().unwrap();
    let path = directory.path().join("project.json");
    ProjectStore::save_project(&path, &project("recoverable")).unwrap();
    ProjectStore::save_project(&path, &project("latest")).unwrap();
    fs::write(&path, b"{ definitely not json").unwrap();

    let loaded = ProjectStore::load_project_with_metadata(&path).unwrap();
    assert_eq!(loaded.value.project_name, "recoverable");
    assert!(loaded.recovery.recovered_from_backup);
    assert_eq!(loaded.recovery.primary_path, path);
    assert!(loaded
        .recovery
        .primary_error
        .unwrap()
        .contains("invalid JSON"));
}

#[test]
fn missing_primary_recovers_from_backup_and_both_failures_are_described() {
    let directory = tempdir().unwrap();
    let path = directory.path().join("project.json");
    let backup = ProjectStore::backup_path(&path);
    fs::write(&backup, serde_json::to_vec(&project("backup")).unwrap()).unwrap();

    let loaded = ProjectStore::load_project_with_metadata(&path).unwrap();
    assert_eq!(loaded.value.project_name, "backup");
    assert!(loaded.recovery.recovered_from_backup);
    assert!(loaded
        .recovery
        .primary_error
        .unwrap()
        .contains("does not exist"));

    fs::write(&backup, b"bad backup").unwrap();
    let error = ProjectStore::load_project_with_metadata(&path).unwrap_err();
    match error {
        PersistenceError::RecoveryFailed {
            path: failed_path,
            backup_path,
            ..
        } => {
            assert_eq!(failed_path, path);
            assert_eq!(backup_path, backup);
        }
        other => panic!("expected recovery context, got {other}"),
    }
}

#[test]
fn relative_asset_paths_cannot_escape_the_project_directory() {
    let directory = tempdir().unwrap();
    let project_path = directory.path().join("nested/project.json");
    let project = ProjectConfiguration {
        excel_file_path: Some("../../outside.xlsx".into()),
        ..project("paths")
    };

    let unsafe_references = ProjectStore::validate_referenced_asset_paths(&project_path, &project);
    assert_eq!(unsafe_references.len(), 1);
    assert_eq!(unsafe_references[0].key, "excel_file");
    assert_eq!(
        excel_id_card_rust::projects::resolve_asset_path(&project_path, "../../outside.xlsx"),
        Err(AssetPathError::Traversal)
    );

    let local_path = excel_id_card_rust::projects::resolve_asset_path(
        &directory.path().join("project.json"),
        "assets/photo.jpg",
    )
    .unwrap();
    assert_eq!(local_path, directory.path().join("assets/photo.jpg"));
}
