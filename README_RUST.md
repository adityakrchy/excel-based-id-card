# Rust migration foundation

This repository still contains the existing Python/PySide6 application. This
document describes the focused first Rust migration slice at the repository
root; it does not claim full application parity.

## Audit findings

The current Python implementation already provides the migration contracts and
behavior used by this slice:

- `core/models.py` defines the JSON field names for `ProjectConfiguration`,
  `TemplateDefinition`, `CanvasElement`, `SourceRecord`, photo matching,
  rendering, review, and export state.
- `core/constants.py` defines the string enum values. The Rust serde models
  preserve those values, including `placeholder`, `skip`, `fail`, `PNG`, and
  `JPEG`.
- `core/geometry.py` uses millimetres, centimetres, inches, pixels, and custom
  DPI. The canonical CR80 input is 85.6 x 54.0 mm; at 300 DPI the rounded
  landscape result is 1011 x 638 pixels (portrait is 638 x 1011).
- `data/photo_matcher.py` selects an arbitrary source column, never silently
  chooses an ambiguous image, and checks stable record-id overrides before key
  overrides.
- `data/photo_scanner.py` indexes supported filename extensions without image
  decoding and streams batches. `tasks/photo_indexing_worker.py` provides the
  cancellation/progressive-worker precedent.
- `core/project_manager.py` saves direct project JSON and checks Excel, photo
  directory, and template background references.

## Implemented slice

The Rust crate is intentionally isolated under Rust-only files and is usable as
a native foundation:

- `src/data/models.rs`: serde-compatible typed models and string enums.
- `src/editor/geometry.rs`: checked unit/DPI conversions and CR80 dimensions.
- `src/projects/persistence.rs`: version-required JSON project/template load,
  pretty save, same-directory temporary write, sync, rename, missing
  reference checks/relinking, atomic `.bak` backup creation, automatic
  recovery from corrupted or missing primary files, and asset path security
  guarantees against directory traversal and symlink escapes.
- `src/photos`: recursive filename-only indexing, metadata-only caching via
  `PhotoLibrary` (`PersistedPhotoIndex`), incremental rescan reports (`added`,
  `modified`, `removed`), and arbitrary-column matching with explicit matched,
  ambiguous, missing, and overridden states.
- `src/data/importer.rs`: synchronous CSV/XLSX/XLS importing through `csv` and
  calamine 0.26, worksheet listing, zero-based header selection, arbitrary
  column names, empty-cell normalization, PIN hint/candidate detection, and
  deterministic row-based `SourceRecord` IDs. The importer reads cell values
  only and does not load workbook pictures.
- `src/tasks`: application-wide `TaskManager` coordinating background task
  lifecycles (`Queued`, `Running`, `Completed`, `Failed`, `Cancelled`) with
  bounded channels and cooperative cancellation. Includes
  `src/tasks/photo_indexing.rs` for progressive filesystem scanning without
  image decoding and `src/tasks/thumbnails.rs` for bounded, prioritized lazy
  image decoding with LRU caching.
- `src/rendering`: a native RGBA renderer for previews and export-oriented
  output. It handles template backgrounds, z-ordered rectangles, rounded
  rectangles and lines, static/dynamic text, photos and static images, cover,
  contain, stretch and crop fitting, circle/rounded masks, element opacity,
   safe image failures, typed warnings/errors, and PNG/JPEG encoding.
- `src/generation`: a batch workflow over `NativeRenderer`. It associates
  optional photos by stable `record_id`, applies each `MissingPhotoPolicy`,
  expands and sanitizes `{PIN_NUMBER}`/`{NAME}` naming patterns, reserves
  collision suffixes without silently overwriting files, writes through
  same-directory temporary files before rename, and uses bounded standard
  library workers with cooperative cancellation. Results retain source order
  and include per-record warnings/errors; progress events include a final
  completed/skipped/failed/cancelled summary.
- `src/export`: review-aware image export and audit manifest support. Approved
  filtering uses `ReviewStatus::Approved`; generated paths are converted or
  encoded through `RenderedImage`/`NativeRenderer` as PNG or JPEG with the
  requested JPEG quality. Output names are collision-safe, and the optional
  UTF-8 BOM manifest combines arbitrary source columns with stable audit
  columns and reports accurate exported/skipped/failed counts.
