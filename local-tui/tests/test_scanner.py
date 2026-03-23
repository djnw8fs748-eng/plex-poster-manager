"""
Unit tests for scanner.py.

These tests cover the pure-Python filesystem scanner with no Textual
dependency — they run fast and require no async infrastructure.
"""

from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from scanner import (
    FolderNode,
    PosterFile,
    _check_magic_bytes,
    _find_plex_db,
    _is_image,
    _load_db_titles,
    _parse_info_xml,
    _read_bundle_info,
    get_default_plex_path,
    scan_directory,
)
from tests.conftest import (
    GIF_HEADER,
    JPEG_HEADER,
    NOT_IMAGE,
    PNG_HEADER,
    WEBP_HEADER,
)


# ═══════════════════════════════════════════════════════════════════════════════
# PosterFile helpers
# ═══════════════════════════════════════════════════════════════════════════════


class TestPosterFileSizeHuman:
    def _make(self, size: int) -> PosterFile:
        return PosterFile(path=Path("x.jpg"), size=size, modified=datetime.now())

    def test_bytes(self):
        assert self._make(512).size_human == "512.0 B"

    def test_kilobytes(self):
        assert self._make(2048).size_human == "2.0 KB"

    def test_megabytes(self):
        assert self._make(2 * 1024 * 1024).size_human == "2.0 MB"

    def test_gigabytes(self):
        assert self._make(3 * 1024 * 1024 * 1024).size_human == "3.0 GB"

    def test_boundary_exactly_1kb(self):
        assert self._make(1024).size_human == "1.0 KB"


class TestPosterFileModifiedStr:
    def test_format(self):
        dt = datetime(2024, 6, 15, 9, 5, 0)
        pf = PosterFile(path=Path("x.jpg"), size=0, modified=dt)
        assert pf.modified_str == "2024-06-15 09:05"

    def test_name(self):
        pf = PosterFile(path=Path("/some/dir/poster.jpg"), size=0, modified=datetime.now())
        assert pf.name == "poster.jpg"


# ═══════════════════════════════════════════════════════════════════════════════
# FolderNode aggregation
# ═══════════════════════════════════════════════════════════════════════════════


def _pf(name: str) -> PosterFile:
    return PosterFile(path=Path(name), size=0, modified=datetime.now())


class TestFolderNodeTotalPosters:
    def test_empty(self):
        node = FolderNode(path=Path("."), name="root")
        assert node.total_posters == 0

    def test_direct_only(self):
        node = FolderNode(path=Path("."), name="root", posters=[_pf("a"), _pf("b")])
        assert node.total_posters == 2

    def test_children_only(self):
        child = FolderNode(path=Path("c"), name="c", posters=[_pf("x")])
        root = FolderNode(path=Path("."), name="root", children=[child])
        assert root.total_posters == 1

    def test_combined(self):
        grandchild = FolderNode(
            path=Path("gc"), name="gc", posters=[_pf("1"), _pf("2")]
        )
        child = FolderNode(
            path=Path("c"), name="c", posters=[_pf("a")], children=[grandchild]
        )
        root = FolderNode(
            path=Path("."), name="root", posters=[_pf("r")], children=[child]
        )
        # root:1 + child:1 + grandchild:2 = 4
        assert root.total_posters == 4


class TestFolderNodeAllPosters:
    def test_empty(self):
        node = FolderNode(path=Path("."), name="root")
        assert node.all_posters() == []

    def test_direct_order_preserved(self):
        p1, p2 = _pf("a"), _pf("b")
        node = FolderNode(path=Path("."), name="root", posters=[p1, p2])
        assert node.all_posters() == [p1, p2]

    def test_recursive_flatten(self):
        gc_poster = _pf("gc")
        grandchild = FolderNode(path=Path("gc"), name="gc", posters=[gc_poster])
        c_poster = _pf("c")
        child = FolderNode(
            path=Path("c"), name="c", posters=[c_poster], children=[grandchild]
        )
        r_poster = _pf("r")
        root = FolderNode(
            path=Path("."), name="root", posters=[r_poster], children=[child]
        )
        result = root.all_posters()
        assert result == [r_poster, c_poster, gc_poster]


# ═══════════════════════════════════════════════════════════════════════════════
# Magic-byte detection
# ═══════════════════════════════════════════════════════════════════════════════


