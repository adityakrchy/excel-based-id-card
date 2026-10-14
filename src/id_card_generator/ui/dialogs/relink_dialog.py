"""Relinking dialog for missing external file assets when reopening projects."""

from pathlib import Path
from typing import Dict, List, Tuple
from PySide6.QtWidgets import (
    QDialog,
    QFileDialog,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)


class RelinkDialog(QDialog):
    """Dialog prompting the user to locate files or directories that moved."""

    def __init__(self, missing_items: List[Tuple[str, str]], parent=None):
        super().__init__(parent)
        self.setWindowTitle("Relink Missing Project Files")
        self.setMinimumWidth(550)
        self.missing_items = missing_items
        self.replacements: Dict[str, str] = {}
        self._inputs: Dict[str, QLineEdit] = {}

        self._setup_ui()

    def _setup_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(14)

        lbl_desc = QLabel(
            "<b>The following files or folders referenced by this project were not found:</b><br>"
            "Please locate their new locations to continue working on this project."
        )
        lbl_desc.setWordWrap(True)
        layout.addWidget(lbl_desc)

        form = QFormLayout()
        for key, old_path in self.missing_items:
            row_layout = QHBoxLayout()
            txt = QLineEdit(old_path)
            btn = QPushButton("Browse...")
            btn.clicked.connect(lambda ch=False, k=key, t=txt: self._browse_replacement(k, t))
            row_layout.addWidget(txt, stretch=1)
            row_layout.addWidget(btn)

            label_name = key.replace("_", " ").title()
            form.addRow(f"{label_name}:", row_layout)
            self._inputs[key] = txt

        layout.addLayout(form)

        btn_row = QHBoxLayout()
        btn_row.addStretch()
        self.btn_cancel = QPushButton("Cancel")
        self.btn_cancel.clicked.connect(self.reject)
        self.btn_ok = QPushButton("Apply & Open Project")
        self.btn_ok.setObjectName("btn_primary")
        self.btn_ok.clicked.connect(self._apply)
        btn_row.addWidget(self.btn_cancel)
        btn_row.addWidget(self.btn_ok)
        layout.addLayout(btn_row)

    def _browse_replacement(self, key: str, line_edit: QLineEdit) -> None:
        if key == "photo_dir":
            folder = QFileDialog.getExistingDirectory(self, "Locate Photo Directory")
            if folder:
                line_edit.setText(folder)
        else:
            filt = "Spreadsheets (*.xlsx *.xls *.csv)" if key == "excel_file" else "Images (*.png *.jpg *.jpeg)"
            file_path, _ = QFileDialog.getOpenFileName(self, f"Locate {key}", "", filt)
            if file_path:
                line_edit.setText(file_path)

    def _apply(self) -> None:
        for key, txt in self._inputs.items():
            val = txt.text().strip()
            if val and Path(val).exists():
                self.replacements[key] = val
        self.accept()
