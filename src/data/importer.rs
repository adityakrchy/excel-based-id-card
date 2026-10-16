//! Synchronous spreadsheet and CSV importing for the Rust migration slice.
//!
//! The importer deliberately reads cell values only.  It never asks calamine
//! for workbook pictures, so image data is not loaded as part of a data import.

use std::{
    collections::{BTreeMap, BTreeSet},
    fs,
    io::{self, BufReader},
    path::{Path, PathBuf},
};

use calamine::{open_workbook, Data, Reader, Xls, Xlsx};
use serde_json::Value;
use thiserror::Error;

use super::models::SourceRecord;

/// Options controlling a single spreadsheet import.
#[derive(Debug, Clone, Default)]
pub struct ImportOptions {
    /// Excel worksheet to read. CSV files always use `Default`.
    pub sheet_name: Option<String>,
    /// Zero-based source row containing the column headers.
    pub header_row: usize,
    /// Exact column name to use for PIN values before candidate detection.
    pub pin_column_hint: Option<String>,
}

/// The columns and records read from one source worksheet.
#[derive(Debug, Clone)]
pub struct ImportResult {
    pub columns: Vec<String>,
    pub records: Vec<SourceRecord>,
    pub pin_column: Option<String>,
    pub sheet_name: String,
}

/// Errors returned by the synchronous importer.
#[derive(Debug, Error)]
pub enum ImportError {
    #[error("could not inspect input file {path}: {source}")]
    Io {
        path: PathBuf,
        #[source]
        source: io::Error,
    },
    #[error("unsupported spreadsheet format for {path} (extension: {extension})")]
    UnsupportedFormat { path: PathBuf, extension: String },
    #[error("could not parse CSV file {path}: {source}")]
    Csv {
        path: PathBuf,
        #[source]
        source: csv::Error,
    },
    #[error("could not open {format} workbook {path}: {message}")]
    Workbook {
        path: PathBuf,
        format: &'static str,
        message: String,
    },
    #[error("worksheet {sheet:?} was not found in {path}; available sheets: {available:?}")]
    SheetNotFound {
        path: PathBuf,
        sheet: String,
        available: Vec<String>,
    },
    #[error("header row {header_row} is outside {sheet:?} in {path}; available source rows: {row_count}")]
    HeaderRowOutOfBounds {
        path: PathBuf,
        sheet: String,
        header_row: usize,
        row_count: usize,
    },
}

/// Return worksheet names, or `Default` for a CSV file.
pub fn list_worksheets<P: AsRef<Path>>(path: P) -> Result<Vec<String>, ImportError> {
    let path = path.as_ref();
    let format = supported_format(path)?;
    ensure_exists(path)?;

    match format {
        FileFormat::Csv => Ok(vec!["Default".to_owned()]),
        FileFormat::Xlsx => {
            let workbook: Xlsx<_> =
                open_workbook(path).map_err(|error| workbook_error(path, "XLSX", error))?;
            Ok(workbook.sheet_names())
        }
        FileFormat::Xls => {
            let workbook: Xls<_> =
                open_workbook(path).map_err(|error| workbook_error(path, "XLS", error))?;
            Ok(workbook.sheet_names())
        }
    }
}

/// Import a CSV, XLSX, or XLS file using the supplied options.
pub fn import_spreadsheet<P: AsRef<Path>>(
    path: P,
    options: &ImportOptions,
) -> Result<ImportResult, ImportError> {
    let path = path.as_ref();
    let format = supported_format(path)?;
    ensure_exists(path)?;

    match format {
        FileFormat::Csv => import_csv(path, options),
        FileFormat::Xlsx => {
            let workbook: Xlsx<_> =
                open_workbook(path).map_err(|error| workbook_error(path, "XLSX", error))?;
            import_excel_workbook(path, workbook, options, "XLSX")
        }
        FileFormat::Xls => {
            let workbook: Xls<_> =
                open_workbook(path).map_err(|error| workbook_error(path, "XLS", error))?;
            import_excel_workbook(path, workbook, options, "XLS")
        }
    }
}

/// Compatibility-shaped helper matching the Python importer's arguments.
pub fn import_data<P: AsRef<Path>>(
    path: P,
    sheet_name: Option<&str>,
    header_row: usize,
    pin_column_hint: Option<&str>,
) -> Result<ImportResult, ImportError> {
    import_spreadsheet(
        path,
        &ImportOptions {
            sheet_name: sheet_name.map(str::to_owned),
            header_row,
            pin_column_hint: pin_column_hint.map(str::to_owned),
        },
    )
}

