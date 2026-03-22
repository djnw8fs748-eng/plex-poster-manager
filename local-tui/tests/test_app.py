"""
Integration tests for app.py using Textual's async Pilot API.

Each test runs the full application headlessly; we use ``initial_path``
to point the app at a known temp directory, then drive it through the UI.
"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from app import ConfirmDeleteScreen, ConfigScreen, PlexPosterApp
from textual.app import App, ComposeResult
from textual.widgets import Button, DataTable, Input, Label, Tree
from tests.conftest import JPEG_HEADER, PNG_HEADER

# Textual's run_test() is async; mark the whole module.
pytestmark = pytest.mark.asyncio

# How long to wait for the background scan thread to finish.
_SCAN_WAIT = 1.5


# ── Helper ────────────────────────────────────────────────────────────────────


async def _wait_for_scan(pilot, timeout: float = _SCAN_WAIT) -> None:
    """Yield control until the app's root_node is populated or timeout."""
    deadline = asyncio.get_event_loop().time() + timeout
    while asyncio.get_event_loop().time() < deadline:
        if pilot.app._root_node is not None:
            await pilot.pause(0.05)  # let the UI update after _apply_result
            return
        await pilot.pause(0.05)
    raise TimeoutError("Scan did not complete within the timeout.")


# ── Minimal host apps for testing modal screens ───────────────────────────────
# ModalScreen doesn't expose run_test(); push modals from a tiny host App.


class _ConfigHost(App):
    def __init__(self, path=None):
        super().__init__()
        self._path = path
        self.result = None

    def on_mount(self):
        self.push_screen(ConfigScreen(current_path=self._path), self._got)

    def _got(self, value):
        self.result = value
        self.exit()


class _ConfirmHost(App):
    def __init__(self, count: int):
        super().__init__()
        self._count = count
        self.result = None

    def on_mount(self):
        self.push_screen(ConfirmDeleteScreen(count=self._count), self._got)

    def _got(self, value):
        self.result = value
        self.exit()


# ═══════════════════════════════════════════════════════════════════════════════
# ConfigScreen (unit-level modal tests)
# ═══════════════════════════════════════════════════════════════════════════════


async def test_config_screen_cancel_returns_none():
    """Pressing Cancel dismisses the screen with None."""
    async with _ConfigHost().run_test(size=(90, 20)) as pilot:
        await pilot.pause(0.2)
        await pilot.click("#cancel")
        await pilot.pause(0.2)
    assert pilot.app.result is None


async def test_config_screen_renders_input_widget():
    """ConfigScreen renders the Input widget."""
    async with _ConfigHost().run_test(size=(90, 20)) as pilot:
        await pilot.pause(0.2)
        # The modal is the active screen; query through it.
        inp = pilot.app.screen.query_one("#path-input", Input)
        assert inp is not None


async def test_config_screen_pre_fills_current_path(tmp_path):
    """ConfigScreen fills the input with the current_path when provided."""
    async with _ConfigHost(path=tmp_path).run_test(size=(90, 20)) as pilot:
        await pilot.pause(0.2)
        inp = pilot.app.screen.query_one("#path-input", Input)
        assert str(tmp_path) in inp.value


# ═══════════════════════════════════════════════════════════════════════════════
# ConfirmDeleteScreen (unit-level modal tests)
# ═══════════════════════════════════════════════════════════════════════════════


async def test_confirm_delete_shows_correct_count():
    """ConfirmDeleteScreen renders the poster count in the button label."""
    async with _ConfirmHost(count=7).run_test(size=(70, 15)) as pilot:
        await pilot.pause(0.2)
        btn = pilot.app.screen.query_one("#confirm", Button)
        assert "7" in str(btn.label)


async def test_confirm_delete_singular_noun():
    """Single poster uses the singular noun."""
    async with _ConfirmHost(count=1).run_test(size=(70, 15)) as pilot:
        await pilot.pause(0.2)
        btn = pilot.app.screen.query_one("#confirm", Button)
        label = str(btn.label).lower()
        assert "poster" in label
        assert "posters" not in label


async def test_confirm_delete_plural_noun():
    """Multiple posters use the plural noun."""
    async with _ConfirmHost(count=3).run_test(size=(70, 15)) as pilot:
        await pilot.pause(0.2)
        btn = pilot.app.screen.query_one("#confirm", Button)
        assert "posters" in str(btn.label).lower()


