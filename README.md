# Excel ID Card Generator — Windows 11 ID Card Designer & Batch Generator

A polished, Windows 11 Fluent-inspired desktop application for designing custom ID cards, binding arbitrary spreadsheet columns to dynamic visual elements, associating photographs via generic key lookups, batch generating cards in bulk, sequentially reviewing results, and exporting approved cards with audit manifests and printable contact sheets.

Built with **Python 3.12**, **PySide6 (Qt for Python)**, and **Pillow**, targeting Windows 10 & 11 (x64) without requiring Python to be installed on target systems.

---

## Key Features & Enhancements

### 1. Windows 11 Fluent-Inspired Interface
- **Modern Restrained UI**: Segoe UI typography, rounded controls (4px - 8px radius), subtle 1px surface borders, consistent spacing, and accessible focus outlines.
- **Three Selectable Themes**:
  - **Black**: Fluent dark theme with charcoal and near-black surfaces (`#121214`, `#18181B`), readable high-contrast text, subtle neutral borders, and clear `#60CDFF` selection indicators.
  - **White**: Fluent light theme with crisp white surfaces (`#FFFFFF`, `#F3F4F6`), dark text, and subtle separation.
  - **System**: Automatically detects Windows dark/light mode appearance via the Windows registry (`AppsUseLightTheme`) with graceful fallback.
- **Instant Runtime Switching**: Theme dropdown located directly in the main top application toolbar and in Settings, applying changes immediately across all widgets and dialogs without restart.

### 2. Generic Photograph Association & Safety
- **Arbitrary Key Column**: Decoupled from mandatory PIN Number; user can choose *any* spreadsheet column as the lookup key (e.g. `Employee Code`, `Candidate ID`, `Staff Number`, `Photo Reference`, `Roll No`).
- **Flexible Matching Rules**: Filename stem matching, configurable prefix/suffix rules (e.g. `EMP_`, `_id`), case-insensitive extension handling (`.jpg`, `.JPG`, `.png`, etc.), and leading-zero retention.
- **Ambiguity Detection**: Flags multiple images matching the same identifier as `AMBIGUOUS` instead of arbitrarily picking one.
- **Stable Manual Overrides**: Custom photo assignments survive spreadsheet refreshes and record reordering by anchoring directly to stable record identifiers.

### 3. Physical Dimensions & Custom DPI Engine
- **Canonical Measurement Units**: Seamless conversions between millimeters (`mm`), centimeters (`cm`), and inches (`inch`) without cumulative rounding errors.
- **High-DPI Support**: Configurable print resolution (default 300 DPI, supports up to 2400 DPI) with lossless scaling calculations (`pixels = inches × DPI`).
- **Standard Presets**: Instant selection for CR80 Standard (`85.60 × 53.98 mm`), CR79 (`83.90 × 52.10 mm`), and Oversized Visitor Badges (`100.00 × 70.00 mm`), with landscape/portrait orientation toggles.
- **Authoritative DPI Metadata**: Embedded directly into exported PNG and JPEG image headers.

### 4. Blank Canvas Creation
- Create blank documents from scratch with customized width, height, measurement unit, DPI, orientation, background color, and optional background surface image.
- Completely clean workspace without unwanted decorative elements or preconfigured dummy fields.

### 5. Photoshop-Inspired Professional Canvas Editor
- **70/30 Resizable Workspace**: 70% central interactive canvas with 30% right-side tabbed dock (`Properties`, `Layers`, `Data Mapping`).
- **Narrow Vertical Icon Tool Strip (Left)**:
  - ↖ Select / Move Tool (`V`)
  - T Text Tool (`T`)
  - {T} Dynamic Field Tool (`D`)
  - 📷 Photo / Image Tool (`P`)
  - ▭ Rectangle Tool (`U`)
  - ▢ Rounded Rectangle Tool (`R`)
  - ― Line Tool (`L`)
  - ⛶ Fit Card to View (`F`)
  - 1:1 Zoom 100% (`1`)
