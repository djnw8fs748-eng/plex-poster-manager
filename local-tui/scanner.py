"""
scanner.py — Filesystem scanner for Plex local poster images.

Plex Media Server caches poster images inside its data directory:

    Windows : %LOCALAPPDATA%\\Plex Media Server\\Metadata\\
    macOS   : ~/Library/Application Support/Plex Media Server/Metadata/
    Linux   : /var/lib/plexmediaserver/Library/Application Support/
                Plex Media Server/Metadata/

Within the Metadata folder, images live inside deeply-nested *.bundle
directories.  This scanner walks any directory tree, finds every image
file (by extension *and* by magic-byte sniffing for Plex's extensionless
cache files), and groups them into a FolderNode hierarchy that the TUI
can render.
"""

from __future__ import annotations

import os
import platform
import sqlite3
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, List, Optional, Tuple


# Extensions that are always treated as images without reading file content.
IMAGE_EXTENSIONS: frozenset[str] = frozenset(
    {".jpg", ".jpeg", ".png", ".webp", ".tbn", ".bmp", ".gif"}
)


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------


@dataclass
class PosterFile:
    """A single image file found on disk."""

    path: Path
    size: int          # bytes
    modified: datetime
    media_title: str = ""    # e.g. "The Dark Knight (2008)" from the parent bundle
    is_plex_selected: bool = False  # True when Plex has this as the active poster

    # ── Formatting helpers ──────────────────────────────────────────────────

    @property
    def name(self) -> str:
        return self.path.name

    @property
    def size_human(self) -> str:
        size = float(self.size)
        for unit in ("B", "KB", "MB", "GB"):
            if size < 1024:
                return f"{size:.1f} {unit}"
            size /= 1024
        return f"{size:.1f} TB"

    @property
    def modified_str(self) -> str:
        return self.modified.strftime("%Y-%m-%d %H:%M")


@dataclass
class FolderNode:
    """A directory in the scanned tree, with its direct images and sub-folders."""

    path: Path
    name: str
    posters: List[PosterFile] = field(default_factory=list)
    children: List["FolderNode"] = field(default_factory=list)
    media_title: Optional[str] = None   # resolved from Info.xml inside the bundle
    media_year: Optional[int] = None
    rating_key: Optional[str] = None   # Plex ratingKey from Info.xml

    @property
    def display_name(self) -> str:
        """Human-readable label: media title+year when known, else the folder name."""
        if self.media_title:
            return f"{self.media_title} ({self.media_year})" if self.media_year else self.media_title
        return self.name

    # ── Aggregate helpers ───────────────────────────────────────────────────

    @property
    def total_posters(self) -> int:
        """Total image count including all descendants."""
        return len(self.posters) + sum(c.total_posters for c in self.children)

    def all_posters(self) -> List[PosterFile]:
        """All images in this folder and every sub-folder, sorted by path."""
        result: List[PosterFile] = list(self.posters)
        for child in self.children:
            result.extend(child.all_posters())
        return result


# ---------------------------------------------------------------------------
# Default-path detection
# ---------------------------------------------------------------------------


def get_default_plex_path() -> Optional[Path]:
    """
    Return the most likely Plex metadata directory for the current OS.
    Returns *None* when no standard location can be determined.
    """
    system = platform.system()

    if system == "Windows":
        local_app_data = os.environ.get("LOCALAPPDATA", "")
        if local_app_data:
            return Path(local_app_data) / "Plex Media Server" / "Metadata"

    elif system == "Darwin":
        return (
            Path.home()
            / "Library"
            / "Application Support"
            / "Plex Media Server"
            / "Metadata"
        )

    elif system == "Linux":
        candidates = [
            Path(
                "/var/lib/plexmediaserver/Library/Application Support"
                "/Plex Media Server/Metadata"
            ),
            Path.home() / ".local" / "share" / "plex" / "Metadata",
            Path("/config/Library/Application Support/Plex Media Server/Metadata"),
        ]
        for candidate in candidates:
            if candidate.exists():
                return candidate

    return None