class TestCheckMagicBytes:
    def test_jpeg(self, tmp_path):
        f = tmp_path / "img"
        f.write_bytes(JPEG_HEADER)
        assert _check_magic_bytes(f) is True

    def test_png(self, tmp_path):
        f = tmp_path / "img"
        f.write_bytes(PNG_HEADER)
        assert _check_magic_bytes(f) is True

    def test_webp(self, tmp_path):
        f = tmp_path / "img"
        f.write_bytes(WEBP_HEADER)
        assert _check_magic_bytes(f) is True

    def test_gif(self, tmp_path):
        f = tmp_path / "img"
        f.write_bytes(GIF_HEADER)
        assert _check_magic_bytes(f) is True

    def test_not_image(self, tmp_path):
        f = tmp_path / "doc"
        f.write_bytes(NOT_IMAGE)
        assert _check_magic_bytes(f) is False

    def test_too_short(self, tmp_path):
        f = tmp_path / "tiny"
        f.write_bytes(b"\xff\xd8")  # only 2 bytes — too short to be valid
        assert _check_magic_bytes(f) is False

    def test_missing_file(self, tmp_path):
        assert _check_magic_bytes(tmp_path / "nonexistent") is False


class TestIsImage:
    def test_jpg_extension(self, tmp_path):
        f = tmp_path / "img.jpg"
        f.write_bytes(b"irrelevant")
        assert _is_image(f, check_magic=False) is True

    def test_jpeg_extension(self, tmp_path):
        f = tmp_path / "img.jpeg"
        f.write_bytes(b"irrelevant")
        assert _is_image(f, check_magic=False) is True

    def test_png_extension(self, tmp_path):
        f = tmp_path / "img.png"
        f.write_bytes(b"irrelevant")
        assert _is_image(f, check_magic=False) is True

    def test_webp_extension(self, tmp_path):
        f = tmp_path / "img.webp"
        f.write_bytes(b"irrelevant")
        assert _is_image(f, check_magic=False) is True

    def test_tbn_extension(self, tmp_path):
        f = tmp_path / "img.tbn"
        f.write_bytes(b"irrelevant")
        assert _is_image(f, check_magic=False) is True

    def test_xml_not_image(self, tmp_path):
        f = tmp_path / "meta.xml"
        f.write_bytes(b"<xml/>")
        assert _is_image(f, check_magic=False) is False

    def test_extensionless_jpeg_with_magic(self, tmp_path):
        f = tmp_path / "0"
        f.write_bytes(JPEG_HEADER)
        assert _is_image(f, check_magic=True) is True

    def test_extensionless_non_image_with_magic(self, tmp_path):
        f = tmp_path / "0"
        f.write_bytes(NOT_IMAGE)
        assert _is_image(f, check_magic=True) is False

    def test_extensionless_skipped_when_magic_disabled(self, tmp_path):
        f = tmp_path / "0"
        f.write_bytes(JPEG_HEADER)
        assert _is_image(f, check_magic=False) is False


# ═══════════════════════════════════════════════════════════════════════════════
# scan_directory
# ═══════════════════════════════════════════════════════════════════════════════


