"""Photoshop-inspired Visual Canvas Editor workspace with vertical tool strip, contextual options bar, layer hierarchy, and integrated field mapping."""

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional
from uuid import uuid4

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QFont, QImage, QKeySequence, QPixmap, QShortcut
from PySide6.QtWidgets import (
    QApplication,
    QButtonGroup,
    QCheckBox,
    QColorDialog,
    QComboBox,
    QDialog,
    QDoubleSpinBox,
    QFileDialog,
    QFontComboBox,
    QFrame,
    QGraphicsItem,
    QGraphicsView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMenuBar,
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
    RenderSettings,
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
from id_card_generator.editor.photoshop_dock_panels import ColorSwatchesPanel, HistoryPanel
from id_card_generator.editor.ruler_widget import CanvasContainer
from id_card_generator.rendering.pillow_renderer import PillowRenderer
from id_card_generator.templates.template_validator import TemplateValidator
from id_card_generator.ui.dialogs.blank_canvas_dialog import BlankCanvasDialog
from id_card_generator.ui.mapping_editor_view import MappingEditorView
from id_card_generator.ui.step_nav_bar import StepNavBar

logger = logging.getLogger(__name__)


class EditorPage(QWidget):
    """Professional, Photoshop-inspired canvas editor workspace."""

    template_updated = Signal(object)  # TemplateDefinition
    navigate_requested = Signal(str)  # WorkflowStep value
    mappings_updated = Signal(dict)  # column_mappings Dict[str, str]

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scene = CanvasScene(self)
        self.view = CanvasView(self.scene, self)
        self.inspector = ElementInspector(self)
        self.layers_panel = LayersPanel(self.scene, self)
        self.mapping_panel = FieldMappingPanel(self)
        self.swatches_panel = ColorSwatchesPanel(self)
        self.history_panel = HistoryPanel(self.scene.undo_stack, self)
        self.canvas_container = CanvasContainer(self.view, self)

        self.foreground_color = "#2563EB"
        self.background_color = "#FFFFFF"

        self.records: List[SourceRecord] = []
        self.match_results: Dict[str, PhotoMatchResult] = {}
        self.columns: List[str] = []
        self.column_mappings: Dict[str, str] = {}
        self.sample_index: int = 0
        self._updating_context_bar: bool = False
        self._user_adjusted_splitter: bool = False

        self._setup_ui()
        self._connect_signals()

    def _create_photoshop_menu_bar(self) -> QMenuBar:
        """Create standard Photoshop menu bar: File, Edit, Layer, Type, View, Window."""
        menubar = QMenuBar()
        menubar.setStyleSheet(
            "QMenuBar { background-color: #18181B; color: #E4E4E7; font-size: 12px; border-bottom: 1px solid #27272A; } "
            "QMenuBar::item { padding: 4px 10px; background: transparent; } "
            "QMenuBar::item:selected { background-color: #27272A; border-radius: 4px; } "
            "QMenu { background-color: #18181B; color: #E4E4E7; border: 1px solid #3F3F46; } "
            "QMenu::item { padding: 6px 24px; } "
            "QMenu::item:selected { background-color: #2563EB; color: #FFFFFF; } "
            "QMenu::separator { height: 1px; background: #3F3F46; margin: 4px 0; }"
        )

        # 1. File Menu
        file_menu = menubar.addMenu("&File")
        act_new = file_menu.addAction("New Canvas...")
        act_new.setShortcut(QKeySequence("Ctrl+N"))
        act_new.triggered.connect(self._create_blank_canvas_clicked)

        act_open = file_menu.addAction("Open Template File...")
        act_open.setShortcut(QKeySequence("Ctrl+O"))
        act_open.triggered.connect(self._open_template_file_clicked)

        file_menu.addSeparator()

        act_save = file_menu.addAction("Save Template")
        act_save.setShortcut(QKeySequence("Ctrl+S"))
        act_save.triggered.connect(self._save_template_clicked)

        act_dup = file_menu.addAction("Duplicate Template...")
        act_dup.triggered.connect(self._duplicate_template_clicked)

        act_import = file_menu.addAction("Import Template JSON...")
        act_import.triggered.connect(self._import_template_clicked)

        file_menu.addSeparator()

        act_preview = file_menu.addAction("Render 300 DPI Preview...")
        act_preview.triggered.connect(self._preview_card_clicked)

        file_menu.addSeparator()

        act_finalize = file_menu.addAction("Finalize & Proceed to Data Mapping ➔")
        act_finalize.triggered.connect(self.finalize_template)

        # 2. Edit Menu
        edit_menu = menubar.addMenu("&Edit")
        act_undo = edit_menu.addAction("Undo")
        act_undo.setShortcut(QKeySequence.Undo)
        act_undo.triggered.connect(self._trigger_undo)

        act_redo = edit_menu.addAction("Redo")
        act_redo.setShortcut(QKeySequence.Redo)
        act_redo.triggered.connect(self._trigger_redo)

        edit_menu.addSeparator()

        act_cut = edit_menu.addAction("Cut")
        act_cut.setShortcut(QKeySequence.Cut)
        act_cut.triggered.connect(self._cut_selected)

        act_copy = edit_menu.addAction("Copy")
        act_copy.setShortcut(QKeySequence.Copy)
        act_copy.triggered.connect(self._copy_selected)

        act_paste = edit_menu.addAction("Paste")
        act_paste.setShortcut(QKeySequence.Paste)
        act_paste.triggered.connect(self._paste_selected)

        act_del = edit_menu.addAction("Delete")
        act_del.setShortcut(QKeySequence.Delete)
        act_del.triggered.connect(self._delete_selected)

        edit_menu.addSeparator()

        act_sel_all = edit_menu.addAction("Select All")
        act_sel_all.setShortcut(QKeySequence.SelectAll)
        act_sel_all.triggered.connect(self._select_all_elements)

        act_desel = edit_menu.addAction("Deselect")
        act_desel.setShortcut(QKeySequence("Ctrl+D"))
        act_desel.triggered.connect(self._deselect_all)

        # 3. Layer Menu
        layer_menu = menubar.addMenu("&Layer")
        act_layer_text = layer_menu.addAction("New Text Layer")
        act_layer_text.triggered.connect(self._add_static_text)

        act_layer_dyn = layer_menu.addAction("New Dynamic Data Layer")
        act_layer_dyn.triggered.connect(self._add_dynamic_text)

        act_layer_photo = layer_menu.addAction("New Photo Placeholder Layer")
        act_layer_photo.triggered.connect(self._add_photo_element)

        act_layer_rect = layer_menu.addAction("New Rectangle Shape Layer")
        act_layer_rect.triggered.connect(self._add_rect_element)

        act_layer_img = layer_menu.addAction("New Image Layer...")
        act_layer_img.triggered.connect(self._add_image_element)

        layer_menu.addSeparator()

        act_front = layer_menu.addAction("Bring to Front")
        act_front.triggered.connect(self.layers_panel._bring_to_front)

        act_fwd = layer_menu.addAction("Bring Forward")
        act_fwd.triggered.connect(self.layers_panel._bring_forward)

        act_backw = layer_menu.addAction("Send Backward")
        act_backw.triggered.connect(self.layers_panel._send_backward)

        act_back = layer_menu.addAction("Send to Back")
        act_back.triggered.connect(self.layers_panel._send_to_back)

        layer_menu.addSeparator()

        act_lock = layer_menu.addAction("Lock / Unlock Layer")
        act_lock.triggered.connect(self._toggle_lock_selected)

        act_del_layer = layer_menu.addAction("Delete Layer")
        act_del_layer.triggered.connect(self._delete_selected)

        # 4. Type Menu
        type_menu = menubar.addMenu("&Type")
        act_t1 = type_menu.addAction("Add Static Text Label")
        act_t1.triggered.connect(self._add_static_text)

        act_t2 = type_menu.addAction("Add Dynamic Database Field")
        act_t2.triggered.connect(self._add_dynamic_text)

        # 5. View Menu
        view_menu = menubar.addMenu("&View")
        act_zin = view_menu.addAction("Zoom In")
        act_zin.setShortcut(QKeySequence("Ctrl++"))
        act_zin.triggered.connect(self.view.zoom_in)

        act_zout = view_menu.addAction("Zoom Out")
        act_zout.setShortcut(QKeySequence("Ctrl+-"))
        act_zout.triggered.connect(self.view.zoom_out)

        act_fit = view_menu.addAction("Fit Card on Screen")
        act_fit.setShortcut(QKeySequence("Ctrl+0"))
        act_fit.triggered.connect(self.view.fit_to_view)

        act_100 = view_menu.addAction("Actual Size (100%)")
        act_100.setShortcut(QKeySequence("Ctrl+1"))
        act_100.triggered.connect(self.view.reset_zoom)

        view_menu.addSeparator()

        act_ruler = view_menu.addAction("Toggle Rulers")
        act_ruler.triggered.connect(self._toggle_rulers)

        act_grid = view_menu.addAction("Toggle Grid")
        act_grid.triggered.connect(self._toggle_grid)

        act_snap = view_menu.addAction("Toggle Snap to Grid")
        act_snap.triggered.connect(self._toggle_snap)

        act_safe = view_menu.addAction("Toggle Safe Area Guides")
        act_safe.triggered.connect(self._toggle_safe_area)

        # 6. Window Menu
        window_menu = menubar.addMenu("&Window")
        act_win_layers = window_menu.addAction("Layers")
        act_win_layers.triggered.connect(lambda: self.right_tabs.setCurrentWidget(self.layers_panel))

        act_win_props = window_menu.addAction("Properties Inspector")
        act_win_props.triggered.connect(lambda: self.right_tabs.setCurrentWidget(self.inspector))

        act_win_swatch = window_menu.addAction("Color Swatches")
        act_win_swatch.triggered.connect(lambda: self.right_tabs.setCurrentWidget(self.swatches_panel))

        act_win_hist = window_menu.addAction("Action History")
        act_win_hist.triggered.connect(lambda: self.right_tabs.setCurrentWidget(self.history_panel))

        act_win_map = window_menu.addAction("Field Mapping")
        act_win_map.triggered.connect(lambda: self.right_tabs.setCurrentWidget(self.mapping_panel))

        window_menu.addSeparator()

        act_win_reset = window_menu.addAction("Reset Workspace Layout (70% Canvas)")
        act_win_reset.triggered.connect(lambda: self.apply_default_splitter_sizes(force=True))

        return menubar

    def _setup_ui(self) -> None:
        self.mode_stack = QStackedWidget(self)

        # =========================================================================
        # 1. TEMPLATE DESIGNER WORKSPACE (Mode 0 - Photoshop Inspired)
        # =========================================================================
        self.designer_container = QWidget()
        designer_layout = QVBoxLayout(self.designer_container)
        designer_layout.setContentsMargins(4, 4, 4, 4)
        designer_layout.setSpacing(4)

        # 1.0 Photoshop Classic Menu Bar
        self.menu_bar = self._create_photoshop_menu_bar()
        designer_layout.addWidget(self.menu_bar)

        # 1.1 Application and Document Header
        self.app_header_frame = QFrame()
        self.app_header_frame.setObjectName("card_panel")
        self.app_header_frame.setFixedHeight(48)
        hf_layout = QHBoxLayout(self.app_header_frame)
        hf_layout.setContentsMargins(10, 4, 10, 4)
        hf_layout.setSpacing(10)

        lbl_hdr_title = QLabel("<b>Template:</b>")
        lbl_hdr_title.setStyleSheet("font-size: 13px; color: #94A3B8;")
        hf_layout.addWidget(lbl_hdr_title)

        self.combo_active_template = QComboBox()
        self.combo_active_template.setMinimumWidth(240)
        self.combo_active_template.setStyleSheet(
            "QComboBox { font-weight: bold; font-size: 12px; padding: 4px 8px; }"
        )
        self.combo_active_template.currentIndexChanged.connect(self._on_combo_template_changed)
        hf_layout.addWidget(self.combo_active_template)

        self.lbl_app_template_name = QLabel("<b>Untitled Template</b>")
        self.lbl_app_template_name.setStyleSheet("font-size: 13px; color: #60CDFF; margin-left: 8px;")
        hf_layout.addWidget(self.lbl_app_template_name)

        hf_layout.addStretch()

        self.btn_new_canvas = QPushButton("+ Blank Canvas...")
        self.btn_new_canvas.clicked.connect(self._create_blank_canvas_clicked)
        hf_layout.addWidget(self.btn_new_canvas)

        self.btn_open_template = QPushButton("📂 Open...")
        self.btn_open_template.clicked.connect(self._open_template_file_clicked)
        hf_layout.addWidget(self.btn_open_template)

        self.btn_dup_template = QPushButton("🗐 Duplicate")
        self.btn_dup_template.clicked.connect(self._duplicate_template_clicked)
        hf_layout.addWidget(self.btn_dup_template)

        self.btn_save_template = QPushButton("💾 Save Template")
        self.btn_save_template.clicked.connect(self._save_template_clicked)
        hf_layout.addWidget(self.btn_save_template)

        self.btn_preview_pil = QPushButton("👁 Preview")
        self.btn_preview_pil.setToolTip("View authoritative Pillow 300 DPI card render preview")
        self.btn_preview_pil.clicked.connect(self._preview_card_clicked)
        hf_layout.addWidget(self.btn_preview_pil)

        self.btn_finalize_template = QPushButton("Finalize Template ➔")
        self.btn_finalize_template.setObjectName("btn_primary")
        self.btn_finalize_template.setStyleSheet(
            "font-weight: bold; font-size: 13px; padding: 6px 16px; background-color: #2563EB; color: white;"
        )
        self.btn_finalize_template.setToolTip("Validate design and proceed to Data Mapping Editor")
        self.btn_finalize_template.clicked.connect(self.finalize_template)
        hf_layout.addWidget(self.btn_finalize_template)

        designer_layout.addWidget(self.app_header_frame)

        # 1.2 Top Contextual Options Bar
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

        designer_layout.addWidget(self.options_bar)

        # 1.3 Editor Central Area: Left Vertical Toolbar + Center Canvas with Rulers + Right Panels
        editor_body = QHBoxLayout()
        editor_body.setSpacing(6)

        # Left Vertical Icon Toolbar (Photoshop inspired)
        self.tool_strip = self._create_vertical_tool_strip()
        editor_body.addWidget(self.tool_strip)

        # Resizable Splitter (Canvas 70% and Right Panels 30% by default)
        self.splitter = QSplitter(Qt.Horizontal)
        self.splitter.setHandleWidth(7)
        self.splitter.setChildrenCollapsible(False)
        self.canvas_container.setMinimumWidth(360)

        # Right Tabbed Dock (Photoshop Style Panels)
        self.right_tabs = QTabWidget()
        self.right_tabs.setMinimumWidth(280)
        self.right_tabs.addTab(self.layers_panel, "Layers")
        self.right_tabs.addTab(self.inspector, "Properties")
        self.right_tabs.addTab(self.swatches_panel, "Swatches")
        self.right_tabs.addTab(self.history_panel, "History")
        self.right_tabs.addTab(self.mapping_panel, "Data Mapping")

        self.splitter.addWidget(self.canvas_container)
        self.splitter.addWidget(self.right_tabs)

        self.splitter.setStretchFactor(0, 7)
        self.splitter.setStretchFactor(1, 3)
        self.splitter.setSizes([840, 360])
        self.splitter.splitterMoved.connect(self._on_splitter_moved)
        editor_body.addWidget(self.splitter, stretch=1)

        designer_layout.addLayout(editor_body, stretch=1)

        # 1.4 Bottom Status Bar Readout
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

        designer_layout.addWidget(self.status_bar_frame)

        # 1.5 Bottom Step Navigation Bar
        self.nav_bar = StepNavBar(
            prev_label="Choose Template",
            next_label="Batch Generate",
            step_badge="Step 3 of 7: Template Designer",
            parent=self,
        )
        self.nav_bar.back_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.TEMPLATES.value))
        self.nav_bar.next_requested.connect(lambda: self.navigate_requested.emit(WorkflowStep.GENERATE.value))
        designer_layout.addWidget(self.nav_bar)

        self.mode_stack.addWidget(self.designer_container)

        # =========================================================================
        # 2. STREAMLINED MAPPING WORKSPACE (Mode 1)
        # =========================================================================
        self.mapping_view = MappingEditorView(self)
        self.mapping_view.edit_template_requested.connect(self._return_to_designer)
        self.mapping_view.mappings_updated.connect(self._on_mapping_view_updated)
        self.mapping_view.navigate_requested.connect(lambda s: self.navigate_requested.emit(s))
        self.mode_stack.addWidget(self.mapping_view)

        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.mode_stack)

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
            ("marquee", "⬚", "Marquee Selection Tool (M)"),
            ("static_text", "T", "Horizontal Type / Text Tool (T)"),
            ("dynamic_text", "{T}", "Dynamic Field / Data Field Tool (D)"),
            ("photo", "📷", "Photo Tool / Profile Photo (P)"),
            ("image", "🖼", "Place Embedded Image / Logo (I)"),
            ("rect", "▭", "Rectangle Vector Shape (U)"),
            ("round_rect", "▢", "Rounded Rectangle Shape (R)"),
            ("line", "―", "Divider Line Tool (L)"),
            ("eyedropper", "💉", "Eyedropper Color Picker (E)"),
            ("hand", "✋", "Hand Pan Tool (H)"),
            ("zoom", "🔍", "Zoom In Tool (Z)"),
        ]

        for tool_id, icon_char, tooltip in tools:
            btn = QToolButton()
            btn.setText(icon_char)
            btn.setToolTip(tooltip)
            btn.setCheckable(True)
            btn.setFixedSize(40, 34)
            btn.setStyleSheet("font-size: 14px; font-weight: bold;")
            if tool_id == "select":
                btn.setChecked(True)
            btn.clicked.connect(lambda checked, tid=tool_id: self._on_tool_selected(tid))
            self.tool_group.addButton(btn)
            layout.addWidget(btn)

        layout.addSpacing(6)
        # Separator line
        sep = QFrame()
        sep.setFrameShape(QFrame.HLine)
        sep.setStyleSheet("color: #3F3F46;")
        layout.addWidget(sep)
        layout.addSpacing(6)

        # Photoshop Classic Overlapping Color Swatches
        color_box = QFrame()
        color_box.setFixedSize(42, 46)
        color_box.setStyleSheet("background: transparent;")

        self.btn_bg_color = QToolButton(color_box)
        self.btn_bg_color.setGeometry(16, 18, 22, 22)
        self.btn_bg_color.setStyleSheet("background-color: #FFFFFF; border: 1px solid #71717A; border-radius: 2px;")
        self.btn_bg_color.setToolTip("Background Color (Click to change)")
        self.btn_bg_color.clicked.connect(self._pick_bg_swatch_color)

        self.btn_fg_color = QToolButton(color_box)
        self.btn_fg_color.setGeometry(4, 6, 22, 22)
        self.btn_fg_color.setStyleSheet("background-color: #2563EB; border: 1px solid #FFFFFF; border-radius: 2px;")
        self.btn_fg_color.setToolTip("Foreground Color (Click to change)")
        self.btn_fg_color.clicked.connect(self._pick_fg_swatch_color)

        self.btn_swap_colors = QToolButton(color_box)
        self.btn_swap_colors.setGeometry(26, 0, 14, 14)
        self.btn_swap_colors.setText("⇄")
        self.btn_swap_colors.setStyleSheet("font-size: 10px; padding: 0; background: transparent; color: #94A3B8; border: none;")
        self.btn_swap_colors.setToolTip("Swap Foreground and Background Colors (X)")
        self.btn_swap_colors.clicked.connect(self._swap_swatch_colors)

        self.btn_default_bw = QToolButton(color_box)
        self.btn_default_bw.setGeometry(0, 30, 14, 14)
        self.btn_default_bw.setText("■")
        self.btn_default_bw.setStyleSheet("font-size: 8px; padding: 0; background: transparent; color: #94A3B8; border: none;")
        self.btn_default_bw.setToolTip("Reset Default Colors (Black & White, D)")
        self.btn_default_bw.clicked.connect(self._reset_default_colors)

        layout.addWidget(color_box)

        layout.addSpacing(6)
        # Separator line
        sep2 = QFrame()
        sep2.setFrameShape(QFrame.HLine)
        sep2.setStyleSheet("color: #3F3F46;")
        layout.addWidget(sep2)
        layout.addSpacing(6)

        # Quick Zoom & Fit actions
        btn_fit = QToolButton()
        btn_fit.setText("⛶")
        btn_fit.setToolTip("Fit Card to View")
        btn_fit.setFixedSize(40, 32)
        btn_fit.clicked.connect(self.view.fit_to_view)
        layout.addWidget(btn_fit)

        btn_100 = QToolButton()
        btn_100.setText("1:1")
        btn_100.setToolTip("Zoom 100%")
        btn_100.setFixedSize(40, 32)
        btn_100.clicked.connect(self.view.reset_zoom)
        layout.addWidget(btn_100)

        btn_reset_split = QToolButton()
        btn_reset_split.setText("70%")
        btn_reset_split.setToolTip("Reset Canvas Area to 70% Screen Width")
        btn_reset_split.setFixedSize(40, 32)
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

        layout.addSpacing(12)
        btn_zoom_in = QPushButton("+ Zoom")
        btn_zoom_in.clicked.connect(self.view.zoom_in)
        layout.addWidget(btn_zoom_in)

        btn_zoom_out = QPushButton("- Zoom")
        btn_zoom_out.clicked.connect(self.view.zoom_out)
        layout.addWidget(btn_zoom_out)

        layout.addStretch()
        return widget

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
        self.ctx_font_size.setRange(6, 200)
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

        # Cursor tracking on rulers
        self.view.cursor_moved.connect(self.canvas_container.update_cursor_pos)

        # Color swatches panel signal
        self.swatches_panel.color_selected.connect(self._on_swatch_color_selected)

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

    def load_template(self, template: TemplateDefinition) -> None:
        """Load template into canvas editor and update metadata readouts."""
        self.scene.load_template(template)
        self.layers_panel.refresh_layers()
        if hasattr(self, "lbl_app_template_name"):
            self.lbl_app_template_name.setText(f"<b>{template.name}</b>")
        self._populate_templates_dropdown()
        if hasattr(self, "canvas_container"):
            unit = template.unit or "mm"
            self.canvas_container.ruler_h.set_unit(unit, template.dpi)
            self.canvas_container.ruler_v.set_unit(unit, template.dpi)
            self.canvas_container.corner.unit = unit
            self.canvas_container.corner.update()
        if not self._user_adjusted_splitter:
            self.apply_default_splitter_sizes(force=False)
            QTimer.singleShot(20, lambda: self.apply_default_splitter_sizes(force=False))
        QTimer.singleShot(60, lambda: self.view.fit_to_view(enlarge_factor=1.35))
        self._update_status_dimensions()
        self._update_sample_preview()
        if hasattr(self, "mapping_view"):
            self.mapping_view.set_mapping_context(
                template=template,
                records=self.records,
                match_results=self.match_results,
                columns=self.columns,
                column_mappings=self.column_mappings,
            )

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
        if self.scene.template and hasattr(self, "mapping_view"):
            self.mapping_view.set_mapping_context(
                template=self.scene.template,
                records=records,
                match_results=match_results,
                columns=columns,
                column_mappings=self.column_mappings,
            )
        self.sample_index = 0
        self._update_sample_preview()

    def finalize_template(self) -> bool:
        """Validate and finalize template before advancing to data mapping."""
        if not self.scene.template:
            return False

        report = TemplateValidator.validate_for_finalization(self.scene.template)
        if not report.is_valid:
            err_msg = "\n• " + "\n• ".join(report.errors)
            QMessageBox.critical(
                self,
                "Template Finalization Failed",
                f"Cannot finalize template due to the following design issues:\n{err_msg}\n\nPlease correct these in the editor before continuing to data mapping.",
            )
            return False

        if report.warnings:
            logger.info("Template finalization notices: %s", report.warnings)

        # Save template to user templates directory
        try:
            from id_card_generator.templates.template_manager import TemplateManager
            mgr = TemplateManager()
            mgr.save_user_template(self.scene.template)
        except Exception as e:
            logger.warning("Could not persist template on finalization: %s", e)

        # Reconcile mappings: preserve surviving valid elements, prune deleted ones
        surviving_ids = {el.id for el in self.scene.template.elements}
        for eid in list(self.column_mappings.keys()):
            if eid not in surviving_ids:
                self.column_mappings.pop(eid, None)

        self.mapping_view.set_mapping_context(
            template=self.scene.template,
            records=self.records,
            match_results=self.match_results,
            columns=self.columns,
            column_mappings=self.column_mappings,
        )

        self.template_updated.emit(self.scene.template)
        self.mode_stack.setCurrentIndex(1)
        self.lbl_sb_status.setText("Template Finalized. Mapping Workspace Active.")
        return True

    def _return_to_designer(self) -> None:
        """Return from Mapping Editor to Template Designer, preserving valid bindings."""
        self.column_mappings.update(self.mapping_view.column_mappings)
        self.mode_stack.setCurrentIndex(0)
        self.lbl_sb_status.setText("Template Designer active.")

    def _on_mapping_view_updated(self, mappings: dict) -> None:
        self.column_mappings.update(mappings)
        self.mappings_updated.emit(self.column_mappings)

    def _create_blank_canvas_clicked(self) -> None:
        dialog = BlankCanvasDialog(self)
        if dialog.exec():
            tmpl = dialog.template_definition
            if tmpl:
                self.load_template(tmpl)
                self.template_updated.emit(tmpl)

    def _save_template_clicked(self) -> None:
        if not self.scene.template:
            return
        from id_card_generator.templates.template_manager import TemplateManager
        mgr = TemplateManager()
        saved_p = mgr.save_user_template(self.scene.template)
        QMessageBox.information(
            self,
            "Template Saved",
            f"Template '{self.scene.template.name}' saved successfully to:\n{saved_p.name}",
        )

    def _preview_card_clicked(self) -> None:
        if not self.scene.template:
            return
        curr_rec = self.records[self.sample_index] if (self.records and 0 <= self.sample_index < len(self.records)) else None
        photo_path = None
        if curr_rec:
            m = self.match_results.get(curr_rec.record_id)
            if m:
                photo_path = m.photo_path

        try:
            pil_img, warnings = PillowRenderer.render_card(
                template=self.scene.template,
                record=curr_rec,
                photo_path=photo_path,
                column_mappings=self.column_mappings,
                settings=RenderSettings(dpi=300),
            )
            dlg = QDialog(self)
            dlg.setWindowTitle(f"Pillow Render Preview — {self.scene.template.name} (300 DPI)")
            dlg.resize(720, 520)
            d_layout = QVBoxLayout(dlg)

            lbl = QLabel()
            lbl.setAlignment(Qt.AlignCenter)
            if pil_img.mode != "RGBA":
                pil_img = pil_img.convert("RGBA")
            qimg = QImage(pil_img.tobytes("raw", "RGBA"), pil_img.width, pil_img.height, QImage.Format_RGBA8888)
            pix = QPixmap.fromImage(qimg)
            lbl.setPixmap(pix.scaled(680, 440, Qt.KeepAspectRatio, Qt.SmoothTransformation))
            d_layout.addWidget(lbl, stretch=1)

            if warnings:
                lbl_warn = QLabel("Warnings:\n• " + "\n• ".join(warnings))
                lbl_warn.setStyleSheet("color: #F59E0B; font-size: 11px;")
                d_layout.addWidget(lbl_warn)

            btn_close = QPushButton("Close")
            btn_close.clicked.connect(dlg.accept)
            d_layout.addWidget(btn_close)
            dlg.exec()
        except Exception as e:
            QMessageBox.critical(self, "Preview Error", f"Failed to render preview: {e}")

    def _add_image_element(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Select Image or Logo", "", "Images (*.png *.jpg *.jpeg *.bmp *.webp *.svg)"
        )
        name = Path(file_path).stem if file_path else "Static Image"
        el = CanvasElement(
            name=name,
            type="image",
            x=60.0,
            y=60.0,
            width=140.0,
            height=70.0,
            static_content=file_path if file_path else "",
        )
        el.style.fit_mode = ImageFitMode.CONTAIN
        self.scene.add_element(el)
        self.layers_panel.refresh_layers()

    def _toggle_rulers(self) -> None:
        if hasattr(self, "canvas_container"):
            self.canvas_container.toggle_rulers()

    def _toggle_grid(self) -> None:
        self.scene.show_grid = not self.scene.show_grid
        self.scene.update()

    def _toggle_snap(self) -> None:
        self.scene.snap_to_grid = not self.scene.snap_to_grid

    def _toggle_safe_area(self) -> None:
        self.scene.show_safe_area = not self.scene.show_safe_area
        self.scene.update()

    def _populate_templates_dropdown(self) -> None:
        if not hasattr(self, "combo_active_template"):
            return
        from id_card_generator.templates.template_manager import TemplateManager
        mgr = TemplateManager()
        all_tmpls = mgr.list_templates()
        self.combo_active_template.blockSignals(True)
        self.combo_active_template.clear()
        current_id = self.scene.template.id if self.scene.template else ""
        sel_idx = 0
        for idx, t in enumerate(all_tmpls):
            is_built = mgr.is_builtin(t.id)
            tag = "Built-in" if is_built else "Custom"
            self.combo_active_template.addItem(f"{t.name} [{tag}]", t.id)
            if t.id == current_id or (self.scene.template and t.name == self.scene.template.name):
                sel_idx = idx
        if all_tmpls:
            self.combo_active_template.setCurrentIndex(sel_idx)
        self.combo_active_template.blockSignals(False)

    def _on_combo_template_changed(self, index: int) -> None:
        if index < 0 or not hasattr(self, "combo_active_template"):
            return
        tid = self.combo_active_template.itemData(index)
        if not tid:
            return
        if self.scene.template and self.scene.template.id == tid:
            return
        from id_card_generator.templates.template_manager import TemplateManager
        mgr = TemplateManager()
        t = mgr.get_template(tid)
        if t:
            self.load_template(t)
            self.template_updated.emit(t)

    def _open_template_file_clicked(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(
            self, "Open Template JSON File", "", "Template Files (*.json)"
        )
        if not file_path:
            return
        try:
            from id_card_generator.templates.template_manager import TemplateManager
            tmpl = TemplateManager.load_template_from_file(Path(file_path))
            self.load_template(tmpl)
            self.template_updated.emit(tmpl)
        except Exception as e:
            QMessageBox.critical(self, "Open Failed", f"Could not load template file:\n{e}")

    def _duplicate_template_clicked(self) -> None:
        if not self.scene.template:
            return
        new_name, ok = QInputDialog.getText(
            self, "Duplicate Template", "New Template Name:", text=f"{self.scene.template.name} Copy"
        )
        if ok and new_name.strip():
            data = self.scene.template.model_dump(mode="json")
            data["id"] = f"tmpl_{uuid4().hex[:8]}"
            data["name"] = new_name.strip()
            dup_tmpl = TemplateDefinition.model_validate(data)
            from id_card_generator.templates.template_manager import TemplateManager
            mgr = TemplateManager()
            mgr.save_user_template(dup_tmpl)
            self.load_template(dup_tmpl)
            self.template_updated.emit(dup_tmpl)

    def _import_template_clicked(self) -> None:
        self._open_template_file_clicked()

    def _pick_fg_swatch_color(self) -> None:
        col = QColorDialog.getColor(QColor(self.foreground_color), self, "Select Foreground Color")
        if col.isValid():
            self.foreground_color = col.name().upper()
            self.btn_fg_color.setStyleSheet(f"background-color: {self.foreground_color}; border: 1px solid #FFFFFF; border-radius: 2px;")
            self._apply_color_to_selected(self.foreground_color)

    def _pick_bg_swatch_color(self) -> None:
        col = QColorDialog.getColor(QColor(self.background_color), self, "Select Background Color")
        if col.isValid():
            self.background_color = col.name().upper()
            self.btn_bg_color.setStyleSheet(f"background-color: {self.background_color}; border: 1px solid #71717A; border-radius: 2px;")

    def _swap_swatch_colors(self) -> None:
        self.foreground_color, self.background_color = self.background_color, self.foreground_color
        self.btn_fg_color.setStyleSheet(f"background-color: {self.foreground_color}; border: 1px solid #FFFFFF; border-radius: 2px;")
        self.btn_bg_color.setStyleSheet(f"background-color: {self.background_color}; border: 1px solid #71717A; border-radius: 2px;")

    def _reset_default_colors(self) -> None:
        self.foreground_color = "#000000"
        self.background_color = "#FFFFFF"
        self.btn_fg_color.setStyleSheet(f"background-color: {self.foreground_color}; border: 1px solid #FFFFFF; border-radius: 2px;")
        self.btn_bg_color.setStyleSheet(f"background-color: {self.background_color}; border: 1px solid #71717A; border-radius: 2px;")

    def _on_swatch_color_selected(self, hex_color: str) -> None:
        self.foreground_color = hex_color.upper()
        self.btn_fg_color.setStyleSheet(f"background-color: {self.foreground_color}; border: 1px solid #FFFFFF; border-radius: 2px;")
        self._apply_color_to_selected(self.foreground_color)

    def _apply_color_to_selected(self, hex_color: str) -> None:
        selected = [it for it in self.scene.selectedItems() if isinstance(it, CanvasItem)]
        if not selected:
            return
        for it in selected:
            elem = it.element
            if elem.type in ("static_text", "dynamic_text", "pin_field"):
                self._apply_context_change(lambda x: setattr(x.element.style, "font_color", hex_color), "Change Font Color")
            elif elem.type in ("rect", "round_rect"):
                self._apply_context_change(lambda x: setattr(x.element.style, "background_color", hex_color), "Change Fill Color")
            elif elem.type == "line":
                self._apply_context_change(lambda x: setattr(x.element.style, "border_color", hex_color), "Change Line Color")

    def _pick_canvas_color(self) -> None:
        col = QColorDialog.getColor(QColor(self.foreground_color), self, "Eyedropper - Pick Color")
        if col.isValid():
            self._on_swatch_color_selected(col.name().upper())

    def _reset_to_select_tool(self) -> None:
        self.view.setDragMode(QGraphicsView.RubberBandDrag)
        for btn in self.tool_group.buttons():
            if btn.text() == "↖":
                btn.setChecked(True)
                break

    def _cut_selected(self) -> None:
        self._copy_selected()
        self._delete_selected()

    def _copy_selected(self) -> None:
        selected = [it for it in self.scene.selectedItems() if isinstance(it, CanvasItem)]
        if not selected:
            return
        data = [it.element.model_dump(mode="json") for it in selected]
        QApplication.clipboard().setText(json.dumps(data))

    def _paste_selected(self) -> None:
        text = QApplication.clipboard().text()
        if not text:
            return
        try:
            raw_items = json.loads(text)
            if not isinstance(raw_items, list):
                return
            for raw in raw_items:
                raw["id"] = f"el_{uuid4().hex[:8]}"
                raw["x"] = raw.get("x", 50) + 20
                raw["y"] = raw.get("y", 50) + 20
                el = CanvasElement.model_validate(raw)
                self.scene.add_element(el)
            self.layers_panel.refresh_layers()
            self._on_template_modified()
        except Exception as e:
            logger.warning("Paste failed: %s", e)

    def _delete_selected(self) -> None:
        selected = [it for it in self.scene.selectedItems() if isinstance(it, CanvasItem)]
        for it in selected:
            self.scene.remove_element(it.element.id)
        self.layers_panel.refresh_layers()
        self._on_template_modified()

    def _select_all_elements(self) -> None:
        for item in self.scene.items():
            if isinstance(item, CanvasItem):
                item.setSelected(True)

    def _deselect_all(self) -> None:
        self.scene.clearSelection()

    def _toggle_lock_selected(self) -> None:
        selected = [it for it in self.scene.selectedItems() if isinstance(it, CanvasItem)]
        if not selected:
            return
        is_locked = any(it.element.locked for it in selected)
        for it in selected:
            it.element.locked = not is_locked
            it.setFlag(QGraphicsItem.ItemIsMovable, not it.element.locked)
            it.setFlag(QGraphicsItem.ItemIsSelectable, True)
        self.layers_panel.refresh_layers()
        self._on_template_modified()

    def _on_tool_selected(self, tool_id: str) -> None:
        if tool_id == "select":
            self.view.setDragMode(QGraphicsView.RubberBandDrag)
            return
        elif tool_id == "marquee":
            self.view.setDragMode(QGraphicsView.RubberBandDrag)
            return
        elif tool_id == "hand":
            self.view.setDragMode(QGraphicsView.ScrollHandDrag)
            return
        elif tool_id == "zoom":
            self.view.zoom_in()
            self._reset_to_select_tool()
            return
        elif tool_id == "eyedropper":
            self._pick_canvas_color()
            self._reset_to_select_tool()
            return
        elif tool_id == "static_text":
            self._add_static_text()
        elif tool_id == "dynamic_text":
            self._add_dynamic_text()
        elif tool_id == "photo":
            self._add_photo_element()
        elif tool_id == "image":
            self._add_image_element()
        elif tool_id == "rect":
            self._add_rect_element()
        elif tool_id == "round_rect":
            self._add_round_rect_element()
        elif tool_id == "line":
            self._add_line_element()

        self._reset_to_select_tool()

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
            self.ctx_font_family.setCurrentFont(elem.style.font_family)
            self.ctx_font_size.setValue(int(elem.style.font_size))
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
        self._apply_context_change(lambda it: setattr(it.element.style, "font_size", sz), "Change Font Size")

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
            width=240.0,
            height=36.0,
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
