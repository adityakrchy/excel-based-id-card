//! Deterministic, bounded batch rendering built on [`NativeRenderer`].

use std::{
    collections::{BTreeMap, BTreeSet},
    fs::{self, OpenOptions},
    io,
    path::{Path, PathBuf},
    sync::{
        atomic::{AtomicBool, AtomicU64, AtomicUsize, Ordering},
        Arc, Mutex,
    },
    thread,
};

use thiserror::Error;

use crate::{
    data::models::{
        MissingPhotoPolicy, OutputFormat, PhotoMatchResult, RenderSettings, SourceRecord,
        TemplateDefinition,
    },
    rendering::{NativeRenderer, RenderError, RenderWarning},
};

static TEMP_FILE_COUNTER: AtomicU64 = AtomicU64::new(0);

/// Cancellation shared by a caller and all generation workers.
#[derive(Clone, Debug, Default)]
pub struct CancellationToken(Arc<AtomicBool>);

impl CancellationToken {
    pub fn new() -> Self {
        Self::default()
    }

    pub fn cancel(&self) {
        self.0.store(true, Ordering::Release);
    }

    pub fn is_cancelled(&self) -> bool {
        self.0.load(Ordering::Acquire)
    }
}

/// Options that control one batch. `max_parallelism` is a hard worker limit.
#[derive(Clone, Debug)]
pub struct GenerationOptions {
    pub output_dir: PathBuf,
    pub settings: RenderSettings,
    pub naming_pattern: String,
    pub max_parallelism: usize,
    pub progress: Option<std::sync::mpsc::Sender<GenerationEvent>>,
}

impl GenerationOptions {
    pub fn new(output_dir: impl Into<PathBuf>) -> Self {
        Self {
            output_dir: output_dir.into(),
            ..Self::default()
        }
    }
}

