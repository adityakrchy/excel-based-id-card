# Excel ID Card Generator

A standalone desktop application for generating personalized, print-ready ID cards in bulk from Excel spreadsheets and photo directories.

Built with **Python 3.12**, **PySide6 (Qt for Python)**, and **Pillow**, targeting Windows 10 & 11 (x64) without requiring Python to be installed on target systems.

---

## Key Features

- **Spreadsheet Importer (`.xlsx`, `.xls`, `.csv`)**:
  - Multi-sheet workbook selection and custom header row configuration.
  - Automatic column detection (`PIN Number`, `Name`, `Designation`, `Office Name`, `Constituency`, etc.).
  - Searchable, virtualized table with empty-cell detection, duplicate PIN alerts, and raw vs. normalized value preservation (safeguards leading zeros such as `00123` and avoids `100001.0` float corruption).

- **Photograph Scanner & PIN Matching Engine**:
  - Scans image directories (`.jpg`, `.jpeg`, `.png`, `.bmp`, `.webp`, `.tiff`).
  - Matches filename stems against person PIN Numbers with case-insensitive normalization.
  - Ambiguity detection: Flags multiple images matching the same PIN instead of arbitrarily selecting one.
  - Manual photo override support and unassigned photo auditing.

- **Interactive Visual Canvas Editor**:
  - Built with `QGraphicsView` & `QGraphicsScene`.
  - Scalable zoom, pan, rulers, alignment guides, and snapping grid.
  - 8-point resize handles, dragging, and keyboard nudges (1px or 10px with Shift).
  - Alignment and distribution tools (Left, Right, Center Horizontally/Vertically, Distribute).
  - Right-side properties inspector: Position, size, font family, size, colors, borders, corner radius, fit modes, and mask shapes.
  - Live WYSIWYG test bar: Navigate records and preview cards rendered in real-time.

- **Authoritative Pillow Rendering Engine**:
  - Pixel-perfect local image synthesis.
  - Dynamic text layout with line wrapping, line spacing, alignment, and auto-shrink font fitting.
  - Anti-aliased image masks: Rectangular, circular, or rounded rectangle with custom borders.
  - Resizing using `Image.Resampling.LANCZOS` with fit modes: `cover`, `contain`, `stretch`, and `crop`.
  - Automated placeholder generation for records with missing photos.

- **Background Batch Processing**:
  - `QThread` execution with thread-safe Qt progress signals.
  - Non-blocking UI with live record progress and cancellation support.
  - Deterministic Windows-sanitized output filenames (`{PIN_NUMBER}_{NAME}.png`).

- **Sequential Review Interface**:
  - Mandatory quality assurance gate prior to export.
  - Large card preview, sequential record navigation (`First`, `Prev`, `Next`, `Last`).
  - Status management: `Approve`, `Reject`, `Mark for Correction`, `Skip`, or `Regenerate`.
  - Batch actions and approval invalidation upon regeneration.

- **Export Manager & Audit Artifacts**:
  - User-selected destination directory.
  - Configurable formats: PNG (lossless) or JPEG with quality slider.
  - Filter: Export approved cards only or all generated cards.
  - Automated **CSV Audit Manifest** (`export_manifest.csv`) detailing PINs, names, source rows, photo paths, and review timestamps.
  - Automated **Printable PDF Contact Sheet** (`contact_sheet.pdf`) via ReportLab.

- **Project Persistence**:
  - Save and load complete project states (`.json`).
  - Automated relinking modal to resolve moved spreadsheets or photo folders without crashing.

---

## Architecture Overview

```
excel-id-card/
├── main.py                          # Root application launcher
├── pyproject.toml                   # Project configuration and metadata
├── requirements.txt                 # Pinned dependencies
├── src/
│   └── id_card_generator/
│       ├── app.py                   # QApplication lifecycle & startup
│       ├── core/                    # Models, constants, exceptions, logging, project manager
│       ├── data/                    # Excel importer, normalizer, validator, photo scanner & matcher
│       ├── templates/               # Built-in and custom template loader & validator
│       ├── editor/                  # QGraphicsView/Scene, canvas items, inspector, undo manager
│       ├── rendering/               # Pillow renderer, text layout, image processing, font manager
│       ├── generation/              # Batch generator & background QThread worker
│       ├── review/                  # Sequential review manager & status tracker
│       ├── export/                  # Export manager, CSV manifest writer, PDF contact sheet
│       ├── ui/                      # PySide6 main window, workflow navigation, pages, and dialogs
│       └── resources/               # QSS stylesheets (Dark & Light themes), icons, fonts
├── tests/                           # Comprehensive Pytest & Pytest-Qt test suite
├── packaging/
│   ├── id_card_generator.spec       # PyInstaller standalone configuration
│   └── installer.iss                # Inno Setup Windows installer script
└── scripts/
    ├── build_windows.ps1            # PowerShell automated build script
    └── clean_build.ps1              # Cleanup script
```

