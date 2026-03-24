"""
Tests for plex.py — PlexClient, data model, and utility functions.

All HTTP calls are intercepted via unittest.mock so no real Plex server
is required.
"""

from __future__ import annotations

import sys
import os
from pathlib import Path
from unittest.mock import MagicMock, patch, mock_open

import pytest
import requests

# Make local-tui/ importable when pytest is run from that directory.
_HERE = Path(__file__).parent.parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from plex import (
    PlexAuthError,
    PlexClient,
    PlexConnectionError,
    PlexError,
    PlexItem,
    PlexLibrary,
    PlexPoster,
    _resolve_delete_key,
    _safe_id,
    find_local_token,
)


# ═══════════════════════════════════════════════════════════════════════════════
# Helpers
# ═══════════════════════════════════════════════════════════════════════════════


def _mock_response(json_data: dict, status: int = 200) -> MagicMock:
    """Build a fake requests.Response."""
    resp = MagicMock()
    resp.status_code = status
    resp.json.return_value = json_data
    resp.raise_for_status = MagicMock()
    if status in (401, 403):
        resp.raise_for_status.side_effect = requests.HTTPError(response=resp)
    return resp


def _client_with_mock_session() -> tuple[PlexClient, MagicMock]:
    """Return a PlexClient whose internal session is replaced by a MagicMock."""
    client = PlexClient(base_url="http://localhost:32400", token="faketoken")
    mock_session = MagicMock()
    client._session = mock_session
    return client, mock_session


# ═══════════════════════════════════════════════════════════════════════════════
# PlexPoster.source_label
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlexPosterSourceLabel:
    def _poster(self, key: str, provider: str = "") -> PlexPoster:
        return PlexPoster(key=key, selected=False, provider=provider, rating_key="1")

    def test_local_upload_key(self):
        p = self._poster("/library/metadata/1/file?url=upload%3A%2F%2Fposters%2Fabc")
        assert p.source_label == "local"

    def test_local_upload_bare(self):
        p = self._poster("upload://posters/abc123")
        assert p.source_label == "local"

    def test_tmdb_in_key(self):
        p = self._poster("https://image.tmdb.org/t/p/original/abc.jpg")
        assert p.source_label == "TMDB"

    def test_themoviedb_in_provider(self):
        p = self._poster("https://example.com/poster.jpg",
                         provider="com.plexapp.agents.themoviedb")
        assert p.source_label == "TMDB"

    def test_fanart_in_key(self):
        p = self._poster("https://fanart.tv/posters/12345.jpg")
        assert p.source_label == "Fanart"

    def test_fanart_in_provider(self):
        p = self._poster("", provider="com.plexapp.agents.fanarttv")
        assert p.source_label == "Fanart"

    def test_tvdb_in_key(self):
        p = self._poster("https://tvdb.com/banners/abc.jpg")
        assert p.source_label == "TVDB"

    def test_tvdb_in_provider(self):
        p = self._poster("", provider="com.plexapp.agents.thetvdb")
        assert p.source_label == "TVDB"

    def test_fallback_last_dotted_segment(self):
        p = self._poster("", provider="com.example.agents.myprovider")
        assert p.source_label == "myprovider"

    def test_empty_provider_returns_question_mark(self):
        p = self._poster("")
        assert p.source_label == "?"


# ═══════════════════════════════════════════════════════════════════════════════
# PlexPoster.short_key
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlexPosterShortKey:
    def _poster(self, key: str) -> PlexPoster:
        return PlexPoster(key=key, selected=False, provider="", rating_key="1")

    def test_url_with_url_query_param(self):
        p = self._poster("/library/metadata/1/file?url=upload%3A%2F%2Fposters%2Fmyhash")
        # parse_qs decodes the url param → upload://posters/myhash → last segment = myhash
        assert p.short_key == "myhash"

    def test_plain_slash_path(self):
        p = self._poster("https://example.com/images/poster.jpg")
        assert p.short_key == "poster.jpg"

    def test_empty_key(self):
        p = self._poster("")
        assert p.short_key == ""


# ═══════════════════════════════════════════════════════════════════════════════
# PlexItem properties
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlexItemDisplayTitle:
    def test_with_year(self):
        item = PlexItem(rating_key="1", title="Inception", year=2010)
        assert item.display_title == "Inception (2010)"

    def test_without_year(self):
        item = PlexItem(rating_key="1", title="Unknown Show")
        assert item.display_title == "Unknown Show"