impl Default for GenerationOptions {
    fn default() -> Self {
        Self {
            output_dir: PathBuf::from("staging"),
            settings: RenderSettings {
                dpi: 300,
                output_format: OutputFormat::Png,
                jpeg_quality: 95,
                missing_photo_policy: MissingPhotoPolicy::GenerateWithPlaceholder,
                text_overflow_policy: crate::data::models::TextOverflowPolicy::AutoShrink,
            },
            naming_pattern: "{PIN_NUMBER}_{NAME}".into(),
            max_parallelism: 1,
            progress: None,
        }
    }
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum GenerationRecordError {
    #[error("record has no PIN number")]
    MissingPin,
    #[error("record is invalid: {details}")]
    InvalidRecord { details: String },
    #[error("missing photo for PIN '{pin}'")]
    MissingPhoto { pin: String },
    #[error("render failed: {details}")]
    Render { details: String },
    #[error("could not write '{path}': {details}")]
    Write { path: String, details: String },
    #[error("output collision at '{path}'")]
    Collision { path: String },
}

#[derive(Debug, Error, Clone, PartialEq, Eq)]
pub enum GenerationError {
    #[error("generation output directory '{path}' could not be created: {details}")]
    OutputDirectory { path: String, details: String },
    #[error("max_parallelism must be greater than zero")]
    InvalidParallelism,
}

/// The result for exactly one input record.
#[derive(Debug, Clone)]
pub struct RenderResult {
    pub record_id: String,
    pub pin: String,
    pub success: bool,
    pub skipped: bool,
    pub cancelled: bool,
    pub output_path: Option<PathBuf>,
    /// String form is convenient for callers that persist the result as JSON.
    pub image_path: Option<String>,
    pub warnings: Vec<RenderWarning>,
    pub error: Option<GenerationRecordError>,
}

impl RenderResult {
    fn cancelled(record: &SourceRecord) -> Self {
        Self {
            record_id: record.record_id.clone(),
            pin: record.pin_or_raw().to_owned(),
            success: false,
            skipped: false,
            cancelled: true,
            output_path: None,
            image_path: None,
            warnings: Vec::new(),
            error: None,
        }
    }
}

/// Progress is emitted in source order after each result has been collected.
#[derive(Debug, Clone)]
pub enum GenerationEvent {
    Record {
        index: usize,
        total: usize,
        result: RenderResult,
    },
    Finished {
        summary: GenerationSummary,
    },
}

#[derive(Debug, Clone, Default)]
pub struct GenerationSummary {
    pub total_records: usize,
    pub completed_count: usize,
    pub skipped_count: usize,
    pub failed_count: usize,
    pub cancelled_count: usize,
    pub cancelled: bool,
    pub results: Vec<RenderResult>,
}

pub struct BatchGenerator;

impl BatchGenerator {
    pub fn generate_batch(
        template: &TemplateDefinition,
        records: &[SourceRecord],
        photo_matches: Option<&BTreeMap<String, PhotoMatchResult>>,
        options: &GenerationOptions,
        cancellation: &CancellationToken,
    ) -> Result<GenerationSummary, GenerationError> {
        generate_batch(template, records, photo_matches, options, cancellation)
    }
}

/// Render all records using at most `options.max_parallelism` workers.
pub fn generate_batch(
    template: &TemplateDefinition,
    records: &[SourceRecord],
    photo_matches: Option<&BTreeMap<String, PhotoMatchResult>>,
    options: &GenerationOptions,
    cancellation: &CancellationToken,
) -> Result<GenerationSummary, GenerationError> {
    if options.max_parallelism == 0 {
        return Err(GenerationError::InvalidParallelism);
    }
    log::info!(
        "generate_batch: starting for {} records into '{}' (max parallelism: {})",
        records.len(),
        options.output_dir.display(),
        options.max_parallelism
    );
    fs::create_dir_all(&options.output_dir).map_err(|error| GenerationError::OutputDirectory {
        path: options.output_dir.display().to_string(),
        details: error.to_string(),
    })?;

    let extension = output_extension(&options.settings.output_format);
    let names = allocate_names(
        records,
        &options.naming_pattern,
        extension,
        &options.output_dir,
    );
    let matches: Vec<Option<PhotoMatchResult>> = records
        .iter()
        .map(|record| photo_matches.and_then(|all| all.get(&record.record_id).cloned()))
        .collect();
    let records = Arc::new(records.to_vec());
    let matches = Arc::new(matches);
    let names = Arc::new(names);
    let template = Arc::new(template.clone());
    let settings = Arc::new(options.settings.clone());
    let next = Arc::new(AtomicUsize::new(0));
    let results = Arc::new(Mutex::new(vec![None; records.len()]));
    let workers = options.max_parallelism.min(records.len().max(1));

    thread::scope(|scope| {
        for _ in 0..workers {
            let records = Arc::clone(&records);
            let matches = Arc::clone(&matches);
            let names = Arc::clone(&names);
            let template = Arc::clone(&template);
            let settings = Arc::clone(&settings);
            let next = Arc::clone(&next);
            let results = Arc::clone(&results);
            let cancellation = cancellation.clone();
            scope.spawn(move || loop {
                if cancellation.is_cancelled() {
                    break;
                }
                let index = next.fetch_add(1, Ordering::AcqRel);
                if index >= records.len() {
                    break;
                }
                if cancellation.is_cancelled() {
                    break;
                }
                let result = render_one(
                    &template,
                    &records[index],
                    matches[index].as_ref(),
                    &settings,
                    &names[index],
                );
                results.lock().expect("generation result lock poisoned")[index] = Some(result);
            });
        }
    });

    let mut ordered = Vec::with_capacity(records.len());
    let mut slots = results.lock().expect("generation result lock poisoned");
    for (index, slot) in slots.iter_mut().enumerate() {
        ordered.push(
            slot.take()
                .unwrap_or_else(|| RenderResult::cancelled(&records[index])),
        );
    }
    drop(slots);

    let mut summary = GenerationSummary {
        total_records: ordered.len(),
        ..Default::default()
    };
    summary.cancelled =
        cancellation.is_cancelled() || ordered.iter().any(|result| result.cancelled);
    for result in &ordered {
        if result.success {
            summary.completed_count += 1;
        } else if result.skipped {
            summary.skipped_count += 1;
        } else if result.cancelled {
            summary.cancelled_count += 1;
        } else {
            summary.failed_count += 1;
        }
    }
    summary.results = ordered;

    if let Some(sender) = &options.progress {
        for (index, result) in summary.results.iter().cloned().enumerate() {
            let _ = sender.send(GenerationEvent::Record {
                index,
                total: summary.total_records,
                result,
            });
        }
        let _ = sender.send(GenerationEvent::Finished {
            summary: summary.clone(),
        });
    }
    log::info!(
        "generate_batch: completed: {} success, {} skipped, {} failed, {} cancelled",
        summary.completed_count,
        summary.skipped_count,
        summary.failed_count,
        summary.cancelled_count
    );
    Ok(summary)
}

fn render_one(
    template: &TemplateDefinition,
    record: &SourceRecord,
    photo_match: Option<&PhotoMatchResult>,
    settings: &RenderSettings,
    output_path: &Path,
) -> RenderResult {
    let mut pin = record.pin_or_raw().to_owned();
    if pin.is_empty() {
        for (col, val) in &record.data {
            let col_lower = col.to_lowercase();
            if (col_lower.contains("id")
                || col_lower.contains("pin")
                || col_lower.contains("roll")
                || col_lower.contains("code")
                || col_lower.contains("emp"))
                && !val.is_null()
            {
                if let Some(s) = val.as_str() {
                    let trimmed = s.trim();
                    if !trimmed.is_empty() {
                        pin = trimmed.to_owned();
                        break;
                    }
                }
            }
        }
    }
    if pin.is_empty() {
        pin = format!("REC-{}", record.row_index);
    }

    let base = RenderResult {
        record_id: record.record_id.clone(),
        pin,
        success: false,
        skipped: false,
        cancelled: false,
        output_path: Some(output_path.to_path_buf()),
        image_path: Some(output_path.display().to_string()),
        warnings: Vec::new(),
        error: None,
    };
    if !record.is_valid() {
        return with_error(
            base,
            GenerationRecordError::InvalidRecord {
                details: record.validation_errors.join("; "),
            },
        );
    }

    let photo_path = photo_match
        .and_then(|matched| matched.photo_path.as_deref())
        .map(Path::new);
    let photo_path = photo_path.filter(|path| path.is_file());
    if photo_path.is_none() {
        match settings.missing_photo_policy {
            MissingPhotoPolicy::SkipRecord => {
                let mut result = base;
                result.skipped = true;
                result.output_path = None;
                result.image_path = None;
                result.warnings.push(RenderWarning::MissingPhoto {
                    pin: record.pin_or_raw().to_owned(),
                });
                return result;
            }
            MissingPhotoPolicy::FailRecord => {
                return with_error(
                    base,
                    GenerationRecordError::MissingPhoto {
                        pin: record.pin_or_raw().to_owned(),
                    },
                );
            }
            MissingPhotoPolicy::GenerateWithPlaceholder => {}
        }
    }

    let rendered = match NativeRenderer::render_with_settings(
        template,
        Some(record),
        photo_path,
        Some(settings),
    ) {
        Ok(rendered) => rendered,
        Err(error) => return with_error(base, render_error(error)),
    };
    let warnings = rendered.warnings.clone();
    if let Err(error) = write_atomic(&rendered, template, settings, output_path) {
        return with_error_and_warnings(base, error, warnings);
    }
    log::debug!(
        "render_one: SUCCESS record #{} (PIN: '{}') -> {}",
        record.row_index,
        base.pin,
        output_path.display()
    );
    RenderResult {
        success: true,
        warnings,
        ..base
    }
}

fn with_error(mut result: RenderResult, error: GenerationRecordError) -> RenderResult {
    log::warn!(
        "render_one: FAILED record ID '{}' (PIN: '{}'): {}",
        result.record_id,
        result.pin,
        error
    );
    result.output_path = None;
    result.image_path = None;
    result.error = Some(error);
    result
}

fn with_error_and_warnings(
    mut result: RenderResult,
    error: GenerationRecordError,
    warnings: Vec<RenderWarning>,
) -> RenderResult {
    result.warnings = warnings;
    with_error(result, error)
}

fn render_error(error: RenderError) -> GenerationRecordError {
    GenerationRecordError::Render {
        details: error.to_string(),
    }
}

fn write_atomic(
    rendered: &crate::rendering::RenderedImage,
    template: &TemplateDefinition,
    settings: &RenderSettings,
    destination: &Path,
) -> Result<(), GenerationRecordError> {
    let parent = destination.parent().unwrap_or_else(|| Path::new("."));
    let name = destination
        .file_name()
        .and_then(|name| name.to_str())
        .unwrap_or("output");
    let temp = loop {
        let id = TEMP_FILE_COUNTER.fetch_add(1, Ordering::Relaxed);
        let candidate = parent.join(format!(".{name}.tmp-{}-{id}", std::process::id()));
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
    let (temp_path, mut file) = temp;
    let result = rendered
        .encode(template, settings, &mut file)
        .and_then(|_| {
            file.sync_all().map_err(|error| RenderError::Encode {
                format: "output".into(),
                details: error.to_string(),
            })
        });
    drop(file);
    if let Err(error) = result {
        let _ = fs::remove_file(&temp_path);
        return Err(render_error(error));
    }
    if destination.exists() {
        let _ = fs::remove_file(&temp_path);
        return Err(GenerationRecordError::Collision {
            path: destination.display().to_string(),
        });
    }
    if let Err(error) = fs::rename(&temp_path, destination) {
        let _ = fs::remove_file(&temp_path);
        return Err(GenerationRecordError::Write {
            path: destination.display().to_string(),
            details: error.to_string(),
        });
    }
    Ok(())
}

pub(crate) fn output_extension(format: &OutputFormat) -> &'static str {
    match format {
        OutputFormat::Png => "png",
        OutputFormat::Jpeg => "jpg",
    }
}

pub(crate) fn allocate_names(
    records: &[SourceRecord],
    pattern: &str,
    extension: &str,
    output_dir: &Path,
) -> Vec<PathBuf> {
    let mut occupied = BTreeSet::new();
    if let Ok(entries) = fs::read_dir(output_dir) {
        for entry in entries.flatten() {
            if entry.path().is_file() {
                if let Some(name) = entry.file_name().to_str() {
                    occupied.insert(name.to_owned());
                }
            }
        }
    }
    records
        .iter()
        .map(|record| {
            let stem = format_output_stem(pattern, record);
            let base = format!("{stem}.{extension}");
            let mut candidate = base.clone();
            let mut suffix = 2;
            while occupied.contains(&candidate) {
                candidate = format!("{stem}_{suffix}.{extension}");
                suffix += 1;
            }
            occupied.insert(candidate.clone());
            output_dir.join(candidate)
        })
        .collect()
}

pub(crate) fn format_output_stem(pattern: &str, record: &SourceRecord) -> String {
    let pin_raw = record.pin_or_raw();
    let fallback_pin;
    let pin_str = if pin_raw.is_empty() {
        fallback_pin = format!("REC-{}", record.row_index);
        &fallback_pin
    } else {
        pin_raw
    };
    let pin = sanitize_filename_component(pin_str);
    let name = sanitize_filename_component(&record_name(record));
    let pattern = if pattern.trim().is_empty() {
        "{PIN_NUMBER}_{NAME}"
    } else {
        pattern
    };
    let expanded = pattern
        .replace("{PIN_NUMBER}", &pin)
        .replace("{NAME}", &name);
    let safe = sanitize_filename_component(&expanded);
    if safe.is_empty() {
        "Card".into()
    } else {
        safe
    }
}

pub(crate) fn sanitize_filename_component(value: &str) -> String {
    let mut result = String::with_capacity(value.len());
    for character in value.trim().chars() {
        if character.is_control()
            || matches!(
                character,
                '<' | '>' | ':' | '"' | '/' | '\\' | '|' | '?' | '*'
            )
        {
            result.push('_');
        } else {
            result.push(character);
        }
    }
    let result = result
        .trim_matches(|character| character == '.' || character == ' ')
        .to_owned();
    if is_reserved_windows_name(&result) {
        format!("_{result}")
    } else {
        result
    }
}

fn is_reserved_windows_name(value: &str) -> bool {
    let stem = value
        .split('.')
        .next()
        .unwrap_or(value)
        .to_ascii_uppercase();
    matches!(
        stem.as_str(),
        "CON"
            | "PRN"
            | "AUX"
            | "NUL"
            | "COM1"
            | "COM2"
            | "COM3"
            | "COM4"
            | "COM5"
            | "COM6"
            | "COM7"
            | "COM8"
            | "COM9"
            | "LPT1"
            | "LPT2"
            | "LPT3"
            | "LPT4"
            | "LPT5"
            | "LPT6"
            | "LPT7"
            | "LPT8"
            | "LPT9"
    )
}

fn record_name(record: &SourceRecord) -> String {
    record.get_value("Name").if_empty_then(|| {
        record
            .data
            .iter()
            .find(|(key, value)| key.to_ascii_lowercase().contains("name") && !value.is_null())
            .map(|(_, value)| match value {
                serde_json::Value::String(value) => value.clone(),
                value => value.to_string(),
            })
            .unwrap_or_else(|| "Card".into())
    })
}

trait EmptyThen {
    fn if_empty_then(self, fallback: impl FnOnce() -> String) -> String;
}
impl EmptyThen for String {
    fn if_empty_then(self, fallback: impl FnOnce() -> String) -> String {
        if self.is_empty() {
            fallback()
        } else {
            self
        }
    }
}