class TestScanDirectory:
    # ── Error cases ───────────────────────────────────────────────────────────

    def test_raises_for_nonexistent_path(self, tmp_path):
        with pytest.raises(FileNotFoundError):
            scan_directory(tmp_path / "does_not_exist")

    def test_raises_for_file_not_dir(self, tmp_path):
        f = tmp_path / "file.txt"
        f.write_bytes(b"text")
        with pytest.raises(NotADirectoryError):
            scan_directory(f)

    # ── Empty directory ───────────────────────────────────────────────────────

    def test_empty_dir_has_zero_posters(self, empty_dir):
        root = scan_directory(empty_dir, check_magic_bytes=False)
        assert root.total_posters == 0
        assert root.posters == []
        assert root.children == []

    # ── Extension-based detection ─────────────────────────────────────────────

    def test_finds_images_by_extension(self, flat_image_dir):
        root = scan_directory(flat_image_dir, check_magic_bytes=False)
        assert root.total_posters == 3  # .jpg, .png, .webp

    def test_ignores_non_image_files(self, mixed_dir):
        root = scan_directory(mixed_dir, check_magic_bytes=False)
        names = {p.name for p in root.all_posters()}
        assert "metadata.xml" not in names
        assert "info.txt" not in names
        assert "video.mp4" not in names

    def test_finds_images_in_subdirectories(self, mixed_dir):
        root = scan_directory(mixed_dir, check_magic_bytes=False)
        all_names = {p.name for p in root.all_posters()}
        assert "poster.jpg" in all_names
        assert "art.png" in all_names

    # ── Magic-byte detection ──────────────────────────────────────────────────

    def test_finds_extensionless_images_with_magic(self, extensionless_image_dir):
        root = scan_directory(extensionless_image_dir, check_magic_bytes=True)
        # 4 real images (JPEG, PNG, WebP, GIF) + 1 non-image
        assert root.total_posters == 4

    def test_skips_extensionless_when_magic_disabled(self, extensionless_image_dir):
        root = scan_directory(extensionless_image_dir, check_magic_bytes=False)
        assert root.total_posters == 0

    # ── Nested structure ──────────────────────────────────────────────────────

    def test_nested_bundle_structure(self, nested_image_dir):
        root = scan_directory(nested_image_dir, check_magic_bytes=False)
        # 2 (bundle_a) + 1 (bundle_b) + 3 (tv show) = 6
        assert root.total_posters == 6

    def test_tree_has_correct_library_children(self, nested_image_dir):
        root = scan_directory(nested_image_dir, check_magic_bytes=False)
        child_names = {c.name for c in root.children}
        assert "Movies" in child_names
        assert "TV Shows" in child_names

    def test_all_posters_flattens_correctly(self, nested_image_dir):
        root = scan_directory(nested_image_dir, check_magic_bytes=False)
        all_p = root.all_posters()
        assert len(all_p) == root.total_posters

    # ── PosterFile attributes ─────────────────────────────────────────────────

    def test_poster_file_has_correct_size(self, tmp_path):
        data = JPEG_HEADER  # 104 bytes
        (tmp_path / "poster.jpg").write_bytes(data)
        root = scan_directory(tmp_path, check_magic_bytes=False)
        assert root.posters[0].size == len(data)

    def test_poster_file_has_correct_name(self, tmp_path):
        (tmp_path / "my_poster.jpg").write_bytes(JPEG_HEADER)
        root = scan_directory(tmp_path, check_magic_bytes=False)
        assert root.posters[0].name == "my_poster.jpg"

    def test_poster_file_modified_is_recent(self, tmp_path):
        (tmp_path / "poster.jpg").write_bytes(JPEG_HEADER)
        root = scan_directory(tmp_path, check_magic_bytes=False)
        age_seconds = (datetime.now() - root.posters[0].modified).total_seconds()
        assert 0 <= age_seconds < 10

    # ── Sorting ───────────────────────────────────────────────────────────────

    def test_posters_sorted_by_name(self, tmp_path):
        for name in ["c.jpg", "a.jpg", "b.jpg"]:
            (tmp_path / name).write_bytes(JPEG_HEADER)
        root = scan_directory(tmp_path, check_magic_bytes=False)
        names = [p.name for p in root.posters]
        assert names == sorted(names)

    # ── Progress callback ─────────────────────────────────────────────────────

    def test_progress_callback_called(self, flat_image_dir):
        visited: list[str] = []
        scan_directory(
            flat_image_dir,
            check_magic_bytes=False,
            progress_cb=lambda p: visited.append(p),
        )
        assert len(visited) > 0
        assert any(str(flat_image_dir) in v for v in visited)

    # ── Symlink handling ──────────────────────────────────────────────────────

    def test_skips_symlinks(self, tmp_path):
        real = tmp_path / "real"
        real.mkdir()
        (real / "poster.jpg").write_bytes(JPEG_HEADER)
        link = tmp_path / "link"
        link.symlink_to(real)
        root = scan_directory(tmp_path, check_magic_bytes=False)
        # Only the real directory's poster should be found, not the symlink's
        assert root.total_posters == 1

    # ── Path accepts strings ──────────────────────────────────────────────────

    def test_accepts_string_path(self, flat_image_dir):
        root = scan_directory(str(flat_image_dir), check_magic_bytes=False)
        assert root.total_posters == 3


# ═══════════════════════════════════════════════════════════════════════════════
# Bundle title resolution
# ═══════════════════════════════════════════════════════════════════════════════


def _make_bundle(tmp_path: Path, xml_content: str) -> Path:
    """Create a minimal .bundle structure with an Info.xml."""
    bundle = tmp_path / "abc123.bundle"
    combined = bundle / "Contents" / "_combined"
    combined.mkdir(parents=True)
    (combined / "Info.xml").write_text(xml_content, encoding="utf-8")
    return bundle