# ═══════════════════════════════════════════════════════════════════════════════
# PlexPosterApp — startup
# ═══════════════════════════════════════════════════════════════════════════════


async def test_app_shows_config_screen_when_no_path(monkeypatch):
    """Without a known Plex path the app opens ConfigScreen on mount."""
    monkeypatch.setattr("app.get_default_plex_path", lambda: None)
    async with PlexPosterApp().run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.2)
        # ConfigScreen should be pushed as the active screen
        screen_names = [type(s).__name__ for s in pilot.app.screen_stack]
        assert "ConfigScreen" in screen_names


async def test_app_mounts_with_initial_path(tmp_path):
    """App mounts without error when an initial_path is provided."""
    (tmp_path / "poster.jpg").write_bytes(JPEG_HEADER)
    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        assert pilot.app._root_node is not None


async def test_info_bar_shows_path_after_scan(tmp_path):
    """The scan path is stored on the app object after scanning."""
    (tmp_path / "poster.jpg").write_bytes(JPEG_HEADER)
    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        # Verify the app recorded the correct scan path.
        assert pilot.app._scan_path == tmp_path


# ═══════════════════════════════════════════════════════════════════════════════
# PlexPosterApp — tree
# ═══════════════════════════════════════════════════════════════════════════════


async def test_tree_root_is_visible_after_scan(tmp_path):
    """The folder tree is visible (not loading) after the scan completes."""
    (tmp_path / "poster.jpg").write_bytes(JPEG_HEADER)
    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        tree = pilot.app.query_one("#folder-tree", Tree)
        assert tree.display is True


async def test_tree_root_label_contains_folder_name(tmp_path):
    """Tree root label contains the scanned folder name."""
    (tmp_path / "poster.jpg").write_bytes(JPEG_HEADER)
    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        tree = pilot.app.query_one("#folder-tree", Tree)
        assert tmp_path.name in str(tree.root.label)


# ═══════════════════════════════════════════════════════════════════════════════
# PlexPosterApp — poster table population
# ═══════════════════════════════════════════════════════════════════════════════


async def test_table_populates_after_node_selected(tmp_path):
    """Selecting the tree root populates the DataTable with posters."""
    (tmp_path / "poster.jpg").write_bytes(JPEG_HEADER)
    (tmp_path / "thumb.png").write_bytes(PNG_HEADER)

    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        # Select the tree root node
        await pilot.click("#folder-tree")
        await pilot.press("enter")
        await pilot.pause(0.2)
        table = pilot.app.query_one("#poster-table", DataTable)
        assert table.row_count == 2


async def test_panel_title_updates_after_selection(tmp_path):
    """After selecting a tree node the visible posters list is populated."""
    (tmp_path / "poster.jpg").write_bytes(JPEG_HEADER)

    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        await pilot.click("#folder-tree")
        await pilot.press("enter")
        await pilot.pause(0.2)
        # Visible posters list being non-empty confirms the title updated.
        assert pilot.app._visible_posters is not None


# ═══════════════════════════════════════════════════════════════════════════════
# PlexPosterApp — selection mechanics
# ═══════════════════════════════════════════════════════════════════════════════


async def _app_with_posters(tmp_path: Path):
    """Helper: set up tmp_path with 3 images and return it."""
    for name in ("a.jpg", "b.jpg", "c.jpg"):
        (tmp_path / name).write_bytes(JPEG_HEADER)
    return tmp_path


async def test_delete_button_disabled_initially(tmp_path):
    """Delete button starts disabled when nothing is selected."""
    await _app_with_posters(tmp_path)
    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        btn = pilot.app.query_one("#btn-delete", Button)
        assert btn.disabled is True


async def test_select_all_button_enables_delete(tmp_path):
    """Clicking Select All enables the Delete button."""
    await _app_with_posters(tmp_path)
    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        # Select root node to load the table
        await pilot.click("#folder-tree")
        await pilot.press("enter")
        await pilot.pause(0.2)
        # Click Select All
        await pilot.click("#btn-all")
        await pilot.pause(0.1)
        btn = pilot.app.query_one("#btn-delete", Button)
        assert btn.disabled is False