- `src/review/mod.rs`: typed review state management keyed by stable
  `record_id`, with pending/approved/rejected/correction/skipped transitions,
  comments, regeneration invalidation, case-insensitive lookup, deterministic
  source-order navigation, and conversion to/from `ReviewRecord` values and
   `ProjectConfiguration.review_states`. Persisted status strings remain the
   existing `snake_case` values.
- `src/templates`: built-in Classic Portrait, Modern Corporate, and
  Government/Office templates are compiled into the Rust crate from the
  existing JSON definitions, so the native app does not need Python or a
  runtime-relative template path to load them.
- `src/ui`: native `egui` interactive components:
  - `TemplateEditor`: interactive canvas with `CanvasTransform`, pan, zoom, grid, snap-to-grid, safe margins, element selection, move/duplicate/delete/z-order mutation, and snapshot-based `EditorHistory` undo/redo.
  - *Photoshop-Style Floating Docks & Rulers*: horizontal and vertical rulers with unit toggle (px/mm), major/minor ticks, labels, dynamic cursor hairline tracking, full-canvas crosshairs, floating bottom HUD (zoom slider, 1:1, fit, toggles), and dockable tabbed panel (`Properties`, `Layers`, `Swatches` with 24 curated design colors, `History` action stack, and `Align` tools for left, center, right, top, vertical center, and bottom alignment).
  - `MappingEditor`: source-column-to-element binding, sample record live preview, unmapped required fields, and photo warning detection.
- `src/app` and `src/main.rs`: native eframe/egui workflow shell with Dashboard,
  Data Source, Photos, Templates, Template Editor, Mapping, Generate, Review,
  Export, and Settings pages.
  - *Review Image Viewer*: dedicated interactive pan/zoom viewport in the Review page with drag-to-pan, mouse wheel zoom, resolution badge, and drop-shadow card canvas for inspecting cards directly within the app before approving or rejecting.
  - *Contact Sheet Export*: integrated printable contact sheet toggle exporting multi-card grids alongside batch cards and UTF-8 BOM audit manifests.
  - File/folder dialogs via native `rfd`, atomic project persistence with recovery, progressive photo discovery, lazy thumbnails, review state, and background workers.
- `src/export/contact_sheet.rs`: multi-card printable contact sheet generator (`ContactSheetGenerator`) with configurable page sizes (A4, Letter, Custom), margins, spacing, DPI (300 DPI default), column/row count, cut marks around each card, title header with pagination ("Page X of Y"), and optional card labels.
- `packaging` and `scripts`: Windows binary version resource embedding via
  `winres` (`build.rs`), Inno Setup 64-bit installer script
  (`packaging/rust_installer.iss`), PowerShell build automation
  (`scripts/build_rust_windows.ps1`), and automated GitHub Actions Windows CI
  (`.github/workflows/build-rust-windows.yml`).
- `tests/rust_foundation.rs`: geometry, JSON round-trip/reference checks,
  matching, bounded progressive scanning, and cancellation coverage.
- `tests/rust_importer.rs`: CSV import, empty values, leading-zero-safe PIN
  strings, arbitrary-column and PIN hint behavior, header-row offsets, typed
  file errors, and CSV worksheet listing. Binary workbook fixtures are not
  included; XLSX/XLS code is compile-ready against calamine 0.26.
- `tests/rust_rendering.rs`: pixel dimensions, background/shape geometry,
  dynamic source binding, missing-photo warnings, and PNG output metadata.
- `tests/rust_generation_export.rs`: naming and collision handling,
  cancellation and render-error results, approved-only export,
  arbitrary-column BOM manifest coverage, and multi-card printable contact
  sheet grid layout generation.
- `tests/rust_review.rs`: deterministic navigation and search, typed status
  transitions/comments, regeneration invalidation, and project review-state
  persistence round trips.
- `tests/rust_templates.rs`: built-in template loading and typed unknown-template
  errors.
- `tests/rust_editor_mapping.rs`: scene-to-screen coordinate round trips,
  command-based editor mutation (move, duplicate, delete, z-order) with undo/redo
  history, Photoshop alignment tools, swatch color application, action stack
  tracking, arbitrary-column mapping validation, and live preview warnings.
