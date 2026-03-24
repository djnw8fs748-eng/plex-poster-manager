# Plex Local Poster Manager — TUI

A fast, keyboard-driven terminal UI for browsing and deleting the poster images
that Plex Media Server stores on your local disk.
Works on **Windows**, macOS, and Linux.

---

## Why use this?

Plex accumulates poster images in its local metadata cache every time you
refresh artwork or change a poster.  Over time this cache can grow to several
GB of unused files.  This tool lets you **browse the cache visually**, see
exactly which movie or TV show each poster belongs to, and delete the ones you
no longer need — all without editing any Plex database.

Optionally connect to your local Plex server so the app can identify the
**currently active poster** for each item and protect it from accidental
deletion.

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
extension-less files by reading their magic bytes.  It also reads the
`Info.xml` file inside each bundle to display the media item's title and year.

---

## Installation

There are two ways to install, depending on whether you want a self-contained
executable you can run from anywhere, or a standard Python package install.

---

### Option A — Standalone executable (recommended for most users)

This builds a single `plex-poster.exe` (Windows) or `plex-poster` binary
(macOS / Linux) that you can copy to any folder on your `PATH` and run from
any terminal — no Python environment needed afterwards.

**Requirements:** Python 3.10+ and Git (only needed for the build step).

#### Windows

```
git clone https://github.com/djnw8fs748-eng/plex-poster-manager.git
cd plex-poster-manager\local-tui
build_exe.bat
```

The script creates a virtual environment, installs all dependencies, and runs
PyInstaller automatically.  When it finishes, copy the executable to a folder
on your `PATH`:

```
copy dist\plex-poster.exe C:\Windows\System32\
```

Then open **any** terminal window and type:

```
plex-poster
```

#### macOS / Linux

```bash
git clone https://github.com/djnw8fs748-eng/plex-poster-manager.git
cd plex-poster-manager/local-tui
chmod +x build_exe.sh
./build_exe.sh
```

When the build finishes, copy the binary to a directory on your `$PATH`:

```bash
sudo cp dist/plex-poster /usr/local/bin/
```

Then run from any directory:

```bash
plex-poster
```

---

### Option B — Python package install (for developers / frequent updaters)

Use this if you want to run from source or update by pulling from Git.

**Requirements:** Python 3.10 or newer.

#### 1 — Clone

```
git clone https://github.com/djnw8fs748-eng/plex-poster-manager.git
cd plex-poster-manager/local-tui
```

#### 2 — Create a virtual environment and install

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install .
```

**Windows:**

```
python -m venv .venv
.venv\Scripts\activate
pip install .
```

> **Why a virtual environment?**  macOS (since Homebrew Python 3.12+) follows
> [PEP 668](https://peps.python.org/pep-0668/) and refuses `pip install`
> without a virtual environment.  Without one, `requests` is not installed,
> the Plex integration silently fails, and the **Plex** option disappears from
> the footer.  Always use the virtual environment.

#### 3 — Run

With the virtual environment **activated**:

```
plex-poster
```

Or without activating:

```bash
# macOS / Linux
.venv/bin/plex-poster

# Windows
.venv\Scripts\plex-poster
```

---

## Updating the app

### If you used Option A (standalone executable)

```
cd plex-poster-manager/local-tui
git pull
```

Then re-run `build_exe.bat` (Windows) or `./build_exe.sh` (macOS / Linux) and
copy the new binary over the old one.

### If you used Option B (Python package)

**Windows:**

```
cd path\to\plex-poster-manager\local-tui
git pull
.venv\Scripts\activate
pip install .
```

**macOS / Linux:**

```bash
cd path/to/plex-poster-manager/local-tui
git pull
source .venv/bin/activate
pip install .
```

> **Note:** You do not need to uninstall the old version first — `pip install .`
> upgrades in place.

---

## Interface overview

```
┌─ Plex Local Poster Manager ──────────────────────────────────────────────────────┐
│ Path: C:\...\Metadata  (342 posters)  ·  Plex: My Server (★ 23 protected)       │
├──────────────────────────────┬───────────────────────────────────────────────────┤
│ Folders                      │ The Dark Knight (2008)  (5 posters)               │
│                              │                                                   │
│ ▼ Metadata (342)             │    Filename       Media Item          Size        │
│   ▼ Movies (180)             │  ★  abc123        The Dark Knight…    2.4 MB      │
│     ▶ The Dark Knight (5)    │  ☐  def456        The Dark Knight…    1.8 MB      │
│     ▶ Inception (3)          │  ☑  ghi789        The Dark Knight…    3.1 MB      │
│   ▼ TV Shows (162)           │                                                   │
│     ▶ Breaking Bad (12)      │                                                   │
│     ▶ ...                    │                                                   │
│                              │                                                   │
├──────────────────────────────┴───────────────────────────────────────────────────┤
│ [Select All] [Select None] [Select All Unused]   47 posters selected (1.2 GB to free)  [Delete Selected] │
└──────────────────────────────────────────────────────────────────────────────────┘
  ^O Path  ^R Rescan  ^P Plex  Space Toggle  ^A All  ^U All Unused  Esc None  Del Delete  Q Quit
