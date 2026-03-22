"""
plex.py — Plex Media Server API client for local use.

Designed to connect to a Plex server running on the same Windows machine
at http://localhost:32400.  On Windows the auth token is read automatically
from Plex's Preferences.xml so the user rarely needs to paste it manually.
"""

from __future__ import annotations

import os
import platform
import re
import urllib.parse
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import requests


# ═══════════════════════════════════════════════════════════════════════════════
# Data model
# ═══════════════════════════════════════════════════════════════════════════════


@dataclass
class PlexPoster:
    """A single poster entry returned by the Plex API."""

    key: str
    selected: bool       # True  → this is the poster Plex is displaying
    provider: str        # e.g. "com.plexapp.agents.themoviedb", "local"
    rating_key: str      # parent item's rating key (numeric string)

    @property
    def source_label(self) -> str:
        """Short human-readable source name shown in the table."""
        k = self.key.lower()
        p = self.provider.lower()
        if "upload://" in k or "upload%3a%2f%2f" in k:
            return "local"
        for token in ("tmdb", "themoviedb"):
            if token in k or token in p:
                return "TMDB"
        if "fanart" in k or "fanart" in p:
            return "Fanart"
        if "tvdb" in k or "tvdb" in p:
            return "TVDB"
        # Fall back to the last segment of the dotted provider string.
        return p.split(".")[-1] if p else "?"

    @property
    def short_key(self) -> str:
        """Shortened key suitable for display in a narrow column."""
        if "url=" in self.key:
            parsed = urllib.parse.urlparse(self.key)
            qs = urllib.parse.parse_qs(parsed.query)
            inner = qs.get("url", [""])[0]
            if inner:
                return inner.split("/")[-1]
        return self.key.split("/")[-1] or self.key


@dataclass
class PlexItem:
    """A media item (movie, TV show, etc.) from a Plex library."""

    rating_key: str
    title: str
    year: Optional[int] = None
    type: str = "movie"           # movie | show | artist | photo
    posters: List[PlexPoster] = field(default_factory=list)
    posters_loaded: bool = False

    @property
    def display_title(self) -> str:
        return f"{self.title} ({self.year})" if self.year else self.title

    @property
    def selected_poster(self) -> Optional[PlexPoster]:
        return next((p for p in self.posters if p.selected), None)

    @property
    def deletable_count(self) -> int:
        """Number of non-selected posters (candidates for deletion)."""
        return sum(1 for p in self.posters if not p.selected)


@dataclass
class PlexLibrary:
    """A Plex library section (Movies, TV Shows, etc.)."""

    key: str            # numeric section key
    title: str
    type: str           # movie | show | artist | photo
    items: List[PlexItem] = field(default_factory=list)
    items_loaded: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Exceptions
# ═══════════════════════════════════════════════════════════════════════════════


class PlexError(Exception):
    """Base class for Plex API errors."""


class PlexAuthError(PlexError):
    """Raised when the server returns 401 or 403."""


class PlexConnectionError(PlexError):
    """Raised when the server cannot be reached at all."""


# ═══════════════════════════════════════════════════════════════════════════════
# Client
# ═══════════════════════════════════════════════════════════════════════════════


