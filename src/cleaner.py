import logging

from config import Config
from plex_client import PlexClient

log = logging.getLogger(__name__)


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
                f"Filtered to {len(libraries)} librar(ies): "
                f"{[lib['title'] for lib in libraries]}"
            )
        else:
            log.info(f"Processing all {len(libraries)} librar(ies)")

        total_deleted = 0
        for library in libraries:
            section_id = library.get("key")
            title = library.get("title", f"id={section_id}")
            log.info(f"Processing library: {title} (id={section_id})")
            total_deleted += self._clean_library(section_id)

        log.info(f"Run complete. Total posters deleted: {total_deleted}")

    def _clean_library(self, section_id: str) -> int:
        items = self.client.get_library_items(section_id)
        log.info(f"  Found {len(items)} item(s)")
        deleted = 0
        for item in items:
            rating_key = item.get("ratingKey")
            item_title = item.get("title", f"ratingKey={rating_key}")
            deleted += self._clean_item(rating_key, item_title)
        return deleted

    def _clean_item(self, rating_key: str, item_title: str) -> int:
        try:
            posters = self.client.get_posters(rating_key)
        except Exception as exc:
            log.warning(f"  [{item_title}] Failed to fetch posters: {exc}")
            return 0

        if not posters:
            log.debug(f"  [{item_title}] No posters found, skipping")
            return 0

        to_delete = [p for p in posters if not p.get("selected")]

        if not to_delete:
            log.debug(f"  [{item_title}] Only the selected poster exists, nothing to do")
            return 0

        selected = next((p for p in posters if p.get("selected")), None)
        selected_key = selected.get("key", "unknown") if selected else "none selected"
        log.info(
            f"  [{item_title}] {len(posters)} poster(s) — "
            f"keeping: {selected_key} — "
            f"deleting: {len(to_delete)}"
        )

        deleted = 0
        for poster in to_delete:
            poster_key = poster.get("key", "")
            if self.config.dry_run:
                log.info(f"    [DRY RUN] Would delete: {poster_key}")
            else:
                try:
                    self.client.delete_poster(rating_key, poster_key)
                    log.info(f"    Deleted: {poster_key}")
                    deleted += 1
                except Exception as exc:
                    log.warning(f"    Failed to delete {poster_key}: {exc}")

        return deleted
