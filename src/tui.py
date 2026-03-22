#!/usr/bin/env python3
"""
Plex Poster Manager — interactive TUI
~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~~
A Textual terminal UI for configuring and running the Plex Poster Manager
without touching environment variables or a shell.

Launch (from the project root):
    python src/tui.py
    # or with PYTHONPATH set:
    PYTHONPATH=src python src/tui.py
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Optional

# Ensure src/ is importable when running from the project root.
sys.path.insert(0, str(Path(__file__).parent))

try:
    from textual import on, work
    from textual.app import App, ComposeResult
    from textual.binding import Binding
    from textual.containers import Horizontal, Vertical
    from textual.widgets import (
        Button,
        Footer,
        Header,
        Input,
        Label,
        RichLog,
        Rule,
        Static,
        Switch,
    )
except ImportError:
    print(
        "textual is required to run the TUI.\n"
        "Install it with:  pip install 'textual>=0.70.0'",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    from rich.text import Text as RichText
except ImportError:
    RichText = None  # type: ignore[assignment,misc]

from config import Config
from plex_client import PlexClient
from cleaner import PosterCleaner

# Try to load python-dotenv for pre-filling form fields from .env.
try:
    from dotenv import dotenv_values

    _HAS_DOTENV = True
except ImportError:
    _HAS_DOTENV = False


# ── Logging colours ───────────────────────────────────────────────────────────

_LEVEL_STYLE: dict[str, str] = {
    "DEBUG": "dim white",
    "INFO": "white",
    "WARNING": "yellow",
    "ERROR": "red",
    "CRITICAL": "bold red",
}

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}


# ── Custom logging handler ────────────────────────────────────────────────────


class _TUIHandler(logging.Handler):
    """
    Logging handler that forwards formatted records to a callback.

    The callback is invoked from the worker thread via
    ``App.call_from_thread``, so it is safe to update Textual widgets
    inside it.
    """

    _FMT = logging.Formatter(
        "%(asctime)s [%(levelname)-8s] %(message)s",
        datefmt="%H:%M:%S",
    )

    def __init__(self, callback) -> None:
        super().__init__()
        self.setFormatter(self._FMT)
        self._callback = callback

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self._callback(self.format(record), record.levelname)
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════════
# Application
# ═══════════════════════════════════════════════════════════════════════════════


class PlexManagerTUI(App):
    """
    Interactive TUI for the Plex Poster Manager.

    Left panel  — connection / option form.
    Right panel — live log output from the cleaner.
    """

    TITLE = "Plex Poster Manager"

    CSS = """
    /* ── Status bar ───────────────────────────────────────────────────────── */
    #status-bar {
        height: 1;
        background: $primary-darken-3;
        color: $text;
        padding: 0 1;
        dock: top;
    }

    /* ── Main split ───────────────────────────────────────────────────────── */
    #main {
        height: 1fr;
        margin-top: 1;
    }

    /* ── Config panel ─────────────────────────────────────────────────────── */
    #config-panel {
        width: 46;
        min-width: 36;
        border-right: solid $primary-darken-2;
        padding: 1 2;
    }
    .section-title {
        text-style: bold;
        color: $accent;
        margin-bottom: 1;
    }
    .field-row {
        height: auto;
        margin-bottom: 1;
        align: left middle;
    }
    .field-label {
        width: 11;
        color: $text-muted;
    }
    .field-label-wide {
        width: 11;
        color: $text-muted;
    }
    #config-panel Input {
        width: 1fr;
    }
    #dry-run-hint {
        margin-left: 1;
        color: $text-muted;
    }
    #rule-spacer {
        margin: 1 0;
    }

    /* ── Buttons ──────────────────────────────────────────────────────────── */
    #buttons {
        margin-top: 2;
        height: auto;
        align: left middle;
    }
    #buttons Button {
        margin-right: 1;
    }

    /* ── Log panel ────────────────────────────────────────────────────────── */
    #log-panel {
        width: 1fr;
        padding: 0 1;
    }
    .log-title {
        text-style: bold;
        color: $accent;
        padding: 1 0;
    }
    #run-log {
        height: 1fr;
        border: solid $primary-darken-2;
        padding: 0 1;
    }
    """

    BINDINGS = [
        Binding("ctrl+r", "start_run", "Run", show=True),
        Binding("ctrl+t", "test_connection", "Test", show=True),
        Binding("ctrl+l", "clear_log", "Clear log", show=True),
        Binding("ctrl+q,q", "quit", "Quit", show=True),
    ]

    def __init__(self) -> None:
        super().__init__()
        self._is_running = False

    # ── Compose ──────────────────────────────────────────────────────────────

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static(
            "Configure connection settings then press  Ctrl+T  to test  "
            "or  Ctrl+R  to run.",
            id="status-bar",
        )
        with Horizontal(id="main"):
            # Left: configuration form
            with Vertical(id="config-panel"):
                yield Static("Connection", classes="section-title")
                with Horizontal(classes="field-row"):
                    yield Label("URL", classes="field-label")
                    yield Input(
                        placeholder="http://192.168.1.10:32400",
                        id="plex-url",
                    )
                with Horizontal(classes="field-row"):
                    yield Label("Token", classes="field-label")
                    yield Input(
                        placeholder="your-plex-token",
                        password=True,
                        id="plex-token",
                    )
                yield Rule(id="rule-spacer")
                yield Static("Options", classes="section-title")
                with Horizontal(classes="field-row"):
                    yield Label("Libraries", classes="field-label")
                    yield Input(
                        placeholder="all  (or comma-separated names / IDs)",
                        id="libraries",
                    )
                with Horizontal(classes="field-row"):
                    yield Label("Dry Run", classes="field-label")
                    yield Switch(value=True, id="dry-run")
                    yield Label(
                        "[dim]preview only — nothing deleted[/dim]",
                        id="dry-run-hint",
                    )
                with Horizontal(classes="field-row"):
                    yield Label("Log Level", classes="field-label")
                    yield Input(value="INFO", id="log-level")
                with Horizontal(id="buttons"):
                    yield Button(
                        "Test Connection", id="btn-test", variant="default"
                    )
                    yield Button("▶  Start", id="btn-start", variant="primary")

            # Right: live log output
            with Vertical(id="log-panel"):
                yield Static("Output Log", classes="log-title")
                yield RichLog(id="run-log", highlight=False, markup=False)

        yield Footer()

    def on_mount(self) -> None:
        self._load_env()

    # ── .env pre-population ───────────────────────────────────────────────────

    def _load_env(self) -> None:
        """Pre-fill form fields from a .env file if one is found."""
        if not _HAS_DOTENV:
            return
        env_path = Path(".env")
        if not env_path.exists():
            return

        values = dotenv_values(env_path)
        if url := values.get("PLEX_URL"):
            self.query_one("#plex-url", Input).value = url
        if token := values.get("PLEX_TOKEN"):
            self.query_one("#plex-token", Input).value = token
        if libs := values.get("PLEX_LIBRARIES"):
            self.query_one("#libraries", Input).value = libs
        if dry := values.get("DRY_RUN"):
            self.query_one("#dry-run", Switch).value = dry.lower() in (
                "true",
                "1",
                "yes",
            )
        if level := values.get("LOG_LEVEL"):
            self.query_one("#log-level", Input).value = level.upper()

        self._set_status(
            "Settings pre-filled from .env — review then press Ctrl+R to run."
        )

    # ── Form validation ───────────────────────────────────────────────────────

    def _build_config(self) -> Optional[Config]:
        """
        Read form fields and build a Config.  Returns None and logs validation
        errors if any field is invalid.
        """
        url = self.query_one("#plex-url", Input).value.strip().rstrip("/")
        token = self.query_one("#plex-token", Input).value.strip()
        libs_raw = self.query_one("#libraries", Input).value.strip()
        dry_run = self.query_one("#dry-run", Switch).value
        log_level = (
            self.query_one("#log-level", Input).value.strip().upper() or "INFO"
        )

        errors: list[str] = []
        if not url:
            errors.append("Plex URL is required.")
        elif not (url.startswith("http://") or url.startswith("https://")):
            errors.append("URL must start with http:// or https://")
        if not token:
            errors.append("Plex Token is required.")
        if log_level not in _VALID_LOG_LEVELS:
            errors.append(
                f"Log Level must be one of: {', '.join(sorted(_VALID_LOG_LEVELS))}"
            )

        if errors:
            for err in errors:
                self._append_log(f"✗ {err}", "ERROR")
            return None

        libraries = [lib.strip() for lib in libs_raw.split(",") if lib.strip()]
        return Config(
            plex_url=url,
            plex_token=token,
            plex_libraries=libraries,
            dry_run=dry_run,
            schedule_cron=None,
            log_level=log_level,
        )

    # ── Actions ───────────────────────────────────────────────────────────────

    def action_test_connection(self) -> None:
        config = self._build_config()
        if config:
            self._run_test(config)

    def action_start_run(self) -> None:
        config = self._build_config()
        if config:
            self._begin_run(config)

    def action_clear_log(self) -> None:
        self.query_one("#run-log", RichLog).clear()

    @on(Button.Pressed, "#btn-test")
    def _btn_test(self) -> None:
        self.action_test_connection()

    @on(Button.Pressed, "#btn-start")
    def _btn_start(self) -> None:
        self.action_start_run()

    @on(Switch.Changed, "#dry-run")
    def _dry_run_toggled(self, event: Switch.Changed) -> None:
        hint = self.query_one("#dry-run-hint", Label)
        if event.value:
            hint.update("[dim]preview only — nothing deleted[/dim]")
        else:
            hint.update(
                "[bold yellow]live mode — posters WILL be deleted from Plex[/bold yellow]"
            )

    # ── Connection test ───────────────────────────────────────────────────────

    def _run_test(self, config: Config) -> None:
        self.query_one("#run-log", RichLog).clear()
        self._set_status("Testing connection…")
        self._test_worker(config)

    @work(exclusive=True, thread=True)
    def _test_worker(self, config: Config) -> None:
        try:
            client = PlexClient(config.plex_url, config.plex_token)
            libs = client.get_libraries()
            names = [lib.get("title", "?") for lib in libs]
            msg = (
                f"✓ Connected.  Found {len(libs)} librar(ies): "
                + ", ".join(names)
            )
            self.call_from_thread(self._append_log, msg, "INFO")
            self.call_from_thread(
                self._set_status, f"Connected — {len(libs)} librar(ies) found."
            )
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(
                self._append_log, f"✗ Connection failed: {exc}", "ERROR"
            )
            self.call_from_thread(
                self._set_status, "Connection failed — check URL and token."
            )

    # ── Main cleaning run ─────────────────────────────────────────────────────

    def _begin_run(self, config: Config) -> None:
        if self._is_running:
            self.notify("A run is already in progress.", severity="warning")
            return
        self._is_running = True
        self.query_one("#run-log", RichLog).clear()
        self.query_one("#btn-start", Button).disabled = True
        self.query_one("#btn-test", Button).disabled = True
        dry = " [DRY RUN]" if config.dry_run else ""
        self._set_status(f"Running{dry}…")
        self._run_worker(config)

    @work(thread=True)
    def _run_worker(self, config: Config) -> None:
        """Run PosterCleaner in a thread, routing its logs into the TUI."""
        handler = _TUIHandler(
            lambda msg, lvl: self.call_from_thread(self._append_log, msg, lvl)
        )
        root_logger = logging.getLogger()
        saved_level = root_logger.level
        root_logger.addHandler(handler)
        root_logger.setLevel(
            getattr(logging, config.log_level, logging.INFO)
        )

        try:
            if config.plex_url.startswith("http://"):
                self.call_from_thread(
                    self._append_log,
                    "WARNING: HTTP is unencrypted — your token travels in plaintext.",
                    "WARNING",
                )
            client = PlexClient(config.plex_url, config.plex_token)
            PosterCleaner(client, config).run()
        except RuntimeError as exc:
            self.call_from_thread(self._append_log, f"Fatal: {exc}", "ERROR")
        except Exception as exc:  # noqa: BLE001
            self.call_from_thread(
                self._append_log, f"Unexpected error: {exc}", "ERROR"
            )
        finally:
            root_logger.removeHandler(handler)
            root_logger.setLevel(saved_level)

        self.call_from_thread(self._on_run_done, config.dry_run)

    def _on_run_done(self, dry_run: bool) -> None:
        self._is_running = False
        self.query_one("#btn-start", Button).disabled = False
        self.query_one("#btn-test", Button).disabled = False
        note = " (dry run)" if dry_run else ""
        self._set_status(f"Run complete{note}.")
        self.notify("Run complete!", timeout=4)

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _append_log(self, msg: str, level: str) -> None:
        log = self.query_one("#run-log", RichLog)
        style = _LEVEL_STYLE.get(level, "white")
        if RichText is not None:
            # Use a Rich Text object to avoid markup injection from log messages
            # that contain square brackets (e.g. "[MovieTitle]").
            log.write(RichText(msg, style=style))
        else:
            log.write(msg)

    def _set_status(self, msg: str) -> None:
        self.query_one("#status-bar", Static).update(msg)


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    PlexManagerTUI().run()


if __name__ == "__main__":
    main()