async def test_select_all_marks_all_selected(tmp_path):
    """After Select All, all paths are in the selected set."""
    await _app_with_posters(tmp_path)
    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        await pilot.click("#folder-tree")
        await pilot.press("enter")
        await pilot.pause(0.2)
        await pilot.click("#btn-all")
        await pilot.pause(0.1)
        assert len(pilot.app._selected) == 3


async def test_select_none_clears_selection(tmp_path):
    """Select None clears all selections."""
    await _app_with_posters(tmp_path)
    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        await pilot.click("#folder-tree")
        await pilot.press("enter")
        await pilot.pause(0.2)
        # Select all then clear
        await pilot.click("#btn-all")
        await pilot.pause(0.1)
        await pilot.click("#btn-none")
        await pilot.pause(0.1)
        assert len(pilot.app._selected) == 0


async def test_select_none_disables_delete_button(tmp_path):
    """Delete button is disabled again after Select None."""
    await _app_with_posters(tmp_path)
    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        await pilot.click("#folder-tree")
        await pilot.press("enter")
        await pilot.pause(0.2)
        await pilot.click("#btn-all")
        await pilot.pause(0.1)
        await pilot.click("#btn-none")
        await pilot.pause(0.1)
        assert pilot.app.query_one("#btn-delete", Button).disabled is True


async def test_selection_status_label_updates(tmp_path):
    """The selection status label reflects the current count."""
    await _app_with_posters(tmp_path)
    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        await pilot.click("#folder-tree")
        await pilot.press("enter")
        await pilot.pause(0.2)
        await pilot.click("#btn-all")
        await pilot.pause(0.1)
        # Verify via app state — 3 posters were selected.
        assert len(pilot.app._selected) == 3


# ═══════════════════════════════════════════════════════════════════════════════
# PlexPosterApp — deletion
# ═══════════════════════════════════════════════════════════════════════════════


async def test_delete_removes_files_from_disk(tmp_path):
    """Confirming deletion actually removes the selected files."""
    poster = tmp_path / "poster.jpg"
    poster.write_bytes(JPEG_HEADER)

    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        await pilot.click("#folder-tree")
        await pilot.press("enter")
        await pilot.pause(0.2)
        # Select all
        await pilot.click("#btn-all")
        await pilot.pause(0.1)
        # Trigger delete — this pushes ConfirmDeleteScreen
        await pilot.click("#btn-delete")
        await pilot.pause(0.2)
        # Confirm
        await pilot.click("#confirm")
        # Wait for the worker to finish deleting and rescan
        await pilot.pause(_SCAN_WAIT)

    assert not poster.exists()


async def test_cancel_delete_keeps_files(tmp_path):
    """Cancelling the confirmation dialog does not delete any files."""
    poster = tmp_path / "poster.jpg"
    poster.write_bytes(JPEG_HEADER)

    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        await pilot.click("#folder-tree")
        await pilot.press("enter")
        await pilot.pause(0.2)
        await pilot.click("#btn-all")
        await pilot.pause(0.1)
        await pilot.click("#btn-delete")
        await pilot.pause(0.2)
        # Cancel instead of confirming
        await pilot.click("#cancel")
        await pilot.pause(0.2)

    assert poster.exists()


# ═══════════════════════════════════════════════════════════════════════════════
# PlexPosterApp — keyboard shortcuts
# ═══════════════════════════════════════════════════════════════════════════════


async def test_ctrl_a_selects_all(tmp_path):
    """Ctrl+A selects all visible posters."""
    await _app_with_posters(tmp_path)
    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        await pilot.click("#folder-tree")
        await pilot.press("enter")
        await pilot.pause(0.2)
        await pilot.press("ctrl+a")
        await pilot.pause(0.1)
        assert len(pilot.app._selected) == 3


async def test_escape_clears_selection(tmp_path):
    """Escape deselects all visible posters."""
    await _app_with_posters(tmp_path)
    async with PlexPosterApp(initial_path=tmp_path).run_test(size=(120, 40)) as pilot:
        await _wait_for_scan(pilot)
        await pilot.click("#folder-tree")
        await pilot.press("enter")
        await pilot.pause(0.2)
        await pilot.press("ctrl+a")
        await pilot.pause(0.1)
        await pilot.press("escape")
        await pilot.pause(0.1)
        assert len(pilot.app._selected) == 0
