import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Config:
    plex_url: str
    plex_token: str
    plex_libraries: List[str]  # empty list = all libraries
    dry_run: bool
    schedule_cron: Optional[str]
    log_level: str


def load_config() -> Config:
    plex_url = os.environ.get("PLEX_URL", "").rstrip("/")
    if not plex_url:
        raise ValueError("PLEX_URL environment variable is required")

    plex_token = os.environ.get("PLEX_TOKEN", "")
    if not plex_token:
        raise ValueError("PLEX_TOKEN environment variable is required")

    libraries_raw = os.environ.get("PLEX_LIBRARIES", "")
    plex_libraries = (
        [lib.strip() for lib in libraries_raw.split(",") if lib.strip()]
        if libraries_raw.strip()
        else []
    )

    dry_run = os.environ.get("DRY_RUN", "false").lower() in ("true", "1", "yes")
    schedule_cron = os.environ.get("SCHEDULE_CRON", "").strip() or None
    log_level = os.environ.get("LOG_LEVEL", "INFO").upper()

    return Config(
        plex_url=plex_url,
        plex_token=plex_token,
        plex_libraries=plex_libraries,
        dry_run=dry_run,
        schedule_cron=schedule_cron,
        log_level=log_level,
    )