class TestParseInfoXml:
    def test_reads_title_and_year(self, tmp_path):
        f = tmp_path / "Info.xml"
        f.write_text('<Video title="Inception" year="2010"/>', encoding="utf-8")
        title, year, rk = _parse_info_xml(f)
        assert (title, year) == ("Inception", 2010)

    def test_reads_rating_key(self, tmp_path):
        f = tmp_path / "Info.xml"
        f.write_text('<Video title="Dune" year="2021" ratingKey="42"/>', encoding="utf-8")
        _, _, rk = _parse_info_xml(f)
        assert rk == "42"

    def test_reads_title_without_year(self, tmp_path):
        f = tmp_path / "Info.xml"
        f.write_text('<Directory title="Breaking Bad"/>', encoding="utf-8")
        title, year, _ = _parse_info_xml(f)
        assert (title, year) == ("Breaking Bad", None)

    def test_falls_back_to_name_attribute(self, tmp_path):
        f = tmp_path / "Info.xml"
        f.write_text('<Media name="Fallback Title" year="2000"/>', encoding="utf-8")
        title, year, _ = _parse_info_xml(f)
        assert (title, year) == ("Fallback Title", 2000)

    def test_returns_none_for_missing_file(self, tmp_path):
        assert _parse_info_xml(tmp_path / "nonexistent.xml") == (None, None, None)

    def test_returns_none_for_malformed_xml(self, tmp_path):
        f = tmp_path / "Info.xml"
        f.write_text("not xml at all <<<", encoding="utf-8")
        assert _parse_info_xml(f) == (None, None, None)

    def test_returns_none_when_no_title_attribute(self, tmp_path):
        f = tmp_path / "Info.xml"
        f.write_text('<Video year="2010"/>', encoding="utf-8")
        assert _parse_info_xml(f) == (None, None, None)


class TestReadBundleInfo:
    def test_reads_combined_info_xml(self, tmp_path):
        bundle = _make_bundle(tmp_path, '<Video title="The Matrix" year="1999"/>')
        title, year, _ = _read_bundle_info(bundle)
        assert (title, year) == ("The Matrix", 1999)

    def test_reads_rating_key_from_xml(self, tmp_path):
        bundle = _make_bundle(tmp_path, '<Video title="X" year="2022" ratingKey="99"/>')
        _, _, rk = _read_bundle_info(bundle)
        assert rk == "99"

    def test_falls_back_to_agent_directory(self, tmp_path):
        bundle = tmp_path / "abc.bundle"
        agent_dir = bundle / "Contents" / "com.plexapp.agents.tmdb_8.0"
        agent_dir.mkdir(parents=True)
        (agent_dir / "Info.xml").write_text(
            '<Video title="Dune" year="2021"/>', encoding="utf-8"
        )
        title, year, _ = _read_bundle_info(bundle)
        assert (title, year) == ("Dune", 2021)

    def test_returns_none_for_empty_bundle(self, tmp_path):
        bundle = tmp_path / "empty.bundle"
        bundle.mkdir()
        assert _read_bundle_info(bundle) == (None, None, None)

    def test_returns_none_when_no_contents_dir(self, tmp_path):
        bundle = tmp_path / "no_contents.bundle"
        bundle.mkdir()
        assert _read_bundle_info(bundle) == (None, None, None)


