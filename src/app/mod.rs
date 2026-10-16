//! Native workflow shell for the Rust migration.
//!
//! The shell deliberately keeps the domain modules independent from egui.  It
//! owns short-lived UI state, starts expensive operations on worker threads,
//! and applies completed values on the UI thread as bounded channel messages.
//! Import, worksheet listing, generation, and export use `TaskManager` as the
//! application-wide status/cancellation adapter while retaining their typed
//! domain result messages for the UI state update.

use std::{
    collections::BTreeMap,
    path::{Path, PathBuf},
    process::Command,
    thread,
    time::Duration,
};

use crossbeam_channel::{unbounded, Receiver, SendTimeoutError, Sender, TryRecvError};
use eframe::egui::{self, Color32, RichText};
use rfd::FileDialog;

use crate::{
    data::{
        importer::{import_spreadsheet, list_worksheets, ImportOptions, ImportResult},
        models::{
            ExportConfiguration, MissingPhotoPolicy, OutputFormat, ProjectConfiguration,
            RenderSettings, ReviewStatus, SourceRecord, TemplateDefinition, TextOverflowPolicy,
            ThemePreference,
        },
    },
    editor::geometry::{calculate_card_dimensions, convert_unit, pixels_to_physical, Unit},
    export::{export_batch, ExportRequest},
    generation::{
        generate_batch, CancellationToken, GenerationEvent, GenerationOptions, GenerationSummary,
        RenderResult,
    },
    photos::{MatchSummary, PhotoIndex, PhotoLibrary, PhotoMatcher},
    projects::ProjectStore,
    review::ReviewManager,
    tasks::{
        IndexEvent, PhotoDiscovery, PhotoIndexingTask, TaskContext, TaskEvent, TaskHandle,
        TaskKind, TaskManager, ThumbnailPriority, ThumbnailQueue, ThumbnailRequest,
    },
    templates::{builtin_templates, BUILTIN_TEMPLATE_IDS},
    ui::{
        MappingEditor, MappingEditorState, NewCanvasDialogState, TemplateEditor,
        TemplateEditorState,
    },
};

const CHANNEL_CAPACITY: usize = 1024;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum WorkflowPage {
    Dashboard,
    DataSource,
    Photos,
    Templates,
    TemplateEditor,
    Mapping,
    Generate,
    Review,
    Export,
    Settings,
}

impl WorkflowPage {
    const ALL: [Self; 10] = [
        Self::Dashboard,
        Self::DataSource,
        Self::Photos,
        Self::Templates,
        Self::TemplateEditor,
        Self::Mapping,
        Self::Generate,
        Self::Review,
        Self::Export,
        Self::Settings,
    ];

    fn label(self) -> &'static str {
        match self {
            Self::Dashboard => "Dashboard",
            Self::DataSource => "Data Source",
            Self::Photos => "Photos",
            Self::Templates => "Templates",
            Self::TemplateEditor => "Template Editor",
            Self::Mapping => "Mapping",
            Self::Generate => "Generate",
            Self::Review => "Review",
            Self::Export => "Export",
            Self::Settings => "Settings",
        }
    }
}

enum WorkerMessage {
    Worksheets {
        path: PathBuf,
        result: Result<Vec<String>, String>,
    },
    Imported(Result<ImportResult, String>),
    ImportCancelled,
    GenerationProgress(GenerationEvent),
    Generated(Result<GenerationSummary, String>),
    Exported(Result<crate::data::models::ExportResult, String>),
    LibraryReady(Result<PhotoLibrary, String>),
    Regenerated(Result<RenderResult, String>),
    OutputFolderOpened(Result<(), String>),
}

