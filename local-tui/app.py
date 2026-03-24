#!/usr/bin/env python3
"""
Plex Local Poster Manager — TUI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
A terminal UI for browsing and selectively deleting poster images stored
in Plex Media Server's local metadata cache.

Run with:
    python app.py

or, if installed as an entry-point:
    plex-poster-tui
"""

from __future__ import annotations

import platform
import subprocess
from pathlib import Path
from typing import Optional, Set

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    LoadingIndicator,
    Static,
    Tree,
)
from textual.widgets._tree import TreeNode

from plex import PlexAuthError, PlexClient, PlexConnectionError, PlexError, find_local_token
from scanner import FolderNode, PosterFile, get_default_plex_path, scan_directory

# ── Selection / status indicator characters ─────────────────────────────────
_SEL = "☑"
_UNS = "☐"
_ACT = "[bold green]★[/bold green]"   # Plex active poster — protected


def _format_size(num_bytes: int) -> str:
    """Return a human-readable byte size string (e.g. '1.4 GB')."""
    size = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


# ═══════════════════════════════════════════════════════════════════════════════
# Modal — Config / path picker
# ═══════════════════════════════════════════════════════════════════════════════


class ConfigScreen(ModalScreen[Optional[Path]]):
    """Pop-up for choosing the directory to scan."""

    DEFAULT_CSS = """
    ConfigScreen {
        align: center middle;
    }
    ConfigScreen > #dialog {
        width: 76;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    ConfigScreen Label {
        margin-bottom: 1;
    }
    ConfigScreen Input {
        margin-bottom: 1;
    }
    ConfigScreen #hint {
        color: $text-muted;
        margin-bottom: 1;
    }
    ConfigScreen #buttons {
        align: right middle;
        height: auto;
        margin-top: 1;
    }
    ConfigScreen Button {
        margin-left: 1;
    }
    """

    def __init__(self, current_path: Optional[Path] = None) -> None:
        super().__init__()
        self._current_path = current_path

    def compose(self) -> ComposeResult:
        default = str(self._current_path or get_default_plex_path() or "")
        with Container(id="dialog"):
            yield Label("[bold]Configure Scan Path[/bold]")
            yield Label(
                "Enter the path to your Plex [bold]Metadata[/bold] folder "
                "or any directory that contains poster images.",
                id="hint",
            )
            yield Input(
                value=default,
                placeholder=(
                    r"C:\Users\You\AppData\Local\Plex Media Server\Metadata"
                ),
                id="path-input",
            )
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button("Scan", variant="primary", id="confirm")

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#confirm")
    def _confirm(self) -> None:
        self._submit()

    @on(Input.Submitted)
    def _submitted(self, _event: Input.Submitted) -> None:
        self._submit()

    def _submit(self) -> None:
        raw = self.query_one("#path-input", Input).value.strip()
        self.dismiss(Path(raw) if raw else None)


# ═══════════════════════════════════════════════════════════════════════════════
# Modal — Delete confirmation
# ═══════════════════════════════════════════════════════════════════════════════


class ConfirmDeleteScreen(ModalScreen[bool]):
    """Warn the user before permanently deleting files."""

    DEFAULT_CSS = """
    ConfirmDeleteScreen {
        align: center middle;
    }
    ConfirmDeleteScreen > #dialog {
        width: 58;
        height: auto;
        border: thick $error;
        background: $surface;
        padding: 1 2;
    }
    ConfirmDeleteScreen #msg {
        text-align: center;
        margin-bottom: 1;
    }
    ConfirmDeleteScreen #buttons {
        align: center middle;
        height: auto;
        margin-top: 1;
    }
    ConfirmDeleteScreen Button {
        margin: 0 1;
    }
    """

    def __init__(self, count: int) -> None:
        super().__init__()
        self._count = count

    def compose(self) -> ComposeResult:
        noun = "poster" if self._count == 1 else "posters"
        with Container(id="dialog"):
            yield Label(
                f"[bold red]Delete {self._count} {noun} from disk?[/bold red]\n\n"
                f"This will [bold]permanently remove[/bold] {self._count} {noun}.\n"
                f"[dim]This action cannot be undone.[/dim]",
                id="msg",
            )
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                yield Button(
                    f"Delete {self._count} {noun}",
                    variant="error",
                    id="confirm",
                )

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(False)

    @on(Button.Pressed, "#confirm")
    def _confirm(self) -> None:
        self.dismiss(True)