```

**Left panel** — the folder tree.  Navigate with `↑`/`↓` and expand/collapse
with `←`/`→` or `Enter`.  Bundle folders are shown with their media title and
year (e.g. `The Dark Knight (5)`) instead of the raw hash name.

**Right panel** — a table of poster files with filename, resolved media item
name, size, last-modified date, and relative path.

- `☐` — not selected
- `☑` — selected for deletion
- `★` — **active in Plex** — protected, cannot be deleted

**Action bar** — buttons, a running count of selected files, and the **total
disk space that will be freed** when you delete the current selection.

---

## Keyboard shortcuts

| Key | Action |
|---|---|
| `↑` / `↓` | Move cursor (tree or table, depending on focus) |
| `←` / `→` | Collapse / expand a tree node |
| `Enter` | Select a tree node **or** toggle a table row's selection |
| `Space` | Toggle the highlighted table row's selection |
| `Ctrl+A` | Select **all** non-protected posters in the current view |
| `Ctrl+U` | Select **all unused** posters across the entire scanned tree |
| `Esc` | Deselect all posters in the current view |
| `Delete` | Open the delete-confirmation dialog |
| `Ctrl+O` | Open the path-configuration dialog |
| `Ctrl+R` | Rescan the current path |
| `Ctrl+P` | Open the Plex connection dialog |
| `Ctrl+Q` or `Q` | Quit |

Click any row with the mouse to toggle its selection.

---

## Plex connection — protecting active posters

Press `Ctrl+P` to open the Plex connection dialog.  Once connected, the app
queries your Plex server after each scan to identify the **currently selected
poster** for every media item and marks those files with `★` in the table.

**Protected posters (`★`) cannot be selected or deleted.**  If you attempt to
toggle one, a warning is shown.  If somehow a protected file ends up in the
selection set (e.g. protection loaded after you selected), it is automatically
skipped during deletion and counted in the completion message.

### Finding your Plex token

Your Plex auth token is needed to authenticate with the server:

1. Open Plex Web and play any item.
2. In the URL bar you will see `X-Plex-Token=<token>` — copy that value.
3. Alternatively, follow the [official guide](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/).

> **Windows shortcut:** On Windows the app reads the token automatically from
> `%LOCALAPPDATA%\Plex Media Server\Preferences.xml` — the token field is
> usually pre-filled for you.

### Connection settings

| Field | Default | Notes |
|---|---|---|
| Server URL | `http://localhost:32400` | Change if Plex runs on another machine |
| Auth Token | Auto-detected on Windows | Paste manually on macOS / Linux — use `Ctrl+V` or click **Show** to verify |

Click **Test & Connect** to verify the connection before saving.  The info bar
at the top updates to show `Plex: <server name> (★ N protected)` once
connected.

The connection is **not** persisted between sessions — re-connect with
`Ctrl+P` each time you launch the app if you want protection enabled.

---

## Step-by-step: cleaning your poster cache

1. Launch the app: `plex-poster`
2. If the path dialog appears, enter your Plex metadata directory and press
   **Scan**.  (The Windows and macOS defaults are usually auto-detected.)
3. **Optional but recommended:** Press `Ctrl+P`, enter your server URL and
   token, and click **Test & Connect**.  Active posters will be marked `★` and
   protected from deletion.
4. Press `Ctrl+U` (**Select All Unused**) to select every non-protected poster
   across the entire library in one go.  The action bar shows the total size
   that will be freed (e.g. `142 posters selected (4.7 GB to free)`).
5. Review the count, then press `Delete` and confirm to remove everything.
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
| Bundle folders still show hash names | The bundle has no `Info.xml` — this is normal for older or incomplete metadata |
| `Permission denied` errors | On Windows, close Plex Media Server before deleting files from its cache |
| Plex connection fails | Verify the URL includes the port (`:32400`) and the token is correct |
| `★` protection not showing | Plex connection required — press `Ctrl+P` to connect |
| `Ctrl+V` doesn't paste the token | Click **Show** to reveal the field, then paste; the app reads directly from the OS clipboard |
| **Plex option missing from footer** | `requests` not installed — use a virtual environment (Option B step 2) or rebuild the exe (Option A) |
| `textual` not found | Activate the virtual environment and run `pip install .` |
| App display looks broken | Use a terminal that supports Unicode and at least 80 columns (Windows Terminal, iTerm2, etc.) |
| `build_exe.bat` fails with "Python not found" | Install Python 3.10+ and ensure it is on your `PATH` |
| PyInstaller build fails | Run `pip install ".[dev]"` inside the venv first, then retry |

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
- **Active poster protection** — when connected to Plex, the currently
  selected poster for each item is identified via the API and blocked from
  deletion entirely.
- **Space freed estimate** — the action bar shows the total size of all
  selected files in real time so you know exactly how much disk space will
  be recovered before you confirm.
- **Extensionless files** — Plex sometimes stores posters without a file
  extension.  The scanner detects these by reading their magic bytes (JPEG,
  PNG, WebP, GIF signatures).
- **Media titles** — resolved from `Info.xml` or the Plex SQLite database
  inside each `.bundle` directory at scan time.  No server connection is
  needed for this.
- After deleting cached posters, Plex will show the correct poster for each
  item because the *selected* poster information is stored in its SQLite
  database (`com.plexapp.plugins.library.db`), not in the image files.