- `tests/rust_photo_library.rs`: incremental rescan reporting (added, modified,
  removed), metadata-only caching with change invalidation, robust decode error
  isolation, and bounded, cancellable lazy thumbnail queues.
- `tests/rust_recovery.rs`: atomic project file saving with backup (.bak)
  rotation, automatic corruption/missing-file recovery with explicit diagnostic
  metadata, and path traversal/symlink escape guards for relative assets.
- `tests/rust_task_manager.rs`: background task lifecycle coordination (queued,
  running, completed, failed, cancelled), cooperative worker cancellation with
  timeout backpressure resolution, and worker wake-up on manager drop.

### Native rendering API

`NativeRenderer::render` and `NativeRenderer::render_with_settings` return a
`RenderedImage` containing an `image::RgbaImage` and typed `RenderWarning`
values. The same `RenderedImage::encode` or `NativeRenderer::render_to` path
is used for export output, so preview and export do not have separate drawing
implementations. `RenderError` is returned for invalid dimensions, required
photo failures, and encoding failures.

PNG output contains a `pHYs` chunk and JPEG output contains JFIF pixel density,
both calculated from `TemplateDefinition::dpi`. JPEG output is flattened onto
the template background because JPEG has no alpha channel. Missing or corrupt
background, static image, and photo files produce typed warnings; a missing
photo uses a generated placeholder unless the render settings request
`MissingPhotoPolicy::FailRecord`.

Text uses `ab_glyph` through `imageproc`. The renderer searches the operating
system's font directories on Windows, macOS, and Linux and does **not** bundle
a font. A deployment must therefore provide at least one usable system font;
if none can be resolved, text is skipped with a `MissingFont` warning while
the rest of the card remains renderable. Font family names are best-effort
platform requests, with common Arial/Calibri/Segoe UI/Helvetica fallbacks.

The dependencies requested for this slice are declared in `Cargo.toml`:
`eframe/egui` (through eframe), `rfd`, `serde`, `serde_json`, `thiserror`,
`uuid`, `image` with PNG/JPEG codecs, `imageproc`, `ab_glyph`, `png`,
`calamine`, `csv`, `crossbeam-channel`, `walkdir`, and `tempfile` for tests.

## Windows build commands

From a PowerShell prompt at the repository root, using the stable MSVC toolchain:

```powershell
winget install --id Rustlang.Rustup --exact
rustup default stable-x86_64-pc-windows-msvc
rustup target add x86_64-pc-windows-msvc
cargo fmt --all -- --check
cargo test --all-targets
cargo build --release --target x86_64-pc-windows-msvc
```

If Rustup is already installed and the stable MSVC toolchain is selected, run:

```powershell
rustup toolchain install stable-x86_64-pc-windows-msvc
rustup default stable-x86_64-pc-windows-msvc
cargo test --all-targets
cargo build --release --target x86_64-pc-windows-msvc
```

The same sequence is available as `scripts\build_rust_windows.ps1` and as the
automated GitHub Actions workflow `.github/workflows/build-rust-windows.yml`.
If `ISCC.exe` is installed and on `PATH`, the script compiles
`packaging\rust_installer.iss`. The installer creates a Start Menu shortcut and
an optional desktop shortcut, while deliberately preserving user data during
uninstall.

The release executable is written to
`target\x86_64-pc-windows-msvc\release\excel-id-card-rust.exe`.

## Verification in this environment

Stable Rust 1.99.1 is installed for this workspace. The following checks pass
on macOS arm64 from the repository root:

```text
cargo fmt --all -- --check
cargo check --all-targets
cargo test --all-targets       # 40 Rust tests passed across 10 test suites + unit tests
cargo clippy --all-targets --all-features -- -D warnings # 0 warnings, strict pass
cargo build --release          # target/release/excel-id-card-rust
git diff --check
```

The Python test suite remains intact; running `.venv/bin/pytest tests/test_template_designer_and_mapping.py` passes 12/12 tests with no Python files modified. All 10 Rust integration test suites (foundation, importer, rendering, generation/export, review, templates, editor/mapping, photo library, recovery, task manager) plus unit tests pass (40 passed). A Windows MSVC build and clean-machine installer test can be executed via `scripts\build_rust_windows.ps1` or on GitHub Actions via `.github/workflows/build-rust-windows.yml`.