# ── OS clipboard helper ──────────────────────────────────────────────────────


def _read_os_clipboard() -> str:
    """
    Read text from the OS clipboard using platform-native commands.

    Textual's built-in ``action_paste`` reads from an internal clipboard that
    is only populated when the user copies *within* Textual.  Tokens copied
    from a browser or another application end up in the OS clipboard, which
    this helper reaches via a subprocess call.  Returns an empty string on
    any failure so the caller can silently fall back.
    """
    try:
        system = platform.system()
        if system == "Windows":
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", "Get-Clipboard"],
                capture_output=True,
                text=True,
                timeout=3,
            )
            return result.stdout.strip()
        if system == "Darwin":
            result = subprocess.run(
                ["pbpaste"], capture_output=True, text=True, timeout=3
            )
            return result.stdout.strip()
        # Linux — try xclip then xsel
        for cmd in (
            ["xclip", "-selection", "clipboard", "-o"],
            ["xsel", "--clipboard", "--output"],
        ):
            try:
                result = subprocess.run(
                    cmd, capture_output=True, text=True, timeout=3
                )
                if result.returncode == 0:
                    return result.stdout.strip()
            except FileNotFoundError:
                continue
    except Exception:  # noqa: BLE001
        pass
    return ""


# ═══════════════════════════════════════════════════════════════════════════════
# Modal — Plex connection
# ═══════════════════════════════════════════════════════════════════════════════


class PlexConnectScreen(ModalScreen[Optional[tuple]]):
    """
    Optional Plex server connection.

    Returns one of:
      None                      — cancelled (no change)
      ("disconnect",)           — user wants to disconnect
      (PlexClient, str)         — (client, server_friendly_name)
    """

    DEFAULT_CSS = """
    PlexConnectScreen {
        align: center middle;
    }
    PlexConnectScreen > #dialog {
        width: 76;
        height: auto;
        border: thick $primary;
        background: $surface;
        padding: 1 2;
    }
    PlexConnectScreen Label {
        margin-bottom: 1;
    }
    PlexConnectScreen .field-label {
        color: $text-muted;
        margin-bottom: 0;
    }
    PlexConnectScreen Input {
        margin-bottom: 1;
    }
    PlexConnectScreen #token-row {
        height: auto;
        margin-bottom: 1;
    }
    PlexConnectScreen #token-row Input {
        width: 1fr;
        margin-bottom: 0;
    }
    PlexConnectScreen #token-row Button {
        width: auto;
        margin-left: 1;
        margin-bottom: 0;
    }
    PlexConnectScreen #status {
        height: 1;
        margin-bottom: 1;
    }
    PlexConnectScreen #buttons {
        align: right middle;
        height: auto;
        margin-top: 1;
    }
    PlexConnectScreen Button {
        margin-left: 1;
    }
    """

    def __init__(self, current_client: Optional[PlexClient] = None) -> None:
        super().__init__()
        self._current_client = current_client
        self._token_visible = False

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label("[bold]Plex Server Connection[/bold]")
            yield Label(
                "Connect to your local Plex server to identify the active poster "
                "for each item so it is never accidentally deleted.",
                id="hint",
            )
            yield Label("Server URL", classes="field-label")
            yield Input(
                value="http://localhost:32400",
                placeholder="http://192.168.1.10:32400",
                id="url-input",
            )
            yield Label("Auth Token", classes="field-label")
            with Horizontal(id="token-row"):
                yield Input(
                    value=find_local_token(),
                    placeholder="Paste your X-Plex-Token here",
                    password=True,
                    id="token-input",
                )
                yield Button("Show", id="toggle-token")
            yield Label("", id="status")
            with Horizontal(id="buttons"):
                yield Button("Cancel", id="cancel")
                if self._current_client is not None:
                    yield Button("Disconnect", variant="warning", id="disconnect")
                yield Button("Test & Connect", variant="primary", id="connect")

    @on(Button.Pressed, "#cancel")
    def _cancel(self) -> None:
        self.dismiss(None)

    @on(Button.Pressed, "#disconnect")
    def _disconnect(self) -> None:
        self.dismiss(("disconnect",))

    def action_paste(self) -> None:
        """Paste from the OS clipboard into whichever input is focused.

        Textual's default action_paste reads from an internal clipboard that
        is empty when text was copied outside the app (e.g. a token from a
        browser).  This override reads from the real OS clipboard so the user
        can paste a Plex token with Ctrl+V just as they would anywhere else.
        """
        focused = self.focused
        if not isinstance(focused, Input):
            return
        text = _read_os_clipboard()
        if not text:
            # Fall back to Textual's internal clipboard if OS read fails.
            text = self.app.clipboard
        if text:
            focused.insert_text_at_cursor(text)

    @on(Button.Pressed, "#toggle-token")
    def _toggle_token(self) -> None:
        self._token_visible = not self._token_visible
        inp = self.query_one("#token-input", Input)
        inp.password = not self._token_visible
        self.query_one("#toggle-token", Button).label = (
            "Hide" if self._token_visible else "Show"
        )

    @on(Button.Pressed, "#connect")
    def _connect(self) -> None:
        url = self.query_one("#url-input", Input).value.strip()
        token = self.query_one("#token-input", Input).value.strip()
        if not url:
            self._set_status("[red]Enter a server URL.[/red]")
            return
        self._set_status("[dim]Connecting…[/dim]")
        self.query_one("#connect", Button).disabled = True
        self._do_test(url, token)

    @work(thread=True)
    def _do_test(self, url: str, token: str) -> None:
        try:
            client = PlexClient(base_url=url, token=token)
            name = client.test_connection()
            self.app.call_from_thread(self._on_success, client, name)
        except PlexAuthError as exc:
            self.app.call_from_thread(self._on_error, str(exc))
        except PlexConnectionError as exc:
            self.app.call_from_thread(self._on_error, str(exc))
        except PlexError as exc:
            self.app.call_from_thread(self._on_error, str(exc))

    def _on_success(self, client: PlexClient, name: str) -> None:
        self.dismiss((client, name))

    def _on_error(self, message: str) -> None:
        self._set_status(f"[red]{message}[/red]")
        self.query_one("#connect", Button).disabled = False

    def _set_status(self, markup: str) -> None:
        self.query_one("#status", Label).update(markup)