/// Small namespace for callers that prefer an importer type.
#[derive(Debug, Default, Copy, Clone)]
pub struct SpreadsheetImporter;

impl SpreadsheetImporter {
    pub fn list_worksheets<P: AsRef<Path>>(path: P) -> Result<Vec<String>, ImportError> {
        list_worksheets(path)
    }

    pub fn import<P: AsRef<Path>>(
        path: P,
        options: &ImportOptions,
    ) -> Result<ImportResult, ImportError> {
        import_spreadsheet(path, options)
    }
}

/// Detect the PIN column using the same candidates and fallback as Python.
pub fn detect_pin_column(columns: &[String], hint: Option<&str>) -> Option<String> {
    if let Some(hint) = hint {
        if columns.iter().any(|column| column == hint) {
            return Some(hint.to_owned());
        }
    }

    let candidates = [
        "pin number",
        "pin_number",
        "pin",
        "id",
        "emp id",
        "employee id",
        "roll no",
        "roll number",
        "badge number",
    ];
    for candidate in candidates {
        if let Some(column) = columns
            .iter()
            .find(|column| column.to_lowercase() == candidate)
        {
            return Some(column.clone());
        }
    }
    for candidate in ["pin", "id"] {
        if let Some(column) = columns
            .iter()
            .find(|column| column.to_lowercase().contains(candidate))
        {
            return Some(column.clone());
        }
    }
    columns.first().cloned()
}

#[derive(Debug, Copy, Clone)]
enum FileFormat {
    Csv,
    Xlsx,
    Xls,
}

fn supported_format(path: &Path) -> Result<FileFormat, ImportError> {
    let extension = path
        .extension()
        .and_then(|extension| extension.to_str())
        .unwrap_or_default()
        .to_ascii_lowercase();
    let format = match extension.as_str() {
        "csv" => FileFormat::Csv,
        "xlsx" => FileFormat::Xlsx,
        "xls" => FileFormat::Xls,
        _ => {
            return Err(ImportError::UnsupportedFormat {
                path: path.to_path_buf(),
                extension,
            })
        }
    };
    Ok(format)
}

fn ensure_exists(path: &Path) -> Result<(), ImportError> {
    fs::metadata(path)
        .map(|_| ())
        .map_err(|source| ImportError::Io {
            path: path.to_path_buf(),
            source,
        })
}

fn workbook_error<E: std::fmt::Debug>(path: &Path, format: &'static str, error: E) -> ImportError {
    ImportError::Workbook {
        path: path.to_path_buf(),
        format,
        message: format!("{error:?}"),
    }
}

fn import_csv(path: &Path, options: &ImportOptions) -> Result<ImportResult, ImportError> {
    let mut reader = csv::ReaderBuilder::new()
        .has_headers(false)
        .from_path(path)
        .map_err(|source| ImportError::Csv {
            path: path.to_path_buf(),
            source,
        })?;
    let rows = reader
        .records()
        .collect::<Result<Vec<_>, _>>()
        .map_err(|source| ImportError::Csv {
            path: path.to_path_buf(),
            source,
        })?;
    let width = rows.iter().map(csv::StringRecord::len).max().unwrap_or(0);
    let rows = rows
        .iter()
        .map(|row| {
            (0..width)
                .map(|column| row.get(column).unwrap_or_default().to_owned())
                .collect()
        })
        .collect::<Vec<Vec<String>>>();
    build_result(path, "Default", options, 0, rows)
}

fn import_excel_workbook<R>(
    path: &Path,
    mut workbook: R,
    options: &ImportOptions,
    format: &'static str,
) -> Result<ImportResult, ImportError>
where
    R: Reader<BufReader<fs::File>>,
    R::Error: std::fmt::Debug,
{
    let available = workbook.sheet_names();
    let sheet_name = options
        .sheet_name
        .clone()
        .or_else(|| available.first().cloned())
        .unwrap_or_default();
    if !available.iter().any(|name| name == &sheet_name) {
        return Err(ImportError::SheetNotFound {
            path: path.to_path_buf(),
            sheet: sheet_name,
            available,
        });
    }

    let range = workbook
        .worksheet_range(&sheet_name)
        .map_err(|error| workbook_error(path, format, error))?;
    let start_row = range.start().map(|(row, _)| row as usize).unwrap_or(0);
    let rows = range
        .rows()
        .map(|row| row.iter().map(cell_to_string).collect::<Vec<_>>())
        .collect::<Vec<_>>();
    build_result(path, &sheet_name, options, start_row, rows)
}