# ---------------------------------------------------------------------------
# Scanner
# ---------------------------------------------------------------------------


def scan_directory(
    root: Path,
    *,
    check_magic_bytes: bool = True,
    progress_cb: Optional[Callable[[str], None]] = None,
) -> FolderNode:
    """
    Recursively scan *root* for image files and return a FolderNode tree.

    Args:
        root:              Directory to scan.
        check_magic_bytes: When True, also detect Plex's extensionless cache
                           files by reading their first 12 bytes.
        progress_cb:       Optional callback called with the path string of
                           each directory visited (useful for progress bars).

    Raises:
        FileNotFoundError: If *root* does not exist.
        NotADirectoryError: If *root* is not a directory.
    """
    root = Path(root)
    if not root.exists():
        raise FileNotFoundError(f"Path not found: {root}")
    if not root.is_dir():
        raise NotADirectoryError(f"Not a directory: {root}")

    # Load bundle hash→(title, year, rating_key) from the Plex SQLite database.
    # Modern Plex (2021+) does not write Info.xml into bundles, so this is the
    # primary source of media titles for most users.
    db_titles: Dict[str, Tuple[str, Optional[int], Optional[str]]] = {}
    db_path = _find_plex_db(root)
    if db_path:
        db_titles = _load_db_titles(db_path)

    _MAX_DEPTH = 40  # Guard against adversarial or accidentally deep trees.

    def _scan(path: Path, bundle_title: str = "", depth: int = 0) -> FolderNode:
        node = FolderNode(path=path, name=path.name or str(path))

        if depth >= _MAX_DEPTH:
            return node

        # Detect the nearest .bundle ancestor and read its media title.
        # Only the outermost bundle is used (bundle_title="" means not yet inside one).
        current_title = bundle_title
        if path.name.endswith(".bundle") and not bundle_title:
            title, year, rating_key = _read_bundle_info(path)
            # Modern Plex does not write Info.xml; fall back to the SQLite DB.
            if not title and db_titles:
                bundle_hash = path.parent.name + path.stem
                db_entry = db_titles.get(bundle_hash)
                if db_entry:
                    title, year, rating_key = db_entry
            if title:
                node.media_title = title
                node.media_year = year
                node.rating_key = rating_key
                current_title = f"{title} ({year})" if year else title

        if progress_cb:
            progress_cb(str(path))

        try:
            # Sort: directories first so tree order is predictable.
            entries = sorted(
                path.iterdir(),
                key=lambda e: (e.is_file(), e.name.lower()),
            )
        except PermissionError:
            return node

        for entry in entries:
            if entry.is_symlink():
                continue  # Skip symlinks to prevent cycles.

            if entry.is_dir():
                child = _scan(entry, current_title, depth + 1)
                if child.total_posters > 0:
                    node.children.append(child)

            elif entry.is_file() and _is_image(entry, check_magic_bytes):
                try:
                    stat = entry.stat()
                    node.posters.append(
                        PosterFile(
                            path=entry,
                            size=stat.st_size,
                            modified=datetime.fromtimestamp(stat.st_mtime),
                            media_title=current_title,
                        )
                    )
                except OSError:
                    pass

        node.posters.sort(key=lambda p: p.name)
        return node

    return _scan(root)


# ---------------------------------------------------------------------------
# Image detection helpers
# ---------------------------------------------------------------------------


def _is_image(path: Path, check_magic: bool) -> bool:
    """Return True if the file is an image (by extension or magic bytes)."""
    if path.suffix.lower() in IMAGE_EXTENSIONS:
        return True
    if check_magic and not path.suffix:
        return _check_magic_bytes(path)
    return False


def _find_plex_db(scan_root: Path) -> Optional[Path]:
    """
    Locate Plex's SQLite metadata database relative to the scan root.

    The database lives in ``Plex Media Server/Plug-in Support/Databases/``
    which is a sibling of the ``Metadata/`` folder we scan.  We walk up a
    few parent directories to find it regardless of how deep the scan root is.
    """
    search = scan_root
    for _ in range(5):
        candidate = (
            search / "Plug-in Support" / "Databases" / "com.plexapp.plugins.library.db"
        )
        if candidate.is_file():
            return candidate
        search = search.parent
    return None


