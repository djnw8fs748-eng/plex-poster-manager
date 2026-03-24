@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM build_exe.bat — Build a standalone plex-poster.exe for Windows.
REM
REM Usage:
REM   1.  Open a terminal in this folder.
REM   2.  Run:  build_exe.bat
REM   3.  Copy  dist\plex-poster.exe  to any folder on your PATH
REM             (e.g. C:\Users\<you>\bin\ or C:\Windows\System32\)
REM   4.  Open a new terminal anywhere and type:  plex-poster
REM ─────────────────────────────────────────────────────────────────────────────

setlocal

REM ── Make sure a virtual environment exists ───────────────────────────────────
if not exist ".venv\Scripts\activate.bat" (
    echo Creating virtual environment...
    python -m venv .venv
    if errorlevel 1 (
        echo ERROR: Could not create virtual environment. Is Python installed?
        exit /b 1
    )
)

REM ── Activate the virtual environment ─────────────────────────────────────────
call .venv\Scripts\activate.bat

REM ── Install / upgrade dependencies (including PyInstaller) ───────────────────
echo Installing dependencies...
pip install --quiet ".[dev]"
if errorlevel 1 (
    echo ERROR: pip install failed.
    exit /b 1
)

REM ── Build the executable ─────────────────────────────────────────────────────
echo Building plex-poster.exe...
pyinstaller plex-poster.spec --noconfirm
if errorlevel 1 (
    echo ERROR: PyInstaller build failed.
    exit /b 1
)

echo.
echo ============================================================
echo  Build complete!
echo  Executable: %CD%\dist\plex-poster.exe
echo.
echo  To run from anywhere, copy it to a folder on your PATH:
echo    copy dist\plex-poster.exe C:\Windows\System32\
echo  Then open any terminal and type:  plex-poster
echo ============================================================

endlocal
