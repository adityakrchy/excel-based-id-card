pub mod contact_sheet;
pub use contact_sheet::{
    ContactSheetCardItem, ContactSheetError, ContactSheetGenerator, ContactSheetOptions, PageSize,
};

use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, OpenOptions},
    io::{self, Write},
    path::{Path, PathBuf},
};

use csv::WriterBuilder;
use thiserror::Error;

use crate::{
    data::models::{
        ExportConfiguration, ExportResult, PhotoMatchResult, RenderSettings, ReviewRecord,
        ReviewStatus, SourceRecord, TemplateDefinition, TextOverflowPolicy,
    },
    generation::{format_output_stem, output_extension, GenerationRecordError, RenderResult},
    rendering::{NativeRenderer, RenderError, RenderedImage},
};

/// Inputs are borrowed so callers can export a review page's current state
/// without converting it into a second persistence model.
pub struct ExportRequest<'a> {
    pub config: &'a ExportConfiguration,
    pub review_records: &'a [ReviewRecord],
    pub source_records: &'a BTreeMap<String, SourceRecord>,
    pub generated_results: &'a BTreeMap<String, RenderResult>,
    pub match_results: Option<&'a BTreeMap<String, PhotoMatchResult>>,
    /// Required only when an image needs to be re-rendered instead of read from
    /// a generated output path.
    pub template: Option<&'a TemplateDefinition>,
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum ExportError {
    #[error("export output directory '{path}' could not be created: {details}")]
    OutputDirectory { path: String, details: String },
    #[error("manifest could not be written: {details}")]
    Manifest { details: String },
    #[error("export has no review records")]
    EmptyInput,
}

pub struct ExportManager;

impl ExportManager {
    pub fn export_batch(request: ExportRequest<'_>) -> Result<ExportResult, ExportError> {
        export_batch(request)
    }

    /// Convenience wrapper for callers that keep generated paths on
    /// `ReviewRecord::rendered_image_path` and do not need re-rendering.
    pub fn export_review_batch(
        config: &ExportConfiguration,
        review_records: &[ReviewRecord],
        source_records: &BTreeMap<String, SourceRecord>,
        match_results: Option<&BTreeMap<String, PhotoMatchResult>>,
    ) -> Result<ExportResult, ExportError> {
        let generated = BTreeMap::new();
        export_batch(ExportRequest {
            config,
            review_records,
            source_records,
            generated_results: &generated,
            match_results,
            template: None,
        })
    }
}

