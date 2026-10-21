"""Main Application Window for Excel-Based ID Card Generator."""

import logging
import os
from pathlib import Path
from typing import Dict, List, Optional
from PySide6.QtCore import Qt, QTimer, Signal
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
from id_card_generator.templates.template_manager import TemplateManager
from id_card_generator.ui.components import (
    StudioHeaderBar,
    StudioNavBar,
    StudioTab,
    normalize_control_heights,
)
from id_card_generator.ui.components.studio_nav_bar import TabState
from id_card_generator.ui.dashboard_page import DashboardPage
from id_card_generator.ui.data_source_page import DataSourcePage
from id_card_generator.ui.dialogs.new_project_dialog import NewProjectDialog
from id_card_generator.ui.dialogs.project_dialog import ProjectDialog
from id_card_generator.ui.dialogs.relink_dialog import RelinkDialog
from id_card_generator.ui.editor_page import EditorPage
from id_card_generator.ui.export_page import ExportPage
from id_card_generator.ui.photo_library_page import PhotoLibraryPage
from id_card_generator.ui.production_page import ProductionPage
from id_card_generator.ui.settings_page import SettingsPage
from id_card_generator.ui.studio_tokens import COLORS
from id_card_generator.ui.template_page import TemplatePage
from id_card_generator.ui.theme_manager import ThemeManager
from id_card_generator.ui import workflow
from id_card_generator.ui.workflow_nav import WorkflowNav

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main window with sidebar, top workflow stepper, and stacked page views."""

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.resize(1280, 850)

        # Application state
        self.current_project_config: Optional[ProjectConfiguration] = None
        self.current_project_path: Optional[Path] = None
        self._startup_prompt_shown = False
        self.active_template: Optional[TemplateDefinition] = None
        self.records: List[SourceRecord] = []
        self.columns: List[str] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.column_mappings: Dict[str, str] = {}
        self.settings = RenderSettings()
        self.last_generation_summary: Optional[GenerationSummary] = None
        self.template_manager = TemplateManager()

        # Progress of every pipeline step, used to badge the workspace ribbon.
        self._completed_steps: Dict[WorkflowStep, bool] = {
            stage.step: False for stage in workflow.STAGES
        }
        self._current_step: WorkflowStep = WorkflowStep.DASHBOARD

        self._setup_ui()
        self._setup_menus()
        self._setup_signals()
        self.apply_theme(ThemeManager.instance().get_preference())

    def showEvent(self, event) -> None:
        super().showEvent(event)

    def _prompt_startup_project(self) -> None:
        """Deprecated startup workspace prompt: no-op to allow direct Project Hub onboarding."""
        pass

    def _setup_ui(self) -> None:
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # 1. Studio Top Command Bar (Level 1 Header)
        self.header_bar = StudioHeaderBar(self)
        self.header_bar.new_requested.connect(self._new_project)
        self.header_bar.open_requested.connect(self._open_project)
        self.header_bar.save_requested.connect(self._save_project)
        self.header_bar.undo_requested.connect(self._on_undo_requested)
        self.header_bar.redo_requested.connect(self._on_redo_requested)
        self.header_bar.theme_requested.connect(self.apply_theme)
        main_layout.addWidget(self.header_bar)

        # 2. Studio Workspace Navigation Ribbon (Level 1.5 Sub-header)
        self.studio_nav = StudioNavBar(self)
        self.studio_nav.tab_selected.connect(self._on_studio_tab_selected)
        self.studio_nav.help_requested.connect(self._show_help)
        main_layout.addWidget(self.studio_nav)

        # Retain legacy toolbar & workflow stepper in memory (hidden) for test compatibility
        self.top_toolbar = self.addToolBar("Main Controls")
        self.top_toolbar.setMovable(False)
        self.top_toolbar.setVisible(False)

        btn_tb_new = QPushButton("New Project")
        btn_tb_new.clicked.connect(self._new_project)
        self.top_toolbar.addWidget(btn_tb_new)

        btn_tb_open = QPushButton("Open...")
        btn_tb_open.clicked.connect(self._open_project)
        self.top_toolbar.addWidget(btn_tb_open)

        btn_tb_save = QPushButton("Save")
        btn_tb_save.clicked.connect(self._save_project)
        self.top_toolbar.addWidget(btn_tb_save)

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

        # Legacy sidebar: kept as an off-canvas state mirror of the workflow so
        # external code can still query which step is active.  It is never
        # added to the visible layout - the studio ribbon is the navigation.
        self.sidebar = QFrame()
        self.sidebar.setObjectName("sidebar")
        self.nav_buttons: Dict[WorkflowStep, QPushButton] = {}
        nav_items = [
            (WorkflowStep.DASHBOARD, "Dashboard"),
            (WorkflowStep.DATA_SOURCE, "Data Source"),
            (WorkflowStep.PHOTOS, "Photo Library"),
            (WorkflowStep.TEMPLATES, "Templates"),
            (WorkflowStep.CANVAS_EDITOR, "Canvas Editor"),
            (WorkflowStep.GENERATE, "Generate & Review"),
            (WorkflowStep.EXPORT, "Export Cards"),
            (WorkflowStep.SETTINGS, "Settings"),
        ]

        for step, text in nav_items:
            btn = QPushButton(text)
            btn.setCheckable(True)
            btn.clicked.connect(lambda ch=False, s=step: self.switch_page(s))
            self.nav_buttons[step] = btn

        self.workflow_nav = WorkflowNav()
        self.workflow_nav.setVisible(False)
        self.workflow_nav.step_clicked.connect(lambda s: self.switch_page(WorkflowStep(s)))
        main_layout.addWidget(self.workflow_nav)

        # 3. Main Stacked Workspace (fills entire width)
        self.stack = QStackedWidget()
        self.page_dashboard = DashboardPage()
        self.page_data_source = DataSourcePage()
        self.page_photos = PhotoLibraryPage()
        self.page_templates = TemplatePage()
        self.page_editor = EditorPage()
        self.page_production = ProductionPage()
        self.page_export = ExportPage()
        self.page_settings = SettingsPage()

        self.stack.addWidget(self.page_dashboard)       # 0
        self.stack.addWidget(self.page_data_source)     # 1
        self.stack.addWidget(self.page_photos)          # 2
        self.stack.addWidget(self.page_templates)       # 3
        self.stack.addWidget(self.page_editor)          # 4
        self.stack.addWidget(self.page_production)      # 5
        self.stack.addWidget(self.page_export)          # 6
        self.stack.addWidget(self.page_settings)        # 7

        self.step_to_index = {
            WorkflowStep.DASHBOARD: 0,
            WorkflowStep.DATA_SOURCE: 1,
            WorkflowStep.PHOTOS: 2,
            WorkflowStep.TEMPLATES: 3,
            WorkflowStep.CANVAS_EDITOR: 4,
            WorkflowStep.GENERATE: 5,
            WorkflowStep.EXPORT: 6,
            WorkflowStep.SETTINGS: 7,
        }

        # Every input control shares one height so the rows read evenly.
        for index in range(self.stack.count()):
            page = self.stack.widget(index)
            if page is not None:
                normalize_control_heights(page)

        main_layout.addWidget(self.stack)

        # Status Bar
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.lbl_sb_format = QLabel("CR80 Standard (85.60 × 53.98 mm) · 300 DPI")
        self.lbl_sb_format.setStyleSheet(
            "color: #8E909F; font-family: 'JetBrains Mono', monospace; font-size: 11px; padding-right: 12px;"
        )
        self.status_bar.addPermanentWidget(self.lbl_sb_format)
        self.status_bar.showMessage("● Ready · PySide6 Engine v2.4.1")

        self.switch_page(WorkflowStep.DASHBOARD)

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt naming
        """Stop the background workers before the window goes away.

        A worker thread that is still running when its parent is destroyed
        crashes the application.
        """
        for page in (
            getattr(self, "page_photos", None),
            getattr(self, "page_production", None),
        ):
            if page is not None and hasattr(page, "shutdown"):
                try:
                    page.shutdown()
                except RuntimeError:
                    pass
        super().closeEvent(event)

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
            (WorkflowStep.GENERATE, "Generate & Review"),
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
        self.page_dashboard.new_project_requested.connect(self._new_project)
        self.page_dashboard.open_project_requested.connect(self._open_project)
        self.page_dashboard.preset_selected.connect(self._on_preset_selected)

        # Sequential step-by-step navigation signals
        self.page_data_source.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))
        self.page_photos.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))
        self.page_templates.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))
        self.page_editor.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))
        self.page_production.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))
        self.page_export.navigate_requested.connect(lambda s: self.switch_page(WorkflowStep(s)))

        # Data source signals
        self.page_data_source.data_loaded.connect(self._on_data_loaded)
        self.page_data_source.photo_lookup_changed.connect(self._on_photo_lookup_changed)
        self.page_data_source.photo_policy_changed.connect(self._on_policy_changed)

        # Photo library signals
        self.page_photos.matching_updated.connect(self._on_matching_updated)
        self.page_photos.lookup_column_changed.connect(
            self.page_data_source.set_photo_lookup_column
        )

        # Template page signals
        self.page_templates.template_selected.connect(self._on_template_selected)
        self.page_templates.open_editor_requested.connect(lambda: self.switch_page(WorkflowStep.CANVAS_EDITOR))

        # Editor page signals
        self.page_editor.template_updated.connect(self._on_editor_template_updated)

        # Generation page signals
        self.page_production.generation_completed.connect(self._on_generation_completed)

        # Review page signals
        self.page_production.review_updated.connect(self._on_review_updated)
        self.page_production.goto_export_requested.connect(lambda: self.switch_page(WorkflowStep.EXPORT))

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
        self._current_step = step

        # Update sidebar buttons (state mirror kept for compatibility)
        for s, btn in self.nav_buttons.items():
            btn.setChecked(s == step)

        # Update top stepper
        self.workflow_nav.set_active_step(step)

        # Update studio nav bar active tab - the ribbon is the pipeline.
        if hasattr(self, "studio_nav"):
            for tab in StudioTab:
                if tab.value == workflow.tab_for(step):
                    self.studio_nav.set_active_tab(tab)
                    break
            self._refresh_tab_states()

        # Keep the hub's flow anchor in sync with the current position.
        self._refresh_hub_flow_state()

        # Context updates on page entry
        if step == WorkflowStep.CANVAS_EDITOR:
            tmpl = self.active_template or self.page_templates.active_template
            if tmpl:
                self.page_editor.load_template(tmpl)
                self.page_editor.set_dataset(self.records, self.match_results, self.columns)

        elif step == WorkflowStep.DATA_SOURCE:
            # The connector shows the policy and the lookup of the project.
            self.page_data_source.set_photo_policy(self.settings.missing_photo_policy)

        elif step == WorkflowStep.GENERATE:
            tmpl = self.active_template or self.page_templates.active_template
            self.page_production.set_generation_context(
                template=tmpl,
                records=self.records,
                match_results=self.match_results,
                column_mappings=self.column_mappings,
                settings=self.settings,
            )
            # The cards of the last run are waiting in the queue.
            if self.last_generation_summary:
                self.page_production.load_review_session(
                    source_records=self.records,
                    generation_results=self.last_generation_summary.results,
                    template=tmpl,
                    match_results=self.match_results,
                    column_mappings=self.column_mappings,
                )

        elif step == WorkflowStep.EXPORT:
            self.page_export.set_export_context(
                review_records=self.page_production.manager.records,
                source_records_map=self.page_production.source_records_map,
                match_results_map=self.match_results,
            )

        self._refresh_status_bar()

    def _refresh_hub_flow_state(self) -> None:
        """Tell the hub where the open project currently is."""
        if not hasattr(self, "page_dashboard"):
            return

        project_name = ""
        if self.current_project_config:
            project_name = self.current_project_config.project_name
        elif self.current_project_path:
            project_name = self.current_project_path.stem

        if not project_name:
            self.page_dashboard.update_flow_state()
            return

        # The next step is the first stage that is not finished yet.
        next_step = None
        next_label = ""
        for step in workflow.PIPELINE:
            if not workflow.step_completed(step, self._completed_steps):
                next_step = step
                next_label = workflow.stage_for(step).title
                break

        hint = (
            f"{workflow.step_badge(self._current_step)} · "
            f"{workflow.subtitle_for(self._current_step)}"
        )
        if self._current_step == WorkflowStep.DASHBOARD and next_step is not None:
            # On the hub the interesting information is the step to do next.
            hint = (
                f"{workflow.step_badge(next_step)} · "
                f"{workflow.subtitle_for(next_step)}"
            )

        self.page_dashboard.update_flow_state(
            project_name=project_name,
            step_title=workflow.title_for(self._current_step),
            step_hint=hint,
            next_step=next_step.value if next_step else None,
        )
        if next_step:
            self.page_dashboard.lbl_flow_next.setText(
                f"{hint}   →   Next: {next_label}"
            )
            self.page_dashboard.btn_flow_continue.setText(f"{next_label}  ➔")

    def _refresh_tab_states(self) -> None:
        """Badge every ribbon entry with its progress state."""
        if not hasattr(self, "studio_nav"):
            return

        # The step right after the current one stays available so the user
        # always sees what to do next, even before its prerequisites are met.
        upcoming = workflow.next_step(self._current_step)

        # Steps the user already moved past are never "blocked".
        passed = set()
        if self._current_step in workflow.PIPELINE:
            position = workflow.PIPELINE.index(self._current_step)
            passed = set(workflow.PIPELINE[:position])

        states: Dict[StudioTab, TabState] = {}
        for tab in StudioTab:
            step = workflow.step_for_tab(tab.value)
            if step is None:
                states[tab] = TabState.IDLE
                continue

            if step == self._current_step:
                states[tab] = TabState.ACTIVE
                continue

            if workflow.step_completed(step, self._completed_steps):
                states[tab] = TabState.DONE
                continue

            if (
                step not in passed
                and step != upcoming
                and workflow.missing_requirements(step, self._completed_steps)
            ):
                states[tab] = TabState.BLOCKED
                continue

            states[tab] = TabState.IDLE

        self.studio_nav.set_tab_states(states)

    def _mark_step_completed(self, step: WorkflowStep, completed: bool = True) -> None:
        """Record the progress of a pipeline step and refresh the ribbon."""
        self._completed_steps[step] = completed
        self.workflow_nav.mark_step_completed(step, completed)
        self._refresh_tab_states()
        self._refresh_hub_flow_state()

    def _on_data_loaded(self, columns: List[str], records: List[SourceRecord], report) -> None:
        self.columns = columns
        self.records = records
        self._mark_step_completed(WorkflowStep.DATA_SOURCE, True)
        self.page_photos.set_columns(columns)
        self.page_photos.set_records(records)
        self.page_templates.set_sample_record(records[0] if records else None)
        self._refresh_dashboard_metrics()
        self.status_bar.showMessage(f"Data source loaded: {len(records)} records ({report.valid_records} valid).")

    def _on_matching_updated(self, match_results: Dict[str, PhotoMatchResult], summary) -> None:
        self.match_results = match_results
        self._mark_step_completed(WorkflowStep.PHOTOS, summary.matched_count > 0)
        self._refresh_dashboard_metrics()
        # The connector shows how the photographs were found.
        ambiguous = sum(
            1 for m in match_results.values() if m.status.value == "ambiguous"
        )
        self.page_data_source.set_photo_stats(
            matched=summary.matched_count,
            missing=summary.missing_count,
            ambiguous=ambiguous,
        )
        self.status_bar.showMessage(f"Photos updated: {summary.matched_count} matched, {summary.missing_count} missing.")

    def _on_photo_lookup_changed(self, column: str) -> None:
        """The photo lookup column was changed on the connector."""
        self.page_photos.matcher.set_key_column(column or None)
        self.page_photos._rematch()
        self.status_bar.showMessage(
            f"Photo lookup column: {column or 'auto-detect'}"
        )

    def _on_template_selected(self, template: TemplateDefinition) -> None:
        self.active_template = template
        self._mark_step_completed(WorkflowStep.TEMPLATES, True)
        self._refresh_dashboard_metrics()
        self.status_bar.showMessage(f"Active template set: {template.name}")

    def _on_editor_template_updated(self, template: TemplateDefinition) -> None:
        self.active_template = template
        self._mark_step_completed(WorkflowStep.CANVAS_EDITOR, True)

    def _on_generation_completed(self, summary: GenerationSummary) -> None:
        self.last_generation_summary = summary
        self._mark_step_completed(WorkflowStep.GENERATE, summary.completed_count > 0)
        self._refresh_dashboard_metrics()
        self.status_bar.showMessage(f"Generation finished: {summary.completed_count} cards produced in staging.")

    def _on_review_updated(self, review_manager) -> None:
        c = review_manager.counts
        self._mark_step_completed(WorkflowStep.GENERATE, c["approved"] > 0)
        self._refresh_dashboard_metrics()

    def _on_policy_changed(self, policy: MissingPhotoPolicy) -> None:
        self.settings.missing_photo_policy = policy
        # The connector shows the same policy.
        self.page_data_source.set_photo_policy(policy)
        logger.info("Missing photo policy set to %s", policy)

    def _refresh_dashboard_metrics(self) -> None:
        valid_count = sum(1 for r in self.records if r.is_valid)
        matched_photos = sum(1 for m in self.match_results.values() if m.status.value in ("matched", "overridden"))
        missing_photos = len(self.records) - matched_photos if self.records else 0

        approved_count = self.page_production.manager.counts["approved"]
        total_review = len(self.page_production.manager.records)

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
        self.page_dashboard.update_workspace_info(self.current_project_config, matched_photos)

    def _refresh_status_bar(self) -> None:
        has_project = bool(self.current_project_config or self.current_project_path)
        if has_project:
            ws_str = ""
            if self.current_project_config and self.current_project_config.workspace_dir:
                ws_str = f"Workspace: {Path(self.current_project_config.workspace_dir).name} • "
            proj_str = self.current_project_config.project_name if self.current_project_config else (
                self.current_project_path.name if self.current_project_path else "Unsaved Project"
            )
            rec_str = f"{len(self.records)} records" if self.records else "No data"
            tmpl_str = self.active_template.name if self.active_template else "No template"
            self.status_bar.showMessage(f"{ws_str}Project: {proj_str} • {rec_str} • Template: {tmpl_str}")
        else:
            self.status_bar.showMessage("● Ready · PySide6 Engine v2.4.1")

        if self.active_template:
            w_mm = getattr(self.active_template, "width_mm", 85.60)
            h_mm = getattr(self.active_template, "height_mm", 53.98)
            dpi = getattr(self.active_template, "dpi", 300)
            name = getattr(self.active_template, "name", "CR80 Standard")
            if hasattr(self, "lbl_sb_format"):
                self.lbl_sb_format.setText(f"{name} ({w_mm:.2f} × {h_mm:.2f} mm) · {dpi} DPI")
        elif hasattr(self, "lbl_sb_format"):
            self.lbl_sb_format.setText("CR80 Standard (85.60 × 53.98 mm) · 300 DPI")

        proj_title = self.current_project_config.project_name if self.current_project_config else (
            self.current_project_path.name if self.current_project_path else ""
        )
        title_suffix = f" - {proj_title}" if proj_title else ""
        if self.current_project_config and self.current_project_config.workspace_dir:
            title_suffix += f" [{self.current_project_config.workspace_dir}]"
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}{title_suffix}")

    def apply_theme(self, theme_name: str) -> None:
        """Apply the application theme (Windows 11 Fluent inspired)."""
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

        self._refresh_theme_styles()

    def _refresh_theme_styles(self) -> None:
        """Re-apply the chrome and every semantic style for the active theme."""
        effective = ThemeManager.instance().active_effective_theme

        if hasattr(self, "header_bar"):
            self.header_bar.refresh_theme(effective)
        if hasattr(self, "studio_nav"):
            self.studio_nav.refresh_theme(effective)
            self._refresh_tab_states()

        # Property based roles (page titles, badges, metrics, ...) have to be
        # re-polished so the new palette is picked up.
        from PySide6.QtWidgets import QWidget

        for widget in self.findChildren(QWidget):
            ThemeManager.retarget_widget(widget, effective)
            widget.style().unpolish(widget)
            widget.style().polish(widget)
            widget.update()
        self.update()

    def _on_toolbar_theme_changed(self) -> None:
        theme_val = self.cmb_toolbar_theme.currentData() or "black"
        self.apply_theme(theme_val)

    # --- Project Save / Load / Relink ---
    def set_project(self, config: ProjectConfiguration, workspace_path: Optional[Path] = None) -> None:
        """Set active project configuration and synchronize across application views."""
        self.current_project_config = config
        path_obj = Path(workspace_path).resolve() if workspace_path else (config.workspace_path if config.workspace_path else None)
        if path_obj:
            if path_obj.is_dir():
                self.current_project_path = path_obj / "project.json"
            else:
                self.current_project_path = path_obj
        else:
            self.current_project_path = None

        # Synchronize project configuration to pages
        self.page_dashboard.set_project_config(config)
        self.page_data_source.set_project_config(config)
        self.page_photos.set_project_config(config)

        # Load spreadsheet if exists
        if config.excel_file_path and Path(config.excel_file_path).exists():
            self.page_data_source.load_file(Path(config.excel_file_path), copy_to_workspace=False)

        # Set photo directory if exists
        if config.photo_dir_path and Path(config.photo_dir_path).exists():
            self.page_photos.set_directory(Path(config.photo_dir_path))

        # Restore overrides & mappings
        if config.column_mappings:
            self.column_mappings = dict(config.column_mappings)
        if config.photo_overrides:
            self.page_photos.matcher.overrides = dict(config.photo_overrides)
        if config.template:
            self.active_template = config.template
            if hasattr(self.page_editor, "load_template"):
                self.page_editor.load_template(config.template)
            self.page_templates.active_template = config.template

        # Set export output directory
        if config.exports_dir:
            self.page_export.lbl_dest_dir.setText(str(config.exports_dir))
            self.page_export.last_export_dir = config.exports_dir
        elif config.last_export_dir:
            self.page_export.lbl_dest_dir.setText(str(config.last_export_dir))
            self.page_export.last_export_dir = Path(config.last_export_dir)

        if hasattr(self, "header_bar"):
            title = self.current_project_path.name if self.current_project_path else config.project_name
            self.header_bar.set_project_title(title, False)
            self.header_bar.set_sync_status("Saved (Local)", COLORS.TERTIARY)

        self.switch_page(WorkflowStep.DASHBOARD)
        self._refresh_dashboard_metrics()
        self._refresh_status_bar()

    def _on_undo_requested(self) -> None:
        if hasattr(self.page_editor, "scene") and hasattr(self.page_editor.scene, "undo_manager"):
            self.page_editor.scene.undo_manager.undo()

    def _on_redo_requested(self) -> None:
        if hasattr(self.page_editor, "scene") and hasattr(self.page_editor.scene, "undo_manager"):
            self.page_editor.scene.undo_manager.redo()

    def _on_studio_tab_selected(self, tab_str: str) -> None:
        """Navigate to the pipeline stage behind a ribbon entry."""
        step = workflow.step_for_tab(tab_str)
        if step is not None:
            self.switch_page(step)

    def _show_help(self) -> None:
        QMessageBox.information(
            self,
            "ID Studio Documentation",
            f"<b>{APP_NAME} v{APP_VERSION}</b><br><br>"
            "<b>Studio Workspaces:</b><br>"
            "• <b>Templates:</b> Credential catalog, CR80 presets, and built-in layouts.<br>"
            "• <b>Template Designer:</b> Precision visual canvas, smart alignment, and layer hierarchy.<br>"
            "• <b>Data Mapping:</b> Multi-sheet Excel/CSV connector, Hindi font transliteration, and photo matching.<br>"
            "• <b>Generate & Preview:</b> Batch multi-threaded card generation and live validation inspector.<br>"
            "• <b>Export & Print:</b> A4 sheet imposition engine, crop marks, duplex alignment, and manifest packaging.<br><br>"
            "<b>Keyboard Shortcuts:</b><br>"
            "• <b>V:</b> Move / Select Tool<br>"
            "• <b>T:</b> Text Element Tool<br>"
            "• <b>I:</b> Photo Frame Tool<br>"
            "• <b>R:</b> Vector Rectangle Tool<br>"
            "• <b>G:</b> Toggle Metric Grid<br>"
            "• <b>Ctrl+Z / Ctrl+Y:</b> Undo / Redo<br>"
            "• <b>Ctrl+S:</b> Save Project Workspace"
        )

    def _new_project(self) -> None:
        """Create a new project document (.idcrt)."""
        dialog = NewProjectDialog(self, template_manager=self.template_manager)
        if dialog.exec():
            if dialog.created_config:
                self.records = []
                self.columns = []
                self.match_results = {}
                self.column_mappings = {}
                self.active_template = dialog.created_config.template
                self.last_generation_summary = None
                self.set_project(dialog.created_config, workspace_path=None)
                if dialog.created_config.template:
                    if hasattr(self.page_editor, "load_template"):
                        self.page_editor.load_template(dialog.created_config.template)
                    self.page_templates.active_template = dialog.created_config.template
                self.switch_page(WorkflowStep.DATA_SOURCE)

    def _on_preset_selected(self, preset_key: str) -> None:
        """Start a new project with the chosen preset template."""
        preset_titles = {
            "corporate_cr80": "Corporate Staff ID",
            "defense_pki": "High-Security Defense",
            "university_pass": "University Student Pass",
            "event_cr100": "Event & Conference Pass",
        }
        title = preset_titles.get(preset_key, "New ID Project")

        # Pick matching template if available, else first built-in
        tmpl = None
        for t in self.template_manager.list_templates():
            if preset_key in t.id or preset_key in t.name.lower():
                tmpl = t
                break
        if not tmpl and self.template_manager.list_templates():
            tmpl = self.template_manager.list_templates()[0]

        cfg = ProjectConfiguration(
            project_name=title,
            template=tmpl,
        )
        self.records = []
        self.columns = []
        self.match_results = {}
        self.column_mappings = {}
        self.active_template = tmpl
        self.last_generation_summary = None
        self.set_project(cfg, workspace_path=None)
        if tmpl:
            if hasattr(self.page_editor, "load_template"):
                self.page_editor.load_template(tmpl)
            self.page_templates.active_template = tmpl
        self.switch_page(WorkflowStep.DATA_SOURCE)

    def _open_project(self) -> None:
        """Open an existing .idcrt project file."""
        file_path, _ = QFileDialog.getOpenFileName(
            self,
            "Open ID Studio Project",
            "",
            "ID Studio Project (*.idcrt);;Legacy Project (*.json *.idproj);;All Files (*)",
        )
        if file_path:
            self.load_project_from_file(Path(file_path))

    def load_project_from_file(self, file_path: Path) -> bool:
        """Load and restore an ID Studio project (.idcrt / .json)."""
        try:
            file_path = Path(file_path).resolve()
            if not file_path.exists():
                QMessageBox.warning(self, "File Not Found", f"Project file does not exist:\n{file_path}")
                return False

            cfg = ProjectManager.load_project(file_path)
            missing = ProjectManager.check_missing_references(cfg)
            if missing:
                relink_dialog = RelinkDialog(missing, self)
                if relink_dialog.exec():
                    cfg = ProjectManager.relink_references(cfg, relink_dialog.replacements)
                else:
                    return False

            self.set_project(cfg, workspace_path=file_path)
            self.status_bar.showMessage(f"Project '{cfg.project_name}' loaded from {file_path.name}")
            return True
        except Exception as e:
            logger.error("Failed to load project: %s", e)
            if not os.environ.get("PYTEST_CURRENT_TEST"):
                QMessageBox.critical(self, "Load Error", f"Could not load project from {file_path.name}:\n{e}")
            else:
                self.status_bar.showMessage(f"Load error: {e}")
            return False

    def _save_project(self) -> None:
        """Save project to active .idcrt path, or prompt if unsaved."""
        if self.current_project_path:
            self._save_to_path(self.current_project_path)
        else:
            self._save_project_as()

    def _save_project_as(self) -> None:
        """Prompt user for destination .idcrt path and save."""
        default_name = "Untitled.idcrt"
        if self.current_project_config and self.current_project_config.project_name:
            clean = "".join(c for c in self.current_project_config.project_name if c.isalnum() or c in (" ", "_", "-")).strip()
            if clean:
                default_name = f"{clean}.idcrt"

        file_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save ID Studio Project",
            default_name,
            "ID Studio Project (*.idcrt);;Legacy Project (*.json *.idproj);;All Files (*)",
        )
        if file_path:
            save_path = Path(file_path)
            if not save_path.suffix:
                save_path = save_path.with_suffix(".idcrt")
            self.current_project_path = save_path
            self._save_to_path(self.current_project_path)

    def _save_to_path(self, path: Path) -> None:
        try:
            path = Path(path).resolve()
            if not path.suffix:
                path = path.with_suffix(".idcrt")

            cfg = self.current_project_config or ProjectConfiguration()
            if cfg.project_name in ("Untitled Project", "Untitled", ""):
                cfg.project_name = path.stem
            cfg.excel_file_path = str(self.page_data_source.current_file_path) if self.page_data_source.current_file_path else cfg.excel_file_path
            cfg.sheet_name = self.page_data_source.cmb_sheets.currentText() or cfg.sheet_name
            cfg.header_row = self.page_data_source.spin_header.value()
            cfg.photo_dir_path = str(self.page_photos.matcher.photo_dir) if (hasattr(self.page_photos, "matcher") and self.page_photos.matcher.photo_dir) else cfg.photo_dir_path
            cfg.template = self.active_template or self.page_templates.active_template or cfg.template
            cfg.column_mappings = self.column_mappings
            cfg.photo_overrides = self.page_photos.matcher.overrides if hasattr(self.page_photos, "matcher") else {}
            cfg.missing_photo_policy = self.settings.missing_photo_policy
            cfg.review_states = {r.record_id: r.status for r in self.page_production.manager.records}
            if hasattr(self.page_export, "last_export_dir") and self.page_export.last_export_dir:
                cfg.last_export_dir = str(self.page_export.last_export_dir)

            ProjectManager.save_project(cfg, path)
            self.current_project_config = cfg
            self.current_project_path = path

            if hasattr(self, "header_bar"):
                self.header_bar.set_project_title(path.name, False)
                self.header_bar.set_sync_status("Saved (Local)", COLORS.TERTIARY)

            self._refresh_status_bar()
            self._refresh_dashboard_metrics()
            # Non-blocking confirmation - a modal dialog would stall the flow.
            self.status_bar.showMessage(f"Project saved to {path.name}")
        except Exception as e:
            logger.error("Failed to save project: %s", e)
            self.status_bar.showMessage(f"Save failed: {e}")
            if not os.environ.get("PYTEST_CURRENT_TEST"):
                QMessageBox.critical(self, "Save Error", f"Could not save project: {e}")
