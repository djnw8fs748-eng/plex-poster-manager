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

import sys
from pathlib import Path
from typing import Optional, Set

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.reactive import reactive
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

from scanner import FolderNode, PosterFile, get_default_plex_path, scan_directory

# ── Selection indicator characters ──────────────────────────────────────────
_SEL = "☑"
_UNS = "☐"


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
        Binding("space", "toggle_selection", "Toggle", show=True),
        Binding("ctrl+a", "select_all", "All", show=True),
        Binding("escape", "select_none", "None", show=True),
        Binding("delete", "delete_selected", "Delete", show=True),
        Binding("ctrl+q,q", "quit", "Quit", show=True),
    ]

    # ── Instance state (not reactive — plain attributes to avoid issues
    #    with Textual's reactive + mutable containers) ─────────────────────

    def __init__(self) -> None:
        super().__init__()
        self._scan_path: Optional[Path] = None
        self._root_node: Optional[FolderNode] = None
        self._current_folder: Optional[FolderNode] = None
        # Set of absolute Path objects the user has marked for deletion.
        self._selected: Set[Path] = set()
        # Row key of the currently highlighted DataTable row.
        self._highlighted_key: Optional[str] = None
        # Ordered list of PosterFile objects currently visible in the table.
        self._visible_posters: list[PosterFile] = []

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
                    yield Label("0 posters selected", id="selection-status")
                    yield Button("Delete Selected", id="btn-delete", variant="error")
        yield Footer()

    def on_mount(self) -> None:
        # Set up DataTable columns with explicit keys for update_cell().
        table = self.query_one("#poster-table", DataTable)
        table.add_column("", key="sel", width=3)
        table.add_column("Filename", key="name", width=30)
        table.add_column("Size", key="size", width=10)
        table.add_column("Modified", key="date", width=17)
        table.add_column("Relative Path", key="relpath")

        self.query_one("#loading", LoadingIndicator).display = False
        self._update_delete_button()

        # Auto-detect Plex data directory and start scanning if it exists.
        default = get_default_plex_path()
        if default and default.exists():
            self._start_scan(default)
        else:
            self.push_screen(ConfigScreen(), self._on_path_chosen)

    # ── Scanning ─────────────────────────────────────────────────────────────

    def _start_scan(self, path: Path) -> None:
        self._scan_path = path
        self._selected.clear()
        self._visible_posters = []
        self.query_one("#info-bar", Static).update(
            f"[bold]Scanning:[/bold] {path}"
        )
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
        total = root.total_posters
        self.query_one("#info-bar", Static).update(
            f"[bold]Path:[/bold] {path}  [dim]({total} poster(s) found)[/dim]"
        )
        self._build_tree(root)
        self._end_scan()
        self.notify(f"Scan complete — {total} poster(s) found.", timeout=4)

    def _end_scan(self) -> None:
        self.query_one("#loading", LoadingIndicator).display = False
        self.query_one("#folder-tree", Tree).display = True

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
            label = f"{child.name} [dim]({count})[/dim]"
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
            f"[bold]{folder.name}[/bold]  [dim]{count} poster(s)[/dim]"
        )

        for poster in posters:
            indicator = _SEL if poster.path in self._selected else _UNS
            rel = self._rel(poster.path)
            table.add_row(
                indicator,
                poster.name,
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
        """Mark every poster in the current view as selected."""
        for poster in self._visible_posters:
            self._selected.add(poster.path)
        self._refresh_indicators()
        self._update_status()

    def action_select_none(self) -> None:
        """Clear all selections in the current view."""
        for poster in self._visible_posters:
            self._selected.discard(poster.path)
        self._refresh_indicators()
        self._update_status()

    def _refresh_indicators(self) -> None:
        table = self.query_one("#poster-table", DataTable)
        for poster in self._visible_posters:
            indicator = _SEL if poster.path in self._selected else _UNS
            try:
                table.update_cell(
                    str(poster.path), "sel", indicator, update_width=False
                )
            except Exception:
                pass

    def _update_status(self) -> None:
        count = len(self._selected)
        noun = "poster" if count == 1 else "posters"
        self.query_one("#selection-status", Label).update(
            f"[bold]{count}[/bold] {noun} selected"
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
            self._do_delete()

    @work(thread=True)
    def _do_delete(self) -> None:
        """Delete selected files on a background thread."""
        paths = list(self._selected)
        deleted = 0
        failed: list[str] = []

        for path in paths:
            try:
                path.unlink()
                deleted += 1
            except OSError as exc:
                failed.append(f"{path.name}: {exc}")

        self.call_from_thread(self._after_delete, deleted, failed)

    def _after_delete(self, deleted: int, failed: list[str]) -> None:
        self._selected.clear()

        noun = "poster" if deleted == 1 else "posters"
        msg = f"Deleted {deleted} {noun}."
        if failed:
            msg += f"  {len(failed)} error(s)."
            for err in failed[:3]:
                self.notify(err, severity="error", timeout=6)

        severity = "warning" if failed else "information"
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