pub fn export_batch(request: ExportRequest<'_>) -> Result<ExportResult, ExportError> {
    if request.review_records.is_empty() {
        return Err(ExportError::EmptyInput);
    }
    let output_dir = PathBuf::from(&request.config.output_dir);
    fs::create_dir_all(&output_dir).map_err(|error| ExportError::OutputDirectory {
        path: output_dir.display().to_string(),
        details: error.to_string(),
    })?;

    let mut result = ExportResult {
        total_records: request.review_records.len(),
        ..Default::default()
    };
    let extension = output_extension(&request.config.format);
    let mut occupied = existing_names(&output_dir);
    let mut manifest_rows = Vec::with_capacity(request.review_records.len());
    let mut source_columns = BTreeSet::new();

    for review in request.review_records {
        if let Some(source) = request.source_records.get(&review.record_id) {
            source_columns.extend(source.data.keys().cloned());
        }
    }
    let fixed_columns = fixed_manifest_columns();
    source_columns.retain(|column| !fixed_columns.iter().any(|fixed| fixed == column));

    for review in request.review_records {
        let source = request.source_records.get(&review.record_id);
        let status = review.status.clone();
        let mut output_filename = String::new();
        let mut export_status = "Skipped".to_owned();
        let mut error_text = String::new();
        let mut matched_photo = request
            .match_results
            .and_then(|matches| matches.get(&review.record_id))
            .and_then(|matched| matched.photo_path.clone())
            .unwrap_or_default();

        if request.config.approved_only && status != ReviewStatus::Approved {
            result.skipped_count += 1;
        } else if source.is_none() {
            result.failed_count += 1;
            error_text = "source record is unavailable".into();
            add_error(&mut result, &review.record_id, &error_text);
        } else if let Some(generated) = request.generated_results.get(&review.record_id) {
            if generated.skipped {
                result.skipped_count += 1;
                error_text = "generation skipped this record".into();
            } else if !generated.success {
                result.failed_count += 1;
                error_text = generated
                    .error
                    .as_ref()
                    .map(ToString::to_string)
                    .unwrap_or_else(|| "generation failed".into());
                add_error(&mut result, &review.record_id, &error_text);
            } else {
                let (path, stem) = allocate_export_path(
                    source.expect("source checked above"),
                    &review.name,
                    &review.pin,
                    request.config.naming_pattern.as_str(),
                    extension,
                    &output_dir,
                    &mut occupied,
                );
                output_filename = path
                    .file_name()
                    .unwrap_or_default()
                    .to_string_lossy()
                    .into_owned();
                match copy_or_encode(
                    generated
                        .output_path
                        .as_deref()
                        .or_else(|| generated.image_path.as_deref().map(Path::new)),
                    &path,
                    request.config,
                    request.template,
                ) {
                    Ok(()) => {
                        result.exported_count += 1;
                        result.exported_files.push(path.display().to_string());
                        export_status = "Success".into();
                    }
                    Err(error) => {
                        result.failed_count += 1;
                        error_text = error;
                        add_error(&mut result, &review.record_id, &error_text);
                    }
                }
                let _ = stem;
            }
        } else {
            let source = source.expect("source checked above");
            let (path, _) = allocate_export_path(
                source,
                &review.name,
                &review.pin,
                &request.config.naming_pattern,
                extension,
                &output_dir,
                &mut occupied,
            );
            output_filename = path
                .file_name()
                .unwrap_or_default()
                .to_string_lossy()
                .into_owned();
            let generated_path = review.rendered_image_path.as_deref().map(Path::new);
            let operation = if generated_path.is_some() {
                copy_or_encode(generated_path, &path, request.config, request.template)
            } else if let Some(template) = request.template {
                let settings = export_settings(request.config, template);
                let photo = request
                    .match_results
                    .and_then(|matches| matches.get(&review.record_id))
                    .and_then(|matched| matched.photo_path.as_deref())
                    .map(Path::new);
                match NativeRenderer::render_with_settings(
                    template,
                    Some(source),
                    photo,
                    Some(&settings),
                ) {
                    Ok(rendered) => write_atomic(&rendered, template, &settings, &path)
                        .map_err(|error| error.to_string()),
                    Err(error) => Err(error.to_string()),
                }
            } else {
                Err("generated output is unavailable".into())
            };
            match operation {
                Ok(()) => {
                    result.exported_count += 1;
                    result.exported_files.push(path.display().to_string());
                    export_status = "Success".into();
                }
                Err(error) => {
                    result.failed_count += 1;
                    error_text = error;
                    add_error(&mut result, &review.record_id, &error_text);
                }
            }
        }

        if matched_photo.is_empty() {
            matched_photo = String::new();
        }
        manifest_rows.push(ManifestRow {
            review,
            source,
            matched_photo,
            output_filename,
            export_status,
            error: error_text,
        });
    }

    if request.config.export_manifest {
        let manifest_path =
            next_available_path(&output_dir.join("export_manifest.csv"), &mut occupied);
        write_manifest(&manifest_path, &source_columns, &manifest_rows)
            .map_err(|error| ExportError::Manifest { details: error })?;
        result.manifest_path = Some(manifest_path.display().to_string());
    }

    if request.config.export_contact_sheet && !result.exported_files.is_empty() {
        let mut card_items = Vec::new();
        for file in &result.exported_files {
            let path = PathBuf::from(file);
            let stem = path
                .file_stem()
                .and_then(|s| s.to_str())
                .unwrap_or_default();
            let parts: Vec<&str> = stem.splitn(2, '_').collect();
            let (pin, name) = if parts.len() == 2 {
                (parts[0].to_string(), parts[1].replace('_', " "))
            } else {
                (stem.to_string(), stem.to_string())
            };
            card_items.push(ContactSheetCardItem {
                image_path: path,
                pin,
                name,
            });
        }
        let sheet_opts = ContactSheetOptions {
            dpi: request.template.map(|t| t.dpi).unwrap_or(300),
            ..Default::default()
        };
        if let Ok(paths) =
            ContactSheetGenerator::generate_sheets(&card_items, &output_dir, &sheet_opts)
        {
            if let Some(first) = paths.first() {
                result.contact_sheet_path = Some(first.display().to_string());
            }
        }
    }
    Ok(result)
}

