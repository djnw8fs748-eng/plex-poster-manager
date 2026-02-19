import logging
from typing import Any, Dict, List

import requests

log = logging.getLogger(__name__)


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
        log.debug(f"GET {url} params={params}")
        response = self.session.get(url, params=params, timeout=30)
        response.raise_for_status()
        return response.json()

    def _delete(self, path: str, **params) -> None:
        url = f"{self.base_url}{path}"
        log.debug(f"DELETE {url} params={params}")
        response = self.session.delete(url, params=params, timeout=30)
        response.raise_for_status()

    def get_libraries(self) -> List[Dict[str, Any]]:
        data = self._get("/library/sections")
        return data.get("MediaContainer", {}).get("Directory", [])

    def get_library_items(self, section_id: str) -> List[Dict[str, Any]]:
        data = self._get(f"/library/sections/{section_id}/all")
        return data.get("MediaContainer", {}).get("Metadata", [])

    def get_posters(self, rating_key: str) -> List[Dict[str, Any]]:
        data = self._get(f"/library/metadata/{rating_key}/posters")
        return data.get("MediaContainer", {}).get("Metadata", [])

    def delete_poster(self, rating_key: str, poster_key: str) -> None:
        self._delete(f"/library/metadata/{rating_key}/posters", url=poster_key)