fn send_worker_message(
    sender: &Sender<WorkerMessage>,
    mut message: WorkerMessage,
    context: &TaskContext,
) -> bool {
    loop {
        if context.is_shutdown_requested() || context.is_cancelled() {
            return false;
        }
        match sender.send_timeout(message, Duration::from_millis(25)) {
            Ok(()) => return true,
            Err(SendTimeoutError::Timeout(returned)) => message = returned,
            Err(SendTimeoutError::Disconnected(_)) => return false,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
enum BusyKind {
    Worksheets,
    Import,
    Generation,
    Export,
    PhotoLibrary,
}

struct BusyState {
    kind: BusyKind,
    label: String,
    progress: Option<(usize, usize)>,
    cancel: Option<CancellationToken>,
    task: Option<TaskHandle>,
    cancel_requested: bool,
}

pub struct MigrationApp {
    project_path: Option<PathBuf>,
    project: ProjectConfiguration,
    page: WorkflowPage,
    theme: ThemePreference,
    status: String,
    dirty: bool,
    recovery_status: Option<String>,

    worker_sender: Sender<WorkerMessage>,
    worker_receiver: Receiver<WorkerMessage>,
    task_manager: TaskManager,
    busy: Option<BusyState>,

    source_path_text: String,
    worksheets: Vec<String>,
    selected_sheet: usize,
    header_row: usize,
    pin_column_hint: String,
    columns: Vec<String>,
    records: Vec<SourceRecord>,
    data_search_query: String,

    photo_root: Option<PathBuf>,
    photo_index: Option<PhotoIndex>,
    photo_library: Option<PhotoLibrary>,
    photo_discovered: usize,
    photo_rows: Vec<PhotoDiscovery>,
    photo_indexing: Option<PhotoIndexingTask>,
    thumbnail_queue: ThumbnailQueue,
    thumbnail_request: Option<ThumbnailRequest>,
    thumbnail_texture: Option<egui::TextureHandle>,
    thumbnail_label: String,
    review_thumbnail_request: Option<ThumbnailRequest>,
    review_thumbnail_texture: Option<egui::TextureHandle>,
    review_preview_path: Option<String>,
    review_preview_label: String,
    review_zoom: f32,
    review_pan: egui::Vec2,
    review_filter_pending_only: bool,
    review_search_query: String,
    match_results: BTreeMap<String, crate::data::models::PhotoMatchResult>,
    match_summary: MatchSummary,

    templates: Vec<(String, TemplateDefinition)>,
    selected_template_id: String,
    editor_state: TemplateEditorState,
    new_canvas_dialog: NewCanvasDialogState,
    mapping_state: MappingEditorState,
    selected_sample: usize,

    output_dir: String,
    export_dir: String,
    naming_pattern: String,
    canvas_width: f64,
    canvas_height: f64,
    canvas_unit: String,
    canvas_dpi: u32,
    canvas_orientation: String,
    canvas_background: String,
    export_format: OutputFormat,
    export_jpeg_quality: u8,
    export_approved_only: bool,
    export_manifest: bool,
    export_contact_sheet: bool,
    export_open_folder: bool,
    generation_summary: Option<GenerationSummary>,
    generated_results: BTreeMap<String, RenderResult>,
    review: ReviewManager,
    last_export: Option<crate::data::models::ExportResult>,
}

impl MigrationApp {
    pub fn new(context: &eframe::CreationContext<'_>, project_path: Option<PathBuf>) -> Self {
        let (worker_sender, worker_receiver) = unbounded();
        let mut app = Self {
            project_path,
            project: ProjectConfiguration::default(),
            page: WorkflowPage::Dashboard,
            theme: ThemePreference::System,
            status: "Native workflow shell ready".into(),
            dirty: false,
            recovery_status: None,
            worker_sender,
            worker_receiver,
            task_manager: TaskManager::new(CHANNEL_CAPACITY),
            busy: None,
            source_path_text: String::new(),
            worksheets: Vec::new(),
            selected_sheet: 0,
            header_row: 0,
            pin_column_hint: String::new(),
            columns: Vec::new(),
            records: Vec::new(),
            data_search_query: String::new(),
            photo_root: None,
            photo_index: None,
            photo_library: None,
            photo_discovered: 0,
            photo_rows: Vec::new(),
            photo_indexing: None,
            thumbnail_queue: ThumbnailQueue::new(32, 32 * 1024 * 1024),
            thumbnail_request: None,
            thumbnail_texture: None,
            thumbnail_label: String::new(),
            review_thumbnail_request: None,
            review_thumbnail_texture: None,
            review_preview_path: None,
            review_preview_label: String::new(),
            review_zoom: 1.0,
            review_pan: egui::Vec2::ZERO,
            review_filter_pending_only: true,
            review_search_query: String::new(),
            match_results: BTreeMap::new(),
            match_summary: MatchSummary::default(),
            templates: builtin_templates()
                .unwrap_or_default()
                .into_iter()
                .enumerate()
                .map(|(index, template)| {
                    (
                        BUILTIN_TEMPLATE_IDS
                            .get(index)
                            .copied()
                            .unwrap_or("builtin-template")
                            .to_owned(),
                        template,
                    )
                })
                .collect(),
            selected_template_id: String::new(),
            editor_state: TemplateEditorState::default(),
            new_canvas_dialog: NewCanvasDialogState::default(),
            mapping_state: MappingEditorState::default(),
            selected_sample: 0,
            output_dir: "staging".into(),
            export_dir: "export".into(),
            naming_pattern: "{PIN_NUMBER}_{NAME}".into(),
            canvas_width: 85.6,
            canvas_height: 54.0,
            canvas_unit: "mm".into(),
            canvas_dpi: 300,
            canvas_orientation: "landscape".into(),
            canvas_background: "#FFFFFF".into(),
            export_format: OutputFormat::Png,
            export_jpeg_quality: 95,
            export_approved_only: true,
            export_manifest: true,
            export_contact_sheet: false,
            export_open_folder: false,
            generation_summary: None,
            generated_results: BTreeMap::new(),
            review: ReviewManager::default(),
            last_export: None,
        };

        if let Some(path) = app.project_path.clone() {
            app.load_project(path);
        }
        app.apply_theme(&context.egui_ctx);
        app
    }

    fn apply_theme(&self, context: &egui::Context) {
        match self.theme {
            ThemePreference::Black => context.set_visuals(egui::Visuals::dark()),
            ThemePreference::White => context.set_visuals(egui::Visuals::light()),
            ThemePreference::System => context.set_visuals(egui::Visuals::default()),
        }
    }

    fn set_theme(&mut self, context: &egui::Context, theme: ThemePreference) {
        log::info!("Theme changed to: {:?}", theme);
        self.theme = theme.clone();
        self.project.theme = theme_label(&theme).into();
        self.apply_theme(context);
        self.dirty = true;
        if self.project_path.is_some() {
            match self.save_project() {
                Ok(()) => self.status = format!("Theme saved: {}", theme_label(&theme)),
                Err(error) => self.status = format!("Theme changed; save failed: {error}"),
            }
        } else {
            self.status = format!(
                "Theme updated: {} (save the project to persist it)",
                theme_label(&theme)
            );
        }
    }

    fn load_project(&mut self, path: PathBuf) {
        log::info!("Loading project from: {}", path.display());
        match ProjectStore::load_project_with_metadata(&path) {
            Ok(loaded) => {
                log::info!(
                    "Project '{}' loaded successfully (recovered: {})",
                    loaded.value.project_name,
                    loaded.recovery.recovered_from_backup
                );
                self.project = loaded.value;
                self.theme = theme_from_string(&self.project.theme);
                self.source_path_text = self.project.excel_file_path.clone().unwrap_or_default();
                self.photo_root = self.project.photo_dir_path.clone().map(PathBuf::from);
                self.output_dir = self
                    .project
                    .last_export_dir
                    .clone()
                    .unwrap_or_else(|| "staging".into());
                self.export_dir = self.output_dir.clone();
                self.export_open_folder = self.project.open_output_dir_on_export;
                self.export_format = self.project.export_format.clone();
                self.export_jpeg_quality = self.project.export_jpeg_quality;
                self.naming_pattern = self.project.export_naming_pattern.clone();
                self.export_approved_only = self.project.export_approved_only;
                self.export_manifest = self.project.export_manifest;
                self.selected_template_id = self
                    .project
                    .template
                    .as_ref()
                    .map(|template| template.id.clone())
                    .unwrap_or_default();
                if let Some(template) = self.project.template.clone() {
                    self.load_canvas_controls(&template);
                }
                self.recovery_status = loaded.recovery.recovered_from_backup.then(|| {
                    format!(
                        "Recovered from backup; primary error: {}",
                        loaded.recovery.primary_error.unwrap_or_default()
                    )
                });
                self.project_path = Some(path.clone());
                self.dirty = false;
                self.status = if self.recovery_status.is_some() {
                    format!("Recovered project: {}", self.project.project_name)
                } else {
                    format!("Loaded project: {}", self.project.project_name)
                };
                self.rebuild_review();
            }
            Err(error) => {
                log::error!("Failed to load project from {}: {}", path.display(), error);
                self.status = format!("Could not load project: {error}");
            }
        }
    }

    fn new_project(&mut self) {
        log::info!("Creating new empty project");
        self.project_path = None;
        self.project = ProjectConfiguration::default();
        self.theme = ThemePreference::System;
        self.source_path_text.clear();
        self.worksheets.clear();
        self.columns.clear();
        self.records.clear();
        self.photo_index = None;
        self.photo_library = None;
        self.photo_rows.clear();
        self.match_results.clear();
        self.match_summary = MatchSummary::default();
        self.selected_template_id.clear();
        self.generation_summary = None;
        self.generated_results.clear();
        self.review = ReviewManager::default();
        self.last_export = None;
        self.output_dir = "staging".into();
        self.export_dir = "export".into();
        self.naming_pattern = "{PIN_NUMBER}_{NAME}".into();
        self.export_format = OutputFormat::Png;
        self.export_jpeg_quality = 95;
        self.project.export_format = self.export_format.clone();
        self.project.export_jpeg_quality = self.export_jpeg_quality;
        self.project.export_naming_pattern = self.naming_pattern.clone();
        self.export_approved_only = true;
        self.export_manifest = true;
        self.project.export_approved_only = true;
        self.project.export_manifest = true;
        self.export_open_folder = false;
        self.load_canvas_controls(&TemplateDefinition::default());
        self.recovery_status = None;
        self.dirty = true;
        self.status = "New project created".into();
    }

    fn open_project_dialog(&mut self) {
        if let Some(path) = FileDialog::new()
            .add_filter("Project JSON", &["json"])
            .pick_file()
        {
            log::info!("Selected project file to open: {}", path.display());
            self.load_project(path);
        }
    }

    fn save_project_dialog(&mut self) {
        let path = FileDialog::new()
            .set_file_name("project.json")
            .add_filter("Project JSON", &["json"])
            .save_file();
        if let Some(path) = path {
            log::info!("Chose save destination: {}", path.display());
            self.project_path = Some(path);
            if let Err(error) = self.save_project() {
                self.status = format!("Save failed: {error}");
            }
        }
    }

    fn save_project(&mut self) -> Result<(), String> {
        self.review
            .apply_to_project_configuration(&mut self.project);
        self.project.last_export_dir =
            (!self.export_dir.trim().is_empty()).then(|| self.export_dir.clone());
        self.project.export_format = self.export_format.clone();
        self.project.export_jpeg_quality = self.export_jpeg_quality;
        self.project.export_naming_pattern = self.naming_pattern.clone();
        self.project.export_approved_only = self.export_approved_only;
        self.project.export_manifest = self.export_manifest;
        self.project.open_output_dir_on_export = self.export_open_folder;
        let Some(path) = self.project_path.as_deref() else {
            log::warn!("Attempted to save project without an established path");
            return Err("choose a project path first".into());
        };
        log::info!(
            "Saving project '{}' to {}",
            self.project.project_name,
            path.display()
        );
        ProjectStore::save_project(path, &self.project).map_err(|error| {
            log::error!("Failed to save project to {}: {}", path.display(), error);
            error.to_string()
        })?;
        log::info!("Project saved successfully to {}", path.display());
        self.dirty = false;
        self.status = format!("Saved {}", path.display());
        Ok(())
    }

    fn start_sheet_listing(&mut self, path: PathBuf) {
        log::info!("Listing worksheets for: {}", path.display());
        let task_sender = self.worker_sender.clone();
        let task_path = path.clone();
        let task = self.task_manager.spawn(TaskKind::Import, move |context| {
            let result = list_worksheets(&task_path).map_err(|error| error.to_string());
            let task_result = if context.is_cancelled() {
                Err("cancelled".to_owned())
            } else {
                result.as_ref().err().cloned().map_or(Ok(()), Err)
            };
            let _ = send_worker_message(
                &task_sender,
                WorkerMessage::Worksheets { path, result },
                &context,
            );
            task_result
        });
        let Ok(task) = task else {
            log::error!("Could not spawn worksheet listing task");
            self.status = "Could not start worksheet listing".into();
            return;
        };
        self.busy = Some(BusyState {
            kind: BusyKind::Worksheets,
            label: "Reading worksheet names…".into(),
            progress: None,
            cancel: None,
            task: Some(task),
            cancel_requested: false,
        });
    }

    fn choose_data_source(&mut self) {
        if let Some(path) = FileDialog::new()
            .add_filter("Spreadsheet", &["csv", "xlsx", "xls"])
            .pick_file()
        {
            log::info!("Selected data source file: {}", path.display());
            self.source_path_text = path.display().to_string();
            self.project.excel_file_path = Some(self.source_path_text.clone());
            self.start_sheet_listing(path);
            self.dirty = true;
        }
    }

    fn start_import(&mut self) {
        let path = PathBuf::from(self.source_path_text.trim());
        if !path.is_file() {
            log::warn!(
                "Cannot start import: source path '{}' is not an existing file",
                path.display()
            );
            self.status = "Choose an existing CSV/XLSX/XLS source first".into();
            return;
        }
        let sheet_name = self.worksheets.get(self.selected_sheet).cloned();
        log::info!(
            "Starting import from {} (sheet: {:?}, header_row: {}, pin_hint: {:?})",
            path.display(),
            sheet_name,
            self.header_row,
            self.pin_column_hint
        );
        let options = ImportOptions {
            sheet_name,
            header_row: self.header_row,
            pin_column_hint: (!self.pin_column_hint.trim().is_empty())
                .then(|| self.pin_column_hint.clone()),
        };
        let sender = self.worker_sender.clone();
        self.busy = Some(BusyState {
            kind: BusyKind::Import,
            label: format!(
                "Importing {}…",
                path.file_name().unwrap_or_default().to_string_lossy()
            ),
            progress: None,
            cancel: None,
            task: None,
            cancel_requested: false,
        });
        let task = self.task_manager.spawn(TaskKind::Import, move |context| {
            let result = import_spreadsheet(path, &options).map_err(|error| error.to_string());
            let cancelled = context.is_cancelled();
            if cancelled {
                let _ = send_worker_message(&sender, WorkerMessage::ImportCancelled, &context);
                Err("cancelled".to_owned())
            } else {
                let task_result = result.as_ref().err().cloned().map_or(Ok(()), Err);
                let _ = send_worker_message(&sender, WorkerMessage::Imported(result), &context);
                task_result
            }
        });
        match task {
            Ok(task) => {
                if let Some(busy) = self.busy.as_mut() {
                    busy.task = Some(task);
                }
            }
            Err(_) => {
                log::error!("Could not spawn spreadsheet import task");
                self.busy = None;
                self.status = "Could not start import".into();
            }
        }
    }

    fn start_photo_indexing(&mut self) {
        let Some(root) = self.photo_root.clone() else {
            log::warn!("Cannot start photo indexing: no photo folder selected");
            self.status = "Choose a photo folder first".into();
            return;
        };
        if !root.is_dir() {
            log::warn!(
                "Cannot start photo indexing: directory does not exist: {}",
                root.display()
            );
            self.status = format!("Photo folder does not exist: {}", root.display());
            return;
        }
        log::info!("Starting background photo indexing for: {}", root.display());
        self.photo_index = None;
        self.photo_library = None;
        self.photo_discovered = 0;
        self.photo_rows.clear();
        self.photo_indexing = Some(PhotoIndexingTask::start(&root, 32, 4));
        self.busy = Some(BusyState {
            kind: BusyKind::PhotoLibrary,
            label: "Discovering photos…".into(),
            progress: None,
            cancel: None,
            task: None,
            cancel_requested: false,
        });
        self.status = format!("Scanning {}", root.display());
    }

    fn choose_photo_folder(&mut self) {
        if let Some(path) = FileDialog::new().pick_folder() {
            log::info!("Selected photo folder: {}", path.display());
            self.photo_root = Some(path.clone());
            self.project.photo_dir_path = Some(path.display().to_string());
            self.start_photo_indexing();
            self.dirty = true;
        }
    }

    fn start_library_refresh(&mut self, root: PathBuf) {
        log::info!("Starting library refresh for: {}", root.display());
        let sender = self.worker_sender.clone();
        thread::spawn(move || {
            let mut library = PhotoLibrary::new(&root);
            let result = library
                .rescan()
                .map(|_| library)
                .map_err(|error| error.to_string());
            let _ = sender.send(WorkerMessage::LibraryReady(result));
        });
    }

    fn refresh_photo_matches(&mut self) {
        let Some(index) = self.photo_index.clone() else {
            log::debug!("Photo matching skipped: photo index not ready yet");
            self.match_results.clear();
            self.match_summary = MatchSummary::default();
            return;
        };
        let key_col = self.project.photo_key_column.clone().or_else(|| {
            self.records
                .first()
                .and_then(|_| self.columns.first().cloned())
        });
        log::info!(
            "Matching photos for {} records against indexed photos (key_column: {:?}, prefix: {:?}, suffix: {:?})",
            self.records.len(),
            key_col,
            self.project.photo_prefix,
            self.project.photo_suffix
        );
        let mut matcher = PhotoMatcher::default();
        matcher.set_index(index);
        matcher.set_key_column(key_col);
        matcher.set_affixes(
            self.project.photo_prefix.clone(),
            self.project.photo_suffix.clone(),
        );
        for (key, path) in &self.project.photo_overrides {
            matcher.set_override(key.clone(), path.clone());
        }
        let (results, summary) = matcher.match_all(&self.records);
        log::info!(
            "Photo matching completed: {} matched, {} missing, {} ambiguous",
            summary.matched_count,
            summary.missing_count,
            summary.ambiguous_count
        );
        self.match_results = results;
        self.match_summary = summary;
    }

    fn choose_template(&mut self, id: String, template: TemplateDefinition) {
        log::info!("Selected template: '{}' (ID: {})", template.name, id);
        self.selected_template_id = id;
        self.load_canvas_controls(&template);
        self.project.template = Some(template);
        self.editor_state = TemplateEditorState::default();
        self.mapping_state = MappingEditorState::default();
        self.dirty = true;
        self.status = "Template selected".into();
    }

    fn create_blank_template(&mut self) {
        log::info!("Opening new blank canvas dialog");
        self.new_canvas_dialog.open();
    }

    fn start_generation(&mut self) {
        let Some(template) = self.project.template.clone() else {
            log::warn!("Cannot start generation: no template selected");
            self.status = "Choose or create a template first".into();
            return;
        };
        if self.records.is_empty() {
            log::warn!("Cannot start generation: no source records imported");
            self.status = "Import source records before generating".into();
            return;
        }
        let output_dir = PathBuf::from(self.output_dir.trim());
        if output_dir.as_os_str().is_empty() {
            log::warn!("Cannot start generation: staging output folder is empty");
            self.status = "Choose a staging output folder first".into();
            return;
        }
        log::info!(
            "Starting batch card generation: {} records (template: '{}', output_dir: {})",
            self.records.len(),
            template.name,
            output_dir.display()
        );
        let token = CancellationToken::new();
        let worker_token = token.clone();
        let records = self.records.clone();
        let matches = (!self.match_results.is_empty()).then(|| self.match_results.clone());
        let naming_pattern = self.naming_pattern.clone();
        let sender = self.worker_sender.clone();
        self.busy = Some(BusyState {
            kind: BusyKind::Generation,
            label: format!("Rendering {} cards…", records.len()),
            progress: Some((0, records.len())),
            cancel: Some(token),
            task: None,
            cancel_requested: false,
        });
        let task = self
            .task_manager
            .spawn(TaskKind::Generation, move |context| {
                let task_token = context.cancellation_token().clone();
                let generation_token = worker_token.clone();
                let cancellation_watcher = thread::spawn(move || {
                    while !task_token.is_cancelled() && !generation_token.is_cancelled() {
                        thread::sleep(Duration::from_millis(10));
                    }
                    if task_token.is_cancelled() {
                        generation_token.cancel();
                    }
                });
                let (progress_sender, progress_receiver) = std::sync::mpsc::channel();
                let forward_sender = sender.clone();
                let progress_context = context.clone();
                let forwarder = thread::spawn(move || {
                    for event in progress_receiver {
                        let is_finished = matches!(&event, GenerationEvent::Finished { .. });
                        if let GenerationEvent::Record { index, total, .. } = &event {
                            let _ = progress_context.report_progress(index + 1, Some(*total));
                        }
                        let _ = send_worker_message(
                            &forward_sender,
                            WorkerMessage::GenerationProgress(event),
                            &progress_context,
                        );
                        if is_finished {
                            break;
                        }
                    }
                });
                let mut options = GenerationOptions::new(output_dir);
                options.settings = RenderSettings {
                    dpi: template.dpi,
                    output_format: OutputFormat::Png,
                    jpeg_quality: 95,
                    missing_photo_policy: MissingPhotoPolicy::GenerateWithPlaceholder,
                    text_overflow_policy: TextOverflowPolicy::AutoShrink,
                };
                options.naming_pattern = naming_pattern;
                options.max_parallelism = 2;
                options.progress = Some(progress_sender);
                let result = generate_batch(
                    &template,
                    &records,
                    matches.as_ref(),
                    &options,
                    &worker_token,
                )
                .map_err(|error| error.to_string());
                drop(options.progress.take());
                let _ = forwarder.join();
                let task_result = result.as_ref().err().cloned().map_or(Ok(()), Err);
                let _ = send_worker_message(&sender, WorkerMessage::Generated(result), &context);
                worker_token.cancel();
                let _ = cancellation_watcher.join();
                task_result
            });
        match task {
            Ok(task) => {
                if let Some(busy) = self.busy.as_mut() {
                    busy.task = Some(task);
                }
            }
            Err(_) => {
                log::error!("Could not spawn batch generation task");
                self.busy = None;
                self.status = "Could not start generation".into();
            }
        }
    }

    fn start_regeneration(&mut self, record_id: String) {
        let Some(template) = self.project.template.clone() else {
            log::warn!("Cannot start regeneration: no template selected");
            self.status = "Choose a template before regenerating".into();
            return;
        };
        let Some(record) = self
            .records
            .iter()
            .find(|record| record.record_id == record_id)
            .cloned()
        else {
            log::warn!(
                "Cannot start regeneration: record ID '{}' is unavailable",
                record_id
            );
            self.status = "The selected source record is unavailable".into();
            return;
        };
        log::info!(
            "Starting regeneration for record {} (PIN: {})",
            record_id,
            record.pin
        );
        let matches = self.match_results.get(&record_id).cloned();
        let match_map = matches.map(|value| {
            let mut values = BTreeMap::new();
            values.insert(record_id.clone(), value);
            values
        });
        let output_dir = PathBuf::from(self.output_dir.trim());
        let naming_pattern = self.naming_pattern.clone();
        let sender = self.worker_sender.clone();
        let token = CancellationToken::new();
        let worker_token = token.clone();
        let _ = self.review.invalidate_regeneration(&record_id);
        self.sync_review_states();
        self.review_preview_path = None;
        self.review_thumbnail_texture = None;
        self.busy = Some(BusyState {
            kind: BusyKind::Generation,
            label: format!("Regenerating {}…", record.pin),
            progress: Some((0, 1)),
            cancel: Some(token),
            task: None,
            cancel_requested: false,
        });
        let task = self
            .task_manager
            .spawn(TaskKind::Generation, move |context| {
                let task_token = context.cancellation_token().clone();
                let generation_token = worker_token.clone();
                let cancellation_watcher = thread::spawn(move || {
                    while !task_token.is_cancelled() && !generation_token.is_cancelled() {
                        thread::sleep(Duration::from_millis(10));
                    }
                    if task_token.is_cancelled() {
                        generation_token.cancel();
                    }
                });
                let mut options = GenerationOptions::new(output_dir);
                options.settings = RenderSettings {
                    dpi: template.dpi,
                    output_format: OutputFormat::Png,
                    jpeg_quality: 95,
                    missing_photo_policy: MissingPhotoPolicy::GenerateWithPlaceholder,
                    text_overflow_policy: TextOverflowPolicy::AutoShrink,
                };
                options.naming_pattern = naming_pattern;
                options.max_parallelism = 1;
                let result = if context.is_cancelled() || worker_token.is_cancelled() {
                    Err("cancelled".into())
                } else {
                    generate_batch(
                        &template,
                        &[record],
                        match_map.as_ref(),
                        &options,
                        &worker_token,
                    )
                    .map_err(|error| error.to_string())
                    .and_then(|summary| {
                        summary
                            .results
                            .into_iter()
                            .next()
                            .ok_or_else(|| "regeneration produced no result".to_owned())
                    })
                };
                let task_result = result.as_ref().err().cloned().map_or(Ok(()), Err);
                let _ = send_worker_message(&sender, WorkerMessage::Regenerated(result), &context);
                worker_token.cancel();
                let _ = cancellation_watcher.join();
                task_result
            });
        match task {
            Ok(task) => {
                if let Some(busy) = self.busy.as_mut() {
                    busy.task = Some(task);
                }
            }
            Err(_) => {
                log::error!("Could not spawn regeneration task for record {}", record_id);
                self.busy = None;
                self.status = "Could not start regeneration".into();
            }
        }
    }

    fn start_export(&mut self) {
        if self.review.is_empty() {
            log::warn!("Cannot start export: no review records");
            self.status = "Import and generate records before exporting".into();
            return;
        }
        let output_dir = PathBuf::from(self.export_dir.trim());
        if output_dir.as_os_str().is_empty() {
            log::warn!("Cannot start export: export folder is empty");
            self.status = "Choose an export folder first".into();
            return;
        }
        log::info!(
            "Starting batch export to {} (approved_only: {}, format: {:?}, manifest: {})",
            output_dir.display(),
            self.export_approved_only,
            self.export_format,
            self.export_manifest
        );
        let config = ExportConfiguration {
            output_dir: output_dir.display().to_string(),
            format: self.export_format.clone(),
            jpeg_quality: self.export_jpeg_quality,
            naming_pattern: self.naming_pattern.clone(),
            approved_only: self.export_approved_only,
            export_manifest: self.export_manifest,
            export_contact_sheet: self.export_contact_sheet,
            open_output_dir_on_complete: self.export_open_folder,
        };
        let reviews = self.review.to_review_records();
        let source_records = self
            .records
            .iter()
            .cloned()
            .map(|record| (record.record_id.clone(), record))
            .collect::<BTreeMap<_, _>>();
        let generated_results = self.generated_results.clone();
        let match_results = self.match_results.clone();
        let template = self.project.template.clone();
        let sender = self.worker_sender.clone();
        let token = CancellationToken::new();
        let worker_token = token.clone();
        self.busy = Some(BusyState {
            kind: BusyKind::Export,
            label: "Exporting reviewed cards…".into(),
            progress: None,
            cancel: Some(token),
            task: None,
            cancel_requested: false,
        });
        let task = self.task_manager.spawn(TaskKind::Export, move |context| {
            let result = if context.is_cancelled() || worker_token.is_cancelled() {
                Err("cancelled".into())
            } else {
                export_batch(ExportRequest {
                    config: &config,
                    review_records: &reviews,
                    source_records: &source_records,
                    generated_results: &generated_results,
                    match_results: Some(&match_results),
                    template: template.as_ref(),
                })
                .map_err(|error| error.to_string())
            };
            let task_result = result.as_ref().err().cloned().map_or(Ok(()), Err);
            let _ = send_worker_message(&sender, WorkerMessage::Exported(result), &context);
            task_result
        });
        match task {
            Ok(task) => {
                if let Some(busy) = self.busy.as_mut() {
                    busy.task = Some(task);
                }
            }
            Err(_) => {
                log::error!("Could not spawn export task");
                self.busy = None;
                self.status = "Could not start export".into();
            }
        }
    }

    fn cancel_busy(&mut self) {
        if let Some(busy) = self.busy.as_mut() {
            log::info!("Cancelling active task: {}", busy.label);
            busy.cancel_requested = true;
            if let Some(token) = &busy.cancel {
                token.cancel();
            }
            if let Some(task) = &busy.task {
                task.cancel();
            }
            self.status = format!("Cancellation requested for {}", busy.label);
        }
        if let Some(task) = &self.photo_indexing {
            log::info!("Cancelling photo indexing task");
            task.cancel();
        }
    }

    fn poll_worker_messages(&mut self) {
        while let Ok(message) = self.worker_receiver.try_recv() {
            self.handle_worker_message(message);
        }
    }

    fn poll_task_events(&mut self) {
        while let Ok(event) = self.task_manager.try_recv() {
            let is_current = self
                .busy
                .as_ref()
                .and_then(|busy| busy.task.as_ref())
                .is_some_and(|task| task.id() == event.id());
            if !is_current {
                continue;
            }
            match event {
                TaskEvent::Progress { progress, .. } => {
                    if let Some(busy) = self.busy.as_mut() {
                        busy.progress = progress.total.map(|total| (progress.completed, total));
                        if let Some(message) = progress.message {
                            busy.label = message;
                        }
                    }
                }
                TaskEvent::Failed { error, .. } => {
                    self.status = format!("Task failed: {error}");
                }
                TaskEvent::Cancelled { .. } => {
                    self.status = "Task cancellation acknowledged".into();
                }
                TaskEvent::Started { .. } | TaskEvent::Completed { .. } => {}
            }
        }
    }

    fn handle_worker_message(&mut self, message: WorkerMessage) {
        match message {
            WorkerMessage::Worksheets { path, result } => {
                self.busy = None;
                match result {
                    Ok(worksheets) => {
                        log::info!(
                            "Worksheets loaded from '{}': {} sheet(s) -> {:?}",
                            path.display(),
                            worksheets.len(),
                            worksheets
                        );
                        self.worksheets = worksheets;
                        self.selected_sheet = 0;
                        self.status = format!("{} worksheet(s) available", self.worksheets.len());
                        if path
                            .extension()
                            .and_then(|value| value.to_str())
                            .is_some_and(|extension| extension.eq_ignore_ascii_case("csv"))
                        {
                            self.worksheets = vec!["Default".into()];
                        }
                    }
                    Err(error) => {
                        log::error!(
                            "Failed to read worksheets from '{}': {error}",
                            path.display()
                        );
                        self.status = format!("Could not read worksheets: {error}");
                    }
                }
            }
            WorkerMessage::Imported(result) => {
                self.busy = None;
                match result {
                    Ok(imported) => {
                        log::info!(
                            "Data import successful: {} records, {} columns, sheet='{}', PIN column={:?}",
                            imported.records.len(),
                            imported.columns.len(),
                            imported.sheet_name,
                            imported.pin_column
                        );
                        self.columns = imported.columns;
                        self.records = imported.records;
                        self.project.sheet_name = Some(imported.sheet_name);
                        self.project.header_row = self.header_row;
                        self.project.photo_key_column = imported.pin_column.clone();
                        self.pin_column_hint = imported.pin_column.clone().unwrap_or_default();
                        self.rebuild_review();
                        self.refresh_photo_matches();
                        self.dirty = true;
                        self.status = format!("Imported {} record(s)", self.records.len());
                    }
                    Err(error) => {
                        log::error!("Data import failed: {error}");
                        self.status = format!("Import failed: {error}");
                    }
                }
            }
            WorkerMessage::ImportCancelled => {
                log::warn!("Data import was cancelled by user");
                self.busy = None;
                self.status = "Import cancelled".into();
            }
            WorkerMessage::GenerationProgress(event) => {
                if let GenerationEvent::Record {
                    index,
                    total,
                    result,
                } = event
                {
                    log::debug!(
                        "Card render progress [{}/{}]: record='{}', pin='{}', success={}",
                        index + 1,
                        total,
                        result.record_id,
                        result.pin,
                        result.success
                    );
                    if let Some(busy) = self.busy.as_mut() {
                        busy.progress = Some((index + 1, total));
                    }
                    self.generated_results
                        .insert(result.record_id.clone(), result);
                }
            }
            WorkerMessage::Generated(result) => {
                let cancelled = self.busy.as_ref().is_some_and(|busy| busy.cancel_requested);
                self.busy = None;
                match result {
                    Ok(summary) => {
                        log::info!(
                            "Batch generation finished: {} completed, {} skipped, {} failed, {} cancelled",
                            summary.completed_count,
                            summary.skipped_count,
                            summary.failed_count,
                            summary.cancelled_count
                        );
                        self.generation_summary = Some(summary.clone());
                        self.generated_results = summary
                            .results
                            .iter()
                            .cloned()
                            .map(|item| (item.record_id.clone(), item))
                            .collect();
                        self.rebuild_review_from_generation(&summary);
                        self.page = WorkflowPage::Review;
                        self.dirty = true;
                        self.status = if cancelled || summary.cancelled {
                            "Generation cancelled".into()
                        } else {
                            format!(
                                "Generated {} card(s); {} failed",
                                summary.completed_count, summary.failed_count
                            )
                        };
                        self.request_review_preview();
                    }
                    Err(error) => {
                        log::error!("Generation failed: {error}");
                        self.status = format!("Generation failed: {error}");
                    }
                }
            }
            WorkerMessage::Exported(result) => {
                let cancelled = self.busy.as_ref().is_some_and(|busy| busy.cancel_requested);
                self.busy = None;
                match result {
                    Ok(export) if !cancelled => {
                        log::info!(
                            "Export finished: {} exported, {} skipped, {} failed (manifest: {:?}, contact sheet: {:?})",
                            export.exported_count,
                            export.skipped_count,
                            export.failed_count,
                            export.manifest_path,
                            export.contact_sheet_path
                        );
                        self.last_export = Some(export.clone());
                        self.project.last_export_dir = Some(self.export_dir.clone());
                        self.dirty = true;
                        if self.export_open_folder {
                            let path = PathBuf::from(self.export_dir.clone());
                            let sender = self.worker_sender.clone();
                            thread::spawn(move || {
                                let result = open_folder_with_platform_command(&path);
                                let _ = sender.send(WorkerMessage::OutputFolderOpened(result));
                            });
                        }
                        self.status = format!("Exported {} card(s)", export.exported_count);
                    }
                    Ok(_) => {
                        log::warn!("Export was cancelled after the active operation completed");
                        self.status = "Export cancelled after the active operation completed".into()
                    }
                    Err(error) => {
                        log::error!("Export failed: {error}");
                        self.status = if cancelled {
                            "Export cancelled".into()
                        } else {
                            format!("Export failed: {error}")
                        }
                    }
                }
            }
            WorkerMessage::LibraryReady(result) => match result {
                Ok(library) => {
                    let count = library.record_count();
                    log::info!("Photo library ready with {count} images");
                    self.photo_library = Some(library);
                    self.status = format!("Photo library ready: {count} image(s)");
                }
                Err(error) => {
                    log::error!("Photo library metadata failed: {error}");
                    self.status = format!("Photo library metadata failed: {error}");
                }
            },
            WorkerMessage::Regenerated(result) => {
                let cancelled = self.busy.as_ref().is_some_and(|busy| busy.cancel_requested);
                self.busy = None;
                match result {
                    Ok(rendered) if !cancelled && rendered.success => {
                        let path = rendered.image_path.clone();
                        let record_id = rendered.record_id.clone();
                        log::info!(
                            "Card regenerated successfully for record '{}' (PIN: '{}') -> {:?}",
                            record_id,
                            rendered.pin,
                            path
                        );
                        self.generated_results.insert(record_id.clone(), rendered);
                        let _ = self.review.regenerate(&record_id, path);
                        self.sync_review_states();
                        self.review_preview_path = None;
                        self.status = "Card regenerated and returned to pending review".into();
                    }
                    Ok(rendered) => {
                        log::warn!("Regeneration for record '{}' did not produce an image or was cancelled", rendered.record_id);
                        self.status = "Regeneration cancelled or did not produce an image".into()
                    }
                    Err(error) => {
                        log::error!("Regeneration failed: {error}");
                        self.status = format!("Regeneration failed: {error}");
                    }
                }
            }
            WorkerMessage::OutputFolderOpened(result) => match result {
                Ok(()) => self.status = "Opened output folder".into(),
                Err(error) => self.status = format!("Could not open output folder: {error}"),
            },
        }
    }

    fn poll_photo_indexing(&mut self) {
        let mut terminal = false;
        if let Some(task) = self.photo_indexing.as_mut() {
            loop {
                match task.try_recv() {
                    Ok(IndexEvent::Discovered {
                        batch,
                        indexed_count,
                    }) => {
                        self.photo_discovered = indexed_count;
                        self.photo_rows.extend(batch);
                        if let Some(busy) = self.busy.as_mut() {
                            busy.label = format!("Discovering photos… {indexed_count} found");
                        }
                    }
                    Ok(IndexEvent::Finished { index }) => {
                        self.photo_discovered = index.total_files();
                        self.photo_index = Some(index);
                        terminal = true;
                        break;
                    }
                    Ok(IndexEvent::Cancelled { indexed_count }) => {
                        self.photo_discovered = indexed_count;
                        terminal = true;
                        self.status =
                            format!("Photo scan cancelled after {indexed_count} image(s)");
                        break;
                    }
                    Ok(IndexEvent::Failed(error)) => {
                        terminal = true;
                        self.status = format!("Photo scan failed: {error}");
                        break;
                    }
                    Err(TryRecvError::Empty) => break,
                    Err(TryRecvError::Disconnected) => {
                        terminal = true;
                        break;
                    }
                }
            }
        }
        if terminal {
            if let Some(mut task) = self.photo_indexing.take() {
                let _ = task.join();
            }
            self.busy = None;
            if let (Some(root), Some(_)) = (self.photo_root.clone(), self.photo_index.as_ref()) {
                self.start_library_refresh(root);
            }
            self.refresh_photo_matches();
        }
    }

    fn poll_thumbnail(&mut self, context: &egui::Context) {
        let Some(request) = self.thumbnail_request.take() else {
            return;
        };
        match request.try_recv() {
            Ok(Ok(thumbnail)) => {
                let image = egui::ColorImage::from_rgba_unmultiplied(
                    [thumbnail.width as usize, thumbnail.height as usize],
                    &thumbnail.pixels,
                );
                self.thumbnail_texture = Some(context.load_texture(
                    "photo-preview",
                    image,
                    egui::TextureOptions::LINEAR,
                ));
            }
            Ok(Err(error)) => self.thumbnail_label = error.to_string(),
            Err(TryRecvError::Empty) => self.thumbnail_request = Some(request),
            Err(TryRecvError::Disconnected) => {
                self.thumbnail_label = "Thumbnail request closed".into()
            }
        }
    }

    fn poll_review_thumbnail(&mut self, context: &egui::Context) {
        let Some(request) = self.review_thumbnail_request.take() else {
            return;
        };
        match request.try_recv() {
            Ok(Ok(thumbnail)) => {
                let image = egui::ColorImage::from_rgba_unmultiplied(
                    [thumbnail.width as usize, thumbnail.height as usize],
                    &thumbnail.pixels,
                );
                self.review_thumbnail_texture = Some(context.load_texture(
                    "review-preview",
                    image,
                    egui::TextureOptions::LINEAR,
                ));
            }
            Ok(Err(error)) => self.review_preview_label = error.to_string(),
            Err(TryRecvError::Empty) => self.review_thumbnail_request = Some(request),
            Err(TryRecvError::Disconnected) => {
                self.review_preview_label = "Preview request closed".into()
            }
        }
    }

    fn request_review_preview(&mut self) {
        let path = self
            .review
            .current_record()
            .and_then(|record| record.rendered_image_path.clone());
        if path == self.review_preview_path
            && (path.is_some() || !self.review_preview_label.is_empty())
        {
            return;
        }
        self.review_preview_path = path.clone();
        self.review_thumbnail_texture = None;
        self.review_preview_label.clear();
        let Some(path) = path else {
            self.review_preview_label = "No rendered image is available".into();
            return;
        };
        match self
            .thumbnail_queue
            .request(Path::new(&path), 900, ThumbnailPriority::Visible)
        {
            Ok(request) => self.review_thumbnail_request = Some(request),
            Err(error) => self.review_preview_label = error.to_string(),
        }
    }

    fn request_first_thumbnail(&mut self) {
        let Some(library) = self.photo_library.as_ref() else {
            self.thumbnail_label = "Finish a photo scan first".into();
            return;
        };
        let Some(record) = library.records().next() else {
            self.thumbnail_label = "No images discovered yet".into();
            return;
        };
        match self
            .thumbnail_queue
            .request(&record.path, 320, ThumbnailPriority::Visible)
        {
            Ok(request) => {
                self.thumbnail_label = record.path.display().to_string();
                self.thumbnail_request = Some(request);
                self.thumbnail_texture = None;
            }
            Err(error) => self.thumbnail_label = error.to_string(),
        }
    }

    fn rebuild_review(&mut self) {
        self.review = ReviewManager::from_sources_with_comments(
            &self.records,
            &self.project.review_states,
            &self.project.review_comments,
        )
        .unwrap_or_default();
    }

    fn rebuild_review_from_generation(&mut self, summary: &GenerationSummary) {
        self.review = ReviewManager::from_generation(
            &self.records,
            &summary.results,
            &self.project.review_states,
        )
        .unwrap_or_default();
        for (record_id, comment) in &self.project.review_comments {
            let _ = self.review.set_comment(record_id, Some(comment.clone()));
        }
    }

    fn sync_review_states(&mut self) {
        self.review
            .apply_to_project_configuration(&mut self.project);
        self.dirty = true;
    }

    fn load_canvas_controls(&mut self, template: &TemplateDefinition) {
        let unit = Unit::parse(&template.unit).unwrap_or(Unit::Mm);
        self.canvas_width = template.width_physical.unwrap_or_else(|| {
            pixels_to_physical(template.width_px, template.dpi, unit).unwrap_or(85.6)
        });
        self.canvas_height = template.height_physical.unwrap_or_else(|| {
            pixels_to_physical(template.height_px, template.dpi, unit).unwrap_or(54.0)
        });
        self.canvas_unit = template.unit.clone();
        self.canvas_dpi = template.dpi;
        self.canvas_orientation = template.orientation.clone();
        self.canvas_background = template.background_color.clone();
    }

    #[allow(dead_code)]
    fn show_canvas_controls(
        &mut self,
        ui: &mut egui::Ui,
        template: &mut TemplateDefinition,
    ) -> bool {
        let before = template.clone();
        ui.collapsing("Blank canvas / geometry", |ui| {
            ui.horizontal(|ui| {
                ui.label("Width");
                ui.add(
                    egui::DragValue::new(&mut self.canvas_width)
                        .speed(0.1)
                        .range(0.01..=10000.0),
                );
                ui.label("Height");
                ui.add(
                    egui::DragValue::new(&mut self.canvas_height)
                        .speed(0.1)
                        .range(0.01..=10000.0),
                );
                ui.label(&self.canvas_unit);
            });
            ui.horizontal(|ui| {
                ui.label("Unit");
                egui::ComboBox::from_id_salt("canvas-unit")
                    .selected_text(&self.canvas_unit)
                    .show_ui(ui, |ui| {
                        for unit in ["mm", "cm", "inch"] {
                            if ui
                                .selectable_value(&mut self.canvas_unit, unit.into(), unit)
                                .changed()
                            {
                                let old_unit = Unit::parse(&template.unit).unwrap_or(Unit::Mm);
                                let new_unit = Unit::parse(&self.canvas_unit).unwrap_or(Unit::Mm);
                                self.canvas_width = convert_unit(
                                    self.canvas_width,
                                    old_unit,
                                    new_unit,
                                    self.canvas_dpi.max(1),
                                )
                                .unwrap_or(self.canvas_width);
                                self.canvas_height = convert_unit(
                                    self.canvas_height,
                                    old_unit,
                                    new_unit,
                                    self.canvas_dpi.max(1),
                                )
                                .unwrap_or(self.canvas_height);
                            }
                        }
                    });
                ui.label("DPI");
                ui.add(egui::DragValue::new(&mut self.canvas_dpi).range(1..=2400));
                ui.label("Orientation");
                egui::ComboBox::from_id_salt("canvas-orientation")
                    .selected_text(&self.canvas_orientation)
                    .show_ui(ui, |ui| {
                        ui.selectable_value(
                            &mut self.canvas_orientation,
                            "portrait".into(),
                            "portrait",
                        );
                        ui.selectable_value(
                            &mut self.canvas_orientation,
                            "landscape".into(),
                            "landscape",
                        );
                    });
            });
            ui.horizontal(|ui| {
                ui.label("Background color");
                ui.text_edit_singleline(&mut self.canvas_background);
            });

            let unit = Unit::parse(&self.canvas_unit);
            match unit.and_then(|unit| {
                calculate_card_dimensions(
                    self.canvas_width,
                    self.canvas_height,
                    unit,
                    self.canvas_dpi,
                    &self.canvas_orientation,
                )
            }) {
                Ok(dimensions) => {
                    template.width_px = dimensions.width_px;
                    template.height_px = dimensions.height_px;
                    template.width_physical = Some(self.canvas_width);
                    template.height_physical = Some(self.canvas_height);
                    template.unit = self.canvas_unit.clone();
                    template.dpi = self.canvas_dpi;
                    template.orientation = self.canvas_orientation.clone();
                    template.background_color = self.canvas_background.clone();
                    ui.small(format!(
                        "Calculated geometry: {} × {} px ({:.2} × {:.2} mm)",
                        dimensions.width_px,
                        dimensions.height_px,
                        dimensions.width_mm,
                        dimensions.height_mm
                    ));
                }
                Err(error) => {
                    ui.colored_label(Color32::RED, format!("Invalid geometry: {error}"));
                }
            }
        });
        *template != before
    }

    fn relink_reference(&mut self, key: &str) {
        let path = match key {
            "excel_file" => FileDialog::new()
                .add_filter("Spreadsheet", &["csv", "xlsx", "xls"])
                .pick_file(),
            "photo_dir" => FileDialog::new().pick_folder(),
            "background_image" => FileDialog::new()
                .add_filter("Image", &["png", "jpg", "jpeg", "bmp", "webp"])
                .pick_file(),
            _ => None,
        };
        let Some(path) = path else { return };
        let mut replacements = BTreeMap::new();
        replacements.insert(key.to_owned(), path.display().to_string());
        ProjectStore::relink_references(&mut self.project, &replacements);
        if key == "photo_dir" {
            self.photo_root = Some(path.clone());
            self.start_photo_indexing();
        }
        self.dirty = true;
        if self.project_path.is_some() {
            if let Err(error) = self.save_project() {
                self.status = format!("Relinked reference; save failed: {error}");
            } else {
                self.status = format!("Relinked {key}");
            }
        } else {
            self.status = format!("Relinked {key}; save the project to persist it");
        }
    }

    fn request_open_output_folder(&mut self) {
        let path = PathBuf::from(self.export_dir.trim());
        log::info!("Requesting system open folder: {}", path.display());
        let sender = self.worker_sender.clone();
        thread::spawn(move || {
            let result = open_folder_with_platform_command(&path);
            let _ = sender.send(WorkerMessage::OutputFolderOpened(result));
        });
    }

    fn show_top_bar(&mut self, ui: &mut egui::Ui) {
        ui.horizontal_wrapped(|ui| {
            ui.heading(RichText::new("CardForge").strong());
            ui.separator();
            for page in WorkflowPage::ALL {
                if ui
                    .selectable_label(self.page == page, page.label())
                    .clicked()
                {
                    log::info!("Navigated to workflow page: {}", page.label());
                    self.page = page;
                }
            }
            ui.separator();
            if ui.button("New").clicked() && self.busy.is_none() {
                log::info!("Toolbar clicked: New project");
                self.new_project();
            }
            if ui.button("Open").clicked() && self.busy.is_none() {
                log::info!("Toolbar clicked: Open project");
                self.open_project_dialog();
            }
            if ui.button("Save").clicked() {
                log::info!("Toolbar clicked: Save project");
                if self.project_path.is_some() {
                    if let Err(error) = self.save_project() {
                        self.status = format!("Save failed: {error}");
                    }
                } else {
                    self.save_project_dialog();
                }
            }
        });
        if let Some(busy) = self.busy.as_ref() {
            let busy_label = busy.label.clone();
            let busy_progress = busy.progress;
            let can_cancel = busy.cancel.is_some()
                || busy.task.is_some()
                || busy.kind == BusyKind::PhotoLibrary
                || busy.kind == BusyKind::Export;
            ui.horizontal(|ui| {
                ui.spinner();
                ui.label(&busy_label);
                if let Some((done, total)) = busy_progress {
                    ui.add(
                        egui::ProgressBar::new(done as f32 / total.max(1) as f32)
                            .text(format!("{done}/{total}")),
                    );
                }
                if can_cancel && ui.button("Cancel").clicked() {
                    log::info!("Toolbar clicked: Cancel busy task '{}'", busy_label);
                    self.cancel_busy();
                }
            });
        }
    }

    fn show_dashboard(&mut self, ui: &mut egui::Ui) {
        ui.heading("Dashboard");
        ui.label(RichText::new(&self.project.project_name).size(20.0));
        ui.label("A native workflow shell for importing records, matching photos, designing cards, and exporting reviewed output.");
        ui.separator();
        ui.columns(4, |columns| {
            metric(&mut columns[0], "Records", self.records.len().to_string());
            metric(&mut columns[1], "Photos", self.photo_discovered.to_string());
            metric(
                &mut columns[2],
                "Matched",
                self.match_summary.matched_count.to_string(),
            );
            metric(
                &mut columns[3],
                "Generated",
                self.generation_summary
                    .as_ref()
                    .map(|summary| summary.completed_count.to_string())
                    .unwrap_or_else(|| "—".into()),
            );
        });
        ui.add_space(14.0);
        ui.horizontal_wrapped(|ui| {
            if ui.button("Start with Data Source").clicked() {
                self.page = WorkflowPage::DataSource;
            }
            if ui.button("Choose Template").clicked() {
                self.page = WorkflowPage::Templates;
            }
            if ui.button("Open Review").clicked() {
                self.page = WorkflowPage::Review;
            }
            if ui.button("Export").clicked() {
                self.page = WorkflowPage::Export;
            }
        });
        if let Some(recovery) = &self.recovery_status {
            ui.colored_label(
                Color32::from_rgb(220, 150, 30),
                format!("Recovery: {recovery}"),
            );
        }
        let missing = self
            .project_path
            .as_deref()
            .map(|path| ProjectStore::check_missing_references_at(path, &self.project))
            .unwrap_or_default();
        if !missing.is_empty() {
            ui.colored_label(
                Color32::from_rgb(220, 120, 35),
                format!("{} referenced asset(s) need attention", missing.len()),
            );
            for reference in missing {
                ui.horizontal(|ui| {
                    ui.label(format!("{}: {}", reference.key, reference.path.display()));
                    if let Some(button) = match reference.key.as_str() {
                        "excel_file" => Some("Relink spreadsheet…"),
                        "photo_dir" => Some("Relink photo folder…"),
                        "background_image" => Some("Relink background…"),
                        _ => None,
                    } {
                        if ui.button(button).clicked() {
                            self.relink_reference(&reference.key);
                        }
                    }
                });
            }
        }
        ui.separator();
        ui.label(format!(
            "Project file: {}",
            self.project_path
                .as_deref()
                .map_or("unsaved".into(), |path| path.display().to_string())
        ));
        ui.label(format!(
            "State: {}{}",
            if self.dirty {
                "unsaved changes"
            } else {
                "saved"
            },
            if self.status.is_empty() { "" } else { " · " }
        ));
    }

    fn show_data_source(&mut self, ui: &mut egui::Ui) {
        ui.heading("Data Source");
        ui.label(
            "Import CSV, XLSX, or XLS records on a background worker. \
             The imported rows are displayed below in a full spreadsheet grid and serve as live sample data.",
        );
        ui.horizontal(|ui| {
            ui.label("Source");
            ui.add(egui::TextEdit::singleline(&mut self.source_path_text).desired_width(420.0));
            if ui.button("Choose file…").clicked() && self.busy.is_none() {
                self.choose_data_source();
            }
        });
        ui.horizontal(|ui| {
            ui.label("Worksheet");
            let selected = self
                .worksheets
                .get(self.selected_sheet)
                .cloned()
                .unwrap_or_else(|| "Choose a source".into());
            egui::ComboBox::from_id_salt("worksheet")
                .selected_text(selected)
                .show_ui(ui, |ui| {
                    for (index, worksheet) in self.worksheets.iter().enumerate() {
                        ui.selectable_value(&mut self.selected_sheet, index, worksheet);
                    }
                });
            ui.label("Header row");
            ui.add(egui::DragValue::new(&mut self.header_row).range(0..=1000));
            ui.label("PIN hint");
            ui.add(egui::TextEdit::singleline(&mut self.pin_column_hint).desired_width(150.0));
        });
        if ui.button("📥 Import records").clicked() && self.busy.is_none() {
            self.start_import();
        }
        ui.separator();

        let search_filter = self.data_search_query.trim().to_lowercase();
        let filtered_indices: Vec<usize> = self
            .records
            .iter()
            .enumerate()
            .filter(|(_, rec)| {
                if search_filter.is_empty() {
                    return true;
                }
                if rec.pin_or_raw().to_lowercase().contains(&search_filter) {
                    return true;
                }
                if rec.record_id.to_lowercase().contains(&search_filter) {
                    return true;
                }
                rec.data.values().any(|val| {
                    val.as_str()
                        .map(|s| s.to_lowercase().contains(&search_filter))
                        .unwrap_or_else(|| val.to_string().to_lowercase().contains(&search_filter))
                })
            })
            .map(|(idx, _)| idx)
            .collect();

        ui.horizontal(|ui| {
            ui.label("🔍 Search Data:");
            ui.add(
                egui::TextEdit::singleline(&mut self.data_search_query)
                    .desired_width(260.0)
                    .hint_text("Search by PIN, name, ID, or any field…"),
            );
            if !self.data_search_query.is_empty() && ui.small_button("✖ Clear").clicked() {
                self.data_search_query.clear();
            }
            ui.add_space(10.0);
            ui.strong(format!(
                "Showing {} of {} records · {} columns",
                filtered_indices.len(),
                self.records.len(),
                self.columns.len()
            ));
        });

        ui.label(
            egui::RichText::new(
                "💡 Click any row to set it as the active sample record for live preview.",
            )
            .small()
            .color(egui::Color32::from_rgb(148, 163, 184)),
        );

        if self.records.is_empty() {
            ui.label("No records imported yet. Choose a spreadsheet file above and click 'Import records'.");
        } else {
            let mut newly_selected_idx = None;
            let current_selected = self.selected_sample;
            let columns = self.columns.clone();
            let grid_height = (ui.available_height() - 170.0).max(280.0);
            egui::ScrollArea::both()
                .max_height(grid_height)
                .auto_shrink([false; 2])
                .show(ui, |ui| {
                    egui::Grid::new("data_source_tabular_grid")
                        .striped(true)
                        .spacing([12.0, 6.0])
                        .min_col_width(70.0)
                        .show(ui, |ui| {
                            // Header Row
                            ui.strong("#");
                            for column in &columns {
                                ui.strong(column);
                            }
                            ui.end_row();

                            // Data Rows
                            for &orig_idx in filtered_indices.iter().take(500) {
                                let is_selected = orig_idx == current_selected;
                                let row_label = format!("#{}", orig_idx + 1);

                                if ui.selectable_label(is_selected, row_label).clicked() {
                                    newly_selected_idx = Some(orig_idx);
                                }

                                if let Some(record) = self.records.get(orig_idx) {
                                    for column in &columns {
                                        let val = record.get_value(column);
                                        let cell_text = if val.is_empty() { "—" } else { &val };
                                        if is_selected {
                                            ui.colored_label(
                                                egui::Color32::from_rgb(56, 189, 248),
                                                cell_text,
                                            );
                                        } else {
                                            ui.label(cell_text);
                                        }
                                    }
                                }
                                ui.end_row();
                            }
                        });
                });

            if let Some(idx) = newly_selected_idx {
                log::debug!("Selected sample record row index: #{}", idx + 1);
                self.selected_sample = idx;
                self.mapping_state.sample_record = self.records.get(idx).cloned();
                self.request_review_preview();
            }

            // Selected Record Inspector
            if let Some(selected_record) = self.records.get(self.selected_sample) {
                ui.separator();
                ui.group(|ui| {
                    ui.horizontal(|ui| {
                        ui.strong(format!(
                            "📌 Active Sample Record: Row #{} (PIN: {})",
                            selected_record.row_index + 1,
                            selected_record.pin_or_raw()
                        ));
                    });
                    egui::ScrollArea::horizontal()
                        .max_height(80.0)
                        .show(ui, |ui| {
                            ui.horizontal_wrapped(|ui| {
                                for col in &self.columns {
                                    ui.group(|ui| {
                                        ui.small(col);
                                        let val = selected_record.get_value(col);
                                        ui.strong(if val.is_empty() { "—" } else { &val });
                                    });
                                }
                            });
                        });
                });

                ui.add_space(8.0);
                ui.horizontal(|ui| {
                    if ui
                        .button(egui::RichText::new("Proceed to Photos ➡").strong())
                        .clicked()
                    {
                        self.page = WorkflowPage::Photos;
                    }
                });
            }
        }
    }

    fn show_photos(&mut self, ui: &mut egui::Ui) {
        ui.heading("Photos");
        ui.label("Progressive filename-only discovery runs off the UI thread. Thumbnails are decoded lazily through the bounded ThumbnailQueue.");
        ui.horizontal(|ui| {
            ui.label("Folder");
            ui.label(
                self.photo_root
                    .as_deref()
                    .map_or("No folder selected".into(), |path| {
                        path.display().to_string()
                    }),
            );
            if ui.button("Choose folder…").clicked() && self.busy.is_none() {
                self.choose_photo_folder();
            }
            if ui.button("Rescan").clicked() && self.busy.is_none() {
                self.start_photo_indexing();
            }
        });
        ui.horizontal(|ui| {
            ui.strong(format!("{} discovered", self.photo_discovered));
            if let Some(library) = &self.photo_library {
                ui.label(format!("{} metadata records", library.record_count()));
            }
            ui.label(format!(
                "{} matched · {} missing · {} ambiguous",
                self.match_summary.matched_count,
                self.match_summary.missing_count,
                self.match_summary.ambiguous_count
            ));
        });
        ui.horizontal(|ui| {
            ui.label("Photo key column");
            let selected = self
                .project
                .photo_key_column
                .clone()
                .unwrap_or_else(|| "PIN (fallback)".into());
            egui::ComboBox::from_id_salt("photo-key-column")
                .selected_text(selected)
                .show_ui(ui, |ui| {
                    if ui
                        .selectable_value(
                            &mut self.project.photo_key_column,
                            None,
                            "PIN (fallback)",
                        )
                        .changed()
                    {
                        if let Some(template) = self.project.template.as_mut() {
                            for el in &mut template.elements {
                                if el.r#type == "photo" {
                                    el.binding = None;
                                }
                            }
                        }
                        self.refresh_photo_matches();
                        self.dirty = true;
                    }
                    for column in self.columns.clone() {
                        if ui
                            .selectable_value(
                                &mut self.project.photo_key_column,
                                Some(column.clone()),
                                column.clone(),
                            )
                            .changed()
                        {
                            if let Some(template) = self.project.template.as_mut() {
                                for el in &mut template.elements {
                                    if el.r#type == "photo" {
                                        el.binding = Some(column.clone());
                                    }
                                }
                            }
                            self.refresh_photo_matches();
                            self.dirty = true;
                        }
                    }
                });
            ui.label("Prefix");
            if ui
                .text_edit_singleline(&mut self.project.photo_prefix)
                .changed()
            {
                self.dirty = true;
            }
            ui.label("Suffix");
            if ui
                .text_edit_singleline(&mut self.project.photo_suffix)
                .changed()
            {
                self.dirty = true;
            }
            if ui.button("Apply matching").clicked() {
                self.refresh_photo_matches();
                self.dirty = true;
                self.status = "Photo matching applied".into();
            }
        });
        // Applying affixes is deliberately explicit, while text edits remain
        // local until the user requests a new match set.
        ui.label("Matching checks prefix + key + suffix first, then the bare key.");
        if ui.button("Load first thumbnail").clicked() {
            self.request_first_thumbnail();
        }
        if !self.thumbnail_label.is_empty() {
            ui.small(&self.thumbnail_label);
        }
        if let Some(texture) = &self.thumbnail_texture {
            ui.image((texture.id(), egui::vec2(180.0, 180.0)));
        }
        ui.separator();
        ui.heading("Discovered photo metadata");
        ui.label(format!(
            "{} filename rows discovered progressively; {} persisted metadata records",
            self.photo_rows.len(),
            self.photo_library
                .as_ref()
                .map(PhotoLibrary::record_count)
                .unwrap_or(0)
        ));
        let scroll_height = (ui.available_height() - 40.0).max(300.0);
        egui::ScrollArea::vertical()
            .max_height(scroll_height)
            .auto_shrink([false; 2])
            .show(ui, |ui| {
                if let Some(library) = &self.photo_library {
                    ui.horizontal(|ui| {
                        ui.strong("Stem");
                        ui.strong("Type");
                        ui.strong("Bytes");
                        ui.strong("Match key");
                        ui.strong("Path");
                    });
                    for row in library.records().take(200) {
                        ui.horizontal(|ui| {
                            ui.monospace(&row.stem);
                            ui.label(&row.extension);
                            ui.label(row.size.to_string());
                            ui.monospace(&row.match_key);
                            ui.label(row.path.display().to_string());
                        });
                    }
                }
                for row in self.photo_rows.iter().take(200) {
                    ui.horizontal(|ui| {
                        ui.monospace(&row.stem);
                        ui.label(row.path.display().to_string());
                    });
                }
                if self.photo_rows.is_empty() {
                    ui.label("Rows will appear while the scanner discovers files.");
                }
            });
        ui.separator();
        ui.label(
            "Matching uses the configured key column, prefix/suffix, and persisted overrides.",
        );
    }

    fn show_templates(&mut self, ui: &mut egui::Ui) {
        ui.heading("Templates");
        ui.label("Select a built-in template or start a blank canvas. Selection writes the typed TemplateDefinition into the project.");
        if ui.button("Create blank canvas").clicked() {
            self.create_blank_template();
        }
        ui.separator();
        for (id, template) in self.templates.clone() {
            ui.group(|ui| {
                ui.horizontal(|ui| {
                    ui.strong(&template.name);
                    ui.small(format!(
                        "{} × {} px · {} elements",
                        template.width_px,
                        template.height_px,
                        template.elements.len()
                    ));
                    if ui
                        .button(if self.selected_template_id == id {
                            "Selected"
                        } else {
                            "Use template"
                        })
                        .clicked()
                    {
                        self.choose_template(id.clone(), template.clone());
                    }
                });
                if !template.description.is_empty() {
                    ui.label(&template.description);
                }
            });
        }
        if let Some(template) = &self.project.template {
            ui.label(format!("Current: {}", template.name));
        }
    }

    fn show_template_editor(&mut self, ui: &mut egui::Ui) {
        if self.project.template.is_some() {
            let mut template = self
                .project
                .template
                .take()
                .expect("template checked above");
            let mut key_col = self.project.photo_key_column.clone();
            let sample_match = self
                .records
                .get(self.selected_sample)
                .and_then(|rec| self.match_results.get(&rec.record_id))
                .cloned();
            let editor_changed = TemplateEditor::with_context(
                &mut template,
                &mut self.editor_state,
                &self.columns,
                Some(&mut key_col),
                sample_match.as_ref(),
            )
            .show(ui);
            self.project.template = Some(template);
            if key_col != self.project.photo_key_column {
                log::info!("Template editor updated photo key column to: {:?}", key_col);
                self.project.photo_key_column = key_col;
                self.refresh_photo_matches();
                self.dirty = true;
            }
            if editor_changed {
                self.dirty = true;
            }
        } else {
            ui.heading("Template Editor");
            ui.label("No template active. Choose a template or create a custom canvas.");
            ui.add_space(8.0);
            ui.horizontal(|ui| {
                if ui.button("📄 Create Blank Canvas…").clicked() {
                    self.new_canvas_dialog.open();
                }
                if ui.button("Browse templates").clicked() {
                    self.page = WorkflowPage::Templates;
                }
            });
        }
    }

    fn show_mapping(&mut self, ui: &mut egui::Ui) {
        ui.heading("Mapping");
        let Some(template_snapshot) = self.project.template.clone() else {
            ui.label("Choose a template first.");
            return;
        };
        if !self.records.is_empty() {
            egui::ComboBox::from_id_salt("sample-record")
                .selected_text(format!("Sample row {}", self.selected_sample + 1))
                .show_ui(ui, |ui| {
                    for (index, record) in self.records.iter().enumerate().take(100) {
                        ui.selectable_value(
                            &mut self.selected_sample,
                            index,
                            format!("{} · {}", record.row_index + 1, record.pin_or_raw()),
                        );
                    }
                });
            self.mapping_state.sample_record = self.records.get(self.selected_sample).cloned();
        }
        let mut key_col = self.project.photo_key_column.clone();
        let sample_match = self
            .records
            .get(self.selected_sample)
            .and_then(|rec| self.match_results.get(&rec.record_id));
        let editor_changed = {
            let mut editor = MappingEditor::with_context(
                &template_snapshot,
                &mut self.mapping_state,
                &self.columns,
                Some(&mut key_col),
                sample_match,
            );
            editor.show(ui, || self.page = WorkflowPage::TemplateEditor)
        };
        if key_col != self.project.photo_key_column {
            log::info!("Mapping editor updated photo key column to: {:?}", key_col);
            self.project.photo_key_column = key_col;
            self.refresh_photo_matches();
            self.dirty = true;
        }
        let mappings = self.mapping_state.mappings(&template_snapshot);
        let before_template = self.project.template.clone();
        let before_mappings = self.project.column_mappings.clone();
        let mut photo_key_to_set = None;
        if let Some(template) = self.project.template.as_mut() {
            for mapping in &mappings {
                if let Some(element) = template
                    .elements
                    .iter_mut()
                    .find(|element| element.id == mapping.element_id)
                {
                    element.binding = (!mapping.source_column.trim().is_empty())
                        .then_some(mapping.source_column.clone());
                    if mapping.is_photo && !mapping.source_column.trim().is_empty() {
                        photo_key_to_set = Some(mapping.source_column.clone());
                    }
                }
            }
        }
        for mapping in mappings {
            self.project
                .column_mappings
                .insert(mapping.element_id, mapping.source_column);
        }
        if let Some(photo_key) = photo_key_to_set {
            if self.project.photo_key_column.as_deref() != Some(&photo_key) {
                log::info!("Photo element bound to column: {}", photo_key);
                self.project.photo_key_column = Some(photo_key);
                self.refresh_photo_matches();
                self.dirty = true;
            }
        }
        if editor_changed
            || before_template != self.project.template
            || before_mappings != self.project.column_mappings
        {
            if before_mappings != self.project.column_mappings {
                log::debug!(
                    "Column mappings updated: {:?}",
                    self.project.column_mappings
                );
            }
            self.dirty = true;
        }
    }

    fn show_generate(&mut self, ui: &mut egui::Ui) {
        ui.heading("Generate");
        ui.label("Render cards into a staging directory on a cancellable background worker.");
        ui.horizontal(|ui| {
            ui.label("Staging folder");
            if ui
                .add(egui::TextEdit::singleline(&mut self.output_dir).desired_width(360.0))
                .changed()
            {
                self.dirty = true;
            }
            if ui.button("Choose…").clicked() {
                if let Some(path) = FileDialog::new().pick_folder() {
                    self.output_dir = path.display().to_string();
                    self.dirty = true;
                }
            }
        });
        ui.horizontal(|ui| {
            ui.label("Naming pattern");
            if ui
                .add(egui::TextEdit::singleline(&mut self.naming_pattern).desired_width(260.0))
                .changed()
            {
                self.project.export_naming_pattern = self.naming_pattern.clone();
                self.dirty = true;
            }
            ui.label("Use {PIN_NUMBER} and {NAME}");
        });
        ui.label(format!(
            "Ready: {} records · {} photo matches · template: {}",
            self.records.len(),
            self.match_summary.matched_count,
            self.project
                .template
                .as_ref()
                .map(|template| template.name.as_str())
                .unwrap_or("none")
        ));
        if ui.button("Generate cards").clicked() && self.busy.is_none() {
            self.start_generation();
        }
        if let Some(summary) = &self.generation_summary {
            ui.separator();
            ui.label(format!(
                "Last run: {} complete · {} skipped · {} failed · {} cancelled",
                summary.completed_count,
                summary.skipped_count,
                summary.failed_count,
                summary.cancelled_count
            ));
        }
    }

    fn show_review(&mut self, ui: &mut egui::Ui) {
        ui.heading("Review & Approval");
        ui.label(
            "Review generated cards, adjust status or comments, and approve cards for export.",
        );
        self.request_review_preview();

        if self.review.is_empty() {
            ui.label("No review records yet. Import data and generate cards first.");
            return;
        }

        let pending_count = self.review.pending_count();
        let approved_count = self.review.approved_count();
        let total_count = self.review.len();

        let mut approve_all_clicked = false;
        let mut approve_record_id = None;
        let mut select_record_id = None;

        ui.columns(2, |columns| {
            // LEFT COLUMN: Card preview canvas and active record details
            let left_ui = &mut columns[0];
            left_ui.group(|ui| {
                ui.horizontal(|ui| {
                    if ui.button("⏮ First").clicked() {
                        self.review.first();
                        log::debug!("Review navigation: First record");
                    }
                    if ui.button("◀ Prev").clicked() {
                        self.review.previous();
                        log::debug!("Review navigation: Previous record");
                    }
                    if ui.button("Next ▶").clicked() {
                        self.review.next();
                        log::debug!("Review navigation: Next record");
                    }
                    if ui.button("Last ⏭").clicked() {
                        self.review.last();
                        log::debug!("Review navigation: Last record");
                    }
                    ui.label(format!(
                        "Card {} / {}",
                        self.review
                            .current_index()
                            .map(|index| index + 1)
                            .unwrap_or(0),
                        self.review.len()
                    ));
                });

                if let Some(record) = self.review.current_record().cloned() {
                    let record_id = record.record_id.clone();
                    ui.separator();
                    ui.horizontal(|ui| {
                        ui.strong(format!("📌 {} · {}", record.pin, record.name));
                        ui.label(format!("(ID: {})", record.record_id));
                        let (badge_text, badge_color) = match record.status {
                            ReviewStatus::Approved => {
                                ("Approved", egui::Color32::from_rgb(74, 222, 128))
                            }
                            ReviewStatus::Pending => {
                                ("Pending", egui::Color32::from_rgb(250, 204, 21))
                            }
                            ReviewStatus::Rejected => {
                                ("Rejected", egui::Color32::from_rgb(248, 113, 113))
                            }
                            ReviewStatus::Correction => {
                                ("Correction", egui::Color32::from_rgb(251, 146, 60))
                            }
                            ReviewStatus::Skipped => {
                                ("Skipped", egui::Color32::from_rgb(148, 163, 184))
                            }
                        };
                        ui.colored_label(badge_color, format!("[{badge_text}]"));
                    });

                    // Canvas preview
                    if let Some(texture) = &self.review_thumbnail_texture.clone() {
                        self.show_review_viewport(ui, texture);
                    } else {
                        ui.group(|ui| {
                            ui.label(&self.review_preview_label);
                            ui.label(format!(
                                "Rendered file: {}",
                                record
                                    .rendered_image_path
                                    .as_deref()
                                    .unwrap_or("not generated")
                            ));
                        });
                    }

                    // Status decision buttons
                    ui.horizontal_wrapped(|ui| {
                        ui.label("Status:");
                        for (label, status, fill_color) in [
                            (
                                "✅ Approve",
                                ReviewStatus::Approved,
                                Some(egui::Color32::from_rgb(22, 101, 52)),
                            ),
                            ("❌ Reject", ReviewStatus::Rejected, None),
                            ("⚠️ Correction", ReviewStatus::Correction, None),
                            ("⏳ Pending", ReviewStatus::Pending, None),
                            ("⏭ Skip", ReviewStatus::Skipped, None),
                        ] {
                            let is_current_status = record.status == status;
                            let btn = egui::Button::new(label);
                            let btn = if is_current_status {
                                btn.fill(fill_color.unwrap_or(egui::Color32::from_rgb(71, 85, 105)))
                            } else if let Some(fill) = fill_color {
                                btn.fill(fill)
                            } else {
                                btn
                            };
                            if ui.add(btn).clicked() {
                                log::info!(
                                    "Review status for record {} (PIN: {}) updated to {:?}",
                                    record_id,
                                    record.pin,
                                    status
                                );
                                let _ = self.review.set_status(&record_id, status);
                                self.sync_review_states();
                            }
                        }
                    });

                    // Comments
                    let mut comments = record.comments.clone().unwrap_or_default();
                    ui.label("Comments & Review Notes:");
                    if ui
                        .add(
                            egui::TextEdit::multiline(&mut comments)
                                .desired_rows(2)
                                .hint_text("Enter review comments or correction notes…")
                                .desired_width(ui.available_width()),
                        )
                        .changed()
                    {
                        let comment = (!comments.trim().is_empty()).then_some(comments);
                        log::debug!(
                            "Updated review comment for record {}: {:?}",
                            record_id,
                            comment
                        );
                        let _ = self.review.set_comment(&record_id, comment);
                        self.sync_review_states();
                    }

                    if ui.button("🔄 Regenerate this card").clicked() && self.busy.is_none() {
                        log::info!("User requested card regeneration for record: {}", record_id);
                        self.start_regeneration(record_id.clone());
                    }
                } else {
                    ui.label("Select a card from the list on the right to view preview.");
                }
            });

            // RIGHT COLUMN: Pending cards list and Approve All at once
            let right_ui = &mut columns[1];
            right_ui.group(|ui| {
                ui.horizontal(|ui| {
                    ui.heading("Cards to Approve");
                    ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                        if ui
                            .add(
                                egui::Button::new(
                                    RichText::new("✅ Approve All at Once")
                                        .strong()
                                        .color(egui::Color32::WHITE),
                                )
                                .fill(egui::Color32::from_rgb(22, 101, 52)),
                            )
                            .on_hover_text("Approve all cards in this project at once")
                            .clicked()
                        {
                            approve_all_clicked = true;
                        }
                    });
                });

                ui.horizontal(|ui| {
                    ui.label(
                        RichText::new(format!(
                            "{} pending · {} approved · {} total",
                            pending_count, approved_count, total_count
                        ))
                        .small(),
                    );
                });

                ui.horizontal(|ui| {
                    ui.selectable_value(
                        &mut self.review_filter_pending_only,
                        true,
                        format!("Pending Only ({pending_count})"),
                    );
                    ui.selectable_value(
                        &mut self.review_filter_pending_only,
                        false,
                        format!("All Cards ({total_count})"),
                    );
                });

                ui.horizontal(|ui| {
                    ui.label("🔍");
                    ui.add(
                        egui::TextEdit::singleline(&mut self.review_search_query)
                            .hint_text("Search PIN, name, ID…")
                            .desired_width(180.0),
                    );
                    if !self.review_search_query.is_empty() && ui.small_button("✖").clicked() {
                        self.review_search_query.clear();
                    }
                });

                ui.separator();

                let current_id = self.review.current_record().map(|r| r.record_id.clone());
                let records: Vec<_> = self
                    .review
                    .records()
                    .into_iter()
                    .filter(|rec| {
                        if self.review_filter_pending_only && rec.status != ReviewStatus::Pending {
                            return false;
                        }
                        let q = self.review_search_query.trim().to_lowercase();
                        if q.is_empty() {
                            return true;
                        }
                        rec.pin.to_lowercase().contains(&q)
                            || rec.name.to_lowercase().contains(&q)
                            || rec.record_id.to_lowercase().contains(&q)
                    })
                    .cloned()
                    .collect();

                if records.is_empty() {
                    if self.review_filter_pending_only {
                        ui.label(
                            RichText::new("🎉 All pending cards have been approved!")
                                .color(egui::Color32::from_rgb(74, 222, 128)),
                        );
                    } else {
                        ui.label("No cards match search filter.");
                    }
                } else {
                    let list_height = (ui.available_height() - 20.0).max(400.0);
                    egui::ScrollArea::vertical()
                        .max_height(list_height)
                        .auto_shrink([false; 2])
                        .show(ui, |ui| {
                            for (idx, record) in records.iter().enumerate() {
                                let is_active = current_id.as_deref() == Some(&record.record_id);
                                ui.horizontal(|ui| {
                                    let label_text =
                                        format!("#{} · {} — {}", idx + 1, record.pin, record.name);
                                    let rich_label = if is_active {
                                        RichText::new(label_text)
                                            .strong()
                                            .color(egui::Color32::from_rgb(56, 189, 248))
                                    } else {
                                        RichText::new(label_text)
                                    };

                                    if ui.selectable_label(is_active, rich_label).clicked() {
                                        select_record_id = Some(record.record_id.clone());
                                    }

                                    let (badge_text, badge_color) = match record.status {
                                        ReviewStatus::Approved => {
                                            ("Approved", egui::Color32::from_rgb(74, 222, 128))
                                        }
                                        ReviewStatus::Pending => {
                                            ("Pending", egui::Color32::from_rgb(250, 204, 21))
                                        }
                                        ReviewStatus::Rejected => {
                                            ("Rejected", egui::Color32::from_rgb(248, 113, 113))
                                        }
                                        ReviewStatus::Correction => {
                                            ("Correction", egui::Color32::from_rgb(251, 146, 60))
                                        }
                                        ReviewStatus::Skipped => {
                                            ("Skipped", egui::Color32::from_rgb(148, 163, 184))
                                        }
                                    };
                                    ui.colored_label(badge_color, badge_text);

                                    if record.status != ReviewStatus::Approved
                                        && ui
                                            .small_button("✓ Approve")
                                            .on_hover_text("Approve this card")
                                            .clicked()
                                    {
                                        approve_record_id = Some(record.record_id.clone());
                                    }
                                });
                            }
                        });
                }
            });
        });

        if approve_all_clicked {
            log::info!("Approving all review records at once");
            self.review.approve_all();
            self.sync_review_states();
            self.status = "All cards approved".into();
        }

        if let Some(id) = approve_record_id {
            log::info!("Review status for record {} updated to Approved", id);
            let _ = self.review.set_status(&id, ReviewStatus::Approved);
            self.sync_review_states();
        }

        if let Some(id) = select_record_id {
            log::debug!("Selected review record from list: {}", id);
            self.review.select_record(&id);
            self.request_review_preview();
        }
    }

    fn show_review_viewport(&mut self, ui: &mut egui::Ui, texture: &egui::TextureHandle) {
        ui.horizontal(|ui| {
            if ui.small_button("−").clicked() {
                self.review_zoom = (self.review_zoom / 1.15).max(0.2);
            }
            ui.add(egui::Slider::new(&mut self.review_zoom, 0.2..=4.0).show_value(false));
            if ui.small_button("+").clicked() {
                self.review_zoom = (self.review_zoom * 1.15).min(4.0);
            }
            ui.label(format!("{}%", (self.review_zoom * 100.0).round() as i32));

            if ui.small_button("⊡ Fit Card").clicked() {
                self.review_zoom = 1.0;
                self.review_pan = egui::Vec2::ZERO;
            }
            if ui.small_button("1:1 Actual").clicked() {
                self.review_zoom = 1.0;
                self.review_pan = egui::Vec2::ZERO;
            }
            let [w, h] = texture.size();
            ui.label(format!("Card: {w} × {h} px"));
        });

        let available_w = ui.available_width().max(320.0);
        let available_h = (ui.available_height() - 210.0).clamp(360.0, 1200.0);
        let desired_size = egui::vec2(available_w, available_h);
        let (rect, resp) = ui.allocate_exact_size(desired_size, egui::Sense::click_and_drag());
        let painter = ui.painter_at(rect);

        // Dark canvas background with crisp border
        painter.rect_filled(rect, 4.0, egui::Color32::from_rgb(20, 20, 24));
        painter.rect_stroke(
            rect,
            4.0,
            egui::Stroke::new(1.0_f32, egui::Color32::from_rgb(45, 45, 50)),
        );

        if resp.dragged() {
            self.review_pan += resp.drag_delta();
        }
        if resp.hovered() {
            let scroll = resp.ctx.input(|i| i.smooth_scroll_delta.y);
            if scroll != 0.0 {
                self.review_zoom = (self.review_zoom * (1.0 + scroll * 0.001)).clamp(0.2, 4.0);
            }
        }

        let tex_size = texture.size_vec2();
        if tex_size.x > 0.0 && tex_size.y > 0.0 {
            let base_scale = ((rect.width() - 32.0) / tex_size.x)
                .min((rect.height() - 32.0) / tex_size.y)
                .max(0.01);
            let final_scale = base_scale * self.review_zoom;
            let card_size = tex_size * final_scale;
            let card_pos = rect.center() - card_size / 2.0 + self.review_pan;
            let card_rect = egui::Rect::from_min_size(card_pos, card_size);

            // Subtle drop shadow
            painter.rect_filled(
                card_rect.translate(egui::vec2(3.0, 4.0)),
                2.0,
                egui::Color32::from_black_alpha(120),
            );

            // Textured card image
            painter.image(
                texture.id(),
                card_rect,
                egui::Rect::from_min_max(egui::pos2(0.0, 0.0), egui::pos2(1.0, 1.0)),
                egui::Color32::WHITE,
            );

            // Subtle border around card
            painter.rect_stroke(
                card_rect,
                1.0,
                egui::Stroke::new(1.0_f32, egui::Color32::from_gray(100)),
            );
        }
    }

    fn show_export(&mut self, ui: &mut egui::Ui) {
        ui.heading("Export");
        ui.label("Export reviewed cards and an optional audit manifest on a background worker.");
        ui.horizontal(|ui| {
            ui.label("Export folder");
            if ui
                .add(egui::TextEdit::singleline(&mut self.export_dir).desired_width(360.0))
                .changed()
            {
                self.dirty = true;
            }
            if ui.button("Choose…").clicked() {
                if let Some(path) = FileDialog::new().pick_folder() {
                    self.export_dir = path.display().to_string();
                    self.dirty = true;
                }
            }
        });
        ui.horizontal(|ui| {
            ui.label("Format");
            if ui
                .selectable_value(&mut self.export_format, OutputFormat::Png, "PNG")
                .changed()
            {
                self.project.export_format = self.export_format.clone();
                self.dirty = true;
            }
            if ui
                .selectable_value(&mut self.export_format, OutputFormat::Jpeg, "JPEG")
                .changed()
            {
                self.project.export_format = self.export_format.clone();
                self.dirty = true;
            }
            if self.export_format == OutputFormat::Jpeg {
                ui.label("JPEG quality");
                if ui
                    .add(egui::Slider::new(&mut self.export_jpeg_quality, 1..=100))
                    .changed()
                {
                    self.project.export_jpeg_quality = self.export_jpeg_quality;
                    self.dirty = true;
                }
            }
        });
        ui.horizontal(|ui| {
            ui.label("Naming pattern");
            if ui
                .add(egui::TextEdit::singleline(&mut self.naming_pattern).desired_width(260.0))
                .changed()
            {
                self.project.export_naming_pattern = self.naming_pattern.clone();
                self.dirty = true;
            }
            ui.label("{PIN_NUMBER} and {NAME}");
        });
        if ui
            .checkbox(&mut self.export_approved_only, "Approved only")
            .changed()
        {
            self.project.export_approved_only = self.export_approved_only;
            self.dirty = true;
        }
        if ui
            .checkbox(&mut self.export_manifest, "Write CSV manifest")
            .changed()
        {
            self.project.export_manifest = self.export_manifest;
            self.dirty = true;
        }
        if ui
            .checkbox(
                &mut self.export_contact_sheet,
                "Generate printable contact sheet (A4/Letter grid)",
            )
            .changed()
        {
            self.project.export_contact_sheet = self.export_contact_sheet;
            self.dirty = true;
        }
        if ui
            .checkbox(
                &mut self.export_open_folder,
                "Open output folder automatically after export",
            )
            .changed()
        {
            self.project.open_output_dir_on_export = self.export_open_folder;
            self.dirty = true;
        }
        let approved = self
            .review
            .records()
            .into_iter()
            .filter(|record| record.status == ReviewStatus::Approved)
            .count();
        ui.label(format!(
            "{} review records · {} approved · manifest {}",
            self.review.len(),
            approved,
            if self.export_manifest {
                "enabled"
            } else {
                "disabled"
            }
        ));
        if ui.button("Export cards").clicked() && self.busy.is_none() {
            self.start_export();
        }
        if ui.button("Open Output Folder").clicked() {
            self.request_open_output_folder();
        }
        if let Some(export) = &self.last_export {
            ui.separator();
            ui.label(format!(
                "Last export: {} files, {} skipped, {} failed",
                export.exported_count, export.skipped_count, export.failed_count
            ));
            if let Some(path) = &export.manifest_path {
                ui.monospace(format!("Manifest: {path}"));
            }
            if let Some(path) = &export.contact_sheet_path {
                ui.monospace(format!("Contact sheet: {path}"));
            }
        }
    }

    fn show_settings(&mut self, context: &egui::Context, ui: &mut egui::Ui) {
        ui.heading("Settings");
        ui.label("Theme changes are applied immediately and saved atomically whenever this project has a path.");
        ui.horizontal(|ui| {
            ui.label("Theme");
            for (label, theme) in [
                ("Black", ThemePreference::Black),
                ("White", ThemePreference::White),
                ("System", ThemePreference::System),
            ] {
                if ui.selectable_label(self.theme == theme, label).clicked() {
                    self.set_theme(context, theme);
                }
            }
        });
        ui.horizontal(|ui| {
            ui.label("Project name");
            if ui
                .text_edit_singleline(&mut self.project.project_name)
                .changed()
            {
                self.dirty = true;
            }
        });
        ui.horizontal(|ui| {
            ui.label("Photo key column");
            let mut value = self.project.photo_key_column.clone().unwrap_or_default();
            if ui.text_edit_singleline(&mut value).changed() {
                self.project.photo_key_column = (!value.trim().is_empty()).then_some(value);
                self.refresh_photo_matches();
                self.dirty = true;
            }
        });
        ui.label(format!("Format version: {}", self.project.version));
        ui.label(format!(
            "Project path: {}",
            self.project_path
                .as_deref()
                .map_or("unsaved".into(), |path| path.display().to_string())
        ));
    }
}