- **Contextual Horizontal Options Bar (Top)**:
  - Dynamically updates controls based on active selection:
    - *Text Elements*: Font family, font size, bold, italic, text color picker, and alignment.
    - *Shape Elements*: Fill color, stroke color, border width, and corner radius.
    - *Photo Elements*: Fit mode (`cover`, `contain`, `stretch`, `crop`) and mask shape (`rect`, `circle`, `rounded`).
    - *Document Mode*: Width, height, unit, DPI, zoom percentage, and fit-to-view.
- **Integrated Layers Hierarchy Panel**:
  - Live tree view of all canvas elements ordered by z-index.
  - Inline visibility toggles (eye), lock toggles (padlock), reordering (Bring Forward / Send Backward), duplication, and deletion.
- **Direct Dynamic Field Mapping Panel**:
  - Interactive spreadsheet column list with quick *"Bind to Selected Element"* and *"+ Add Field"* actions.
  - Live sample record navigator (◀ Prev, Next ▶, record search) displaying resolved values and real-time photo match status.
- **Canvas Interaction**:
  - 8-point resizing handles, dragging, keyboard nudging (1px or 10px with Shift), alignment tools, snapping grid, safe-area guides, undo/redo (`Ctrl+Z` / `Ctrl+Y`).

### 6. Centralized Background Task Manager
- Shared worker framework (`QThreadPool` and `QRunnable`) ensuring zero GUI freezing or direct widget manipulation from worker threads.
- Thread-safe Qt progress signals (`task_progress`, `task_completed`, `task_failed`, `task_cancelled`) feeding real-time status bar indicators.

### 7. Authoritative Pillow Rendering, Sequential Review & Audit Export
- **Authoritative Image Synthesis**: Canvas preview and final exported cards use the exact same Pillow rendering pipeline.
- **Sequential Review Interface**: Dedicated QA stage with large preview, sequential navigation, per-record approval (`Approve`, `Reject`, `Mark for Correction`, `Regenerate`).
- **Audit Export**:
  - Export approved cards only or all generated cards.
  - Lossless PNG or high-quality JPEG with quality compression slider.
  - Comprehensive **CSV Audit Manifest** (`export_manifest.csv`) detailing all spreadsheet fields, photo paths, and review outcomes.
  - Automated **Printable PDF Contact Sheet** (`contact_sheet.pdf`) via ReportLab.

---

## Architecture Overview

```
excel-id-card/
├── main.py                          # Application entry point
├── pyproject.toml                   # Project configuration and metadata
├── requirements.txt                 # Dependencies
├── src/
│   └── id_card_generator/
│       ├── app.py                   # QApplication lifecycle & startup
│       ├── core/                    # Models, constants, geometry conversion, logging, project manager
│       │   ├── geometry.py          # Canonical physical dimensions & DPI conversion
│       │   └── models.py            # Pydantic schemas (TemplateDefinition, SourceRecord, etc.)
│       ├── data/                    # Excel importer, normalizer, validator, photo scanner & generic matcher
│       ├── templates/               # Built-in and user template manager & validator
│       ├── editor/                  # QGraphicsView/Scene, canvas items, inspector, layers, field mapping
│       │   ├── field_mapping_panel.py # Direct dynamic spreadsheet field mapping panel
│       │   ├── layers_panel.py      # Layer hierarchy, ordering, visibility, and lock controls
│       │   └── canvas_items.py      # Interactive canvas items with 8-point handles
│       ├── tasks/                   # Centralized background task manager and runnable workers
│       ├── rendering/               # Authoritative Pillow renderer, text layout, image processing
│       ├── generation/              # Batch generator & staging area manager
│       ├── review/                  # Sequential review manager & status tracker
│       ├── export/                  # Export manager, CSV manifest writer, PDF contact sheet
│       ├── ui/                      # Windows 11 UI, main window, theme manager, pages, and dialogs
│       │   ├── theme_manager.py     # Windows 11 Fluent ThemeManager (Black, White, System)
│       │   └── dialogs/             # BlankCanvasDialog, RelinkDialog
│       └── resources/               # Built-in templates, stylesheets, icons, fonts
├── tests/                           # Complete 30-test automated suite (pytest & pytest-qt)
├── packaging/
│   ├── id_card_generator.spec       # PyInstaller standalone executable specification
│   └── installer.iss                # Inno Setup Windows installer script
└── .github/workflows/
    └── build-windows.yml            # CI/CD Windows automated build workflow
```