class PlexClient:
    """
    Thin HTTP wrapper around the Plex Media Server API.

    All methods are synchronous and intended to be called from a worker
    thread so the Textual UI stays responsive.
    """

    DEFAULT_URL: str = "http://localhost:32400"

    def __init__(self, base_url: str = DEFAULT_URL, token: str = "") -> None:
        self.base_url = base_url.rstrip("/")
        self._session = requests.Session()
        self._session.headers.update(
            {"X-Plex-Token": token, "Accept": "application/json"}
        )

    # ── Public API ────────────────────────────────────────────────────────────

    def test_connection(self) -> str:
        """
        Verify the connection and token.  Returns the server's friendly name.
        Raises PlexAuthError or PlexConnectionError on failure.
        """
        try:
            data = self._get("/")
            return data.get("MediaContainer", {}).get(
                "friendlyName", "Plex Media Server"
            )
        except requests.HTTPError as exc:
            code = exc.response.status_code if exc.response else None
            if code in (401, 403):
                raise PlexAuthError(
                    "Authentication failed — your Plex token is invalid or expired."
                ) from exc
            raise PlexError(f"HTTP {code} from Plex server.") from exc
        except requests.ConnectionError as exc:
            raise PlexConnectionError(
                f"Cannot connect to {self.base_url} — "
                "is Plex Media Server running?"
            ) from exc
        except requests.Timeout as exc:
            raise PlexConnectionError("Connection timed out.") from exc

    def get_libraries(self) -> List[PlexLibrary]:
        data = self._get("/library/sections")
        dirs = data.get("MediaContainer", {}).get("Directory", [])
        return [
            PlexLibrary(
                key=str(d["key"]),
                title=d.get("title", "?"),
                type=d.get("type", "unknown"),
            )
            for d in dirs
        ]

    def get_items(self, library_key: str) -> List[PlexItem]:
        data = self._get(f"/library/sections/{_safe_id(library_key)}/all")
        meta = data.get("MediaContainer", {}).get("Metadata", [])
        return [_parse_item(m) for m in meta]

    def get_posters(self, rating_key: str) -> List[PlexPoster]:
        data = self._get(f"/library/metadata/{_safe_id(rating_key)}/posters")
        meta = data.get("MediaContainer", {}).get("Metadata", [])
        return [
            PlexPoster(
                key=m.get("key", ""),
                selected=bool(m.get("selected", False)),
                provider=m.get("provider", ""),
                rating_key=rating_key,
            )
            for m in meta
        ]

    def delete_poster(self, rating_key: str, poster_key: str) -> None:
        """
        Delete a poster via the Plex API.

        Locally-uploaded posters use a listing key like
        ``/library/metadata/{id}/file?url=upload://...``; the DELETE
        endpoint needs just the bare ``upload://`` URL.
        """
        pk = _resolve_delete_key(poster_key)
        self._delete(
            f"/library/metadata/{_safe_id(rating_key)}/posters", url=pk
        )

    # ── Internal helpers ──────────────────────────────────────────────────────

    def _get(self, path: str, **params: Any) -> Dict[str, Any]:
        resp = self._session.get(
            f"{self.base_url}{path}", params=params, timeout=(5, 30)
        )
        _raise_for_status(resp)
        return resp.json()

    def _delete(self, path: str, **params: Any) -> None:
        resp = self._session.delete(
            f"{self.base_url}{path}", params=params, timeout=(5, 30)
        )
        _raise_for_status(resp)


# ═══════════════════════════════════════════════════════════════════════════════
# Windows token auto-detection
# ═══════════════════════════════════════════════════════════════════════════════


def find_local_token() -> str:
    """
    Read the Plex authentication token from the local Plex Preferences.xml.

    Plex stores the auth token in plain text inside Preferences.xml in its
    data directory.  This only works on Windows (and only when the app runs
    on the same machine as Plex), which is the intended use case.

    Returns an empty string on non-Windows platforms or if the file cannot
    be read.
    """
    if platform.system() != "Windows":
        return ""

    local_app_data = os.environ.get("LOCALAPPDATA", "")
    if not local_app_data:
        return ""

    prefs = Path(local_app_data) / "Plex Media Server" / "Preferences.xml"
    if not prefs.exists():
        return ""

    try:
        text = prefs.read_text(encoding="utf-8", errors="ignore")
        match = re.search(r'PlexOnlineToken="([^"]+)"', text)
        return match.group(1) if match else ""
    except OSError:
        return ""


# ═══════════════════════════════════════════════════════════════════════════════
# Private module-level helpers
# ═══════════════════════════════════════════════════════════════════════════════


_NUMERIC_RE = re.compile(r"^\d+$")


def _safe_id(value: str) -> str:
    """Validate that a Plex ID is purely numeric to prevent path injection."""
    s = str(value)
    if not _NUMERIC_RE.match(s):
        raise ValueError(f"Invalid Plex ID (must be numeric): {s!r}")
    return s


def _raise_for_status(resp: requests.Response) -> None:
    if resp.status_code in (401, 403):
        raise PlexAuthError(
            f"HTTP {resp.status_code} — invalid or expired Plex token."
        )
    resp.raise_for_status()


def _parse_item(meta: Dict[str, Any]) -> PlexItem:
    return PlexItem(
        rating_key=str(meta.get("ratingKey", "")),
        title=meta.get("title", "Unknown"),
        year=meta.get("year"),
        type=meta.get("type", "movie"),
    )


def _resolve_delete_key(poster_key: str) -> str:
    """
    Convert a Plex poster listing key to the key needed for the DELETE call.

    For locally-uploaded posters the listing key is a path like
    ``/library/metadata/{id}/file?url=upload%3A%2F%2Fposters%2F{hash}``
    but the DELETE endpoint expects the bare decoded ``upload://`` URL.
    """
    if poster_key.startswith("/"):
        parsed = urllib.parse.urlparse(poster_key)
        qs = urllib.parse.parse_qs(parsed.query)
        inner = qs.get("url", [None])[0]
        if inner and inner.startswith("upload://"):
            return inner
    return poster_key