impl eframe::App for MigrationApp {
    fn update(&mut self, context: &egui::Context, _frame: &mut eframe::Frame) {
        self.poll_task_events();
        self.poll_worker_messages();
        self.poll_photo_indexing();
        self.poll_thumbnail(context);
        self.poll_review_thumbnail(context);
        context.request_repaint_after(Duration::from_millis(50));

        egui::TopBottomPanel::top("workflow-bar").show(context, |ui| self.show_top_bar(ui));
        egui::TopBottomPanel::bottom("status-bar").show(context, |ui| {
            ui.horizontal(|ui| {
                ui.label(if self.dirty {
                    "● Unsaved"
                } else {
                    "✓ Saved"
                });
                ui.separator();
                ui.label(&self.status);
            });
        });
        egui::CentralPanel::default().show(context, |ui| match self.page {
            WorkflowPage::Dashboard => self.show_dashboard(ui),
            WorkflowPage::DataSource => self.show_data_source(ui),
            WorkflowPage::Photos => self.show_photos(ui),
            WorkflowPage::Templates => self.show_templates(ui),
            WorkflowPage::TemplateEditor => self.show_template_editor(ui),
            WorkflowPage::Mapping => self.show_mapping(ui),
            WorkflowPage::Generate => self.show_generate(ui),
            WorkflowPage::Review => self.show_review(ui),
            WorkflowPage::Export => self.show_export(ui),
            WorkflowPage::Settings => self.show_settings(context, ui),
        });

        // Show Photoshop-style New Document modal dialog if opened
        if let Some(new_template) = self.new_canvas_dialog.show(context) {
            log::info!(
                "Created new custom blank canvas: {} ({}x{} px @ {} DPI)",
                new_template.name,
                new_template.width_px,
                new_template.height_px,
                new_template.dpi
            );
            self.choose_template("custom-blank-template".into(), new_template);
            self.page = WorkflowPage::TemplateEditor;
        }
    }
}