class TestBundleTitleInScan:
    def test_folder_node_has_media_title(self, tmp_path):
        bundle = _make_bundle(tmp_path, '<Video title="Blade Runner" year="1982"/>')
        (bundle / "Contents" / "_combined" / "poster.jpg").write_bytes(JPEG_HEADER)
        root = scan_directory(tmp_path, check_magic_bytes=False)
        bundle_node = next(
            c for c in root.children if c.name == "abc123.bundle"
        )
        assert bundle_node.media_title == "Blade Runner"
        assert bundle_node.media_year == 1982

    def test_folder_node_display_name(self, tmp_path):
        bundle = _make_bundle(tmp_path, '<Video title="Blade Runner" year="1982"/>')
        (bundle / "Contents" / "_combined" / "poster.jpg").write_bytes(JPEG_HEADER)
        root = scan_directory(tmp_path, check_magic_bytes=False)
        bundle_node = next(c for c in root.children if c.name == "abc123.bundle")
        assert bundle_node.display_name == "Blade Runner (1982)"

    def test_poster_file_has_media_title(self, tmp_path):
        bundle = _make_bundle(tmp_path, '<Video title="Alien" year="1979"/>')
        (bundle / "Contents" / "_combined" / "poster.jpg").write_bytes(JPEG_HEADER)
        root = scan_directory(tmp_path, check_magic_bytes=False)
        all_p = root.all_posters()
        assert all(p.media_title == "Alien (1979)" for p in all_p)

    def test_poster_has_no_title_outside_bundle(self, tmp_path):
        (tmp_path / "poster.jpg").write_bytes(JPEG_HEADER)
        root = scan_directory(tmp_path, check_magic_bytes=False)
        assert root.posters[0].media_title == ""

    def test_folder_node_has_rating_key(self, tmp_path):
        bundle = _make_bundle(tmp_path, '<Video title="X" year="2000" ratingKey="77"/>')
        (bundle / "Contents" / "_combined" / "poster.jpg").write_bytes(JPEG_HEADER)
        root = scan_directory(tmp_path, check_magic_bytes=False)
        bundle_node = next(c for c in root.children if c.name == "abc123.bundle")
        assert bundle_node.rating_key == "77"

    def test_poster_is_plex_selected_defaults_false(self, tmp_path):
        bundle = _make_bundle(tmp_path, '<Video title="X" year="2000"/>')
        (bundle / "Contents" / "_combined" / "poster.jpg").write_bytes(JPEG_HEADER)
        root = scan_directory(tmp_path, check_magic_bytes=False)
        assert all(not p.is_plex_selected for p in root.all_posters())

    def test_display_name_falls_back_to_folder_name(self, tmp_path):
        bundle = tmp_path / "xyz999.bundle"
        posters = bundle / "Contents" / "_combined"
        posters.mkdir(parents=True)
        (posters / "poster.jpg").write_bytes(JPEG_HEADER)
        root = scan_directory(tmp_path, check_magic_bytes=False)
        bundle_node = next(c for c in root.children if c.name == "xyz999.bundle")
        assert bundle_node.display_name == "xyz999.bundle"


# ═══════════════════════════════════════════════════════════════════════════════
# SQLite DB helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _make_plex_db(path: Path) -> Path:
    """Create a minimal Plex-style SQLite database with a metadata_items table."""
    import sqlite3
    db = path / "com.plexapp.plugins.library.db"
    con = sqlite3.connect(str(db))
    con.execute(
        "CREATE TABLE metadata_items "
        "(id INTEGER, hash TEXT, title TEXT, year INTEGER)"
    )
    con.execute(
        "INSERT INTO metadata_items VALUES (42, 'abcdef1234567890', 'Alien', 1979)"
    )
    con.execute(
        "INSERT INTO metadata_items VALUES (7, 'ff00112233445566', 'The Bear', 2022)"
    )
    con.execute(
        "INSERT INTO metadata_items VALUES (99, NULL, 'No Hash', 2000)"
    )
    con.commit()
    con.close()
    return db


class TestFindPlexDb:
    def test_finds_db_in_sibling_directory(self, tmp_path):
        plex_root = tmp_path / "Plex Media Server"
        metadata = plex_root / "Metadata"
        metadata.mkdir(parents=True)
        db_dir = plex_root / "Plug-in Support" / "Databases"
        db_dir.mkdir(parents=True)
        db = db_dir / "com.plexapp.plugins.library.db"
        db.write_bytes(b"")
        assert _find_plex_db(metadata) == db

    def test_finds_db_when_scanning_subdirectory(self, tmp_path):
        plex_root = tmp_path / "Plex Media Server"
        metadata = plex_root / "Metadata" / "Movies"
        metadata.mkdir(parents=True)
        db_dir = plex_root / "Plug-in Support" / "Databases"
        db_dir.mkdir(parents=True)
        db = db_dir / "com.plexapp.plugins.library.db"
        db.write_bytes(b"")
        assert _find_plex_db(metadata) == db

    def test_returns_none_when_not_found(self, tmp_path):
        assert _find_plex_db(tmp_path) is None


class TestLoadDbTitles:
    def test_loads_titles_from_db(self, tmp_path):
        _make_plex_db(tmp_path)
        db = tmp_path / "com.plexapp.plugins.library.db"
        titles = _load_db_titles(db)
        assert "abcdef1234567890" in titles
        assert titles["abcdef1234567890"][0] == "Alien"
        assert titles["abcdef1234567890"][1] == 1979
        assert titles["abcdef1234567890"][2] == "42"

    def test_skips_rows_with_null_hash(self, tmp_path):
        _make_plex_db(tmp_path)
        db = tmp_path / "com.plexapp.plugins.library.db"
        titles = _load_db_titles(db)
        assert all(v[0] != "No Hash" for v in titles.values())

    def test_returns_empty_dict_for_missing_file(self, tmp_path):
        assert _load_db_titles(tmp_path / "nonexistent.db") == {}

    def test_returns_empty_dict_for_corrupt_file(self, tmp_path):
        bad = tmp_path / "com.plexapp.plugins.library.db"
        bad.write_bytes(b"not a sqlite database")
        assert _load_db_titles(bad) == {}