# ═══════════════════════════════════════════════════════════════════════════════
# Main application
# ═══════════════════════════════════════════════════════════════════════════════


class PlexPosterApp(App):
    """
    Browse Plex's local metadata cache and delete unwanted poster images.

    Layout
    ------
    Left panel  — folder tree (navigate with arrow keys, Enter to expand).
    Right panel — poster table for the selected folder (space/enter to toggle
                  selection, then Delete or the button to remove files).
    """

    TITLE = "Plex Local Poster Manager"
    ENABLE_COMMAND_PALETTE = False  # Ctrl+P is used for Plex connection

    CSS = """
    /* ── Top info bar ─────────────────────────────────────────────────────── */
    #info-bar {
        height: 1;
        background: $primary-darken-3;
        color: $text;
        padding: 0 1;
        dock: top;
    }

    /* ── Main split layout ────────────────────────────────────────────────── */
    #main {
        height: 1fr;
        margin-top: 1;
    }

    /* ── Left tree panel ──────────────────────────────────────────────────── */
    #left-panel {
        width: 34;
        min-width: 20;
        border-right: solid $primary-darken-2;
        padding: 0 1;
    }
    #tree-header {
        color: $text-muted;
        padding: 0 0 1 0;
        text-style: bold;
    }
    #folder-tree {
        height: 1fr;
    }
    #loading {
        height: 1fr;
        display: none;
    }

    /* ── Right poster panel ───────────────────────────────────────────────── */
    #right-panel {
        width: 1fr;
        padding: 0 1;
    }
    #panel-title {
        padding: 0 0 1 0;
        color: $text;
    }
    #poster-table {
        height: 1fr;
    }

    /* ── Action bar ───────────────────────────────────────────────────────── */
    #action-bar {
        height: auto;
        align: left middle;
        padding: 1 0 0 0;
        border-top: solid $primary-darken-2;
    }
    #action-bar Button {
        margin-right: 1;
    }
    #selection-status {
        width: 1fr;
        text-align: right;
        color: $text-muted;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+o", "configure", "Path", show=True),
        Binding("ctrl+r", "rescan", "Rescan", show=True),
        Binding("ctrl+p", "plex_connect", "Plex", show=True),
        Binding("space", "toggle_selection", "Toggle", show=True),
        Binding("ctrl+a", "select_all", "All", show=True),
        Binding("ctrl+u", "select_all_unused", "All Unused", show=True),
        Binding("escape", "select_none", "None", show=True),
        Binding("delete", "delete_selected", "Delete", show=True),
        Binding("ctrl+q,q", "quit", "Quit", show=True),
    ]

    # ── Instance state (not reactive — plain attributes to avoid issues
    #    with Textual's reactive + mutable containers) ─────────────────────

    def __init__(self, initial_path: Optional[Path] = None) -> None:
        super().__init__()
        self._scan_path: Optional[Path] = initial_path
        self._root_node: Optional[FolderNode] = None
        self._current_folder: Optional[FolderNode] = None
        # Set of absolute Path objects the user has marked for deletion.
        self._selected: Set[Path] = set()
        # Row key of the currently highlighted DataTable row.
        self._highlighted_key: Optional[str] = None
        # Ordered list of PosterFile objects currently visible in the table.
        self._visible_posters: list[PosterFile] = []
        # Plex API client (optional — set via Ctrl+P).
        self._plex_client: Optional[PlexClient] = None
        self._plex_server_name: str = ""
        # Paths of files currently selected as active in Plex (protected).
        self._plex_protected: Set[Path] = set()
        # path → byte size cache, rebuilt after each scan for O(1) size lookups.
        self._size_cache: dict[Path, int] = {}

    # ── UI construction ─────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("[dim]No path configured — press Ctrl+O to set a path[/dim]", id="info-bar")
        with Horizontal(id="main"):
            with Vertical(id="left-panel"):
                yield Static("Folders", id="tree-header")
                yield Tree("(no scan)", id="folder-tree")
                yield LoadingIndicator(id="loading")
            with Vertical(id="right-panel"):
                yield Label(
                    "[dim]Select a folder in the tree to view its posters.[/dim]",
                    id="panel-title",
                )
                yield DataTable(
                    id="poster-table",
                    cursor_type="row",
                    zebra_stripes=True,
                )
                with Horizontal(id="action-bar"):
                    yield Button("Select All", id="btn-all", variant="default")
                    yield Button("Select None", id="btn-none", variant="default")
                    yield Button("Select All Unused", id="btn-all-unused", variant="warning")
                    yield Label("0 posters selected", id="selection-status")
                    yield Button("Delete Selected", id="btn-delete", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        # Set up DataTable columns with explicit keys for update_cell().
        table = self.query_one("#poster-table", DataTable)
        table.add_column("", key="sel", width=3)
        table.add_column("Filename", key="name", width=28)
        table.add_column("Media Item", key="media", width=26)
        table.add_column("Size", key="size", width=9)
        table.add_column("Modified", key="date", width=17)
        table.add_column("Relative Path", key="relpath")

        self.query_one("#loading", LoadingIndicator).display = False
        self._update_delete_button()

        # Use initial_path (e.g. from tests), then auto-detect, then ask.
        if self._scan_path:
            self._start_scan(self._scan_path)
        else:
            default = get_default_plex_path()
            if default and default.exists():
                self._start_scan(default)
            else:
                self.push_screen(ConfigScreen(), self._on_path_chosen)

    # ── Scanning ─────────────────────────────────────────────────────────────

    def _start_scan(self, path: Path) -> None:
        self._scan_path = path
        self._selected.clear()
        self._plex_protected.clear()
        self._visible_posters = []
        self.query_one("#info-bar", Static).update(f"[bold]Scanning:[/bold] {path}")
        self.query_one("#loading", LoadingIndicator).display = True
        self.query_one("#folder-tree", Tree).display = False
        # Clear the poster table while we rescan.
        self.query_one("#poster-table", DataTable).clear()
        self.query_one("#panel-title", Label).update(
            "[dim]Scanning… please wait.[/dim]"
        )
        self._update_status()
        self._do_scan(path)

    @work(exclusive=True, thread=True)
    def _do_scan(self, path: Path) -> None:
        """Background worker — runs scan_directory on a thread."""
        try:
            root = scan_directory(path, check_magic_bytes=True)
            self.call_from_thread(self._apply_result, path, root)
        except (FileNotFoundError, NotADirectoryError) as exc:
            self.call_from_thread(
                self.notify, str(exc), severity="error", timeout=8
            )
            self.call_from_thread(self._end_scan)
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(
                self.notify,
                f"Unexpected scan error: {exc}",
                severity="error",
                timeout=8,
            )
            self.call_from_thread(self._end_scan)

    def _apply_result(self, path: Path, root: FolderNode) -> None:
        self._root_node = root
        self._size_cache = {pf.path: pf.size for pf in root.all_posters()}
        total = root.total_posters
        self._update_info_bar()
        self._build_tree(root)
        self._end_scan()
        self.notify(f"Scan complete — {total} poster(s) found.", timeout=4)
        if self._plex_client:
            self._fetch_plex_selections()

    def _end_scan(self) -> None:
        self.query_one("#loading", LoadingIndicator).display = False
        self.query_one("#folder-tree", Tree).display = True

    def _update_info_bar(self) -> None:
        """Rewrite the top info bar with current scan path and Plex status."""
        if not self._scan_path or not self._root_node:
            return
        total = self._root_node.total_posters
        plex_part = (
            f"  [dim]·[/dim]  [bold]Plex:[/bold] {self._plex_server_name} "
            f"[dim](★ {len(self._plex_protected)} protected)[/dim]"
            if self._plex_client
            else ""
        )
        self.query_one("#info-bar", Static).update(
            f"[bold]Path:[/bold] {self._scan_path}  "
            f"[dim]({total} poster(s) found)[/dim]{plex_part}"
        )

    # ── Plex integration ─────────────────────────────────────────────────────

    def _iter_bundle_nodes(self, node: FolderNode):
        """Yield every FolderNode that has a Plex ratingKey (i.e. is a bundle)."""
        if node.rating_key:
            yield node
        for child in node.children:
            yield from self._iter_bundle_nodes(child)

    @work(exclusive=True, thread=True)
    def _fetch_plex_selections(self) -> None:
        """
        Background worker: for every scanned bundle with a ratingKey, ask Plex
        which poster is currently selected and mark the matching disk file.
        """
        if not self._plex_client or not self._root_node:
            return

        self.call_from_thread(
            self.notify, "Fetching active posters from Plex…", timeout=3
        )

        protected: Set[Path] = set()

        for bundle_node in self._iter_bundle_nodes(self._root_node):
            try:
                api_posters = self._plex_client.get_posters(bundle_node.rating_key)
            except Exception:  # noqa: BLE001
                continue

            for api_poster in api_posters:
                if not api_poster.selected:
                    continue
                short = api_poster.short_key
                bundle_posters = bundle_node.all_posters()
                matched = False
                # Pass 1 — exact filename match.
                # Works for upload://posters/{hash} keys where the disk file
                # is stored extensionless with the hash as its name.
                for pf in bundle_posters:
                    if pf.path.name == short:
                        pf.is_plex_selected = True
                        protected.add(pf.path)
                        matched = True
                if not matched:
                    # Pass 2 — stem match.
                    # Handles external-URL keys (TMDB, Fanart, etc.) where
                    # short_key is e.g. "abc.jpg" but the disk file is stored
                    # extensionless as "abc".
                    stem = Path(short).stem
                    if stem:
                        for pf in bundle_posters:
                            if pf.path.stem == stem:
                                pf.is_plex_selected = True
                                protected.add(pf.path)
                                matched = True

        self.call_from_thread(self._after_plex_fetch, protected)

    def _after_plex_fetch(self, protected: Set[Path]) -> None:
        self._plex_protected = protected
        # Drop any user-selected paths that are now known to be active in Plex.
        self._selected -= protected
        self._update_info_bar()
        self.notify(
            f"Plex: {len(protected)} active poster(s) marked as protected.",
            timeout=5,
        )
        if self._current_folder:
            self._populate_table(self._current_folder)

    def action_plex_connect(self) -> None:
        self.push_screen(
            PlexConnectScreen(current_client=self._plex_client),
            self._on_plex_result,
        )

    def _on_plex_result(self, result: Optional[tuple]) -> None:
        if result is None:
            return
        if result == ("disconnect",):
            self._plex_client = None
            self._plex_server_name = ""
            self._plex_protected.clear()
            # Clear is_plex_selected on all poster files in the tree.
            if self._root_node:
                for pf in self._root_node.all_posters():
                    pf.is_plex_selected = False
            self._update_info_bar()
            if self._current_folder:
                self._populate_table(self._current_folder)
            self.notify("Plex disconnected.", timeout=3)
            return
        client, name = result
        self._plex_client = client
        self._plex_server_name = name
        self.notify(f"Connected to Plex: {name}", timeout=4)
        self._fetch_plex_selections()

    # ── Tree building ────────────────────────────────────────────────────────

    def _build_tree(self, root: FolderNode) -> None:
        tree = self.query_one("#folder-tree", Tree)
        tree.clear()
        tree.root.set_label(
            f"[bold]{root.name}[/bold] [dim]({root.total_posters})[/dim]"
        )
        tree.root.data = root
        self._add_tree_children(tree.root, root)
        tree.root.expand()

    def _add_tree_children(self, parent: TreeNode, folder: FolderNode) -> None:
        """Recursively add FolderNode children as tree nodes."""
        for child in folder.children:
            count = child.total_posters
            label = f"{child.display_name} [dim]({count})[/dim]"
            child_node = parent.add(label, data=child)
            if child.children:
                self._add_tree_children(child_node, child)

    # ── Tree events ──────────────────────────────────────────────────────────

    def on_tree_node_selected(self, event: Tree.NodeSelected) -> None:
        folder: Optional[FolderNode] = event.node.data
        if folder is not None:
            self._current_folder = folder
            self._populate_table(folder)

    # ── Table population ─────────────────────────────────────────────────────

    def _populate_table(self, folder: FolderNode) -> None:
        table = self.query_one("#poster-table", DataTable)
        table.clear()

        posters = folder.all_posters()
        self._visible_posters = posters

        count = len(posters)
        self.query_one("#panel-title", Label).update(
            f"[bold]{folder.display_name}[/bold]  [dim]{count} poster(s)[/dim]"
        )

        for poster in posters:
            if poster.is_plex_selected:
                indicator = _ACT
            elif poster.path in self._selected:
                indicator = _SEL
            else:
                indicator = _UNS
            rel = self._rel(poster.path)
            table.add_row(
                indicator,
                poster.name,
                poster.media_title or "—",
                poster.size_human,
                poster.modified_str,
                str(rel.parent) if rel != poster.path else str(poster.path.parent),
                key=str(poster.path),
            )

        self._update_status()

    def _rel(self, path: Path) -> Path:
        """Return *path* relative to the scan root, or the absolute path."""
        if self._scan_path:
            try:
                return path.relative_to(self._scan_path)
            except ValueError:
                pass
        return path

    # ── Table events & selection ─────────────────────────────────────────────

    def on_data_table_row_highlighted(
        self, event: DataTable.RowHighlighted
    ) -> None:
        self._highlighted_key = (
            str(event.row_key.value) if event.row_key else None
        )

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Enter / row-click toggles the selection indicator."""
        if event.row_key:
            self._toggle(str(event.row_key.value))

    def action_toggle_selection(self) -> None:
        """Space bar toggles the highlighted row."""
        if self._highlighted_key:
            self._toggle(self._highlighted_key)

    def _toggle(self, path_str: str) -> None:
        path = Path(path_str)
        if path in self._plex_protected:
            self.notify(
                "This is Plex's active poster — it cannot be selected for deletion.",
                severity="warning",
                timeout=4,
            )
            return
        table = self.query_one("#poster-table", DataTable)
        if path in self._selected:
            self._selected.discard(path)
            indicator = _UNS
        else:
            self._selected.add(path)
            indicator = _SEL
        try:
            table.update_cell(path_str, "sel", indicator, update_width=False)
        except Exception:  # row may not exist after a rescan
            pass
        self._update_status()

    def action_select_all(self) -> None:
        """Mark every non-protected poster in the current view as selected."""
        for poster in self._visible_posters:
            if poster.path not in self._plex_protected:
                self._selected.add(poster.path)
        self._refresh_indicators()
        self._update_status()

    def action_select_all_unused(self) -> None:
        """Mark every non-protected poster across the entire tree as selected.

        Unlike Select All (which only covers the current folder view), this
        walks all scanned posters so the user can queue up a full library
        clean-up in one keystroke — then review or delete in one pass.
        """
        if not self._root_node:
            self.notify("No scan loaded — press Ctrl+O to scan a path.", severity="warning", timeout=4)
            return
        all_posters = self._root_node.all_posters()
        added = 0
        for poster in all_posters:
            if poster.path not in self._plex_protected:
                self._selected.add(poster.path)
                added += 1
        self._refresh_indicators()
        self._update_status()
        self.notify(
            f"{added} unused poster(s) selected across all folders.",
            timeout=4,
        )

    def action_select_none(self) -> None:
        """Clear all selections in the current view."""
        for poster in self._visible_posters:
            self._selected.discard(poster.path)
        self._refresh_indicators()
        self._update_status()

    def _refresh_indicators(self) -> None:
        table = self.query_one("#poster-table", DataTable)
        for poster in self._visible_posters:
            if poster.is_plex_selected:
                indicator = _ACT
            elif poster.path in self._selected:
                indicator = _SEL
            else:
                indicator = _UNS
            try:
                table.update_cell(
                    str(poster.path), "sel", indicator, update_width=False
                )
            except Exception:
                pass

    def _update_status(self) -> None:
        count = len(self._selected)
        noun = "poster" if count == 1 else "posters"
        total_bytes = sum(self._size_cache.get(p, 0) for p in self._selected)
        size_str = f"  [dim]({_format_size(total_bytes)} to free)[/dim]" if count else ""
        self.query_one("#selection-status", Label).update(
            f"[bold]{count}[/bold] {noun} selected{size_str}"
        )
        self._update_delete_button()

    def _update_delete_button(self) -> None:
        self.query_one("#btn-delete", Button).disabled = len(self._selected) == 0

    # ── Deletion ─────────────────────────────────────────────────────────────

    def action_delete_selected(self) -> None:
        if not self._selected:
            self.notify("Nothing selected.", severity="warning", timeout=3)
            return
        self.push_screen(ConfirmDeleteScreen(len(self._selected)), self._on_confirm)

    def _on_confirm(self, confirmed: bool) -> None:
        if confirmed:
            # Snapshot both sets on the main thread to avoid races with
            # concurrent mutations from _after_plex_fetch / _start_scan.
            self._do_delete(list(self._selected), set(self._plex_protected))

    @work(thread=True)
    def _do_delete(self, paths: list, protected: set) -> None:
        """Delete selected files on a background thread, skipping protected ones."""
        deleted = 0
        skipped = 0
        failed: list[str] = []

        for path in paths:
            if path in protected:
                skipped += 1
                continue
            try:
                path.unlink()
                deleted += 1
            except OSError as exc:
                failed.append(f"{path.name}: {exc}")

        self.call_from_thread(self._after_delete, deleted, skipped, failed)

    def _after_delete(self, deleted: int, skipped: int, failed: list[str]) -> None:
        self._selected.clear()

        noun = "poster" if deleted == 1 else "posters"
        msg = f"Deleted {deleted} {noun}."
        if skipped:
            msg += f"  {skipped} active Plex poster(s) skipped."
        if failed:
            msg += f"  {len(failed)} error(s)."
            for err in failed[:3]:
                self.notify(err, severity="error", timeout=6)

        severity = "warning" if (failed or skipped) else "information"
        self.notify(msg, severity=severity, timeout=5)

        # Rescan so the tree and table reflect the deletions.
        if self._scan_path:
            self._start_scan(self._scan_path)

    # ── Other actions ────────────────────────────────────────────────────────

    def action_configure(self) -> None:
        self.push_screen(ConfigScreen(self._scan_path), self._on_path_chosen)

    def _on_path_chosen(self, path: Optional[Path]) -> None:
        if path:
            self._start_scan(path)

    def action_rescan(self) -> None:
        if self._scan_path:
            self._start_scan(self._scan_path)
        else:
            self.push_screen(ConfigScreen(), self._on_path_chosen)

    # ── Button handlers ───────────────────────────────────────────────────────

    @on(Button.Pressed, "#btn-all")
    def _btn_all(self) -> None:
        self.action_select_all()

    @on(Button.Pressed, "#btn-none")
    def _btn_none(self) -> None:
        self.action_select_none()

    @on(Button.Pressed, "#btn-all-unused")
    def _btn_all_unused(self) -> None:
        self.action_select_all_unused()

    @on(Button.Pressed, "#btn-delete")
    def _btn_delete(self) -> None:
        self.action_delete_selected()


# ═══════════════════════════════════════════════════════════════════════════════
# Entry point
# ═══════════════════════════════════════════════════════════════════════════════


def main() -> None:
    app = PlexPosterApp()
    app.run()


if __name__ == "__main__":
    main()