fn metric(ui: &mut egui::Ui, label: &str, value: String) {
    ui.group(|ui| {
        ui.small(label);
        ui.heading(value);
    });
}

fn theme_from_string(value: &str) -> ThemePreference {
    match value.to_ascii_lowercase().as_str() {
        "black" => ThemePreference::Black,
        "white" => ThemePreference::White,
        _ => ThemePreference::System,
    }
}

fn theme_label(theme: &ThemePreference) -> &'static str {
    match theme {
        ThemePreference::Black => "black",
        ThemePreference::White => "white",
        ThemePreference::System => "system",
    }
}

fn open_folder_with_platform_command(path: &Path) -> Result<(), String> {
    if !path.is_dir() {
        return Err(format!("output folder does not exist: {}", path.display()));
    }
    #[cfg(target_os = "windows")]
    let mut command = {
        let mut command = Command::new("explorer");
        command.arg(path);
        command
    };
    #[cfg(target_os = "macos")]
    let mut command = {
        let mut command = Command::new("open");
        command.arg(path);
        command
    };
    #[cfg(all(unix, not(target_os = "macos")))]
    let mut command = {
        let mut command = Command::new("xdg-open");
        command.arg(path);
        command
    };
    #[cfg(not(any(windows, unix)))]
    let _ = path;
    #[cfg(any(windows, unix))]
    {
        command
            .spawn()
            .map(|_| ())
            .map_err(|error| error.to_string())
    }
    #[cfg(not(any(windows, unix)))]
    {
        Err("opening folders is unsupported on this platform".into())
    }
}

#[cfg(test)]
mod tests {
    use super::{theme_from_string, theme_label, WorkflowPage};
    use crate::data::models::ThemePreference;

    #[test]
    fn workflow_shell_has_complete_navigation_and_theme_round_trip() {
        assert_eq!(WorkflowPage::ALL.len(), 10);
        assert_eq!(theme_label(&theme_from_string("BLACK")), "black");
        assert_eq!(theme_label(&theme_from_string("unknown")), "system");
        assert!(WorkflowPage::ALL.contains(&WorkflowPage::Export));
        assert_eq!(ThemePreference::System, theme_from_string("system"));
    }
}