---

## Getting Started

### Prerequisites

- Python 3.10, 3.11, or 3.12 (Python 3.12 recommended).
- Git.

### 1. Installation

Clone repository and install dependencies:

```bash
git clone https://github.com/your-org/excel-id-card.git
cd excel-id-card

# Using standard virtual environment:
python3 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
pip install -e .

# Or using uv:
uv venv --python 3.12
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install -e .
```

### 2. Running Locally

Launch the application:

```bash
python main.py
```

---

## User Workflow Guide

1. **Dashboard**: View project summary, review metrics, and validation alerts.
2. **Data Source**: Click **Browse Spreadsheet...** to import `.xlsx`, `.xls`, or `.csv`. Select worksheet and header row. Inspect the preview table.
3. **Photos**: Click **Select Photo Folder...** to choose image folder. Inspect matched thumbnails or assign manual overrides.
4. **Templates**: Pick one of three built-in templates (*Classic Portrait*, *Modern Corporate*, or *Government/Office ID Card*) or import a custom JSON template.
5. **Canvas Editor**: Drag elements, resize with 8-point handles, modify colors/fonts in the right inspector, and test with live records.
6. **Generate Cards**: Review the pre-flight checklist and click **Generate All ID Cards**.
7. **Review Cards**: Sequentially inspect generated cards, verify photos, and click **Approve Card** or **Approve All Valid Cards**.
8. **Export Cards**: Choose output folder, toggle CSV Manifest and PDF Contact Sheet, and click **Export Cards Now**.

---

## Automated Test Suite

Run the full automated test suite:

```bash
# Backend unit & integration tests
pytest tests/

# With Qt offscreen flag for headless CI environments:
QT_QPA_PLATFORM=offscreen pytest tests/
```

### Test Coverage Highlights
- `test_excel_importer.py`: Sheet inspection, data typing, leading zero retention, CSV fallback.
- `test_data_validation.py`: Missing PIN flags, duplicate detection, whitespace warnings.
- `test_photo_matching.py`: Case-insensitive stem matching, format handling, ambiguous match detection, manual overrides.
- `test_template_validation.py`: Schema validation, dimension limits, safety traversal checks.
- `test_pillow_renderer.py`: High-DPI rendering, masks, auto-shrink text layout, RGB flattening for JPEG.
- `test_batch_generation.py`: Deterministic naming, background processing, collision resolution.
- `test_review_workflow.py`: Per-record approval, rejection, and invalidation upon regeneration.
- `test_export_manager.py`: File copy/conversion, audit CSV generation, ReportLab contact sheet creation.
- `test_project_persistence.py`: JSON save/load, missing asset detection, relinking workflow.
- `test_ui_workflow.py`: PySide6 MainWindow navigation, workflow stepper synchronization, theme switching.

---

## Windows Packaging & Release

### Standalone Executable (PyInstaller)

Run the automated build script on Windows PowerShell:

```powershell
.\scripts\build_windows.ps1
```

Or manually:

```bash
pyinstaller --clean packaging/id_card_generator.spec
```

The resulting standalone folder will be located at:
`dist/ExcelIDCardGenerator/ExcelIDCardGenerator.exe`

### Inno Setup Installer

To create a Windows setup installer (`.exe`) with Start Menu and Desktop shortcuts:
1. Install [Inno Setup 6](https://jrsoftware.org/isdl.php).
2. Open `packaging/installer.iss` in Inno Setup Compiler.
3. Click **Build > Compile**.
4. The output installer will be created in `dist/installer/ExcelIDCardGenerator-Setup-1.0.0.exe`.

---

## License

MIT License. Free for commercial and non-commercial use.
