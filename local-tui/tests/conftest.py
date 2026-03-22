"""
Shared pytest fixtures for the local-tui test suite.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make the local-tui source importable regardless of where pytest is run from.
sys.path.insert(0, str(Path(__file__).parent.parent))

# ── Image magic-byte constants ────────────────────────────────────────────────

JPEG_HEADER = b"\xff\xd8\xff\xe0" + b"\x00" * 100
PNG_HEADER = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
WEBP_HEADER = b"RIFF\x00\x00\x00\x00WEBP" + b"\x00" * 100
GIF_HEADER = b"GIF89a" + b"\x00" * 100
NOT_IMAGE = b"This is not an image file.\n" * 4


# ── Directory fixtures ────────────────────────────────────────────────────────


@pytest.fixture()
def empty_dir(tmp_path: Path) -> Path:
    """A temporary directory with no files."""
    return tmp_path


@pytest.fixture()
def flat_image_dir(tmp_path: Path) -> Path:
    """A directory with a few image files at the top level."""
    (tmp_path / "poster.jpg").write_bytes(JPEG_HEADER)
    (tmp_path / "thumb.png").write_bytes(PNG_HEADER)
    (tmp_path / "art.webp").write_bytes(WEBP_HEADER)
    return tmp_path


@pytest.fixture()
def nested_image_dir(tmp_path: Path) -> Path:
    """A directory tree that mimics a Plex metadata bundle structure."""
    movies = tmp_path / "Movies"
    movies.mkdir()

    bundle_a = movies / "a" / "abc123.bundle" / "Contents" / "_stored" / "poster"
    bundle_a.mkdir(parents=True)
    (bundle_a / "poster_0.jpg").write_bytes(JPEG_HEADER)
    (bundle_a / "poster_1.jpg").write_bytes(JPEG_HEADER)

    bundle_b = movies / "b" / "bcd456.bundle" / "Contents" / "_stored" / "poster"
    bundle_b.mkdir(parents=True)
    (bundle_b / "poster_0.jpg").write_bytes(JPEG_HEADER)

    tv = tmp_path / "TV Shows"
    tv.mkdir()
    show_dir = tv / "c" / "cde789.bundle" / "Contents" / "_stored" / "poster"
    show_dir.mkdir(parents=True)
    (show_dir / "poster_0.jpg").write_bytes(JPEG_HEADER)
    (show_dir / "poster_1.jpg").write_bytes(JPEG_HEADER)
    (show_dir / "poster_2.jpg").write_bytes(JPEG_HEADER)

    return tmp_path


@pytest.fixture()
def extensionless_image_dir(tmp_path: Path) -> Path:
    """A directory with Plex-style extensionless cache files."""
    (tmp_path / "0").write_bytes(JPEG_HEADER)     # JPEG
    (tmp_path / "1").write_bytes(PNG_HEADER)      # PNG
    (tmp_path / "2").write_bytes(WEBP_HEADER)     # WebP
    (tmp_path / "3").write_bytes(GIF_HEADER)      # GIF
    (tmp_path / "4").write_bytes(NOT_IMAGE)       # not an image
    return tmp_path


@pytest.fixture()
def mixed_dir(tmp_path: Path) -> Path:
    """A directory with images and non-image files mixed together."""
    (tmp_path / "poster.jpg").write_bytes(JPEG_HEADER)
    (tmp_path / "metadata.xml").write_bytes(b"<xml/>")
    (tmp_path / "info.txt").write_bytes(b"some text")
    (tmp_path / "video.mp4").write_bytes(b"\x00\x00\x00\x18")
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "art.png").write_bytes(PNG_HEADER)
    (sub / "readme.md").write_bytes(b"# readme")
    return tmp_path