fn build_result(
    path: &Path,
    sheet_name: &str,
    options: &ImportOptions,
    start_row: usize,
    rows: Vec<Vec<String>>,
) -> Result<ImportResult, ImportError> {
    let end_row = start_row.saturating_add(rows.len());
    if options.header_row < start_row || options.header_row >= end_row {
        return Err(ImportError::HeaderRowOutOfBounds {
            path: path.to_path_buf(),
            sheet: sheet_name.to_owned(),
            header_row: options.header_row,
            row_count: end_row,
        });
    }

    let width = rows.iter().map(Vec::len).max().unwrap_or(0);
    let header = &rows[options.header_row - start_row];
    let columns =
        unique_columns((0..width).map(|index| header.get(index).cloned().unwrap_or_default()));
    let pin_column = detect_pin_column(&columns, options.pin_column_hint.as_deref());
    let mut records = Vec::with_capacity(
        rows.len()
            .saturating_sub(options.header_row - start_row + 1),
    );

    for (relative_row, row) in rows
        .iter()
        .enumerate()
        .skip(options.header_row - start_row + 1)
    {
        let source_row = start_row + relative_row;
        let data = columns
            .iter()
            .enumerate()
            .map(|(column, name)| {
                (
                    name.clone(),
                    Value::String(row.get(column).cloned().unwrap_or_default()),
                )
            })
            .collect::<BTreeMap<_, _>>();
        let raw_pin = pin_column
            .as_deref()
            .and_then(|column| data.get(column))
            .and_then(Value::as_str)
            .unwrap_or_default()
            .to_owned();
        let pin = normalize_pin(&raw_pin);
        records.push(SourceRecord {
            record_id: stable_record_id(path, sheet_name, source_row + 1),
            row_index: source_row + 1,
            raw_pin,
            pin,
            data,
            validation_errors: Vec::new(),
            validation_warnings: Vec::new(),
        });
    }

    Ok(ImportResult {
        columns,
        records,
        pin_column,
        sheet_name: sheet_name.to_owned(),
    })
}

fn unique_columns<I>(names: I) -> Vec<String>
where
    I: IntoIterator<Item = String>,
{
    let mut used = BTreeSet::new();
    names
        .into_iter()
        .enumerate()
        .map(|(index, name)| {
            let base = {
                let trimmed = name.trim();
                if trimmed.is_empty() {
                    format!("Column {}", index + 1)
                } else {
                    trimmed.to_owned()
                }
            };
            let mut candidate = base.clone();
            let mut suffix = 2;
            while !used.insert(candidate.clone()) {
                candidate = format!("{base} ({suffix})");
                suffix += 1;
            }
            candidate
        })
        .collect()
}

fn cell_to_string(cell: &Data) -> String {
    match cell {
        Data::Empty => String::new(),
        Data::String(value) => value.clone(),
        Data::Int(value) => value.to_string(),
        Data::Float(value) if value.is_finite() && value.fract() == 0.0 => format!("{value:.0}"),
        Data::Float(value) => value.to_string(),
        Data::Bool(value) => value.to_string(),
        Data::DateTime(value) => value.to_string(),
        Data::DateTimeIso(value) | Data::DurationIso(value) => value.clone(),
        Data::Error(value) => value.to_string(),
    }
}

fn normalize_pin(raw_pin: &str) -> String {
    let trimmed = raw_pin.trim();
    if let Some(integer) = trimmed.strip_suffix(".0") {
        if !integer.is_empty()
            && integer
                .strip_prefix('-')
                .unwrap_or(integer)
                .chars()
                .all(|character| character.is_ascii_digit())
        {
            return integer.to_owned();
        }
    }
    trimmed.to_owned()
}

fn stable_record_id(path: &Path, sheet_name: &str, row_index: usize) -> String {
    // FNV-1a is small, deterministic, and avoids random UUIDs for re-imported rows.
    let mut hash = 0xcbf29ce484222325_u64;
    for byte in format!("{}\0{}\0{}", path.to_string_lossy(), sheet_name, row_index).bytes() {
        hash ^= u64::from(byte);
        hash = hash.wrapping_mul(0x100000001b3);
    }
    format!("record-{hash:016x}")
}
