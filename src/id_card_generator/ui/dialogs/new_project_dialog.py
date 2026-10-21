"""New Project creation dialog for document-based ID Studio workflow."""

import logging
from pathlib import Path
from typing import Optional, Tuple
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QFileDialog,
    QFrame,
    QMessageBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

from id_card_generator.core.models import ProjectConfiguration, TemplateDefinition
from id_card_generator.core.project_manager import ProjectManager
from id_card_generator.templates.template_manager import TemplateManager
from id_card_generator.ui.studio_tokens import COLORS, TYPOGRAPHY

logger = logging.getLogger(__name__)


class NewProjectDialog(QDialog):
    """Modern modal dialog for creating a new document-based ID project (.idcrt)."""

    project_created = Signal(object)  # ProjectConfiguration

    def __init__(self, parent=None, template_manager: Optional[TemplateManager] = None):
        super().__init__(parent)
        self.setWindowTitle("Create New Project")
        self.setFixedWidth(460)
        self.setModal(True)
        self.template_manager = template_manager or TemplateManager()
        self.created_config: Optional[ProjectConfiguration] = None
        # The location the user picked is kept, so the name of the project can
        # still update the path until the user types one of their own.
        self._location_edited = False

        self._setup_ui()

    def _setup_ui(self) -> None:
        self.setStyleSheet(
            f"QDialog {{"
            f"  background-color: {COLORS.SURFACE_CONTAINER};"
            f"  color: {COLORS.ON_SURFACE};"
            f"  font-family: {TYPOGRAPHY.FONT_FAMILY_UI};"
            f"}}"
            f"QLabel {{"
            f"  color: {COLORS.ON_SURFACE};"
            f"}}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(18)

        # Header Section
        header_layout = QVBoxLayout()
        header_layout.setSpacing(4)

        lbl_title = QLabel("Create New Project")
        lbl_title.setStyleSheet(
            f"font-size: 17px; font-weight: 700; color: #FFFFFF;"
        )
        header_layout.addWidget(lbl_title)

        lbl_desc = QLabel("Start a new ID credential project")
        lbl_desc.setStyleSheet(
            f"font-size: 12px; color: {COLORS.ON_SURFACE_VARIANT};"
        )
        header_layout.addWidget(lbl_desc)
        layout.addLayout(header_layout)

        # Divider
        divider = QFrame()
        divider.setFrameShape(QFrame.HLine)
        divider.setStyleSheet(f"background-color: {COLORS.BORDER_HAIRLINE}; max-height: 1px;")
        layout.addWidget(divider)

        # Form Controls
        form_layout = QVBoxLayout()
        form_layout.setSpacing(14)

        # Project Name
        lbl_name = QLabel("PROJECT NAME")
        lbl_name.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: #8E909F; letter-spacing: 0.05em;"
        )
        form_layout.addWidget(lbl_name)

        self.txt_project_name = QLineEdit("ID Card Project")
        self.txt_project_name.textChanged.connect(self._on_name_changed)
        self.txt_project_name.setFixedHeight(34)
        self.txt_project_name.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {COLORS.SURFACE_DIM};"
            f"  color: #FFFFFF;"
            f"  border: 1px solid {COLORS.BORDER_HAIRLINE};"
            f"  border-radius: 5px;"
            f"  padding: 0 10px;"
            f"  font-size: 13px;"
            f"}}"
            f"QLineEdit:focus {{"
            f"  border-color: {COLORS.PRIMARY};"
            f"}}"
        )
        form_layout.addWidget(self.txt_project_name)

        # Starter Template
        lbl_tmpl = QLabel("STARTER TEMPLATE")
        lbl_tmpl.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: #8E909F; letter-spacing: 0.05em;"
        )
        form_layout.addWidget(lbl_tmpl)

        self.cmb_template = QComboBox()
        self.cmb_template.setFixedHeight(34)
        self.cmb_template.setStyleSheet(
            f"QComboBox {{"
            f"  background-color: {COLORS.SURFACE_DIM};"
            f"  color: #FFFFFF;"
            f"  border: 1px solid {COLORS.BORDER_HAIRLINE};"
            f"  border-radius: 5px;"
            f"  padding: 0 10px;"
            f"  font-size: 12px;"
            f"}}"
            f"QComboBox:focus {{"
            f"  border-color: {COLORS.PRIMARY};"
            f"}}"
            f"QComboBox QAbstractItemView {{"
            f"  background-color: {COLORS.SURFACE_CONTAINER};"
            f"  color: #FFFFFF;"
            f"  selection-background-color: {COLORS.PRIMARY};"
            f"  selection-color: #FFFFFF;"
            f"}}"
        )

        self.cmb_template.addItem("Blank Canvas (CR80 Standard · 85.6 × 53.98 mm)", None)
        templates = self.template_manager.list_templates()
        for tmpl in templates:
            self.cmb_template.addItem(f"{tmpl.name} ({tmpl.orientation.title()})", tmpl.id)

        form_layout.addWidget(self.cmb_template)

        # Where the project is saved.  The workspace of the project holds the
        # imported sheet, the matched photographs and the exported cards.
        lbl_location = QLabel("SAVE LOCATION")
        lbl_location.setStyleSheet(
            f"font-size: 10px; font-weight: 700; color: #8E909F; letter-spacing: 0.05em;"
        )
        form_layout.addWidget(lbl_location)

        location_row = QHBoxLayout()
        location_row.setSpacing(8)

        self.txt_location = QLineEdit()
        self.txt_location.setFixedHeight(34)
        self.txt_location.setPlaceholderText("Choose a folder for the project")
        self.txt_location.setStyleSheet(
            f"QLineEdit {{"
            f"  background-color: {COLORS.SURFACE_DIM};"
            f"  color: #FFFFFF;"
            f"  border: 1px solid {COLORS.BORDER_HAIRLINE};"
            f"  border-radius: 5px;"
            f"  padding: 0 10px;"
            f"  font-size: 12px;"
            f"}}"
            f"QLineEdit:focus {{"
            f"  border-color: {COLORS.PRIMARY};"
            f"}}"
        )
        self.txt_location.textEdited.connect(self._on_location_edited)
        location_row.addWidget(self.txt_location, stretch=1)

        self.btn_browse = QPushButton("Browse...")
        self.btn_browse.setFixedHeight(34)
        self.btn_browse.setCursor(Qt.PointingHandCursor)
        self.btn_browse.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLORS.SURFACE_HIGH};"
            f"  color: {COLORS.ON_SURFACE};"
            f"  border: 1px solid {COLORS.BORDER_HAIRLINE};"
            f"  border-radius: 5px;"
            f"  padding: 0 14px;"
            f"  font-size: 12px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {COLORS.SURFACE_HIGHEST};"
            f"  border-color: {COLORS.PRIMARY};"
            f"}}"
        )
        self.btn_browse.clicked.connect(self._browse_location)
        location_row.addWidget(self.btn_browse)

        form_layout.addLayout(location_row)

        lbl_location_hint = QLabel(
            "The folder is filled with the project: the imported sheet in "
            "<code>data</code>, the matched photographs in <code>photos</code> "
            "and the exported cards in <code>export</code>."
        )
        lbl_location_hint.setWordWrap(True)
        lbl_location_hint.setStyleSheet(
            f"font-size: 11px; color: {COLORS.TEXT_MUTED};"
        )
        form_layout.addWidget(lbl_location_hint)

        layout.addLayout(form_layout)

        layout.addSpacing(6)

        # Buttons
        btn_layout = QHBoxLayout()
        btn_layout.setSpacing(10)
        btn_layout.addStretch()

        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.setFixedHeight(32)
        self.btn_cancel.setFixedWidth(80)
        self.btn_cancel.setCursor(Qt.PointingHandCursor)
        self.btn_cancel.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: transparent;"
            f"  color: {COLORS.ON_SURFACE_VARIANT};"
            f"  border: 1px solid {COLORS.BORDER_HAIRLINE};"
            f"  border-radius: 5px;"
            f"  font-size: 12px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {COLORS.SURFACE_HIGH};"
            f"  color: {COLORS.ON_SURFACE};"
            f"}}"
        )
        self.btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(self.btn_cancel)

        self.btn_create = QPushButton("Create Project")
        self.btn_create.setFixedHeight(32)
        self.btn_create.setFixedWidth(120)
        self.btn_create.setCursor(Qt.PointingHandCursor)
        self.btn_create.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {COLORS.PRIMARY};"
            f"  color: #FFFFFF;"
            f"  border: none;"
            f"  border-radius: 5px;"
            f"  font-weight: 600;"
            f"  font-size: 12px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: #5C7CFA;"
            f"}}"
        )
        self.btn_create.clicked.connect(self._on_create_clicked)
        btn_layout.addWidget(self.btn_create)

        layout.addLayout(btn_layout)

        self.txt_location.setText(self._default_location())

    def _default_location(self) -> str:
        """The folder the project is saved in by default."""
        name = self.txt_project_name.text().strip() or "Untitled Project"
        safe = "".join(c for c in name if c not in '<>:"/\\|?*').strip() or "Untitled Project"
        return str(Path.home() / "IDCardProjects" / safe)

    def _on_name_changed(self, text: str) -> None:
        """The location follows the name until the user picks one."""
        if not self._location_edited:
            self.txt_location.setText(self._default_location())

    def _on_location_edited(self, text: str) -> None:
        """The user typed a location of their own."""
        self._location_edited = True

    def _browse_location(self) -> None:
        """Let the user pick the folder of the project."""
        current = self.txt_location.text().strip()
        start = current if current and Path(current).exists() else str(Path.home())
        folder = QFileDialog.getExistingDirectory(self, "Choose a folder for the project", start)
        if folder:
            self._location_edited = True
            self.txt_location.setText(folder)

    def _on_create_clicked(self) -> None:
        name = self.txt_project_name.text().strip() or "Untitled Project"
        tmpl_id = self.cmb_template.currentData()
        template: Optional[TemplateDefinition] = None
        if tmpl_id:
            template = self.template_manager.get_template(tmpl_id)

        location = self.txt_location.text().strip() or self._default_location()
        workspace = Path(location).expanduser()

        # The workspace holds the sheet, the photographs and the export.
        try:
            config = ProjectManager.create_workspace(name, workspace)
        except Exception as e:
            QMessageBox.critical(
                self, "Workspace Error", f"Could not create the project folder:\n{e}"
            )
            return

        config.template = template
        self.created_config = config
        self.project_created.emit(config)
        self.accept()