class TestPlexItemSelectedPoster:
    def test_returns_selected(self):
        p1 = PlexPoster(key="a", selected=False, provider="", rating_key="1")
        p2 = PlexPoster(key="b", selected=True, provider="", rating_key="1")
        item = PlexItem(rating_key="1", title="X", posters=[p1, p2])
        assert item.selected_poster is p2

    def test_returns_none_when_no_selected(self):
        p1 = PlexPoster(key="a", selected=False, provider="", rating_key="1")
        item = PlexItem(rating_key="1", title="X", posters=[p1])
        assert item.selected_poster is None

    def test_empty_posters(self):
        item = PlexItem(rating_key="1", title="X")
        assert item.selected_poster is None


class TestPlexItemDeletableCount:
    def test_counts_non_selected(self):
        posters = [
            PlexPoster(key="a", selected=True, provider="", rating_key="1"),
            PlexPoster(key="b", selected=False, provider="", rating_key="1"),
            PlexPoster(key="c", selected=False, provider="", rating_key="1"),
        ]
        item = PlexItem(rating_key="1", title="X", posters=posters)
        assert item.deletable_count == 2

    def test_all_selected_is_zero(self):
        posters = [PlexPoster(key="a", selected=True, provider="", rating_key="1")]
        item = PlexItem(rating_key="1", title="X", posters=posters)
        assert item.deletable_count == 0

    def test_empty_posters(self):
        item = PlexItem(rating_key="1", title="X")
        assert item.deletable_count == 0


# ═══════════════════════════════════════════════════════════════════════════════
# _safe_id
# ═══════════════════════════════════════════════════════════════════════════════


class TestSafeId:
    def test_valid_numeric(self):
        assert _safe_id("12345") == "12345"

    def test_single_digit(self):
        assert _safe_id("0") == "0"

    def test_coerces_int_like_string(self):
        assert _safe_id("99") == "99"

    def test_rejects_slash(self):
        with pytest.raises(ValueError, match="Invalid Plex ID"):
            _safe_id("1/etc/passwd")

    def test_rejects_alpha(self):
        with pytest.raises(ValueError, match="Invalid Plex ID"):
            _safe_id("abc")

    def test_rejects_empty(self):
        with pytest.raises(ValueError, match="Invalid Plex ID"):
            _safe_id("")

    def test_rejects_alphanumeric(self):
        with pytest.raises(ValueError, match="Invalid Plex ID"):
            _safe_id("123abc")


# ═══════════════════════════════════════════════════════════════════════════════
# _resolve_delete_key
# ═══════════════════════════════════════════════════════════════════════════════


class TestResolveDeleteKey:
    def test_local_upload_path_extracts_url(self):
        key = "/library/metadata/42/file?url=upload%3A%2F%2Fposters%2Fmyhash"
        result = _resolve_delete_key(key)
        assert result == "upload://posters/myhash"

    def test_http_url_returned_unchanged(self):
        key = "https://image.tmdb.org/t/p/original/abc.jpg"
        result = _resolve_delete_key(key)
        assert result == key

    def test_path_without_url_param_returned_unchanged(self):
        key = "/library/metadata/42/posters"
        result = _resolve_delete_key(key)
        assert result == key

    def test_url_param_not_upload_returned_unchanged(self):
        key = "/library/metadata/42/file?url=https%3A%2F%2Fexample.com%2Fposter.jpg"
        result = _resolve_delete_key(key)
        # inner URL doesn't start with upload:// → returned as-is
        assert result == key


