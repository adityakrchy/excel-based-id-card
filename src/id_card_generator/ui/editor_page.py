"""Photoshop-inspired Visual Canvas Editor workspace with vertical tool strip, contextual options bar, layer hierarchy, and integrated field mapping."""

import logging
from typing import Dict, List, Optional
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QKeySequence, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDoubleSpinBox,
    QFontComboBox,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSpinBox,
    QSplitter,
    QStackedWidget,
    QTabWidget,
    QTextEdit,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import ImageFitMode, WorkflowStep
from id_card_generator.core.models import (
    CanvasElement,
    PhotoMatchResult,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.editor.alignment_tools import AlignmentTools
from id_card_generator.editor.canvas_items import CanvasItem
from id_card_generator.editor.canvas_scene import CanvasScene
from id_card_generator.editor.canvas_view import CanvasView
from id_card_generator.editor.element_inspector import ElementInspector
from id_card_generator.editor.field_mapping_panel import FieldMappingPanel
from id_card_generator.editor.layers_panel import LayersPanel
from id_card_generator.templates.template_manager import TemplateManager
from id_card_generator.ui.dialogs.template_cleanup_dialog import TemplateCleanupDialog
from id_card_generator.ui.step_nav_bar import StepNavBar

logger = logging.getLogger(__name__)


class EditorPage(QWidget):
    """Professional, Photoshop-inspired canvas editor workspace."""

    template_updated = Signal(object)  # TemplateDefinition
    navigate_requested = Signal(str)  # WorkflowStep value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = CanvasScene(self)
        self.view = CanvasView(self.scene, self)
        self.inspector = ElementInspector(self)
        self.layers_panel = LayersPanel(self.scene, self)
        self.mapping_panel = FieldMappingPanel(self)

        self.records: List[SourceRecord] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.columns: List[str] = []
        self.sample_index: int = 0
        self._updating_context_bar: bool = False
        self._user_adjusted_splitter: bool = False
        self.template_manager = TemplateManager()

        self._setup_ui()
        self._connect_signals()

    def _setup_ui(self) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(6, 6, 6, 6)
        main_layout.setSpacing(6)

        # 0. Top Template Management Bar
        self.template_bar = QFrame()
        self.template_bar.setObjectName("card_panel")
        self.template_bar.setFixedHeight(42)
        tmpl_bar_layout = QHBoxLayout(self.template_bar)
        tmpl_bar_layout.setContentsMargins(10, 4, 10, 4)
        tmpl_bar_layout.setSpacing(8)

        tmpl_icon = QLabel("📐")
        tmpl_icon.setStyleSheet("font-size: 15px;")
        tmpl_bar_layout.addWidget(tmpl_icon)

        self.lbl_tmpl_name = QLabel("<b>Template:</b> Default Template")
        self.lbl_tmpl_name.setStyleSheet("color: #F8FAFC; font-size: 13px;")
        tmpl_bar_layout.addWidget(self.lbl_tmpl_name)

        self.lbl_tmpl_badge = QLabel("Built-in")
        self.lbl_tmpl_badge.setStyleSheet(
            "color: #94A3B8; font-size: 10px; font-weight: bold; padding: 2px 6px; background: #27272A; border-radius: 4px;"
        )
        tmpl_bar_layout.addWidget(self.lbl_tmpl_badge)

        tmpl_bar_layout.addStretch()

        self.btn_tmpl_save = QPushButton("💾 Save Template")
        self.btn_tmpl_save.setToolTip("Save canvas design to custom saved templates")
        self.btn_tmpl_save.clicked.connect(self._save_current_template)
        tmpl_bar_layout.addWidget(self.btn_tmpl_save)

        self.btn_tmpl_delete = QPushButton("🗑 Delete Template")
        self.btn_tmpl_delete.setObjectName("btn_danger")
        self.btn_tmpl_delete.setToolTip("Delete this custom saved template from disk (built-in templates cannot be deleted)")
        self.btn_tmpl_delete.setEnabled(False)
        self.btn_tmpl_delete.clicked.connect(self._delete_current_template)
        tmpl_bar_layout.addWidget(self.btn_tmpl_delete)

        self.btn_tmpl_cleanup = QPushButton("🧹 Clean Up Older Templates...")
        self.btn_tmpl_cleanup.setToolTip("Open template cleanup manager to search, delete, and clean up older saved templates")
        self.btn_tmpl_cleanup.clicked.connect(self._open_cleanup_dialog)
        tmpl_bar_layout.addWidget(self.btn_tmpl_cleanup)

        main_layout.addWidget(self.template_bar)

        # 1. Top Contextual Options Bar
        self.options_bar = QFrame()
        self.options_bar.setObjectName("card_panel")
        self.options_bar.setFixedHeight(48)
        self.opt_layout = QHBoxLayout(self.options_bar)
        self.opt_layout.setContentsMargins(8, 4, 8, 4)
        self.opt_layout.setSpacing(8)

        # Stacked widget for contextual options
        self.stack_context = QStackedWidget()

        # Page 0: Document Default Context
        self.page_doc_context = self._create_doc_context_page()
        self.stack_context.addWidget(self.page_doc_context)

        # Page 1: Text Element Context
        self.page_text_context = self._create_text_context_page()
        self.stack_context.addWidget(self.page_text_context)

        # Page 2: Shape Element Context
        self.page_shape_context = self._create_shape_context_page()
        self.stack_context.addWidget(self.page_shape_context)

        # Page 3: Photo / Image Element Context
        self.page_photo_context = self._create_photo_context_page()
        self.stack_context.addWidget(self.page_photo_context)

        self.opt_layout.addWidget(self.stack_context, stretch=1)

        # Common action buttons on far right of options bar
        self.btn_undo = QPushButton("↶ Undo")
        self.btn_undo.setToolTip("Undo last action (Ctrl+Z / Cmd+Z)")
        self.opt_layout.addWidget(self.btn_undo)

        self.btn_redo = QPushButton("↷ Redo")
        self.btn_redo.setToolTip("Redo last action (Ctrl+Y / Cmd+Y)")
        self.opt_layout.addWidget(self.btn_redo)

        self.btn_dup = QPushButton("⧉ Duplicate")
        self.btn_dup.clicked.connect(self.scene.duplicate_selected)
        self.opt_layout.addWidget(self.btn_dup)

        self.btn_del = QPushButton("🗑 Delete")
        self.btn_del.setObjectName("btn_danger")
        self.btn_del.clicked.connect(self.scene.delete_selected)
        self.opt_layout.addWidget(self.btn_del)

        main_layout.addWidget(self.options_bar)

        # 2. Editor Central Area: Left Vertical Toolbar + Center Canvas + Right Panels
        editor_body = QHBoxLayout()
        editor_body.setSpacing(6)

        # Left Vertical Icon Toolbar (Photoshop inspired)
        self.tool_strip = self._create_vertical_tool_strip()
        editor_body.addWidget(self.tool_strip)

        # Resizable Splitter (Canvas 70% and Right Panels 30% by default)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(7)
        self.splitter.setChildrenCollapsible(False)
        self.view.setMinimumWidth(360)

        # Right Tabbed Dock
        self.right_tabs = QTabWidget()
        self.right_tabs.setMinimumWidth(260)
        self.right_tabs.addTab(self.inspector, "Properties")
        self.right_tabs.addTab(self.layers_panel, "Layers")
        self.right_tabs.addTab(self.mapping_panel, "Data Mapping")

        self.splitter.addWidget(self.view)
        self.splitter.addWidget(self.right_tabs)

        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes([840, 360])
        self.splitter.splitterMoved.connect(self._on_splitter_moved)
        editor_body.addWidget(self.splitter, stretch=1)

        main_layout.addLayout(editor_body, stretch=1)

        # 3. Bottom Status Bar Readout
        self.status_bar_frame = QFrame()
        self.status_bar_frame.setObjectName("card_panel")
        self.status_bar_frame.setFixedHeight(28)
        sb_layout = QHBoxLayout(self.status_bar_frame)
        sb_layout.setContentsMargins(10, 2, 10, 2)

        self.lbl_sb_zoom = QLabel("Zoom: 100%")
        sb_layout.addWidget(self.lbl_sb_zoom)
        sb_layout.addSpacing(16)

        self.lbl_sb_dim = QLabel("Size: 85.6 × 54.0 mm (1011 × 638 px)")
        sb_layout.addWidget(self.lbl_sb_dim)
        sb_layout.addSpacing(16)

        self.lbl_sb_dpi = QLabel("DPI: 300")
        sb_layout.addWidget(self.lbl_sb_dpi)
        sb_layout.addSpacing(16)

        self.lbl_sb_selection = QLabel("No selection")
        self.lbl_sb_selection.setStyleSheet("color: #60CDFF;")
        sb_layout.addWidget(self.lbl_sb_selection)

        sb_layout.addStretch()

        self.lbl_sb_status = QLabel("Ready")
        sb_layout.addWidget(self.lbl_sb_status)

        main_layout.addWidget(self.status_bar_frame)

        # 4. Bottom Step Navigation Bar
        self.nav_bar = StepNavBar(
            prev_label="Choose Template",
            next_label="Batch Generate",
            step_badge="Step 4 of 7: Canvas Editor & Field Mapping",
            parent=self,
        )
        self.nav_bar.back_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.TEMPLATES.value))
        self.nav_bar.next_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.GENERATE.value))
        main_layout.addWidget(self.nav_bar)

    def _create_vertical_tool_strip(self) -> QFrame:
        """Create Photoshop-inspired vertical icon toolbar."""
        frame = QFrame()
        frame.setObjectName("card_panel")
        frame.setFixedWidth(52)
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(4, 8, 4, 8)
        layout.setSpacing(6)

        self.tool_group = QButtonGroup(self)
        self.tool_group.setExclusive(True)

        tools = [
            ("select", "↖", "Select / Move Tool (V)"),
            ("static_text", "T", "Text Tool (T)"),
            ("dynamic_text", "{T}", "Dynamic Field Tool (D)"),
            ("photo", "📷", "Photo Tool (P)"),
            ("rect", "▭", "Rectangle Tool (U)"),
            ("round_rect", "▢", "Rounded Rectangle Tool (R)"),
            ("line", "―", "Line Tool (L)"),
        ]

        for tool_id, icon_char, tooltip in tools:
            btn = QToolButton()
            btn.setText(icon_char)
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setFixedSize(40, 36)
            btn.setStyleSheet("font-size: 15px; font-weight: bold;")
            if tool_id == "select":
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, tid=tool_id: self._on_tool_selected(tid))
            self.tool_group.addButton(btn)
            layout.addWidget(btn)

        layout.addSpacing(10)
        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #3F3F46;")
        layout.addWidget(sep)
        layout.addSpacing(10)

        # Zoom & Fit actions
        btn_fit = QToolButton()
        btn_fit.setText("⛶")
        btn_fit.setToolTip("Fit Card to View")
        btn_fit.setFixedSize(40, 36)
        btn_fit.clicked.connect(self.view.fit_to_view)
        layout.addWidget(btn_fit)

        btn_100 = QToolButton()
        btn_100.setText("1:1")
        btn_100.setToolTip("Zoom 100%")
        btn_100.setFixedSize(40, 36)
        btn_100.clicked.connect(self.view.reset_zoom)
        layout.addWidget(btn_100)

        btn_reset_split = QToolButton()
        btn_reset_split.setText("70%")
        btn_reset_split.setToolTip("Reset Canvas Area to 70% Screen Width")
        btn_reset_split.setFixedSize(40, 36)
        btn_reset_split.clicked.connect(lambda: self.apply_default_splitter_sizes(force=True))
        layout.addWidget(btn_reset_split)

        layout.addStretch()
        return frame

    def _create_doc_context_page(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("<b>Document:</b>"))
        self.lbl_ctx_doc_dims = QLabel("CR80 Standard")
        layout.addWidget(self.lbl_ctx_doc_dims)

        layout.addSpacing(8)
        btn_zoom_in = QPushButton("+ Zoom")
        btn_zoom_in.clicked.connect(self.view.zoom_in)
        layout.addWidget(btn_zoom_in)

        btn_zoom_out = QPushButton("- Zoom")
        btn_zoom_out.clicked.connect(self.view.zoom_out)
        layout.addWidget(btn_zoom_out)

        layout.addSpacing(10)
        # Snapping and Smart Guides Controls
        self._setup_snapping_ui(layout)

        layout.addStretch()
        return widget

    def _setup_snapping_ui(self, layout: QHBoxLayout) -> None:
        """Add Smart Guides and Magnetic Snapping controls to document context bar."""
        # 1. Quick toggle button: Guides
        self.btn_guides_toggle = QToolButton()
        self.btn_guides_toggle.setText("⚡ Guides")
        self.btn_guides_toggle.setCheckable(True)
        self.btn_guides_toggle.setChecked(self.scene.snap_settings.smart_guides_enabled)
        self.btn_guides_toggle.setToolTip("Toggle Smart Alignment Guides (Magenta Lines)")
        self.btn_guides_toggle.toggled.connect(self._on_guides_toggled)
        layout.addWidget(self.btn_guides_toggle)

        # 2. Quick toggle button: Snap
        self.btn_snap_toggle = QToolButton()
        self.btn_snap_toggle.setText("🧲 Snap")
        self.btn_snap_toggle.setCheckable(True)
        self.btn_snap_toggle.setChecked(self.scene.snap_settings.object_snapping_enabled)
        self.btn_snap_toggle.setToolTip("Toggle Magnetic Object Snapping (Hold Alt while dragging to bypass)")
        self.btn_snap_toggle.toggled.connect(self._on_snap_toggled)
        layout.addWidget(self.btn_snap_toggle)

        # 3. Settings dropdown menu
        self.btn_snap_menu = QToolButton()
        self.btn_snap_menu.setText("Snapping ▾")
        self.btn_snap_menu.setPopupMode(QToolButton.InstantPopup)
        self.btn_snap_menu.setToolTip("Smart Alignment, Spacing, and Grid Snapping Options")

        menu = QMenu(self.btn_snap_menu)
        menu.setStyleSheet("font-size: 13px; padding: 4px;")

        self.act_guides = menu.addAction("Smart Guides (Magenta)")
        self.act_guides.setCheckable(True)
        self.act_guides.setChecked(self.scene.snap_settings.smart_guides_enabled)
        self.act_guides.toggled.connect(self._on_guides_toggled)

        self.act_snap = menu.addAction("Magnetic Object Snapping")
        self.act_snap.setCheckable(True)
        self.act_snap.setChecked(self.scene.snap_settings.object_snapping_enabled)
        self.act_snap.toggled.connect(self._on_snap_toggled)

        self.act_spacing = menu.addAction("Smart Spacing & Distribution")
        self.act_spacing.setCheckable(True)
        self.act_spacing.setChecked(self.scene.snap_settings.smart_spacing_enabled)
        self.act_spacing.toggled.connect(self.scene.set_smart_spacing_enabled)

        self.act_canvas = menu.addAction("Snap to Canvas Bounds & Center")
        self.act_canvas.setCheckable(True)
        self.act_canvas.setChecked(self.scene.snap_settings.snap_to_canvas_enabled)
        self.act_canvas.toggled.connect(self.scene.set_snap_to_canvas_enabled)

        self.act_grid = menu.addAction("Snap to Grid Lines")
        self.act_grid.setCheckable(True)
        self.act_grid.setChecked(self.scene.snap_to_grid)
        self.act_grid.toggled.connect(self._on_grid_snap_toggled)

        menu.addSeparator()

        # Threshold submenu
        thresh_menu = menu.addMenu("Snapping Threshold")
        for label, val in [("Fine (4 px)", 4.0), ("Standard (8 px)", 8.0), ("Magnetic (14 px)", 14.0)]:
            act = thresh_menu.addAction(label)
            act.setCheckable(True)
            if self.scene.snap_settings.snap_threshold_screen == val:
                act.setChecked(True)
            act.triggered.connect(lambda chk=False, v=val: self.scene.set_snap_threshold(v))

        menu.addSeparator()
        info_act = menu.addAction("Tip: Hold Alt/Option while dragging to bypass snap")
        info_act.setEnabled(False)

        self.btn_snap_menu.setMenu(menu)
        layout.addWidget(self.btn_snap_menu)

    def _on_guides_toggled(self, checked: bool) -> None:
        self.scene.set_smart_guides_enabled(checked)
        if hasattr(self, "btn_guides_toggle") and self.btn_guides_toggle.isChecked() != checked:
            self.btn_guides_toggle.setChecked(checked)
        if hasattr(self, "act_guides") and self.act_guides.isChecked() != checked:
            self.act_guides.setChecked(checked)

    def _on_snap_toggled(self, checked: bool) -> None:
        self.scene.set_object_snapping_enabled(checked)
        if hasattr(self, "btn_snap_toggle") and self.btn_snap_toggle.isChecked() != checked:
            self.btn_snap_toggle.setChecked(checked)
        if hasattr(self, "act_snap") and self.act_snap.isChecked() != checked:
            self.act_snap.setChecked(checked)

    def _on_grid_snap_toggled(self, checked: bool) -> None:
        self.scene.set_snap_to_grid_enabled(checked)
        if hasattr(self, "act_grid") and self.act_grid.isChecked() != checked:
            self.act_grid.setChecked(checked)

    def _create_text_context_page(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(6)

        layout.addWidget(QLabel("<b>Text:</b>"))

        self.ctx_font_family = QFontComboBox()
        self.ctx_font_family.setFixedWidth(140)
        self.ctx_font_family.currentFontChanged.connect(self._on_ctx_font_changed)
        layout.addWidget(self.ctx_font_family)

        self.ctx_font_size = QSpinBox()
        self.ctx_font_size.setRange(4, 144)
        self.ctx_font_size.setSuffix(" pt")
        self.ctx_font_size.setValue(10)
        self.ctx_font_size.valueChanged.connect(self._on_ctx_font_size_changed)
        layout.addWidget(self.ctx_font_size)

        self.ctx_chk_bold = QCheckBox("B")
        self.ctx_chk_bold.setStyleSheet("font-weight: bold;")
        self.ctx_chk_bold.toggled.connect(self._on_ctx_bold_toggled)
        layout.addWidget(self.ctx_chk_bold)

        self.ctx_chk_italic = QCheckBox("I")
        self.ctx_chk_italic.setStyleSheet("font-style: italic;")
        self.ctx_chk_italic.toggled.connect(self._on_ctx_italic_toggled)
        layout.addWidget(self.ctx_chk_italic)

        self.ctx_btn_color = QPushButton("Color")
        self.ctx_btn_color.setFixedWidth(60)
        self.ctx_btn_color.clicked.connect(self._on_ctx_color_clicked)
        layout.addWidget(self.ctx_btn_color)

        self.ctx_cmb_align = QComboBox()
        self.ctx_cmb_align.addItems(["left", "center", "right"])
        self.ctx_cmb_align.currentTextChanged.connect(self._on_ctx_align_changed)
        layout.addWidget(self.ctx_cmb_align)

        layout.addStretch()
        return widget

    def _create_shape_context_page(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("<b>Shape:</b>"))

        self.ctx_btn_fill = QPushButton("Fill")
        self.ctx_btn_fill.clicked.connect(self._on_ctx_fill_clicked)
        layout.addWidget(self.ctx_btn_fill)

        self.ctx_btn_stroke = QPushButton("Stroke")
        self.ctx_btn_stroke.clicked.connect(self._on_ctx_stroke_clicked)
        layout.addWidget(self.ctx_btn_stroke)

        layout.addWidget(QLabel("Width:"))
        self.ctx_spin_stroke_w = QSpinBox()
        self.ctx_spin_stroke_w.setRange(0, 50)
        self.ctx_spin_stroke_w.valueChanged.connect(self._on_ctx_stroke_w_changed)
        layout.addWidget(self.ctx_spin_stroke_w)

        layout.addWidget(QLabel("Radius:"))
        self.ctx_spin_radius = QSpinBox()
        self.ctx_spin_radius.setRange(0, 500)
        self.ctx_spin_radius.valueChanged.connect(self._on_ctx_radius_changed)
        layout.addWidget(self.ctx_spin_radius)

        layout.addStretch()
        return widget

    def _create_photo_context_page(self) -> QWidget:
        widget = QWidget()
        layout = QHBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        layout.addWidget(QLabel("<b>Photo / Image:</b>"))

        layout.addWidget(QLabel("Fit:"))
        self.ctx_cmb_fit = QComboBox()
        self.ctx_cmb_fit.addItems(["cover", "contain", "stretch", "crop"])
        self.ctx_cmb_fit.currentTextChanged.connect(self._on_ctx_fit_changed)
        layout.addWidget(self.ctx_cmb_fit)

        layout.addWidget(QLabel("Mask:"))
        self.ctx_cmb_mask = QComboBox()
        self.ctx_cmb_mask.addItems(["rect", "circle", "rounded"])
        self.ctx_cmb_mask.currentTextChanged.connect(self._on_ctx_mask_changed)
        layout.addWidget(self.ctx_cmb_mask)

        layout.addStretch()
        return widget

    def _connect_signals(self) -> None:
        self.scene.element_selected.connect(self._on_element_selected)
        self.scene.template_modified.connect(self._on_template_modified)
        self.inspector.property_changed.connect(self._on_inspector_property_changed)
        self.layers_panel.item_selected.connect(self.inspector.set_selected_item)
        self.layers_panel.order_changed.connect(self._on_template_modified)

        # Field mapping panel signals
        self.mapping_panel.bind_column_requested.connect(self._bind_selected_element)
        self.mapping_panel.create_dynamic_requested.connect(self._create_dynamic_element_for_column)
        self.mapping_panel.sample_changed.connect(self._on_sample_index_changed)

        # Undo / Redo buttons & stack observation
        self.btn_undo.clicked.connect(self._trigger_undo)
        self.btn_redo.clicked.connect(self._trigger_redo)
        self.scene.undo_stack.canUndoChanged.connect(self.btn_undo.setEnabled)
        self.scene.undo_stack.canRedoChanged.connect(self.btn_redo.setEnabled)
        self.btn_undo.setEnabled(self.scene.undo_stack.canUndo())
        self.btn_redo.setEnabled(self.scene.undo_stack.canRedo())

        # Setup keyboard shortcuts for Windows (Ctrl+Z, Ctrl+Y) and Mac (Cmd+Z, Cmd+Y)
        self._setup_shortcuts()

    def _trigger_undo(self) -> None:
        """Undo last action, letting active text input widgets handle internal undo first."""
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):
            fw.undo()
            return
        self.scene.undo()

    def _trigger_redo(self) -> None:
        """Redo last undone action, letting active text input widgets handle internal redo first."""
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit)):
            fw.redo()
            return
        self.scene.redo()

    def _setup_shortcuts(self) -> None:
        """Register platform-agnostic, Windows, and macOS shortcuts for Undo and Redo."""
        # Undo: Ctrl+Z (Windows/Linux), Cmd+Z / Meta+Z (macOS), QKeySequence.Undo
        undo_sequences = [
            QKeySequence.Undo,
            QKeySequence("Ctrl+Z"),
            QKeySequence("Meta+Z"),
        ]
        self._undo_shortcuts = []
        for seq in undo_sequences:
            sc = QShortcut(seq, self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(self._trigger_undo)
            self._undo_shortcuts.append(sc)

        # Redo: Ctrl+Y (Windows), Cmd+Y / Meta+Y (macOS), Ctrl+Shift+Z, Cmd+Shift+Z, QKeySequence.Redo
        redo_sequences = [
            QKeySequence.Redo,
            QKeySequence("Ctrl+Y"),
            QKeySequence("Meta+Y"),
            QKeySequence("Ctrl+Shift+Z"),
            QKeySequence("Meta+Shift+Z"),
        ]
        self._redo_shortcuts = []
        for seq in redo_keys if (redo_keys := redo_sequences) else []:
            sc = QShortcut(seq, self)
            sc.setContext(Qt.WindowShortcut)
            sc.activated.connect(self._trigger_redo)
            self._redo_shortcuts.append(sc)

    def _on_splitter_moved(self, pos: int, index: int) -> None:
        """Record when user manually resizes canvas using the center slider handle."""
        self._user_adjusted_splitter = True

    def apply_default_splitter_sizes(self, force: bool = False) -> None:
        """Ensure canvas area occupies 70% of available screen width by default."""
        if self._user_adjusted_splitter and not force:
            return

        total_w = self.splitter.width()
        if total_w <= 100:
            total_w = self.width() - self.tool_strip.width() - 24
            if total_w <= 100 and self.window():
                total_w = self.window().width() - self.tool_strip.width() - 32

        if total_w > 100:
            canvas_w = int(total_w * 0.70)
            right_w = max(240, total_w - canvas_w)
            self.splitter.setSizes([canvas_w, right_w])
            if force:
                self._user_adjusted_splitter = False
                self.view.fit_to_view(enlarge_factor=1.35)

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if not self._user_adjusted_splitter:
            self.apply_default_splitter_sizes(force=False)
            QTimer.singleShot(0, lambda: self.apply_default_splitter_sizes(force=False))
            QTimer.singleShot(50, lambda: self.apply_default_splitter_sizes(force=False))
        QTimer.singleShot(80, lambda: self.view.fit_to_view(enlarge_factor=1.35))

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        if not self._user_adjusted_splitter:
            self.apply_default_splitter_sizes(force=False)

    def keyPressEvent(self, event) -> None:
        """Forward arrow keys and element actions from editor page to canvas scene."""
        fw = QApplication.focusWidget()
        if isinstance(fw, (QLineEdit, QTextEdit, QPlainTextEdit, QSpinBox, QDoubleSpinBox)):
            super().keyPressEvent(event)
            return

        if event.key() in (Qt.Key_Left, Qt.Key_Right, Qt.Key_Up, Qt.Key_Down, Qt.Key_Delete, Qt.Key_Backspace):
            if self.scene and hasattr(self.scene, "keyPressEvent"):
                self.scene.keyPressEvent(event)
                if event.isAccepted():
                    return
        super().keyPressEvent(event)

    def load_template(self, template: TemplateDefinition) -> None:
        """Load template into canvas editor and update metadata readouts."""
        self.scene.load_template(template)
        self.layers_panel.refresh_layers()
        self._update_template_bar_ui()
        if not self._user_adjusted_splitter:
            self.apply_default_splitter_sizes(force=False)
            QTimer.singleShot(20, lambda: self.apply_default_splitter_sizes(force=False))
        QTimer.singleShot(60, lambda: self.view.fit_to_view(enlarge_factor=1.35))
        self._update_status_dimensions()
        self._update_sample_preview()

    def set_dataset(
        self,
        records: List[SourceRecord],
        match_results: Dict[str, PhotoMatchResult],
        columns: List[str],
    ) -> None:
        """Set spreadsheet dataset for live binding and preview."""
        self.records = records
        self.match_results = match_results
        self.columns = columns
        self.inspector.set_available_columns(columns)
        self.mapping_panel.set_dataset(columns, records, match_results)
        self.sample_index = 0
        self._update_sample_preview()

    def _on_tool_selected(self, tool_id: str) -> None:
        if tool_id == "select":
            return
        elif tool_id == "static_text":
            self._add_static_text()
        elif tool_id == "dynamic_text":
            self._add_dynamic_text()
        elif tool_id == "photo":
            self._add_photo_element()
        elif tool_id == "rect":
            self._add_rect_element()
        elif tool_id == "round_rect":
            self._add_round_rect_element()
        elif tool_id == "line":
            self._add_line_element()

        # Reset selection tool
        for btn in self.tool_group.buttons():
            if btn.text() == "↖":
                btn.setChecked(True)
                break

    def _on_element_selected(self, item: Optional[CanvasItem]) -> None:
        self.inspector.set_selected_item(item)
        self.mapping_panel.set_selected_item(item)
        self._update_context_options(item)

        if item:
            elem = item.element
            self.lbl_sb_selection.setText(f"Selected: {elem.name} ({int(item.x())}, {int(item.y())}) {int(elem.width)}×{int(elem.height)}px")
        else:
            self.lbl_sb_selection.setText("No selection")

    def _update_context_options(self, item: Optional[CanvasItem]) -> None:
        if not item:
            self.stack_context.setCurrentIndex(0)
            return

        self._updating_context_bar = True
        elem = item.element
        if elem.type in ("static_text", "dynamic_text", "pin_field"):
            self.stack_context.setCurrentIndex(1)
            if not self.ctx_font_family.hasFocus() and self.ctx_font_family.currentFont().family() != elem.style.font_family:
                self.ctx_font_family.setCurrentFont(QFont(elem.style.font_family))
            sz_val = int(round(elem.style.font_size))
            if not self.ctx_font_size.hasFocus() and self.ctx_font_size.value() != sz_val:
                self.ctx_font_size.setValue(sz_val)
            self.ctx_chk_bold.setChecked(elem.style.font_bold)
            self.ctx_chk_italic.setChecked(elem.style.font_italic)
            self.ctx_cmb_align.setCurrentText(elem.style.text_align)
            self.ctx_btn_color.setStyleSheet(f"background-color: {elem.style.font_color}; color: #FFFFFF;")
        elif elem.type in ("rect", "round_rect", "line"):
            self.stack_context.setCurrentIndex(2)
            self.ctx_spin_stroke_w.setValue(elem.style.border_width)
            self.ctx_spin_radius.setValue(elem.style.border_radius)
        elif elem.type in ("photo", "image"):
            self.stack_context.setCurrentIndex(3)
            self.ctx_cmb_fit.setCurrentText(str(elem.style.fit_mode.value))
            self.ctx_cmb_mask.setCurrentText(elem.style.mask_shape)
        else:
            self.stack_context.setCurrentIndex(0)

        self._updating_context_bar = False

    def _on_inspector_property_changed(self, item: CanvasItem) -> None:
        self.scene.update()
        self._update_context_options(item)
        self.layers_panel.refresh_layers()

    def _on_template_modified(self) -> None:
        self.layers_panel.refresh_layers()
        sel = self.scene.get_selected_item()
        from PySide6.QtWidgets import QWidget
        if not self.inspector.hasFocus() and not any(w.hasFocus() for w in self.inspector.findChildren(QWidget)):
            self.inspector.set_selected_item(sel)
        self._update_context_options(sel)
        self._update_sample_preview()
        if self.scene.template:
            self.template_updated.emit(self.scene.template)

    def _update_status_dimensions(self) -> None:
        if not self.scene.template:
            return
        tmpl = self.scene.template
        w_px, h_px = tmpl.width_px, tmpl.height_px
        w_mm = tmpl.width_physical or round(w_px / tmpl.dpi * 25.4, 1)
        h_mm = tmpl.height_physical or round(h_px / tmpl.dpi * 25.4, 1)
        self.lbl_sb_dim.setText(f"Size: {w_mm} × {h_mm} mm ({w_px} × {h_px} px)")
        self.lbl_sb_dpi.setText(f"DPI: {tmpl.dpi}")
        self.lbl_ctx_doc_dims.setText(f"{tmpl.name} • {w_px} × {h_px} px @ {tmpl.dpi} DPI")

    def _update_sample_preview(self) -> None:
        if not self.records:
            self.scene.set_sample_data(None, None)
            return

        self.sample_index = max(0, min(len(self.records) - 1, self.sample_index))
        rec = self.records[self.sample_index]
        match = self.match_results.get(rec.record_id)
        photo_path = match.photo_path if match else None

        self.scene.set_sample_data(rec, photo_path)

    def _on_sample_index_changed(self, index: int) -> None:
        self.sample_index = index
        self._update_sample_preview()

    def _bind_selected_element(self, column_name: str) -> None:
        selected = [it for it in self.scene.selectedItems() if isinstance(it, CanvasItem)]
        if not selected:
            return
        item = selected[0]
        old_state = item.element.model_dump(mode="json")
        item.element.binding = column_name
        if item.element.type == "static_text":
            item.element.type = "dynamic_text"
        new_state = item.element.model_dump(mode="json")
        from id_card_generator.editor.undo_manager import ChangeElementStateCommand
        self.scene.undo_stack.push(
            ChangeElementStateCommand(
                self.scene, item.element.id, old_state, new_state, f"Bind to {column_name}"
            )
        )
        self.inspector.set_selected_item(item)
        self.layers_panel.refresh_layers()
        self._update_sample_preview()
        self._on_template_modified()

    def _create_dynamic_element_for_column(self, column_name: str) -> None:
        el = CanvasElement(
            name=column_name,
            type="dynamic_text",
            x=60.0,
            y=120.0,
            width=280.0,
            height=40.0,
            binding=column_name,
        )
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()
        self._update_sample_preview()

    def _apply_context_change(self, update_item_fn, description: str = "Change Style") -> None:
        if self._updating_context_bar:
            return
        selected = [it for it in self.scene.selectedItems() if isinstance(it, CanvasItem)]
        if not selected:
            return

        old_states = [(it.element.id, it.element.model_dump(mode="json")) for it in selected]
        for it in selected:
            update_item_fn(it)
            it.update()
        new_states = [(it.element.id, it.element.model_dump(mode="json")) for it in selected]

        from id_card_generator.editor.undo_manager import BatchStateChangeCommand
        changes = [(eid, old_s, new_s) for (eid, old_s), (_, new_s) in zip(old_states, new_states)]
        self.scene.undo_stack.push(BatchStateChangeCommand(self.scene, changes, description))
        self.scene.update()
        self.scene.template_modified.emit()

    # Contextual Options Handlers
    def _on_ctx_font_changed(self, font: QFont) -> None:
        self._apply_context_change(lambda it: setattr(it.element.style, "font_family", font.family()), "Change Font Family")

    def _on_ctx_font_size_changed(self, sz: int) -> None:
        self._apply_context_change(lambda it: setattr(it.element.style, "font_size", float(sz)), "Change Font Size")

    def _on_ctx_bold_toggled(self, checked: bool) -> None:
        self._apply_context_change(lambda it: setattr(it.element.style, "font_bold", checked), "Toggle Bold")

    def _on_ctx_italic_toggled(self, checked: bool) -> None:
        self._apply_context_change(lambda it: setattr(it.element.style, "font_italic", checked), "Toggle Italic")

    def _on_ctx_color_clicked(self) -> None:
        col = QColorDialog.getColor(QColor("#1A1A1A"), self, "Select Text Color")
        if col.isValid():
            hex_col = col.name().upper()
            self._apply_context_change(lambda it: setattr(it.element.style, "font_color", hex_col), "Change Text Color")
            self.ctx_btn_color.setStyleSheet(f"background-color: {hex_col}; color: #FFFFFF;")

    def _on_ctx_align_changed(self, align: str) -> None:
        self._apply_context_change(lambda it: setattr(it.element.style, "text_align", align), "Change Alignment")

    def _on_ctx_fill_clicked(self) -> None:
        col = QColorDialog.getColor(QColor("#E2E8F0"), self, "Select Shape Fill Color")
        if col.isValid():
            hex_col = col.name().upper()
            self._apply_context_change(lambda it: setattr(it.element.style, "background_color", hex_col), "Change Fill Color")

    def _on_ctx_stroke_clicked(self) -> None:
        col = QColorDialog.getColor(QColor("#0078D4"), self, "Select Shape Stroke Color")
        if col.isValid():
            hex_col = col.name().upper()
            self._apply_context_change(lambda it: setattr(it.element.style, "border_color", hex_col), "Change Stroke Color")

    def _on_ctx_stroke_w_changed(self, val: int) -> None:
        self._apply_context_change(lambda it: setattr(it.element.style, "border_width", val), "Change Stroke Width")

    def _on_ctx_radius_changed(self, val: int) -> None:
        self._apply_context_change(lambda it: setattr(it.element.style, "border_radius", val), "Change Border Radius")

    def _on_ctx_fit_changed(self, fit_str: str) -> None:
        self._apply_context_change(lambda it: setattr(it.element.style, "fit_mode", ImageFitMode(fit_str)), "Change Image Fit")

    def _on_ctx_mask_changed(self, mask_str: str) -> None:
        self._apply_context_change(lambda it: setattr(it.element.style, "mask_shape", mask_str), "Change Mask Shape")

    # Element Creation Methods
    def _add_static_text(self) -> None:
        el = CanvasElement(
            name="Static Label",
            type="static_text",
            x=60.0,
            y=60.0,
            width=320.0,
            height=48.0,
            static_content="Sample Text",
        )
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()

    def _add_dynamic_text(self) -> None:
        col = self.columns[0] if self.columns else "Name"
        el = CanvasElement(
            name=f"Dynamic {col}",
            type="dynamic_text",
            x=60.0,
            y=110.0,
            width=280.0,
            height=40.0,
            binding=col,
        )
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()
        self._update_sample_preview()

    def _add_photo_element(self) -> None:
        el = CanvasElement(
            name="Profile Photo",
            type="photo",
            x=80.0,
            y=160.0,
            width=180.0,
            height=200.0,
            binding="photo",
        )
        el.style.border_width = 2
        el.style.border_color = "#0078D4"
        el.style.border_radius = 8
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()
        self._update_sample_preview()

    def _add_rect_element(self) -> None:
        el = CanvasElement(
            name="Rectangle",
            type="rect",
            x=50.0,
            y=200.0,
            width=300.0,
            height=80.0,
        )
        el.style.background_color = "#27272A"
        el.style.border_width = 1
        el.style.border_color = "#3F3F46"
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()

    def _add_round_rect_element(self) -> None:
        el = CanvasElement(
            name="Rounded Card",
            type="round_rect",
            x=50.0,
            y=200.0,
            width=320.0,
            height=90.0,
        )
        el.style.background_color = "#202023"
        el.style.border_width = 1
        el.style.border_color = "#3F3F46"
        el.style.border_radius = 12
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()

    def _add_line_element(self) -> None:
        el = CanvasElement(
            name="Divider",
            type="line",
            x=50.0,
            y=240.0,
            width=350.0,
            height=2.0,
        )
        el.style.border_color = "#3F3F46"
        el.style.border_width = 2
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()

    def _update_template_bar_ui(self) -> None:
        """Update top template bar title, badge, and delete button enabled state."""
        if not hasattr(self, "lbl_tmpl_name") or not self.scene.template:
            return
        tmpl = self.scene.template
        is_built = self.template_manager.is_builtin(tmpl.id)
        self.lbl_tmpl_name.setText(f"<b>Template:</b> {tmpl.name}")
        if is_built:
            self.lbl_tmpl_badge.setText("Built-in")
            self.lbl_tmpl_badge.setStyleSheet(
                "color: #94A3B8; font-size: 10px; font-weight: bold; padding: 2px 6px; background: #27272A; border-radius: 4px;"
            )
            self.btn_tmpl_delete.setEnabled(False)
            self.btn_tmpl_delete.setToolTip("Built-in templates cannot be deleted")
        else:
            self.lbl_tmpl_badge.setText("Custom Saved")
            self.lbl_tmpl_badge.setStyleSheet(
                "color: #C084FC; font-size: 10px; font-weight: bold; padding: 2px 6px; background: rgba(192, 132, 252, 0.15); border-radius: 4px;"
            )
            self.btn_tmpl_delete.setEnabled(True)
            self.btn_tmpl_delete.setToolTip(f"Delete '{tmpl.name}' from disk")

    def _save_current_template(self) -> None:
        """Save the current canvas elements and settings as a user template."""
        tmpl = self.scene.get_current_template_definition()
        if not tmpl:
            QMessageBox.warning(self, "No Template", "No active template to save.")
            return

        is_built = self.template_manager.is_builtin(tmpl.id)
        default_name = f"{tmpl.name} (Custom)" if is_built and not tmpl.name.endswith("(Custom)") else tmpl.name

        name, ok = QInputDialog.getText(
            self,
            "Save Template",
            "Enter template name:",
            text=default_name,
        )
        if not ok or not name.strip():
            return

        tmpl.name = name.strip()
        try:
            saved_path = self.template_manager.save_user_template(tmpl)
            self.scene.template = tmpl
            self._update_template_bar_ui()
            self.template_updated.emit(tmpl)
            QMessageBox.information(
                self,
                "Template Saved",
                f"Template '{tmpl.name}' has been successfully saved to:\n{saved_path.name}",
            )
        except Exception as e:
            logger.error("Failed to save template: %s", e)
            QMessageBox.critical(self, "Save Error", f"Could not save template:\n{e}")

    def _delete_current_template(self) -> None:
        """Delete the current custom template from disk with confirmation and fallback to a default template."""
        tmpl = self.scene.template
        if not tmpl:
            return

        if self.template_manager.is_builtin(tmpl.id):
            QMessageBox.warning(
                self,
                "Protected Template",
                "Built-in templates cannot be deleted.",
            )
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Delete Template",
            f"Are you sure you want to permanently delete custom template '{tmpl.name}' from disk?\n\nThis cannot be undone.",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if confirm != QMessageBox.Yes:
            return

        try:
            self.template_manager.delete_user_template(tmpl.id)
            QMessageBox.information(
                self,
                "Template Deleted",
                f"Custom template '{tmpl.name}' has been deleted.",
            )

            # Fallback to a built-in or remaining template
            templates = self.template_manager.list_templates()
            fallback = next(
                (t for t in templates if self.template_manager.is_builtin(t.id)),
                templates[0] if templates else None,
            )
            if fallback:
                self.load_template(fallback)
                self.template_updated.emit(fallback)
        except Exception as e:
            logger.error("Failed to delete template: %s", e)
            QMessageBox.critical(self, "Delete Error", f"Could not delete template:\n{e}")

    def _open_cleanup_dialog(self) -> None:
        """Open modal cleanup dialog to search, delete, and clean up older templates."""
        active_id = self.scene.template.id if self.scene.template else ""
        dialog = TemplateCleanupDialog(self, active_template_id=active_id)
        dialog.template_selected.connect(self._on_template_selected_from_cleanup)
        dialog.exec()
        self.template_manager.reload()
        self._update_template_bar_ui()

    def _on_template_selected_from_cleanup(self, template: TemplateDefinition) -> None:
        """Load template selected from cleanup dialog."""
        self.load_template(template)
        self.template_updated.emit(template)