struct ManifestRow<'a> {
    review: &'a ReviewRecord,
    source: Option<&'a SourceRecord>,
    matched_photo: String,
    output_filename: String,
    export_status: String,
    error: String,
}

fn fixed_manifest_columns() -> Vec<String> {
    [
        "Record ID",
        "PIN Number",
        "Name",
        "Source Row",
        "Matched Photo Path",
        "Output Filename",
        "Review Status",
        "Export Status",
        "Export Error",
        "Exported At",
    ]
    .into_iter()
    .map(str::to_owned)
    .collect()
}

fn write_manifest(
    path: &Path,
    source_columns: &BTreeSet<String>,
    rows: &[ManifestRow<'_>],
) -> Result<(), String> {
    let mut bytes = Vec::new();
    bytes.extend_from_slice(b"\xEF\xBB\xBF");
    {
        let mut writer = WriterBuilder::new()
            .has_headers(false)
            .from_writer(&mut bytes);
        let mut header: Vec<String> = source_columns.iter().cloned().collect();
        header.extend(fixed_manifest_columns());
        writer
            .write_record(&header)
            .map_err(|error| error.to_string())?;
        let exported_at = format!(
            "{}",
            std::time::SystemTime::now()
                .duration_since(std::time::UNIX_EPOCH)
                .unwrap_or_default()
                .as_secs()
        );
        for row in rows {
            let mut values = source_columns
                .iter()
                .map(|column| {
                    row.source
                        .map(|source| source.get_value(column))
                        .unwrap_or_default()
                })
                .collect::<Vec<_>>();
            values.extend([
                row.review.record_id.clone(),
                row.source
                    .map(|source| source.pin_or_raw().to_owned())
                    .unwrap_or_else(|| row.review.pin.clone()),
                row.source
                    .map(|source| source.get_value("Name"))
                    .filter(|name| !name.is_empty())
                    .unwrap_or_else(|| row.review.name.clone()),
                row.source
                    .map(|source| source.row_index.to_string())
                    .unwrap_or_default(),
                row.matched_photo.clone(),
                row.output_filename.clone(),
                review_status_value(&row.review.status).into(),
                row.export_status.clone(),
                row.error.clone(),
                exported_at.clone(),
            ]);
            writer
                .write_record(values)
                .map_err(|error| error.to_string())?;
        }
        writer.flush().map_err(|error| error.to_string())?;
    }
    write_bytes_atomic(path, &bytes)
}

fn copy_or_encode(
    source: Option<&Path>,
    destination: &Path,
    config: &ExportConfiguration,
    template: Option<&TemplateDefinition>,
) -> Result<(), String> {
    let source = source.ok_or_else(|| "generated output is unavailable".to_owned())?;
    let image = image::open(source)
        .map_err(|error| error.to_string())?
        .to_rgba8();
    let rendered = RenderedImage {
        image,
        warnings: Vec::new(),
    };
    let template = template.cloned().unwrap_or_default();
    let settings = export_settings(config, &template);
    write_atomic(&rendered, &template, &settings, destination).map_err(|error| error.to_string())
}

fn export_settings(config: &ExportConfiguration, template: &TemplateDefinition) -> RenderSettings {
    RenderSettings {
        dpi: template.dpi,
        output_format: config.format.clone(),
        jpeg_quality: config.jpeg_quality,
        missing_photo_policy: crate::data::models::MissingPhotoPolicy::GenerateWithPlaceholder,
        text_overflow_policy: TextOverflowPolicy::AutoShrink,
    }
}

fn write_atomic(
    rendered: &RenderedImage,
    template: &TemplateDefinition,
    settings: &RenderSettings,
    destination: &Path,
) -> Result<(), GenerationRecordError> {
    let parent = destination.parent().unwrap_or_else(|| Path::new("."));
    let name = destination
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("output");
    let mut counter = 0u64;
    let (temp_path, mut file) = loop {
        let candidate = parent.join(format!(".{name}.tmp-{}-{counter}", std::process::id()));
        counter += 1;
        match OpenOptions::new()
            .write(true)
            .create_new(true)
            .open(&candidate)
        {
            Ok(file) => break (candidate, file),
            Err(error) if error.kind() == io::ErrorKind::AlreadyExists => continue,
            Err(error) => {
                return Err(GenerationRecordError::Write {
                    path: destination.display().to_string(),
                    details: error.to_string(),
                })
            }
        }
    };
    let encoded = rendered
        .encode(template, settings, &mut file)
        .and_then(|_| {
            file.sync_all().map_err(|error| RenderError::Encode {
                format: "output".into(),
                details: error.to_string(),
            })
        });
    drop(file);
    if let Err(error) = encoded {
        let _ = fs::remove_file(&temp_path);
        return Err(GenerationRecordError::Render {
            details: error.to_string(),
        });
    }
    if destination.exists() {
        let _ = fs::remove_file(&temp_path);
        return Err(GenerationRecordError::Collision {
            path: destination.display().to_string(),
        });
    }
    fs::rename(&temp_path, destination).map_err(|error| GenerationRecordError::Write {
        path: destination.display().to_string(),
        details: error.to_string(),
    })
}

fn write_bytes_atomic(path: &Path, bytes: &[u8]) -> Result<(), String> {
    let parent = path.parent().unwrap_or_else(|| Path::new("."));
    let temp = parent.join(format!(
        ".{}.tmp-{}",
        path.file_name().unwrap_or_default().to_string_lossy(),
        std::process::id()
    ));
    let mut file = OpenOptions::new()
        .write(true)
        .create_new(true)
        .open(&temp)
        .map_err(|error| error.to_string())?;
    file.write_all(bytes)
        .and_then(|_| file.sync_all())
        .map_err(|error| error.to_string())?;
    drop(file);
    if path.exists() {
        let _ = fs::remove_file(&temp);
        return Err(format!("manifest collision at {}", path.display()));
    }
    fs::rename(temp, path).map_err(|error| error.to_string())
}

fn allocate_export_path(
    source: &SourceRecord,
    review_name: &str,
    review_pin: &str,
    pattern: &str,
    extension: &str,
    directory: &Path,
    occupied: &mut BTreeSet<String>,
) -> (PathBuf, String) {
    let mut record = source.clone();
    if record.pin.is_empty() {
        record.pin = review_pin.to_owned();
    }
    if !record.data.contains_key("Name") && !review_name.is_empty() {
        record.data.insert(
            "Name".into(),
            serde_json::Value::String(review_name.to_owned()),
        );
    }
    let stem = format_output_stem(pattern, &record);
    let base = format!("{stem}.{extension}");
    let mut candidate = base.clone();
    let mut suffix = 2;
    while occupied.contains(&candidate) {
        candidate = format!("{stem}_{suffix}.{extension}");
        suffix += 1;
    }
    occupied.insert(candidate.clone());
    (directory.join(candidate), stem)
}

fn existing_names(directory: &Path) -> BTreeSet<String> {
    fs::read_dir(directory)
        .map(|entries| {
            entries
                .flatten()
                .filter_map(|entry| entry.file_name().to_str().map(str::to_owned))
                .collect()
        })
        .unwrap_or_default()
}

fn next_available_path(path: &Path, occupied: &mut BTreeSet<String>) -> PathBuf {
    let stem = path.file_stem().unwrap_or_default().to_string_lossy();
    let extension = path
        .extension()
        .map(|extension| extension.to_string_lossy())
        .unwrap_or_default();
    let mut name = path
        .file_name()
        .unwrap_or_default()
        .to_string_lossy()
        .into_owned();
    let mut suffix = 2;
    while occupied.contains(&name) {
        name = format!("{stem}_{suffix}.{extension}");
        suffix += 1;
    }
    occupied.insert(name.clone());
    path.with_file_name(name)
}

fn add_error(result: &mut ExportResult, record_id: &str, message: &str) {
    result.errors.push(BTreeMap::from([
        ("record_id".into(), record_id.into()),
        ("error".into(), message.into()),
    ]));
}

fn review_status_value(status: &ReviewStatus) -> &'static str {
    match status {
        ReviewStatus::Pending => "pending",
        ReviewStatus::Approved => "approved",
        ReviewStatus::Rejected => "rejected",
        ReviewStatus::Correction => "correction",
        ReviewStatus::Skipped => "skipped",
    }
}