# ═══════════════════════════════════════════════════════════════════════════════
# PlexClient.test_connection
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlexClientTestConnection:
    def test_returns_friendly_name(self):
        client, mock_session = _client_with_mock_session()
        mock_session.get.return_value = _mock_response(
            {"MediaContainer": {"friendlyName": "My Plex"}}
        )
        assert client.test_connection() == "My Plex"

    def test_missing_friendly_name_falls_back(self):
        client, mock_session = _client_with_mock_session()
        mock_session.get.return_value = _mock_response({"MediaContainer": {}})
        assert client.test_connection() == "Plex Media Server"

    def test_401_raises_plex_auth_error(self):
        client, mock_session = _client_with_mock_session()
        resp = _mock_response({}, status=401)
        exc = requests.HTTPError(response=resp)
        mock_session.get.return_value.raise_for_status.side_effect = exc
        mock_session.get.return_value.status_code = 401
        mock_session.get.return_value.json.return_value = {}
        # Simulate the HTTPError being raised during _get → raise_for_status
        mock_session.get.return_value.raise_for_status.side_effect = exc
        # Wire the internal _get to trigger the error path
        with patch.object(client, "_get", side_effect=exc):
            with pytest.raises(PlexAuthError):
                client.test_connection()

    def test_403_raises_plex_auth_error(self):
        client, _ = _client_with_mock_session()
        resp = MagicMock()
        resp.status_code = 403
        exc = requests.HTTPError(response=resp)
        with patch.object(client, "_get", side_effect=exc):
            with pytest.raises(PlexAuthError):
                client.test_connection()

    def test_connection_error_raises_plex_connection_error(self):
        client, _ = _client_with_mock_session()
        with patch.object(
            client, "_get", side_effect=requests.ConnectionError("refused")
        ):
            with pytest.raises(PlexConnectionError, match="Cannot connect"):
                client.test_connection()

    def test_timeout_raises_plex_connection_error(self):
        client, _ = _client_with_mock_session()
        with patch.object(
            client, "_get", side_effect=requests.Timeout("timed out")
        ):
            with pytest.raises(PlexConnectionError, match="timed out"):
                client.test_connection()


# ═══════════════════════════════════════════════════════════════════════════════
# PlexClient.get_libraries
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlexClientGetLibraries:
    def test_returns_library_list(self):
        client, mock_session = _client_with_mock_session()
        mock_session.get.return_value = _mock_response(
            {
                "MediaContainer": {
                    "Directory": [
                        {"key": "1", "title": "Movies", "type": "movie"},
                        {"key": "2", "title": "TV Shows", "type": "show"},
                    ]
                }
            }
        )
        libs = client.get_libraries()
        assert len(libs) == 2
        assert libs[0].key == "1"
        assert libs[0].title == "Movies"
        assert libs[0].type == "movie"
        assert libs[1].title == "TV Shows"

    def test_empty_directory_returns_empty_list(self):
        client, mock_session = _client_with_mock_session()
        mock_session.get.return_value = _mock_response(
            {"MediaContainer": {"Directory": []}}
        )
        assert client.get_libraries() == []

    def test_missing_directory_returns_empty_list(self):
        client, mock_session = _client_with_mock_session()
        mock_session.get.return_value = _mock_response({"MediaContainer": {}})
        assert client.get_libraries() == []


# ═══════════════════════════════════════════════════════════════════════════════
# PlexClient.get_items
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlexClientGetItems:
    def test_returns_item_list(self):
        client, mock_session = _client_with_mock_session()
        mock_session.get.return_value = _mock_response(
            {
                "MediaContainer": {
                    "Metadata": [
                        {"ratingKey": "10", "title": "Alien", "year": 1979, "type": "movie"},
                        {"ratingKey": "11", "title": "Aliens", "year": 1986, "type": "movie"},
                    ]
                }
            }
        )
        items = client.get_items("1")
        assert len(items) == 2
        assert items[0].rating_key == "10"
        assert items[0].title == "Alien"
        assert items[0].year == 1979
        assert items[1].display_title == "Aliens (1986)"

    def test_invalid_library_key_raises(self):
        client, _ = _client_with_mock_session()
        with pytest.raises(ValueError, match="Invalid Plex ID"):
            client.get_items("../etc/passwd")

    def test_empty_metadata_returns_empty_list(self):
        client, mock_session = _client_with_mock_session()
        mock_session.get.return_value = _mock_response({"MediaContainer": {}})
        assert client.get_items("1") == []


