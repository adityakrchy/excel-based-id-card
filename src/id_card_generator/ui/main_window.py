"""Main Application Window for Excel-Based ID Card Generator."""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QAction, QIcon
from PySide6.QtWidgets import (
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import (
    APP_NAME,
    APP_VERSION,
    MissingPhotoPolicy,
    WorkflowStep,
)
from id_card_generator.core.models import (
    PhotoMatchResult,
    ProjectConfiguration,
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.core.project_manager import ProjectManager
from id_card_generator.generation.batch_generator import GenerationSummary
from id_card_generator.resources.resource_loader import get_resource_path
from id_card_generator.tasks.task_manager import TaskManager
from id_card_generator.ui.dashboard_page import DashboardPage
from id_card_generator.ui.data_source_page import DataSourcePage
from id_card_generator.ui.dialogs.relink_dialog import RelinkDialog
from id_card_generator.ui.editor_page import EditorPage
from id_card_generator.ui.export_page import ExportPage
from id_card_generator.ui.generation_page import GenerationPage
from id_card_generator.ui.photo_library_page import PhotoLibraryPage
from id_card_generator.ui.review_page import ReviewPage
from id_card_generator.ui.settings_page import SettingsPage
from id_card_generator.ui.template_page import TemplatePage
from id_card_generator.ui.theme_manager import ThemeManager
from id_card_generator.ui.workflow_nav import WorkflowNav

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main window with sidebar, top workflow stepper, and stacked page views."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1280, 850)

        # Application state
        self.current_project_path: Optional[Path] = None
        self.active_template: Optional[TemplateDefinition] = None
        self.records: List[SourceRecord] = []
        self.columns: List[str] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.column_mappings: Dict[str, str] = {}
        self.settings = RenderSettings()
        self.last_generation_summary: Optional[GenerationSummary] = None

        self._setup_ui()
        self._setup_menus()
        self._setup_signals()
        self.apply_theme(ThemeManager.instance().get_preference())

    def _setup_ui(self) -> None:
        # Main Top Application Toolbar
        self.top_toolbar = self.addToolBar("Main Controls")
        self.top_toolbar.setMovable(False)

        btn_tb_new = QPushButton("New Project")
        btn_tb_new.clicked.connect(self._new_project)
        self.top_toolbar.addWidget(btn_tb_new)

        btn_tb_open = QPushButton("Open...")
        btn_tb_open.clicked.connect(self._open_project)
        self.top_toolbar.addWidget(btn_tb_open)

        btn_tb_save = QPushButton("Save")
        btn_tb_save.clicked.connect(self._save_project)
        self.top_toolbar.addWidget(btn_tb_save)

        self.top_toolbar.addSeparator()

        lbl_theme = QLabel(" Theme: ")
        lbl_theme.setStyleSheet("font-weight: 500;")
        self.top_toolbar.addWidget(lbl_theme)

        self.cmb_toolbar_theme = QComboBox()
        self.cmb_toolbar_theme.addItem("Black (Fluent Dark)", "black")
        self.cmb_toolbar_theme.addItem("White (Fluent Light)", "white")
        self.cmb_toolbar_theme.addItem("System (Auto)", "system")
        curr_pref = ThemeManager.instance().get_preference()
        idx = self.cmb_toolbar_theme.findData(curr_pref)
        if idx >= 0:
            self.cmb_toolbar_theme.setCurrentIndex(idx)
        self.cmb_toolbar_theme.currentIndexChanged.connect(self._on_toolbar_theme_changed)
        self.top_toolbar.addWidget(self.cmb_toolbar_theme)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Retain nav_buttons dictionary in memory for compatibility,
        # but remove the left sidebar completely from the visual layout.
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.nav_buttons: Dict[WorkflowStep, QPushButton] = {}
        nav_items = [
            (WorkflowStep.DASHBOARD, "Dashboard"),
            (WorkflowStep.DATA_SOURCE, "Data Source"),
            (WorkflowStep.PHOTOS, "Photo Library"),
            (WorkflowStep.TEMPLATES, "Templates"),
            (WorkflowStep.CANVAS_EDITOR, "Canvas Editor"),
            (WorkflowStep.GENERATE, "Generate Cards"),
            (WorkflowStep.REVIEW, "Review Cards"),
            (WorkflowStep.EXPORT, "Export Cards"),
            (WorkflowStep.SETTINGS, "Settings"),
        ]

        for step, text in nav_items:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.clicked.connect(lambda ch=False, s=step: self.switch_page(s))
            self.nav_buttons[step] = btn

        # 1. Top Persistent Workflow Stepper (includes Dashboard & Settings)
        self.workflow_nav = WorkflowNav()
        self.workflow_nav.step_clicked.connect(lambda s: self.switch_page(WorkflowStep(s)))
        main_layout.addWidget(self.workflow_nav)

        # 2. Main Stacked Workspace (fills entire width)
        self.stack = QStackedWidget()
        self.page_dashboard = DashboardPage()
        self.page_data_source = DataSourcePage()
        self.page_photos = PhotoLibraryPage()
        self.page_templates = TemplatePage()
        self.page_editor = EditorPage()
        self.page_generation = GenerationPage()
        self.page_review = ReviewPage()
        self.page_export = ExportPage()
        self.page_settings = SettingsPage()

        self.stack.addWidget(self.page_dashboard)       # 0
        self.stack.addWidget(self.page_data_source)     # 1
        self.stack.addWidget(self.page_photos)          # 2
        self.stack.addWidget(self.page_templates)       # 3
        self.stack.addWidget(self.page_editor)          # 4
        self.stack.addWidget(self.page_generation)      # 5
        self.stack.addWidget(self.page_review)          # 6
        self.stack.addWidget(self.page_export)          # 7
        self.stack.addWidget(self.page_settings)        # 8

        self.step_to_index = {
            WorkflowStep.DASHBOARD: 0,
            WorkflowStep.DATA_SOURCE: 1,
            WorkflowStep.PHOTOS: 2,
            WorkflowStep.TEMPLATES: 3,
            WorkflowStep.CANVAS_EDITOR: 4,
            WorkflowStep.GENERATE: 5,
            WorkflowStep.REVIEW: 6,
            WorkflowStep.EXPORT: 7,
            WorkflowStep.SETTINGS: 8,
        }

        main_layout.addWidget(self.stack)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Load an Excel data source to begin.")

        self.switch_page(WorkflowStep.DASHBOARD)

    def _setup_menus(self) -> None:
        menubar = self.menuBar()

        # File Menu
        file_menu = menubar.addMenu("&File")

        act_new = QAction("&New Project", self)
        act_new.setShortcut("Ctrl+N")
        act_new.triggered.connect(self._new_project)
        file_menu.addAction(act_new)

        act_open = QAction("&Open Project...", self)
        act_open.setShortcut("Ctrl+O")
        act_open.triggered.connect(self._open_project)
        file_menu.addAction(act_open)

        act_save = QAction("&Save Project", self)
        act_save.setShortcut("Ctrl+S")
        act_save.triggered.connect(self._save_project)
        file_menu.addAction(act_save)

        act_save_as = QAction("Save Project &As...", self)
        act_save_as.setShortcut("Ctrl+Shift+S")
        act_save_as.triggered.connect(self._save_project_as)
        file_menu.addAction(act_save_as)

        file_menu.addSeparator()

        act_exit = QAction("E&xit", self)
        act_exit.setShortcut("Ctrl+Q")
        act_exit.triggered.connect(self.close)
        file_menu.addAction(act_exit)

        # Navigate Menu
        nav_menu = menubar.addMenu("&Navigate")
        for step, name in [
            (WorkflowStep.DASHBOARD, "Dashboard"),
            (WorkflowStep.DATA_SOURCE, "Data Source"),
            (WorkflowStep.PHOTOS, "Photo Library"),
            (WorkflowStep.TEMPLATES, "Templates"),
            (WorkflowStep.CANVAS_EDITOR, "Canvas Editor"),
            (WorkflowStep.GENERATE, "Generate Cards"),
            (WorkflowStep.REVIEW, "Review Cards"),
            (WorkflowStep.EXPORT, "Export Cards"),
        ]:
            act = QAction(name, self)
            act.triggered.connect(lambda ch=False, s=step: self.switch_page(s))
            nav_menu.addAction(act)

    def _setup_signals(self) -> None:
        # Dashboard signals (including embedded settings & workflow launcher)
        self.page_dashboard.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))
        self.page_dashboard.theme_changed.connect(self.apply_theme)
        self.page_dashboard.policy_changed.connect(self._on_policy_changed)
        self.page_dashboard.dpi_changed.connect(lambda dpi: setattr(self.settings, "dpi", dpi))

        # Sequential step-by-step navigation signals
        self.page_data_source.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))
        self.page_photos.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))
        self.page_templates.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))
        self.page_editor.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))
        self.page_generation.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))
        self.page_review.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))
        self.page_export.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))

        # Data source signals
        self.page_data_source.data_loaded.connect(self._on_data_loaded)

        # Photo library signals
        self.page_photos.matching_updated.connect(self._on_matching_updated)

        # Template page signals
        self.page_templates.template_selected.connect(self._on_template_selected)
        self.page_templates.open_editor_requested.connect(lambda: self.switch_page(WorkflowStep.CANVAS_EDITOR))

        # Editor page signals
        self.page_editor.template_updated.connect(self._on_editor_template_updated)

        # Generation page signals
        self.page_generation.generation_completed.connect(self._on_generation_completed)
        self.page_generation.goto_review_requested.connect(lambda: self.switch_page(WorkflowStep.REVIEW))

        # Review page signals
        self.page_review.review_updated.connect(self._on_review_updated)
        self.page_review.goto_export_requested.connect(lambda: self.switch_page(WorkflowStep.EXPORT))

        # Settings page signals (kept for legacy support)
        self.page_settings.theme_changed.connect(self.apply_theme)
        self.page_settings.policy_changed.connect(self._on_policy_changed)

        # Background task progress indicators
        def _safe_status(msg: str) -> None:
            try:
                if hasattr(self, "status_bar") and self.status_bar:
                    self.status_bar.showMessage(msg)
            except RuntimeError:
                pass

        task_signals = TaskManager.instance().signals
        task_signals.task_progress.connect(
            lambda tid, cur, tot, msg: _safe_status(
                f"{msg} ({cur}/{tot})" if tot > 0 else msg
            )
        )
        task_signals.task_completed.connect(
            lambda tid, res: _safe_status("Background task completed successfully.")
        )
        task_signals.task_failed.connect(
            lambda tid, err: _safe_status(f"Task error: {err}")
        )

    def switch_page(self, step: WorkflowStep) -> None:
        """Switch workspace page and synchronize navigation indicators."""
        idx = self.step_to_index.get(step, 0)
        self.stack.setCurrentIndex(idx)

        # Update sidebar buttons
        for s, btn in self.nav_buttons.items():
            btn.setChecked(s == step)

        # Update top stepper
        self.workflow_nav.set_active_step(step)

        # Context updates on page entry
        if step == WorkflowStep.CANVAS_EDITOR:
            tmpl = self.active_template or self.page_templates.active_template
            if tmpl:
                self.page_editor.load_template(tmpl)
                self.page_editor.set_dataset(self.records, self.match_results, self.columns)

        elif step == WorkflowStep.GENERATE:
            tmpl = self.active_template or self.page_templates.active_template
            self.page_generation.set_generation_context(
                template=tmpl,
                records=self.records,
                match_results=self.match_results,
                column_mappings=self.column_mappings,
                settings=self.settings,
            )

        elif step == WorkflowStep.REVIEW:
            if self.last_generation_summary:
                tmpl = self.active_template or self.page_templates.active_template
                self.page_review.load_review_session(
                    source_records=self.records,
                    generation_results=self.last_generation_summary.results,
                    template=tmpl,
                    match_results=self.match_results,
                    column_mappings=self.column_mappings,
                )

        elif step == WorkflowStep.EXPORT:
            self.page_export.set_export_context(
                review_records=self.page_review.manager.records,
                source_records_map=self.page_review.source_records_map,
                match_results_map=self.match_results,
            )

        self._refresh_status_bar()

    def _on_data_loaded(self, columns: List[str], records: List[SourceRecord], report) -> None:
        self.columns = columns
        self.records = records
        self.workflow_nav.mark_step_completed(WorkflowStep.DATA_SOURCE, True)
        self.page_photos.set_columns(columns)
        self.page_photos.set_records(records)
        self.page_templates.set_sample_record(records[0] if records else None)
        self._refresh_dashboard_metrics()
        self.status_bar.showMessage(f"Data source loaded: {len(records)} records ({report.valid_records} valid).")

    def _on_matching_updated(self, match_results: Dict[str, PhotoMatchResult], summary) -> None:
        self.match_results = match_results
        self.workflow_nav.mark_step_completed(WorkflowStep.PHOTOS, summary.matched_count > 0)
        self._refresh_dashboard_metrics()
        self.status_bar.showMessage(f"Photos updated: {summary.matched_count} matched, {summary.missing_count} missing.")

    def _on_template_selected(self, template: TemplateDefinition) -> None:
        self.active_template = template
        self.workflow_nav.mark_step_completed(WorkflowStep.TEMPLATES, True)
        self._refresh_dashboard_metrics()
        self.status_bar.showMessage(f"Active template set: {template.name}")

    def _on_editor_template_updated(self, template: TemplateDefinition) -> None:
        self.active_template = template
        self.workflow_nav.mark_step_completed(WorkflowStep.CANVAS_EDITOR, True)

    def _on_generation_completed(self, summary: GenerationSummary) -> None:
        self.last_generation_summary = summary
        self.workflow_nav.mark_step_completed(WorkflowStep.GENERATE, summary.completed_count > 0)
        self._refresh_dashboard_metrics()
        self.status_bar.showMessage(f"Generation finished: {summary.completed_count} cards produced in staging.")

    def _on_review_updated(self, review_manager) -> None:
        c = review_manager.counts
        self.workflow_nav.mark_step_completed(WorkflowStep.REVIEW, c["approved"] > 0)
        self._refresh_dashboard_metrics()

    def _on_policy_changed(self, policy: MissingPhotoPolicy) -> None:
        self.settings.missing_photo_policy = policy
        logger.info("Missing photo policy set to %s", policy)

    def _refresh_dashboard_metrics(self) -> None:
        valid_count = sum(1 for r in self.records if r.is_valid)
        matched_photos = sum(1 for m in self.match_results.values() if m.status.value in ("matched", "overridden"))
        missing_photos = len(self.records) - matched_photos if self.records else 0

        approved_count = self.page_review.manager.counts["approved"]
        total_review = len(self.page_review.manager.records)

        warn_count = sum(len(r.validation_warnings) for r in self.records)
        err_count = sum(len(r.validation_errors) for r in self.records)

        tmpl_name = self.active_template.name if self.active_template else (
            self.page_templates.active_template.name if self.page_templates.active_template else "None"
        )

        self.page_dashboard.update_metrics(
            record_count=len(self.records),
            matched_photos=matched_photos,
            missing_photos=missing_photos,
            template_name=tmpl_name,
            approved_count=approved_count,
            total_review=total_review,
            validation_warnings=warn_count,
            validation_errors=err_count,
        )

    def _refresh_status_bar(self) -> None:
        proj_str = self.current_project_path.name if self.current_project_path else "Unsaved Project"
        rec_str = f"{len(self.records)} records" if self.records else "No data"
        tmpl_str = self.active_template.name if self.active_template else "No template"
        self.status_bar.showMessage(f"Project: {proj_str} • {rec_str} • Template: {tmpl_str}")

    def apply_theme(self, theme_name: str) -> None:
        """Apply Windows 11 Fluent theme via centralized ThemeManager."""
        theme_str = str(theme_name).lower().strip()
        if theme_str == "dark":
            theme_str = "black"
        elif theme_str == "light":
            theme_str = "white"

        ThemeManager.instance().set_theme(theme_str)

        # Synchronize toolbar dropdown without re-triggering signal
        if hasattr(self, "cmb_toolbar_theme"):
            self.cmb_toolbar_theme.blockSignals(True)
            idx = self.cmb_toolbar_theme.findData(theme_str)
            if idx >= 0:
                self.cmb_toolbar_theme.setCurrentIndex(idx)
            self.cmb_toolbar_theme.blockSignals(False)

    def _on_toolbar_theme_changed(self) -> None:
        theme_val = self.cmb_toolbar_theme.currentData() or "black"
        self.apply_theme(theme_val)

    # --- Project Save / Load / Relink ---
    def _new_project(self) -> None:
        confirm = QMessageBox.question(self, "New Project", "Create a new project? Unsaved changes will be lost.")
        if confirm == QMessageBox.Yes:
            self.current_project_path = None
            self.records = []
            self.columns = []
            self.match_results = {}
            self.column_mappings = {}
            self.active_template = None
            self.last_generation_summary = None
            self.switch_page(WorkflowStep.DASHBOARD)
            self._refresh_dashboard_metrics()
            self._refresh_status_bar()

    def _open_project(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Open Project", "", "Project Files (*.json)")
        if not file_path:
            return

        p = Path(file_path)
        try:
            cfg = ProjectManager.load_project(p)

            # Check missing references
            missing = ProjectManager.check_missing_references(cfg)
            if missing:
                dialog = RelinkDialog(missing, self)
                if dialog.exec():
                    cfg = ProjectManager.relink_references(cfg, dialog.replacements)
                else:
                    return

            self.current_project_path = p
            self.active_template = cfg.template

            if cfg.excel_file_path and Path(cfg.excel_file_path).exists():
                self.page_data_source.load_file(Path(cfg.excel_file_path))

            if cfg.photo_dir_path and Path(cfg.photo_dir_path).exists():
                self.page_photos.set_directory(Path(cfg.photo_dir_path))

            self.column_mappings = cfg.column_mappings
            self.settings.missing_photo_policy = cfg.missing_photo_policy

            self.switch_page(WorkflowStep.DASHBOARD)
            self._refresh_dashboard_metrics()
            self._refresh_status_bar()
            QMessageBox.information(self, "Project Loaded", f"Project '{cfg.project_name}' loaded successfully.")

        except Exception as e:
            logger.error("Failed to load project: %s", e)
            QMessageBox.critical(self, "Project Error", f"Could not load project: {e}")

    def _save_project(self) -> None:
        if self.current_project_path:
            self._save_to_path(self.current_project_path)
        else:
            self._save_project_as()

    def _save_project_as(self) -> None:
        file_path, _ = QFileDialog.getSaveFileName(self, "Save Project", "id_cards_project.json", "Project Files (*.json)")
        if file_path:
            self.current_project_path = Path(file_path)
            self._save_to_path(self.current_project_path)

    def _save_to_path(self, path: Path) -> None:
        try:
            cfg = ProjectConfiguration(
                project_name=path.stem,
                excel_file_path=str(self.page_data_source.current_file_path) if self.page_data_source.current_file_path else None,
                sheet_name=self.page_data_source.cmb_sheets.currentText() or None,
                header_row=self.page_data_source.spin_header.value(),
                photo_dir_path=str(self.page_photos.matcher.photo_dir) if self.page_photos.matcher.photo_dir else None,
                template=self.active_template or self.page_templates.active_template,
                column_mappings=self.column_mappings,
                photo_overrides=self.page_photos.matcher.overrides,
                missing_photo_policy=self.settings.missing_photo_policy,
                review_states={r.record_id: r.status for r in self.page_review.manager.records},
            )
            ProjectManager.save_project(cfg, path)
            self._refresh_status_bar()
            QMessageBox.information(self, "Project Saved", f"Project successfully saved to {path.name}.")
        except Exception as e:
            logger.error("Failed to save project: %s", e)
            QMessageBox.critical(self, "Save Error", f"Could not save project: {e}")
