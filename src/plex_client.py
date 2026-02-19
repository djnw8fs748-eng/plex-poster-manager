import logging
import re
import urllib.parse
from typing import Any, Dict, List

import requests

log = logging.getLogger(__name__)

# Plex section IDs and rating keys are always numeric
_NUMERIC_ID_RE = re.compile(r'^\d+$')


def _safe_id(value: Any, name: str) -> str:
    """Ensure a Plex ID value is a plain numeric string to prevent path injection."""
    s = str(value)
    if not _NUMERIC_ID_RE.match(s):
        raise ValueError(f"Invalid {name}: expected numeric ID, got {s!r}")
    return s


def _safe_poster_key(value: str, name: str) -> str:
    """
    Validate a poster key from the Plex API before using it in a request.
    Accepts internal Plex paths (/library/...) and external HTTP/HTTPS URLs.
    """
    if not isinstance(value, str) or not value:
        raise ValueError(f"Invalid {name}: empty or non-string value")

    if value.startswith("/"):
        # Internal Plex path — reject path traversal attempts
        if ".." in value.split("/"):
            raise ValueError(f"Invalid {name}: path traversal detected in {value!r}")
        return value

    if value.startswith(("http://", "https://")):
        # External poster URL (e.g. from TMDB) — ensure it is well-formed
        parsed = urllib.parse.urlparse(value)
        if not parsed.netloc:
            raise ValueError(f"Invalid {name}: malformed URL {value!r}")
        return value

    raise ValueError(f"Invalid {name}: unrecognised format {value!r}")


class PlexClient:
    def __init__(self, base_url: str, token: str):
        self.base_url = base_url.rstrip("/")
        self.session = requests.Session()
        self.session.headers.update({
            "X-Plex-Token": token,
            "Accept": "application/json",
        })

    def _get(self, path: str, **params) -> Dict[str, Any]:
        url = f"{self.base_url}{path}"
        # Log path only — never log the full URL (contains server address)
        # or headers (contain the auth token).
        log.debug("GET %s", path)
        response = self.session.get(url, params=params, timeout=(5, 30))
        response.raise_for_status()
        return response.json()

    def _delete(self, path: str, **params) -> None:
        url = f"{self.base_url}{path}"
        log.debug("DELETE %s", path)
        response = self.session.delete(url, params=params, timeout=(5, 30))
        response.raise_for_status()

    def get_libraries(self) -> List[Dict[str, Any]]:
        data = self._get("/library/sections")
        return data.get("MediaContainer", {}).get("Directory", [])

    def get_library_items(self, section_id: str) -> List[Dict[str, Any]]:
        sid = _safe_id(section_id, "section_id")
        data = self._get(f"/library/sections/{sid}/all")
        return data.get("MediaContainer", {}).get("Metadata", [])

    def get_posters(self, rating_key: str) -> List[Dict[str, Any]]:
        rk = _safe_id(rating_key, "rating_key")
        data = self._get(f"/library/metadata/{rk}/posters")
        return data.get("MediaContainer", {}).get("Metadata", [])

    def delete_poster(self, rating_key: str, poster_key: str) -> None:
        rk = _safe_id(rating_key, "rating_key")
        pk = _safe_poster_key(poster_key, "poster_key")
        self._delete(f"/library/metadata/{rk}/posters", url=pk)
