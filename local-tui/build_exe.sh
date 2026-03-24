#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# build_exe.sh — Build a standalone plex-poster binary for macOS / Linux.
#
# Usage:
#   chmod +x build_exe.sh
#   ./build_exe.sh
#
# The resulting binary is written to dist/plex-poster.
# Copy it to any directory on your $PATH, e.g.:
#   sudo cp dist/plex-poster /usr/local/bin/
# Then run from anywhere with:  plex-poster
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

# ── Virtual environment ──────────────────────────────────────────────────────
if [ ! -f ".venv/bin/activate" ]; then
    echo "Creating virtual environment..."
    python3 -m venv .venv
fi

# shellcheck disable=SC1091
source .venv/bin/activate

# ── Dependencies ─────────────────────────────────────────────────────────────
echo "Installing dependencies..."
pip install --quiet ".[dev]"

# ── Build ─────────────────────────────────────────────────────────────────────
echo "Building plex-poster..."
pyinstaller plex-poster.spec --noconfirm

echo ""
echo "============================================================"
echo " Build complete!"
echo " Binary: $(pwd)/dist/plex-poster"
echo ""
echo " To run from anywhere, copy it to a directory on your PATH:"
echo "   sudo cp dist/plex-poster /usr/local/bin/"
echo " Then open any terminal and type:  plex-poster"
echo "============================================================"