def _load_db_titles(
    db_path: Path,
) -> Dict[str, Tuple[str, Optional[int], Optional[str]]]:
    """
    Read bundle-hash → (title, year, rating_key) from Plex's SQLite database.

    The ``metadata_items`` table stores the same hash that Plex uses to name
    ``.bundle`` directories: the first two characters become the parent folder
    and the remainder is the bundle stem, so the full hash is
    ``parent_dir_name + bundle_stem``.

    Opens the database read-only so it is safe to call while Plex is running.
    Returns an empty dict on any error (locked DB, missing table, etc.).
    """
    result: Dict[str, Tuple[str, Optional[int], Optional[str]]] = {}
    try:
        uri = f"file:{db_path}?mode=ro"
        con = sqlite3.connect(uri, uri=True, timeout=3, check_same_thread=False)
        try:
            cur = con.cursor()
            cur.execute(
                "SELECT hash, title, year, id FROM metadata_items "
                "WHERE hash IS NOT NULL AND title IS NOT NULL AND title != ''"
            )
            for row in cur.fetchall():
                bundle_hash, title, year, item_id = row
                if bundle_hash:
                    result[bundle_hash] = (
                        title,
                        int(year) if year else None,
                        str(item_id) if item_id else None,
                    )
        finally:
            con.close()
    except Exception:  # noqa: BLE001 — any DB error is non-fatal
        pass
    return result


def _read_bundle_info(
    bundle_path: Path,
) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """
    Try to extract a media title, year, and Plex ratingKey from a .bundle directory.

    Plex stores per-item metadata in XML files inside the bundle's Contents
    sub-directory.  We check the combined cache first, then fall back to any
    agent-specific Info.xml we can find.

    Returns (title, year, rating_key) or (None, None, None) if nothing readable.
    """
    contents = bundle_path / "Contents"
    if not contents.is_dir():
        return None, None, None

    # Prefer the combined/cached copy; fall back to any agent directory.
    candidates: List[Path] = [contents / "_combined" / "Info.xml"]
    try:
        for sub in sorted(contents.iterdir()):
            if sub.is_dir() and sub.name != "_combined":
                candidates.append(sub / "Info.xml")
    except OSError:
        pass

    for xml_path in candidates:
        if xml_path.is_file():
            title, year, rating_key = _parse_info_xml(xml_path)
            if title:
                return title, year, rating_key

    return None, None, None


def _parse_info_xml(
    path: Path,
) -> Tuple[Optional[str], Optional[int], Optional[str]]:
    """
    Parse a Plex Info.xml file and return (title, year, rating_key).

    Plex's XML root element varies by agent (Video, Directory, Movie, …)
    but always carries ``title``, optionally ``year``, and usually
    ``ratingKey`` as attributes.
    """
    try:
        root = ET.parse(path).getroot()  # noqa: S314  (local trusted file)
        title = root.get("title") or root.get("name")
        if not title:
            return None, None, None
        year_str = root.get("year", "")
        year = int(year_str) if year_str.isdigit() else None
        rating_key = root.get("ratingKey") or root.get("id") or None
        return title, year, rating_key
    except Exception:  # noqa: BLE001
        return None, None, None


def _check_magic_bytes(path: Path) -> bool:
    """Detect image files by their magic-byte signature."""
    try:
        with open(path, "rb") as fh:
            header = fh.read(12)
        if len(header) < 4:
            return False
        if header[:3] == b"\xff\xd8\xff":                       # JPEG
            return True
        if header[:4] == b"\x89PNG":                            # PNG
            return True
        if header[:4] == b"RIFF" and header[8:12] == b"WEBP":  # WebP
            return True
        if header[:6] in (b"GIF87a", b"GIF89a"):               # GIF
            return True
    except (OSError, IOError):
        pass
    return False
