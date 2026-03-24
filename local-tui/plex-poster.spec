# PyInstaller spec for plex-poster standalone executable.
#
# Build with:
#   Windows : build_exe.bat
#   macOS   : ./build_exe.sh
#   Manual  : pyinstaller plex-poster.spec

import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

# Collect all Textual CSS / data files so the TUI renders correctly.
textual_datas = collect_data_files("textual")

a = Analysis(
    ["app.py"],
    pathex=[str(Path(__file__).parent)],
    binaries=[],
    datas=textual_datas,
    hiddenimports=collect_submodules("textual"),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="plex-poster",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,          # TUI app — keep the console window
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