---

## Running Locally

### 1. Setup Environment

```bash
# Clone the repository
git clone https://github.com/adityakrchy/excel-based-id-card.git
cd excel-based-id-card

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate       # macOS / Linux
# .venv\Scripts\activate        # Windows PowerShell

# Install dependencies
pip install -r requirements.txt
pip install -e .
```

### 2. Launch Application

```bash
python main.py
```

---

## Running the Automated Test Suite

The repository includes a comprehensive 30-test suite verifying unit conversions, generic matching, canvas items, Pillow rendering, batch generation, review, export, and UI workflows:

```bash
# Run all tests
pytest tests/

# Headless mode (for CI or servers)
QT_QPA_PLATFORM=offscreen pytest tests/
```

### Verified Test Suites (30/30 Passing):
- `tests/test_geometry.py`: Canonical mm/cm/inch conversions, custom DPI scaling, orientation adjustments.
- `tests/test_photo_matching.py`: Arbitrary column selection, prefix/suffix matching, case-insensitive extensions, ambiguous matches, stable `record_id` manual overrides across reordering.
- `tests/test_task_manager.py`: Centralized background task runner, thread pool dispatching, progress signals.
- `tests/test_end_to_end_workflow.py`: Complete synthetic end-to-end pipeline (Excel import -> generic photo matching -> blank canvas design -> batch generation -> review approvals -> export with CSV manifest).
- `tests/test_excel_importer.py`: Worksheet discovery, leading zero retention, CSV fallback.
- `tests/test_data_validation.py`: Missing values, duplicate detection, data integrity.
- `tests/test_pillow_renderer.py`: Authoritative rendering, masks, auto-shrink text, RGB flattening.
- `tests/test_batch_generation.py`: Sanitized filename creation, background rendering.
- `tests/test_review_workflow.py`: Sequential review, approval invalidation upon regeneration.
- `tests/test_export_manager.py`: Filtered export, CSV manifest, ReportLab PDF contact sheet.
- `tests/test_project_persistence.py`: JSON project serialization and reference relinking.
- `tests/test_ui_workflow.py`: PySide6 MainWindow navigation, workflow stepper synchronization, theme switching.

---

## Windows Packaging

### 1. Build Standalone Executable (PyInstaller)

To build a standalone executable on Windows:

```powershell
pyinstaller --clean packaging/id_card_generator.spec
```

The resulting standalone executable will be generated at:
`dist\ExcelIDCardGenerator\ExcelIDCardGenerator.exe`

### 2. Build Inno Setup Installer

To compile the setup installer:
1. Open `packaging\installer.iss` in [Inno Setup 6](https://jrsoftware.org/isdl.php).
2. Click **Build > Compile** (or run `ISCC.exe packaging\installer.iss`).
3. The installer `ExcelIDCardGenerator-Setup-1.0.0.exe` will be generated in `dist\installer\`.

### 3. Automated GitHub Actions CI/CD

The workflow `.github/workflows/build-windows.yml` runs on `windows-latest` on every push to `main`, running the test suite, compiling the PyInstaller executable, compiling the Inno Setup installer, and uploading the artifacts for direct download.

---

## License

MIT License. Free for commercial and non-commercial use.