# ═══════════════════════════════════════════════════════════════════════════════
# PlexClient.get_posters
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlexClientGetPosters:
    def test_returns_poster_list(self):
        client, mock_session = _client_with_mock_session()
        mock_session.get.return_value = _mock_response(
            {
                "MediaContainer": {
                    "Photo": [
                        {
                            "key": "https://image.tmdb.org/abc.jpg",
                            "selected": True,
                            "provider": "com.plexapp.agents.themoviedb",
                        },
                        {
                            "key": "upload://posters/xyz",
                            "selected": False,
                            "provider": "local",
                        },
                    ]
                }
            }
        )
        posters = client.get_posters("42")
        assert len(posters) == 2
        assert posters[0].selected is True
        assert posters[0].source_label == "TMDB"
        assert posters[1].selected is False
        assert posters[1].source_label == "local"
        # rating_key is propagated to each poster
        assert all(p.rating_key == "42" for p in posters)

    def test_invalid_rating_key_raises(self):
        client, _ = _client_with_mock_session()
        with pytest.raises(ValueError, match="Invalid Plex ID"):
            client.get_posters("abc")


# ═══════════════════════════════════════════════════════════════════════════════
# PlexClient.delete_poster
# ═══════════════════════════════════════════════════════════════════════════════


class TestPlexClientDeletePoster:
    def test_delete_http_poster(self):
        client, mock_session = _client_with_mock_session()
        mock_session.delete.return_value = _mock_response({}, status=200)
        client.delete_poster("42", "https://example.com/poster.jpg")
        mock_session.delete.assert_called_once()
        call_url = mock_session.delete.call_args[0][0]
        assert call_url.endswith("/library/metadata/42/posters")

    def test_delete_local_upload_poster(self):
        client, mock_session = _client_with_mock_session()
        mock_session.delete.return_value = _mock_response({}, status=200)
        key = "/library/metadata/42/file?url=upload%3A%2F%2Fposters%2Fmyhash"
        client.delete_poster("42", key)
        call_kwargs = mock_session.delete.call_args[1]
        assert call_kwargs["params"]["url"] == "upload://posters/myhash"

    def test_invalid_rating_key_raises(self):
        client, _ = _client_with_mock_session()
        with pytest.raises(ValueError, match="Invalid Plex ID"):
            client.delete_poster("bad-id!", "https://example.com/poster.jpg")

    def test_auth_error_propagated(self):
        client, mock_session = _client_with_mock_session()
        resp = MagicMock()
        resp.status_code = 401
        mock_session.delete.return_value = resp
        # _raise_for_status will raise PlexAuthError for 401
        with pytest.raises(PlexAuthError):
            client.delete_poster("42", "https://example.com/poster.jpg")


# ═══════════════════════════════════════════════════════════════════════════════
# find_local_token
# ═══════════════════════════════════════════════════════════════════════════════


class TestFindLocalToken:
    def test_returns_empty_on_non_windows(self):
        with patch("platform.system", return_value="Linux"):
            result = find_local_token()
        assert result == ""

    def test_returns_empty_on_macos(self):
        with patch("platform.system", return_value="Darwin"):
            result = find_local_token()
        assert result == ""

    def test_returns_empty_when_no_localappdata(self):
        with patch("platform.system", return_value="Windows"):
            with patch.dict(os.environ, {}, clear=True):
                # Ensure LOCALAPPDATA is absent
                env = {k: v for k, v in os.environ.items() if k != "LOCALAPPDATA"}
                with patch.dict(os.environ, env, clear=True):
                    result = find_local_token()
        assert result == ""

    def test_returns_empty_when_prefs_missing(self):
        with patch("platform.system", return_value="Windows"):
            with patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}):
                with patch("pathlib.Path.exists", return_value=False):
                    result = find_local_token()
        assert result == ""

    def test_extracts_token_from_xml(self):
        xml = 'some xml PlexOnlineToken="mytoken123" other stuff'
        with patch("platform.system", return_value="Windows"):
            with patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.read_text", return_value=xml):
                        result = find_local_token()
        assert result == "mytoken123"

    def test_returns_empty_when_token_not_in_xml(self):
        xml = "<Preferences SomeOtherAttr=\"value\" />"
        with patch("platform.system", return_value="Windows"):
            with patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.read_text", return_value=xml):
                        result = find_local_token()
        assert result == ""

    def test_returns_empty_on_oserror(self):
        with patch("platform.system", return_value="Windows"):
            with patch.dict(os.environ, {"LOCALAPPDATA": r"C:\Users\Test\AppData\Local"}):
                with patch("pathlib.Path.exists", return_value=True):
                    with patch("pathlib.Path.read_text", side_effect=OSError("denied")):
                        result = find_local_token()
        assert result == ""
