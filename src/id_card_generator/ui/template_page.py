"""Template selection, visual canvas preview, property editing, importing, duplication, and management page."""

import logging
from pathlib import Path
from typing import Dict, List, Optional
from PIL import Image
from PySide6.QtCore import QSize, Qt, Signal
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QAbstractItemView,
    QColorDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListView,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSplitter,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.constants import WorkflowStep
from id_card_generator.core.geometry import convert_unit
from id_card_generator.core.models import (
    RenderSettings,
    SourceRecord,
    TemplateDefinition,
)
from id_card_generator.rendering.pillow_renderer import PillowRenderer
from id_card_generator.templates.template_manager import TemplateManager
from id_card_generator.ui.dialogs.blank_canvas_dialog import (
    BlankCanvasDialog,
    CanvasPropertiesDialog,
)
from id_card_generator.ui.dialogs.template_cleanup_dialog import TemplateCleanupDialog
from id_card_generator.ui import workflow
from id_card_generator.ui.components.page_scaffold import InlineNotice, PageFooter, PageHeader
from id_card_generator.ui.components.spec_list import SpecList
from id_card_generator.ui.components.template_gallery import (
    TemplateGalleryDelegate,
    pil_to_qimage,
)
from id_card_generator.ui.studio_tokens import (
    BORDER_DEFAULT,
    SIZES,
    FONT_FAMILY_MONO,
    PRIMARY,
    SEMANTIC_ERROR,
    SURFACE,
    SURFACE_CONTAINER,
    SURFACE_HIGH,
    SURFACE_LOW,
    SURFACE_LOWEST,
    TEXT_MUTED,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

logger = logging.getLogger(__name__)

# Every control in the page uses the same height as the rest of the app.
CONTROL_HEIGHT = SIZES.CONTROL_HEIGHT


class CanvasPreviewCard(QFrame):
    """Visual preview card container that renders and responsively scales ID card canvas."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("card_panel")
        self._original_pixmap: Optional[QPixmap] = None

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(10)

        # Header bar
        header = QHBoxLayout()
        self.lbl_header = QLabel("Preview")
        self.lbl_header.setProperty("role", "sectionLabel")
        header.addWidget(self.lbl_header)

        self.lbl_badge = QLabel("")
        self.lbl_badge.setProperty("role", "badgeMuted")
        header.addWidget(self.lbl_badge)
        header.addStretch()

        self.btn_refresh = QToolButton()
        self.btn_refresh.setText("⟳")
        self.btn_refresh.setObjectName("btn_ghost")
        self.btn_refresh.setFixedSize(CONTROL_HEIGHT, CONTROL_HEIGHT)
        self.btn_refresh.setToolTip("Re-render the preview")
        header.addWidget(self.btn_refresh)
        layout.addLayout(header)

        # Center card container
        self.image_container = QFrame()
        self.image_container.setStyleSheet(
            "background-color: #0F172A; border-radius: 8px; border: 1px solid #1E293B;"
        )
        container_layout = QVBoxLayout(self.image_container)
        container_layout.setContentsMargins(16, 16, 16, 16)
        container_layout.setAlignment(Qt.AlignCenter)

        self.lbl_image = QLabel("No template selected")
        self.lbl_image.setAlignment(Qt.AlignCenter)
        self.lbl_image.setStyleSheet("color: #64748B; font-size: 13px;")
        container_layout.addWidget(self.lbl_image)

        layout.addWidget(self.image_container, stretch=1)

    def set_preview(self, pixmap: Optional[QPixmap], specs_text: str = "") -> None:
        self._original_pixmap = pixmap
        if specs_text:
            self.lbl_badge.setText(specs_text)
            self.lbl_badge.setVisible(True)
        else:
            self.lbl_badge.setVisible(False)
        self._update_scaled_pixmap()

    def _update_scaled_pixmap(self) -> None:
        if not self._original_pixmap or self._original_pixmap.isNull():
            self.lbl_image.setPixmap(QPixmap())
            self.lbl_image.setText("No template preview available")
            return

        avail_w = max(100, self.image_container.width() - 36)
        avail_h = max(100, self.image_container.height() - 36)

        scaled = self._original_pixmap.scaled(
            avail_w,
            avail_h,
            Qt.KeepAspectRatio,
            Qt.SmoothTransformation,
        )
        self.lbl_image.setPixmap(scaled)
        self.lbl_image.setText("")

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._update_scaled_pixmap()


class TemplatePage(QWidget):
    """Template manager interface for choosing, previewing, property-editing, importing, duplicating, and exporting templates."""

    template_selected = Signal(object)  # TemplateDefinition
    open_editor_requested = Signal()
    navigate_requested = Signal(str)  # WorkflowStep value

    def __init__(self, parent=None):
        super().__init__(parent)
        self.manager = TemplateManager()
        self.active_template: Optional[TemplateDefinition] = None
        self.sample_record: Optional[SourceRecord] = None

        self._current_bg_color = "#FFFFFF"
        self._current_bg_image_path: Optional[str] = None
        self._updating_ui = False
        self._dirty = False
        # Rendered gallery thumbnails, keyed by template id.
        self._thumbnail_cache: Dict[str, Optional[QPixmap]] = {}

        self._setup_ui()
        self._load_templates()

    def set_sample_record(self, record: Optional[SourceRecord] = None) -> None:
        """Set sample data record for rendering realistic card preview."""
        self.sample_record = record
        if self.active_template:
            self._update_preview(self.active_template)

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ---------------------------------------------------------
        # Page header
        # ---------------------------------------------------------
        badge, title, subtitle = workflow.page_header_text(WorkflowStep.TEMPLATES)
        self.page_header = PageHeader(title, subtitle, badge)
        layout.addWidget(self.page_header)

        self.notice = InlineNotice()
        notice_row = QHBoxLayout()
        notice_row.setContentsMargins(16, 8, 16, 0)
        notice_row.addWidget(self.notice)
        layout.addLayout(notice_row)

        body = QVBoxLayout()
        body.setContentsMargins(16, 12, 16, 12)
        body.setSpacing(12)
        layout.addLayout(body, stretch=1)

        # One primary action, everything else lives in the overflow menu.
        self.btn_blank = QPushButton("+  New template")
        self.btn_blank.setObjectName("btn_primary")
        self.btn_blank.clicked.connect(self._create_blank_canvas)
        self.page_header.add_action(self.btn_blank)

        self.btn_import = QPushButton("Import Template JSON...")
        self.btn_import.clicked.connect(self._import_template)
        self.page_header.add_action(self.btn_import)

        self.btn_cleanup = QPushButton("🧹 Clean Up...")
        self.btn_cleanup.setToolTip(
            "Open template cleanup manager to search, delete, and clean up older saved templates"
        )
        self.btn_cleanup.clicked.connect(self._open_cleanup_dialog)
        self.page_header.add_action(self.btn_cleanup)

        # ---------------------------------------------------------
        # Gallery | Preview | Details
        # ---------------------------------------------------------
        main_splitter = QSplitter(Qt.Horizontal)
        main_splitter.setChildrenCollapsible(False)

        # --- Left: the gallery -------------------------------------
        gallery_panel = QFrame()
        gallery_layout = QVBoxLayout(gallery_panel)
        gallery_layout.setContentsMargins(0, 0, 8, 0)
        gallery_layout.setSpacing(10)

        self.txt_filter = QLineEdit()
        self.txt_filter.setPlaceholderText("Filter templates...")
        self.txt_filter.setClearButtonEnabled(True)
        self.txt_filter.setFixedHeight(CONTROL_HEIGHT)
        self.txt_filter.textChanged.connect(self._filter_template_list)
        gallery_layout.addWidget(self.txt_filter)

        self.list_widget = QListWidget()
        self.list_widget.setViewMode(QListView.IconMode)
        self.list_widget.setFlow(QListView.LeftToRight)
        self.list_widget.setWrapping(True)
        self.list_widget.setResizeMode(QListView.Adjust)
        self.list_widget.setMovement(QListView.Static)
        self.list_widget.setSpacing(4)
        self.list_widget.setUniformItemSizes(True)
        self.list_widget.setIconSize(QSize(1, 1))
        self.list_widget.setSelectionMode(QAbstractItemView.SingleSelection)
        self.list_widget.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.list_widget.setVerticalScrollMode(QAbstractItemView.ScrollPerPixel)
        self.list_widget.currentItemChanged.connect(self._on_item_changed)
        self.list_widget.itemDoubleClicked.connect(self._on_item_double_clicked)
        self._gallery_delegate = TemplateGalleryDelegate(
            thumbnail_provider=self._template_thumbnail,
            is_builtin_provider=self.manager.is_builtin,
        )
        self.list_widget.setItemDelegate(self._gallery_delegate)
        gallery_layout.addWidget(self.list_widget, stretch=1)

        main_splitter.addWidget(gallery_panel)

        # --- Center: the preview ------------------------------------
        self.preview_card = CanvasPreviewCard()
        self.preview_card.btn_refresh.clicked.connect(self._refresh_current_preview)
        main_splitter.addWidget(self.preview_card)

        # --- Right: the details -------------------------------------
        self.detail_card = QFrame()
        self.detail_card.setObjectName("card_panel")
        detail_layout = QVBoxLayout(self.detail_card)
        detail_layout.setContentsMargins(18, 16, 18, 16)
        detail_layout.setSpacing(14)

        # Title + type tag
        title_row = QHBoxLayout()
        title_row.setSpacing(8)
        self.lbl_tmpl_title = QLabel("Select a template")
        self.lbl_tmpl_title.setProperty("role", "pageTitle")
        title_row.addWidget(self.lbl_tmpl_title)
        title_row.addStretch()

        self.lbl_tmpl_badge = QLabel("")
        self.lbl_tmpl_badge.setProperty("role", "badgeAccent")
        title_row.addWidget(self.lbl_tmpl_badge)
        detail_layout.addLayout(title_row)

        # --- Identity (inline editing, no group boxes) ---------------
        self.lbl_identity_head = QLabel("IDENTITY")
        self.lbl_identity_head.setProperty("role", "sectionLabel")
        detail_layout.addWidget(self.lbl_identity_head)

        self.txt_tmpl_name = QLineEdit()
        self.txt_tmpl_name.setPlaceholderText("Template name")
        self.txt_tmpl_name.setFixedHeight(CONTROL_HEIGHT)
        self.txt_tmpl_name.setProperty("role", "fieldFlat")
        self.txt_tmpl_name.textChanged.connect(self._on_inline_name_changed)
        detail_layout.addWidget(self.txt_tmpl_name)

        self.txt_tmpl_desc = QLineEdit()
        self.txt_tmpl_desc.setPlaceholderText("Short description")
        self.txt_tmpl_desc.setFixedHeight(CONTROL_HEIGHT)
        self.txt_tmpl_desc.setProperty("role", "fieldFlat")
        self.txt_tmpl_desc.textChanged.connect(self._on_inline_desc_changed)
        detail_layout.addWidget(self.txt_tmpl_desc)

        # The save action only appears when something was edited.
        self.btn_save_prop = QPushButton("Save changes")
        self.btn_save_prop.setObjectName("btn_ghost")
        self.btn_save_prop.setFixedHeight(CONTROL_HEIGHT)
        self.btn_save_prop.setToolTip("Save the edited name, description and background")
        self.btn_save_prop.clicked.connect(self._save_inline_properties)
        self.btn_save_prop.setVisible(False)
        detail_layout.addWidget(self.btn_save_prop)

        detail_layout.addWidget(self._separator())

        # --- Specifications -----------------------------------------
        self.lbl_specs_head = QLabel("SPECIFICATIONS")
        self.lbl_specs_head.setProperty("role", "sectionLabel")
        detail_layout.addWidget(self.lbl_specs_head)

        self.spec_list = SpecList()
        detail_layout.addWidget(self.spec_list)

        detail_layout.addWidget(self._separator())

        # --- Surface ------------------------------------------------
        self.lbl_surface_head = QLabel("SURFACE")
        self.lbl_surface_head.setProperty("role", "sectionLabel")
        detail_layout.addWidget(self.lbl_surface_head)

        color_row = QHBoxLayout()
        color_row.setSpacing(10)
        self.btn_prop_bg_color = QToolButton()
        self.btn_prop_bg_color.setFixedSize(26, 26)
        self.btn_prop_bg_color.setToolTip("Select Card Background Color")
        self.btn_prop_bg_color.clicked.connect(self._pick_prop_color)
        color_row.addWidget(self.btn_prop_bg_color)

        self.lbl_prop_bg_hex = QLabel("#FFFFFF")
        self.lbl_prop_bg_hex.setProperty("role", "monoMuted")
        color_row.addWidget(self.lbl_prop_bg_hex)
        color_row.addStretch()

        btn_change_col = QPushButton("Change")
        btn_change_col.setFixedHeight(CONTROL_HEIGHT)
        btn_change_col.clicked.connect(self._pick_prop_color)
        color_row.addWidget(btn_change_col)
        detail_layout.addLayout(color_row)

        img_row = QHBoxLayout()
        img_row.setSpacing(10)
        self.lbl_prop_bg_img = QLabel("No background image")
        self.lbl_prop_bg_img.setProperty("role", "pageSubtitle")
        img_row.addWidget(self.lbl_prop_bg_img)
        img_row.addStretch()

        btn_browse_bg = QPushButton("Browse...")
        btn_browse_bg.setFixedHeight(CONTROL_HEIGHT)
        btn_browse_bg.clicked.connect(self._browse_prop_image)
        img_row.addWidget(btn_browse_bg)

        btn_clear_bg = QPushButton("Clear")
        btn_clear_bg.setFixedHeight(CONTROL_HEIGHT)
        btn_clear_bg.clicked.connect(self._clear_prop_image)
        img_row.addWidget(btn_clear_bg)
        detail_layout.addLayout(img_row)

        detail_layout.addStretch(1)

        # --- Actions ------------------------------------------------
        self.btn_use = QPushButton("Use this template")
        self.btn_use.setObjectName("btn_primary")
        self.btn_use.setFixedHeight(34)
        self.btn_use.clicked.connect(self._use_template)
        detail_layout.addWidget(self.btn_use)

        self.btn_edit = QPushButton("Open in Designer")
        self.btn_edit.setObjectName("btn_secondary")
        self.btn_edit.setFixedHeight(CONTROL_HEIGHT)
        self.btn_edit.clicked.connect(lambda: self.open_editor_requested.emit())
        detail_layout.addWidget(self.btn_edit)

        # Everything secondary lives in the overflow menu.
        self.btn_more = QToolButton()
        self.btn_more.setText("\u22EF")
        self.btn_more.setObjectName("btn_ghost")
        self.btn_more.setFixedSize(CONTROL_HEIGHT, CONTROL_HEIGHT)
        self.btn_more.setToolTip("More actions")
        self.btn_more.setPopupMode(QToolButton.InstantPopup)
        more_menu = QMenu(self.btn_more)
        self._act_edit_specs = more_menu.addAction("Card size & DPI...")
        self._act_edit_specs.triggered.connect(lambda: self._edit_canvas_properties())
        self._act_dup = more_menu.addAction("Duplicate")
        self._act_dup.triggered.connect(self._duplicate_template)
        self._act_export = more_menu.addAction("Export JSON")
        self._act_export.triggered.connect(self._export_template)
        more_menu.addSeparator()
        self._act_delete = more_menu.addAction("Delete custom template")
        self._act_delete.triggered.connect(self._delete_template)
        self.btn_more.setMenu(more_menu)
        detail_layout.addWidget(self.btn_more, 0, Qt.AlignRight)

        # The legacy buttons stay available for the existing API.
        self.btn_edit_specs = QPushButton("Card size & DPI...")
        self.btn_edit_specs.setFixedHeight(CONTROL_HEIGHT)
        self.btn_edit_specs.clicked.connect(lambda: self._edit_canvas_properties())
        self.btn_edit_specs.setVisible(False)
        detail_layout.addWidget(self.btn_edit_specs)

        self.btn_dup = QPushButton("Duplicate")
        self.btn_dup.clicked.connect(self._duplicate_template)
        self.btn_dup.setVisible(False)
        detail_layout.addWidget(self.btn_dup)

        self.btn_export = QPushButton("Export JSON")
        self.btn_export.clicked.connect(self._export_template)
        self.btn_export.setVisible(False)
        detail_layout.addWidget(self.btn_export)

        self.btn_delete = QPushButton("Delete Custom")
        self.btn_delete.setObjectName("btn_danger")
        self.btn_delete.clicked.connect(self._delete_template)
        self.btn_delete.setVisible(False)
        detail_layout.addWidget(self.btn_delete)

        main_splitter.addWidget(self.detail_card)

        main_splitter.setStretchFactor(0, 2)
        main_splitter.setStretchFactor(1, 4)
        main_splitter.setStretchFactor(2, 2)
        main_splitter.setSizes([360, 580, 340])
        body.addWidget(main_splitter, stretch=1)

        # ---------------------------------------------------------
        # Bottom Step Navigation Bar
        # ---------------------------------------------------------
        back_label, next_label, badge = workflow.footer_labels(WorkflowStep.TEMPLATES)
        self.nav_bar = PageFooter(
            prev_label=back_label,
            next_label=next_label,
            step_badge=badge,
            parent=self,
        )
        self.nav_bar.back_requested.connect(
            lambda: self.navigate_requested.emit(WorkflowStep.PHOTOS.value)
        )
        self.nav_bar.next_requested.connect(
            lambda: self.navigate_requested.emit(WorkflowStep.CANVAS_EDITOR.value)
        )
        layout.addWidget(self.nav_bar)

    @staticmethod
    def _separator() -> QFrame:
        """A thin hairline between the sections of the details rail."""
        line = QFrame()
        line.setFixedHeight(1)
        line.setStyleSheet(f"background-color: {BORDER_DEFAULT};")
        return line

    def _template_thumbnail(self, template_id: str) -> Optional[QPixmap]:
        """Return (and cache) the thumbnail of a template."""
        if not template_id:
            return None
        if template_id in self._thumbnail_cache:
            return self._thumbnail_cache[template_id]

        tmpl = self.manager.get_template(template_id)
        if not tmpl:
            return None

        pixmap = None
        try:
            image, _ = PillowRenderer.render_card(
                template=tmpl,
                record=self.sample_record,
                photo_path=None,
                column_mappings={},
                settings=RenderSettings(),
            )
            pixmap = QPixmap.fromImage(pil_to_qimage(image))
        except Exception as exc:  # pragma: no cover - defensive
            logger.debug("Could not render the thumbnail of %s: %s", tmpl.name, exc)
            pixmap = None

        self._thumbnail_cache[template_id] = pixmap
        return pixmap

    def _load_templates(self) -> None:
        self.manager.reload()
        self.list_widget.clear()
        templates = self.manager.list_templates()

        for tmpl in templates:
            item = QListWidgetItem(tmpl.name)
            item.setData(Qt.UserRole, tmpl.id)
            item.setSizeHint(QSize(164, 168))
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def _on_item_changed(self, current: Optional[QListWidgetItem], previous=None) -> None:
        if not current:
            return
        tmpl_id = current.data(Qt.UserRole)
        tmpl = self.manager.get_template(tmpl_id)
        if not tmpl:
            return

        self._updating_ui = True
        self.active_template = tmpl
        is_built = self.manager.is_builtin(tmpl.id)

        self.lbl_tmpl_title.setText(tmpl.name)
        self.lbl_tmpl_badge.setText("Built-in" if is_built else "Custom Saved")
        self.txt_tmpl_name.setText(tmpl.name)
        self.txt_tmpl_name.setCursorPosition(0)
        self.txt_tmpl_desc.setText(tmpl.description or "")
        self.txt_tmpl_desc.setCursorPosition(0)

        # Compute physical dimensions readout
        unit = tmpl.unit or "mm"
        if tmpl.width_physical and tmpl.height_physical:
            w_phys = tmpl.width_physical
            h_phys = tmpl.height_physical
        else:
            w_mm = tmpl.width_px / tmpl.dpi * 25.4
            h_mm = tmpl.height_px / tmpl.dpi * 25.4
            w_phys = convert_unit(w_mm, "mm", unit)
            h_phys = convert_unit(h_mm, "mm", unit)

        orient = tmpl.orientation.title() if tmpl.orientation else ("Landscape" if tmpl.is_landscape else "Portrait")
        element_summary = f"{len(tmpl.elements)} elements"

        self.spec_list.set_rows([
            ("Size", f"{w_phys:.2f} × {h_phys:.2f} {unit}"),
            ("Pixels", f"{tmpl.width_px} × {tmpl.height_px} px"),
            ("Print", f"{tmpl.dpi} DPI"),
            ("Orientation", orient),
            ("Elements", element_summary),
        ])

        # Background color & image
        self._current_bg_color = tmpl.background_color or "#FFFFFF"
        self._update_prop_color_btn()

        self._current_bg_image_path = tmpl.background_image_path
        if tmpl.background_image_path:
            self.lbl_prop_bg_img.setText(Path(tmpl.background_image_path).name)
        else:
            self.lbl_prop_bg_img.setText("No background image")

        self.btn_delete.setEnabled(not is_built)
        self._act_delete.setEnabled(not is_built)
        self._set_dirty(False)
        self._updating_ui = False

        # Live Canvas Preview
        self._update_preview(tmpl)

    def _on_item_double_clicked(self, item: QListWidgetItem) -> None:
        """Double clicking a template item directly opens the canvas property editor dialog."""
        tmpl_id = item.data(Qt.UserRole)
        tmpl = self.manager.get_template(tmpl_id)
        if tmpl:
            self._edit_canvas_properties(tmpl)

    def _on_inline_name_changed(self, text: str) -> None:
        """Keep the heading in sync while the name is edited."""
        if not self._updating_ui:
            self.lbl_tmpl_title.setText(text.strip() or "Untitled Template")
            self._set_dirty(True)

    def _on_inline_desc_changed(self, text: str) -> None:
        """Mark the template as changed when the description is edited."""
        if not self._updating_ui:
            self._set_dirty(True)

    def _set_dirty(self, dirty: bool) -> None:
        """Show the save action only when something was actually edited."""
        self._dirty = dirty
        self.btn_save_prop.setVisible(dirty)
        self.btn_save_prop.setEnabled(dirty and self.active_template is not None)

    def _pick_prop_color(self) -> None:
        col = QColorDialog.getColor(QColor(self._current_bg_color), self, "Select Card Background Color")
        if col.isValid():
            self._current_bg_color = col.name().upper()
            self._update_prop_color_btn()
            self._set_dirty(True)
            # Live-preview the change immediately
            if self.active_template:
                temp_preview = self.active_template.model_copy(deep=True)
                temp_preview.background_color = self._current_bg_color
                temp_preview.background_image_path = self._current_bg_image_path
                self._update_preview(temp_preview)

    def _update_prop_color_btn(self) -> None:
        c = QColor(self._current_bg_color) if self._current_bg_color else QColor("#FFFFFF")
        pix = QPixmap(22, 22)
        pix.fill(Qt.transparent)
        p = QPainter(pix)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setBrush(c)
        p.setPen(QPen(QColor("#52525B"), 1))
        p.drawRoundedRect(1, 1, 20, 20, 3, 3)
        p.end()
        self.btn_prop_bg_color.setIcon(QIcon(pix))
        self.btn_prop_bg_color.setIconSize(QSize(22, 22))
        self.btn_prop_bg_color.setStyleSheet("""
            QToolButton {
                background-color: #202023;
                border: 1px solid #3F3F46;
                border-radius: 4px;
            }
            QToolButton:hover {
                border-color: #52525B;
                background-color: #2A2A2E;
            }
        """)
        self.lbl_prop_bg_hex.setText(self._current_bg_color)

    def _browse_prop_image(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self,
            "Select Background Image",
            "",
            "Image Files (*.png *.jpg *.jpeg *.bmp *.webp)",
        )
        if path:
            self._current_bg_image_path = path
            self.lbl_prop_bg_img.setText(Path(path).name)
            if self.active_template:
                temp_preview = self.active_template.model_copy(deep=True)
                temp_preview.background_color = self._current_bg_color
                temp_preview.background_image_path = self._current_bg_image_path
                self._update_preview(temp_preview)

    def _clear_prop_image(self) -> None:
        self._current_bg_image_path = None
        self.lbl_prop_bg_img.setText("(None)")
        if self.active_template:
            temp_preview = self.active_template.model_copy(deep=True)
            temp_preview.background_color = self._current_bg_color
            temp_preview.background_image_path = None
            self._update_preview(temp_preview)

    def _save_inline_properties(self) -> None:
        """Save inline canvas property edits (name, description, background) to template."""
        if not self.active_template:
            return

        updated = self.active_template.model_copy(deep=True)
        updated.name = self.txt_tmpl_name.text().strip() or updated.name
        updated.description = self.txt_tmpl_desc.text().strip()
        updated.background_color = self._current_bg_color
        updated.background_image_path = self._current_bg_image_path

        if self.manager.is_builtin(updated.id) and not updated.name.endswith("(Custom)"):
            updated.name = f"{updated.name} (Custom)"

        self.manager.save_user_template(updated)
        self._load_templates()

        for idx in range(self.list_widget.count()):
            it = self.list_widget.item(idx)
            if it.data(Qt.UserRole) == updated.id:
                self.list_widget.setCurrentItem(it)
                break

        self.template_selected.emit(updated)
        self._set_dirty(False)
        self.notice.set_message(
            f"Canvas properties for '{updated.name}' have been saved.", severity="success"
        )

    def _edit_canvas_properties(self, tmpl: Optional[TemplateDefinition] = None) -> None:
        """Open full modal dialog to edit canvas physical dimensions, DPI, orientation, and background."""
        target = tmpl or self.active_template
        if not target:
            return

        dialog = CanvasPropertiesDialog(self, existing_template=target)
        if dialog.exec():
            updated = dialog.template_definition
            if updated:
                if self.manager.is_builtin(updated.id) and not updated.name.endswith("(Custom)"):
                    updated.name = f"{updated.name} (Custom)"

                self.manager.save_user_template(updated)
                self._load_templates()

                # Re-select the updated template
                for idx in range(self.list_widget.count()):
                    it = self.list_widget.item(idx)
                    if it.data(Qt.UserRole) == updated.id:
                        self.list_widget.setCurrentItem(it)
                        break

                self.template_selected.emit(updated)
                self.notice.set_message(
                    f"Canvas properties for '{updated.name}' updated successfully.",
                    severity="success",
                )

    def _update_preview(self, tmpl: TemplateDefinition) -> None:
        """Render high quality ID card canvas preview using PillowRenderer."""
        try:
            pil_img, _ = PillowRenderer.render_card(
                template=tmpl,
                record=self.sample_record,
            )
            if pil_img.mode != "RGBA":
                pil_img = pil_img.convert("RGBA")
            data = pil_img.tobytes("raw", "RGBA")
            qimg = QImage(data, pil_img.width, pil_img.height, QImage.Format_RGBA8888)
            pix = QPixmap.fromImage(qimg.copy())

            unit = tmpl.unit or "mm"
            if tmpl.width_physical and tmpl.height_physical:
                w_str = f"{tmpl.width_physical:.1f} × {tmpl.height_physical:.1f} {unit}"
            else:
                w_mm = tmpl.width_px / tmpl.dpi * 25.4
                h_mm = tmpl.height_px / tmpl.dpi * 25.4
                w_str = f"{w_mm:.1f} × {h_mm:.1f} mm"

            orient_icon = "↔" if tmpl.is_landscape else "↕"
            specs_badge = f"{w_str} ({tmpl.width_px}×{tmpl.height_px} px) @ {tmpl.dpi} DPI {orient_icon}"

            self.preview_card.set_preview(pix, specs_badge)
        except Exception as e:
            logger.error("Failed to render preview for template %s: %s", tmpl.name, e)
            self.preview_card.set_preview(None, "")

    def _refresh_current_preview(self) -> None:
        if self.active_template:
            self._update_preview(self.active_template)

    def _use_template(self) -> None:
        if self.active_template:
            self.template_selected.emit(self.active_template)
            self.notice.set_message(
                f"'{self.active_template.name}' is now the active template for your project.",
                severity="success",
            )

    def _duplicate_template(self) -> None:
        if not self.active_template:
            return
        new_name = f"{self.active_template.name} (Copy)"
        new_tmpl = self.manager.duplicate_template(self.active_template.id, new_name)
        self._load_templates()
        for idx in range(self.list_widget.count()):
            it = self.list_widget.item(idx)
            if it.data(Qt.UserRole) == new_tmpl.id:
                self.list_widget.setCurrentItem(it)
                break
        self.notice.set_message(f"Created '{new_name}'.", severity="success")

    def _import_template(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Import Template JSON", "", "JSON Files (*.json)")
        if file_path:
            try:
                imported = self.manager.import_template(Path(file_path))
                self._load_templates()
                for idx in range(self.list_widget.count()):
                    it = self.list_widget.item(idx)
                    if it.data(Qt.UserRole) == imported.id:
                        self.list_widget.setCurrentItem(it)
                        break
                self.notice.set_message(
                    f"Imported '{imported.name}' successfully.", severity="success"
                )
            except Exception as e:
                logger.error("Failed to import template %s: %s", file_path, e)
                QMessageBox.critical(self, "Import Error", f"Failed to import template: {e}")

    def _export_template(self) -> None:
        if not self.active_template:
            return
        dest, _ = QFileDialog.getSaveFileName(
            self,
            "Export Template JSON",
            f"{self.active_template.name.replace(' ', '_').lower()}.json",
            "JSON Files (*.json)",
        )
        if dest:
            try:
                self.manager.export_template(self.active_template.id, Path(dest))
                self.notice.set_message(f"Saved template to {dest}.", severity="success")
            except Exception as e:
                logger.error("Failed to export template: %s", e)
                QMessageBox.critical(self, "Export Error", f"Failed to export template: {e}")

    def _delete_template(self) -> None:
        if not self.active_template:
            return
        if self.manager.is_builtin(self.active_template.id):
            QMessageBox.warning(self, "Protected", "Built-in templates cannot be deleted.")
            return

        confirm = QMessageBox.question(
            self,
            "Confirm Deletion",
            f"Are you sure you want to delete custom template '{self.active_template.name}'?",
        )
        if confirm == QMessageBox.Yes:
            self.manager.delete_user_template(self.active_template.id)
            self._load_templates()

    def _create_blank_canvas(self) -> None:
        dialog = BlankCanvasDialog(self)
        if dialog.exec():
            tmpl = dialog.template_definition
            if tmpl:
                self.manager.save_user_template(tmpl)
                self._load_templates()
                for idx in range(self.list_widget.count()):
                    item = self.list_widget.item(idx)
                    if item.data(Qt.UserRole) == tmpl.id:
                        self.list_widget.setCurrentItem(item)
                        break
                self.template_selected.emit(tmpl)
                self.open_editor_requested.emit()

    def _open_cleanup_dialog(self) -> None:
        """Open modal cleanup dialog to search, delete, and clean up older templates."""
        active_id = self.active_template.id if self.active_template else ""
        dialog = TemplateCleanupDialog(self, active_template_id=active_id)
        dialog.template_selected.connect(self._on_template_selected_from_dialog)
        dialog.exec()
        self.manager.reload()
        self._load_templates()

    def _on_template_selected_from_dialog(self, template: TemplateDefinition) -> None:
        """Handle template selected from cleanup dialog."""
        self.manager.reload()
        self._load_templates()
        for idx in range(self.list_widget.count()):
            it = self.list_widget.item(idx)
            if it.data(Qt.UserRole) == template.id:
                self.list_widget.setCurrentItem(it)
                break

    def _filter_template_list(self, text: str) -> None:
        """Filter the templates list widget based on search text."""
        query = text.strip().lower()
        for idx in range(self.list_widget.count()):
            it = self.list_widget.item(idx)
            tmpl_id = it.data(Qt.UserRole)
            tmpl = self.manager.get_template(tmpl_id)
            if not tmpl or not query:
                it.setHidden(False)
            else:
                match = (
                    query in tmpl.name.lower()
                    or query in (tmpl.description or "").lower()
                    or query in tmpl.id.lower()
                )
                it.setHidden(not match)
