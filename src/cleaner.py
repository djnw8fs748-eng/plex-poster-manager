import logging

import requests

from config import Config
from plex_client import PlexClient

log = logging.getLogger(__name__)

_AUTH_STATUS_CODES = {401, 403}


class PosterCleaner:
    def __init__(self, client: PlexClient, config: Config):
        self.client = client
        self.config = config

    def run(self) -> None:
        libraries = self.client.get_libraries()

        if self.config.plex_libraries:
            libraries = [
                lib for lib in libraries
                if lib.get("title") in self.config.plex_libraries
                or str(lib.get("key")) in self.config.plex_libraries
            ]
            log.info(
                "Filtered to %d librar(ies): %s",
                len(libraries),
                [lib["title"] for lib in libraries],
            )
        else:
            log.info("Processing all %d librar(ies)", len(libraries))

        total_deleted = 0
        for library in libraries:
            section_id = library.get("key")
            title = library.get("title", f"id={section_id}")
            log.info("Processing library: %s (id=%s)", title, section_id)
            total_deleted += self._clean_library(section_id)

        log.info("Run complete. Total posters deleted: %d", total_deleted)

    def _clean_library(self, section_id: str) -> int:
        items = self.client.get_library_items(section_id)
        log.info("  Found %d item(s)", len(items))
        deleted = 0
        for item in items:
            rating_key = item.get("ratingKey")
            item_title = item.get("title", f"ratingKey={rating_key}")
            deleted += self._clean_item(rating_key, item_title)
        return deleted

    def _clean_item(self, rating_key: str, item_title: str) -> int:
        try:
            posters = self.client.get_posters(rating_key)
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            if status in _AUTH_STATUS_CODES:
                # Auth failures are fatal — raise so the run aborts clearly
                raise RuntimeError(
                    f"Authentication failed (HTTP {status}) fetching posters for "
                    f"[{item_title}] — check your PLEX_TOKEN"
                ) from exc
            log.warning("  [%s] HTTP error fetching posters: status=%s", item_title, status)
            return 0
        except (requests.ConnectionError, requests.Timeout) as exc:
            # Log type only — not the full message, which may contain server addresses
            log.warning("  [%s] Network error fetching posters: %s", item_title, type(exc).__name__)
            return 0
        except ValueError as exc:
            log.warning("  [%s] Invalid data from server: %s", item_title, exc)
            return 0

        if not posters:
            log.debug("  [%s] No posters found, skipping", item_title)
            return 0

        to_delete = [p for p in posters if not p.get("selected")]

        if not to_delete:
            log.debug("  [%s] Only the selected poster exists, nothing to do", item_title)
            return 0

        selected = next((p for p in posters if p.get("selected")), None)
        selected_key = selected.get("key", "unknown") if selected else "none selected"
        log.info(
            "  [%s] %d poster(s) — keeping: %s — deleting: %d",
            item_title, len(posters), selected_key, len(to_delete),
        )

        deleted = 0
        for poster in to_delete:
            poster_key = poster.get("key", "")
            if self.config.dry_run:
                log.info("    [DRY RUN] Would delete: %s", poster_key)
            else:
                try:
                    self.client.delete_poster(rating_key, poster_key)
                    log.info("    Deleted: %s", poster_key)
                    deleted += 1
                except requests.HTTPError as exc:
                    status = exc.response.status_code if exc.response is not None else None
                    if status in _AUTH_STATUS_CODES:
                        raise RuntimeError(
                            f"Authentication failed (HTTP {status}) deleting poster for "
                            f"[{item_title}] — check your PLEX_TOKEN"
                        ) from exc
                    log.warning("    HTTP error deleting poster: status=%s", status)
                except (requests.ConnectionError, requests.Timeout) as exc:
                    log.warning("    Network error deleting poster: %s", type(exc).__name__)
                except ValueError as exc:
                    log.warning("    Skipping invalid poster key: %s", exc)

        return deleted
