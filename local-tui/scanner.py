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
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional


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

    def _scan(path: Path) -> FolderNode:
        node = FolderNode(path=path, name=path.name or str(path))

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
                child = _scan(entry)
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
