use std::fs;

use excel_id_card_rust::data::importer::{
    detect_pin_column, import_spreadsheet, list_worksheets, ImportError, ImportOptions,
};
use tempfile::tempdir;

#[test]
fn imports_csv_values_and_normalizes_empty_cells() {
    let directory = tempdir().unwrap();
    let path = directory.path().join("people.csv");
    fs::write(
        &path,
        "PIN Number,Name,Notes\n005001,Alice,\n009999,Bob,ready\n",
    )
    .unwrap();

    let result = import_spreadsheet(&path, &ImportOptions::default()).unwrap();

    assert_eq!(result.columns, vec!["PIN Number", "Name", "Notes"]);
    assert_eq!(result.pin_column.as_deref(), Some("PIN Number"));
    assert_eq!(result.records.len(), 2);
    assert_eq!(result.records[0].row_index, 2);
    assert_eq!(result.records[0].pin, "005001");
    assert_eq!(result.records[0].raw_pin, "005001");
    assert_eq!(result.records[0].get_value("Notes"), "");

    let repeated = import_spreadsheet(&path, &ImportOptions::default()).unwrap();
    assert_eq!(result.records[0].record_id, repeated.records[0].record_id);
}

#[test]
fn detects_arbitrary_columns_and_honors_a_pin_hint() {
    let directory = tempdir().unwrap();
    let path = directory.path().join("employees.csv");
    fs::write(&path, "Employee Code,Full Name\nEMP-7,Ada\n").unwrap();

    let default_result = import_spreadsheet(&path, &ImportOptions::default()).unwrap();
    assert_eq!(default_result.pin_column.as_deref(), Some("Employee Code"));
    assert_eq!(default_result.records[0].pin, "EMP-7");
    assert_eq!(
        detect_pin_column(&default_result.columns, Some("Full Name")),
        Some("Full Name".into())
    );

    let hinted = import_spreadsheet(
        &path,
        &ImportOptions {
            pin_column_hint: Some("Full Name".into()),
            ..Default::default()
        },
    )
    .unwrap();
    assert_eq!(hinted.pin_column.as_deref(), Some("Full Name"));
    assert_eq!(hinted.records[0].pin, "Ada");
}

#[test]
fn supports_a_zero_based_header_row_and_source_row_indices() {
    let directory = tempdir().unwrap();
    let path = directory.path().join("prefixed.csv");
    fs::write(&path, "generated at,2026\nPIN,Name\n 1001 ,Casey\n").unwrap();

    let result = import_spreadsheet(
        &path,
        &ImportOptions {
            header_row: 1,
            ..Default::default()
        },
    )
    .unwrap();

    assert_eq!(result.columns, vec!["PIN", "Name"]);
    assert_eq!(result.records[0].row_index, 3);
    assert_eq!(result.records[0].raw_pin, " 1001 ");
    assert_eq!(result.records[0].pin, "1001");
}

#[test]
fn reports_missing_files_and_unsupported_formats() {
    let directory = tempdir().unwrap();
    let missing = directory.path().join("missing.csv");
    assert!(matches!(
        list_worksheets(&missing),
        Err(ImportError::Io { .. })
    ));

    let unsupported = directory.path().join("people.tsv");
    fs::write(&unsupported, "PIN\n1\n").unwrap();
    assert!(matches!(
        import_spreadsheet(&unsupported, &ImportOptions::default()),
        Err(ImportError::UnsupportedFormat { .. })
    ));
}

#[test]
fn lists_csv_as_the_default_worksheet_without_binary_fixtures() {
    let directory = tempdir().unwrap();
    let path = directory.path().join("people.csv");
    fs::write(&path, "PIN\n1\n").unwrap();

    assert_eq!(list_worksheets(&path).unwrap(), vec!["Default"]);
}
