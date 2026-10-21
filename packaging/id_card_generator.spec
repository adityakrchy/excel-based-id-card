# -*- mode: python ; coding: utf-8 -*-
"""
PyInstaller specification for Bulk ID Card Generator.
Builds a standalone Windows x64 desktop application without console window.
"""

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Determine repository root
# PyInstaller executes spec files without __file__ in globals, but injects SPECPATH
try:
    root_dir = Path(SPECPATH).resolve().parent
except NameError:
    root_dir = Path.cwd().resolve()
src_dir = root_dir / "src"

# Data files to bundle
datas = [
    (str(src_dir / "id_card_generator" / "templates" / "builtins"), "templates/builtins"),
    (str(src_dir / "id_card_generator" / "resources" / "styles"), "resources/styles"),
    (str(src_dir / "id_card_generator" / "resources" / "icons"), "resources/icons"),
    (str(src_dir / "id_card_generator" / "resources" / "fonts"), "resources/fonts"),
    (str(src_dir / "id_card_generator" / "resources" / "assets"), "resources/assets"),
]

# Hidden imports
hidden_imports = [
    "PySide6.QtCore",
    "PySide6.QtGui",
    "PySide6.QtWidgets",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "PIL.ImageFont",
    "PIL.ImageOps",
    "PIL.ImageChops",
    "pandas",
    "openpyxl",
    "xlrd",
    "pydantic",
    "platformdirs",
    "reportlab",
]
hidden_imports += collect_submodules("id_card_generator")

a = Analysis(
    [str(root_dir / "main.py")],
    pathex=[str(src_dir)],
    binaries=[],
    datas=datas,
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "tkinter",
        "matplotlib",
        "scipy",
        "IPython",
        "notebook",
        "pytest",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="BulkIDCardGenerator",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # No console window for production GUI
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    # icon=str(src_dir / "id_card_generator" / "resources" / "icons" / "app.ico"),
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BulkIDCardGenerator",
)
