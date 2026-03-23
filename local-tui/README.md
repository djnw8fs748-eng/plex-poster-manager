# Plex Local Poster Manager — TUI

A fast, keyboard-driven terminal UI for browsing and deleting the poster images
that Plex Media Server stores on your local disk.
Works on **Windows**, macOS, and Linux.

---

## Why use this?

Plex accumulates poster images in its local metadata cache every time you
refresh artwork or change a poster.  Over time this cache can grow to several
GB of unused files.  This tool lets you **browse the cache visually**, select
exactly the files you want to remove, and delete them — all without editing
any Plex database or touching a live Plex server.

---

## How Plex stores local posters

By default Plex Media Server saves all metadata (including every poster it has
ever downloaded or uploaded for an item) inside a platform-specific data
directory:

| Platform | Default path |
|---|---|
| Windows | `%LOCALAPPDATA%\Plex Media Server\Metadata\` |
| macOS | `~/Library/Application Support/Plex Media Server/Metadata/` |
| Linux | `/var/lib/plexmediaserver/Library/Application Support/Plex Media Server/Metadata/` |

Inside that folder, images are nested inside `*.bundle` directories, sometimes
**without file extensions** (Plex's internal cache format).  This tool detects
both regular image files (`.jpg`, `.png`, `.webp`, `.tbn`, …) **and**
extension-less files by reading their magic bytes.

---

## Requirements

- **Python 3.10 or newer** (Python 3.12+ recommended)
- All Python dependencies are installed automatically by `pip install .` — no manual dependency management needed

No Plex server connection is required — everything is read directly from disk.

---

## Installation

### 1 — Clone

```
git clone https://github.com/djnw8fs748-eng/plex-poster-manager.git
cd plex-poster-manager/local-tui
```

### 2 — Install (all dependencies included)

```
pip install .
```

This installs `textual`, `requests`, and everything else the app needs, and
adds a `plex-poster` command to your PATH.

> **Tip (Windows):** Open a Command Prompt or PowerShell window, `cd` into the
> `local-tui` folder, then run the pip command above.  Python 3.10+ must be in
> your `PATH`.

> **Tip:** Use a virtual environment to keep dependencies isolated:
> ```
> python -m venv .venv
> source .venv/bin/activate   # Windows: .venv\Scripts\activate
> pip install .
> ```

### 3 — Run

```
plex-poster
```

Or without installing:

```
python app.py
```

The app will **auto-detect** your Plex metadata folder on startup.  If it
cannot find one it will immediately open the path-configuration dialog so you
can enter the correct location.

---

## Interface overview

```
┌─ Plex Local Poster Manager ──────────────────────────────────────────────────┐
│ Path: C:\Users\You\AppData\Local\Plex Media Server\Metadata  (342 posters)  │
├──────────────────────────────┬───────────────────────────────────────────────┤
│ Folders                      │ Metadata  (342 posters)                       │
│                              │                                               │
│ ▼ Metadata (342)             │    Filename              Size      Modified   │
│   ▼ Movies (180)             │  ☐  poster_a.jpg         2.4 MB    2024-01-15 │
│     ▶ abc123.bundle (3)      │  ☑  poster_b.jpg         1.8 MB    2024-01-10 │
│     ▶ def456.bundle (5)      │  ☑  0                    3.1 MB    2023-12-05 │
│   ▼ TV Shows (162)           │                                               │
│     ▶ ghi789.bundle (12)     │                                               │
│     ▶ ...                    │                                               │
│                              │                                               │
├──────────────────────────────┴───────────────────────────────────────────────┤
│ [Select All] [Select None]            2 posters selected  [Delete Selected]  │
└──────────────────────────────────────────────────────────────────────────────┘
  ^O Path   ^R Rescan   Space Toggle   ^A All   Esc None   Del Delete   Q Quit
```

**Left panel** — the folder tree.  Navigate with `↑`/`↓` and expand/collapse
with `←`/`→` or `Enter`.  Each folder shows a poster count in parentheses.
Selecting a folder populates the right panel with **all posters in that folder
and every sub-folder**.

**Right panel** — a table of poster files showing filename, size, last-modified
date, and relative path.  The `☐`/`☑` column shows the current selection
state.

**Action bar** — buttons and a running count of selected files at the bottom.

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| `↑` / `↓` | Move cursor (tree or table, depending on focus) |
| `←` / `→` | Collapse / expand a tree node |
| `Enter` | Select a tree node **or** toggle a table row's selection |
| `Space` | Toggle the highlighted table row's selection |
| `Ctrl+A` | Select **all** posters in the current view |
| `Esc` | Deselect all posters in the current view |
| `Delete` | Open the delete-confirmation dialog |
| `Ctrl+O` | Open the path-configuration dialog |
| `Ctrl+R` | Rescan the current path |
| `Ctrl+Q` or `Q` | Quit |

Click any row with the mouse to toggle its selection.

---

## Step-by-step: cleaning your poster cache

1. Launch the app: `plex-poster` (or `python app.py` if you skipped `pip install .`)
2. If the path dialog appears, enter your Plex metadata directory and press
   **Scan**.  (The Windows default is usually auto-detected.)
3. Expand `Movies` or `TV Shows` in the left tree and click a bundle folder to
   see its cached posters on the right.
4. Use `Space`/`Enter` to select files you want to delete, or press `Ctrl+A`
   to select everything in the current view.
5. Press `Delete` (or click **Delete Selected**) and confirm when prompted.
6. The app rescans automatically and updates the tree and table.

> **Tip:** Plex will re-download metadata the next time you refresh a library
> section, so deleting cached posters is safe — your selections in Plex are
> stored in its database, not in the image files.

---

## Scanning a custom directory

Press `Ctrl+O` at any time to open the path dialog.  You can point the app at:

- A specific library sub-folder, e.g. `…\Metadata\Movies\`
- Your entire Plex metadata folder (the default)
- Any other directory that contains image files

---

## Troubleshooting

| Problem | Solution |
|---|---|
| "Path not found" error on launch | Press `Ctrl+O` and manually enter the correct metadata path |
| Posters are not showing up | Make sure you are pointing at the **Metadata** folder, not the Plex data root |
| `Permission denied` errors | On Windows, close Plex Media Server before deleting files from its cache |
| `textual` not found | Run `pip install .` from the `local-tui` folder |
| `requests` not found | Run `pip install .` from the `local-tui` folder |
| App display looks broken | Use a terminal that supports Unicode and at least 80 columns (Windows Terminal, iTerm2, etc.) |

---

## Running the tests

```bash
cd plex-poster-manager/local-tui
pip install ".[dev]"
pytest
```

---

## Notes

- **Safe by design** — the app only calls `Path.unlink()` on files you
  explicitly select and confirm.  It never touches the Plex database.
- **No network access** — everything is local filesystem I/O.
- **Extensionless files** — Plex sometimes stores posters without a file
  extension.  The scanner detects these by reading their magic bytes (JPEG,
  PNG, WebP, GIF signatures).
- After deleting cached posters, Plex will show the correct poster for each
  item because the *selected* poster information is stored in its SQLite
  database (`com.plexapp.plugins.library.db`), not in the image files.