class TestDbTitleFallbackInScan:
    def test_uses_db_title_when_no_info_xml(self, tmp_path):
        # Create a bundle without Info.xml (modern Plex style)
        bundle = tmp_path / "Plex Media Server" / "Metadata" / "Movies" / "ab" / "cdef1234567890.bundle"
        posters = bundle / "Contents" / "_stored"
        posters.mkdir(parents=True)
        (posters / "poster.jpg").write_bytes(JPEG_HEADER)

        # Create matching DB entry (hash = "ab" + "cdef1234567890")
        db_dir = tmp_path / "Plex Media Server" / "Plug-in Support" / "Databases"
        db_dir.mkdir(parents=True)
        import sqlite3
        db = db_dir / "com.plexapp.plugins.library.db"
        con = sqlite3.connect(str(db))
        con.execute("CREATE TABLE metadata_items (id INTEGER, hash TEXT, title TEXT, year INTEGER)")
        con.execute("INSERT INTO metadata_items VALUES (5, 'abcdef1234567890', 'Inception', 2010)")
        con.commit()
        con.close()

        metadata = tmp_path / "Plex Media Server" / "Metadata"
        root = scan_directory(metadata, check_magic_bytes=False)
        all_p = root.all_posters()
        assert len(all_p) == 1
        assert all_p[0].media_title == "Inception (2010)"

    def test_info_xml_takes_priority_over_db(self, tmp_path):
        # Bundle with both Info.xml and a DB entry — XML wins
        bundle = tmp_path / "Plex Media Server" / "Metadata" / "Movies" / "ab" / "cdef1234567890.bundle"
        combined = bundle / "Contents" / "_combined"
        combined.mkdir(parents=True)
        (combined / "Info.xml").write_text('<Video title="XML Title" year="2001"/>', encoding="utf-8")
        (combined / "poster.jpg").write_bytes(JPEG_HEADER)

        db_dir = tmp_path / "Plex Media Server" / "Plug-in Support" / "Databases"
        db_dir.mkdir(parents=True)
        import sqlite3
        db = db_dir / "com.plexapp.plugins.library.db"
        con = sqlite3.connect(str(db))
        con.execute("CREATE TABLE metadata_items (id INTEGER, hash TEXT, title TEXT, year INTEGER)")
        con.execute("INSERT INTO metadata_items VALUES (5, 'abcdef1234567890', 'DB Title', 2010)")
        con.commit()
        con.close()

        metadata = tmp_path / "Plex Media Server" / "Metadata"
        root = scan_directory(metadata, check_magic_bytes=False)
        bundle_node = next(c for c in root.all_posters())
        assert bundle_node.media_title == "XML Title (2001)"


# ═══════════════════════════════════════════════════════════════════════════════
# get_default_plex_path
# ═══════════════════════════════════════════════════════════════════════════════


class TestGetDefaultPlexPath:
    def test_windows(self):
        fake_appdata = "/fake/AppData/Local"
        with patch("platform.system", return_value="Windows"), patch.dict(
            os.environ, {"LOCALAPPDATA": fake_appdata}
        ):
            path = get_default_plex_path()
        assert path is not None
        # Compare component-by-component to stay cross-platform
        normalized = str(path).replace("\\", "/")
        assert "Plex Media Server" in normalized
        assert normalized.endswith("Metadata")

    def test_windows_no_localappdata(self):
        with patch("platform.system", return_value="Windows"), patch.dict(
            os.environ, {}, clear=True
        ):
            path = get_default_plex_path()
        assert path is None

    def test_macos(self):
        with patch("platform.system", return_value="Darwin"), patch(
            "pathlib.Path.home", return_value=Path("/Users/test")
        ):
            path = get_default_plex_path()
        assert path == Path(
            "/Users/test/Library/Application Support/Plex Media Server/Metadata"
        )

    def test_linux_no_existing_path_returns_none(self):
        """Returns None when no standard Linux candidate paths exist."""
        with patch("platform.system", return_value="Linux"), patch(
            "pathlib.Path.exists", return_value=False
        ):
            path = get_default_plex_path()
        assert path is None

    def test_unknown_os_returns_none(self):
        with patch("platform.system", return_value="SunOS"):
            path = get_default_plex_path()
        assert path is None
