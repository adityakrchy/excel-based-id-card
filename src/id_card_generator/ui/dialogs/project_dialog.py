"""Project and workspace creation and opening dialog."""

import os
from pathlib import Path
from typing import Optional
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)

from id_card_generator.core.exceptions import ProjectError
from id_card_generator.core.models import ProjectConfiguration
from id_card_generator.core.project_manager import ProjectManager


class ProjectDialog(QDialog):
    """Dialog for creating a new project workspace or opening an existing one."""

    workspace_ready = Signal(object, object)  # (ProjectConfiguration, Path)

    def __init__(self, parent=None, initial_mode: str = "create"):
        super().__init__(parent)
        self.setWindowTitle("Project Workspace Setup")
        self.setMinimumWidth(560)
        self.resize(580, 420)

        self.created_config: Optional[ProjectConfiguration] = None
        self.selected_workspace_path: Optional[Path] = None
        self._user_customized_path = False

        self._setup_ui(initial_mode)

    def _setup_ui(self, initial_mode: str) -> None:
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(20, 20, 20, 20)
        main_layout.setSpacing(16)

        # Header Title
        lbl_title = QLabel("<h3>Project Workspace</h3>")
        lbl_subtitle = QLabel(
            "A project workspace organizes all assets into a self-contained directory: "
            "imported spreadsheets, matched photographs, and exported ID cards."
        )
        lbl_subtitle.setWordWrap(True)
        lbl_subtitle.setStyleSheet("color: #64748B; font-size: 12px;")
        main_layout.addWidget(lbl_title)
        main_layout.addWidget(lbl_subtitle)

        # Tabs for Create vs Open
        self.tabs = QTabWidget()

        # Tab 1: Create New Project
        tab_create = QWidget()
        create_layout = QVBoxLayout(tab_create)
        create_layout.setContentsMargins(14, 14, 14, 14)
        create_layout.setSpacing(12)

        create_layout.addWidget(QLabel("<b>Project Name:</b>"))
        self.txt_project_name = QLineEdit("ID Card Project")
        self.txt_project_name.textChanged.connect(self._on_project_name_changed)
        create_layout.addWidget(self.txt_project_name)

        create_layout.addWidget(QLabel("<b>Workspace Directory:</b>"))
        ws_row = QHBoxLayout()
        self.txt_workspace_path = QLineEdit()
        self.btn_browse_ws = QPushButton("Browse...")
        self.btn_browse_ws.clicked.connect(self._browse_workspace_location)
        ws_row.addWidget(self.txt_workspace_path, stretch=1)
        ws_row.addWidget(self.btn_browse_ws)
        create_layout.addLayout(ws_row)

        # Structure Preview Card
        preview_card = QFrame()
        preview_card.setObjectName("card_panel")
        preview_card.setStyleSheet("background: rgba(148, 163, 184, 0.08); border-radius: 6px; padding: 10px;")
        prev_layout = QVBoxLayout(preview_card)
        prev_layout.setContentsMargins(8, 8, 8, 8)
        prev_layout.setSpacing(4)
        prev_layout.addWidget(QLabel("<b>Workspace Structure to be Created:</b>"))

        self.lbl_tree = QLabel(
            "📁 <i>workspace_folder/</i><br>"
            "&nbsp;&nbsp;├── 📄 <b>project.json</b> (Project config & mappings)<br>"
            "&nbsp;&nbsp;├── 📊 <b>data/</b> (Spreadsheet copied automatically on import)<br>"
            "&nbsp;&nbsp;├── 🖼 <b>photos/</b> (Only matched photos copied here)<br>"
            "&nbsp;&nbsp;└── 📦 <b>exports/</b> (Generated ID cards & manifest)"
        )
        self.lbl_tree.setStyleSheet("font-size: 11px; color: #475569;")
        prev_layout.addWidget(self.lbl_tree)
        create_layout.addWidget(preview_card)

        self.tabs.addTab(tab_create, "Create New Project")

        # Tab 2: Open Existing Project
        tab_open = QWidget()
        open_layout = QVBoxLayout(tab_open)
        open_layout.setContentsMargins(14, 14, 14, 14)
        open_layout.setSpacing(12)

        open_layout.addWidget(QLabel("<b>Open Workspace Folder or project.json:</b>"))
        open_row = QHBoxLayout()
        self.txt_open_path = QLineEdit()
        self.btn_browse_open = QPushButton("Browse Folder...")
        self.btn_browse_open.clicked.connect(self._browse_open_workspace)
        self.btn_browse_file = QPushButton("Browse project.json...")
        self.btn_browse_file.clicked.connect(self._browse_open_file)
        open_row.addWidget(self.txt_open_path, stretch=1)
        open_row.addWidget(self.btn_browse_open)
        open_row.addWidget(self.btn_browse_file)
        open_layout.addLayout(open_row)

        lbl_open_hint = QLabel(
            "Select an existing workspace directory (containing <code>project.json</code>) "
            "or directly select the <code>project.json</code> file to resume work."
        )
        lbl_open_hint.setWordWrap(True)
        lbl_open_hint.setStyleSheet("color: #64748B; font-size: 12px;")
        open_layout.addWidget(lbl_open_hint)
        open_layout.addStretch()

        self.tabs.addTab(tab_open, "Open Existing Workspace")

        main_layout.addWidget(self.tabs)

        # Dialog Buttons
        btn_row = QHBoxLayout()
        self.btn_skip = QPushButton("Skip Workspace")
        self.btn_skip.setToolTip("Continue without creating a dedicated workspace folder")
        self.btn_skip.clicked.connect(self.reject)

        self.btn_submit = QPushButton("Create Workspace & Begin")
        self.btn_submit.setObjectName("btn_primary")
        self.btn_submit.setFixedHeight(34)
        self.btn_submit.setStyleSheet("font-weight: bold; padding: 0 18px;")
        self.btn_submit.clicked.connect(self._on_submit)

        btn_row.addWidget(self.btn_skip)
        btn_row.addStretch()
        btn_row.addWidget(self.btn_submit)
        main_layout.addLayout(btn_row)

        self.tabs.currentChanged.connect(self._on_tab_changed)
        if initial_mode == "open":
            self.tabs.setCurrentIndex(1)
        else:
            self.tabs.setCurrentIndex(0)

        # Set default workspace directory
        default_base = Path.home() / "IDCardProjects"
        default_dir = default_base / "ID_Card_Project"
        self.txt_workspace_path.setText(str(default_dir))

    def _on_tab_changed(self, index: int) -> None:
        if index == 0:
            self.btn_submit.setText("Create Workspace & Begin")
        else:
            self.btn_submit.setText("Open Workspace")

    def _on_project_name_changed(self, text: str) -> None:
        if not self._user_customized_path:
            clean_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in text.strip()) or "project"
            default_base = Path.home() / "IDCardProjects"
            self.txt_workspace_path.setText(str(default_base / clean_name))

    def _browse_workspace_location(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Parent Folder for Workspace")
        if folder:
            self._user_customized_path = True
            clean_name = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in self.txt_project_name.text().strip()) or "project"
            self.txt_workspace_path.setText(str(Path(folder) / clean_name))

    def _browse_open_workspace(self) -> None:
        folder = QFileDialog.getExistingDirectory(self, "Select Existing Workspace Folder")
        if folder:
            self.txt_open_path.setText(folder)

    def _browse_open_file(self) -> None:
        file_path, _ = QFileDialog.getOpenFileName(self, "Select project.json", "", "Project Configuration (project.json *.json)")
        if file_path:
            self.txt_open_path.setText(file_path)

    def _on_submit(self) -> None:
        idx = self.tabs.currentIndex()
        if idx == 0:
            # Create
            name = self.txt_project_name.text().strip()
            if not name:
                QMessageBox.warning(self, "Missing Name", "Please provide a name for your project.")
                return

            ws_str = self.txt_workspace_path.text().strip()
            if not ws_str:
                QMessageBox.warning(self, "Missing Directory", "Please choose a workspace directory.")
                return

            ws_path = Path(ws_str).resolve()
            try:
                config = ProjectManager.create_workspace(name, ws_path)
                self.created_config = config
                self.selected_workspace_path = ws_path
                self.workspace_ready.emit(config, ws_path)
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "Workspace Error", f"Could not create workspace: {e}")
        else:
            # Open
            open_str = self.txt_open_path.text().strip()
            if not open_str:
                QMessageBox.warning(self, "Missing Path", "Please specify a workspace directory or project.json.")
                return

            p = Path(open_str).resolve()
            try:
                config = ProjectManager.load_project(p)
                self.created_config = config
                self.selected_workspace_path = Path(config.workspace_dir) if config.workspace_dir else p.parent
                self.workspace_ready.emit(config, self.selected_workspace_path)
                self.accept()
            except Exception as e:
                QMessageBox.critical(self, "Open Error", f"Could not open project: {e}")
