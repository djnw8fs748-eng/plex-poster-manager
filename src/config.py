import os
import re
from dataclasses import dataclass
from typing import List, Optional

_VALID_LOG_LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

# Allow only digits, *, -, ,, / in cron fields (standard cron characters)
_CRON_FIELD_RE = re.compile(r'^[\d\*\-\,\/]+$')


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
    if schedule_cron is not None:
        _validate_cron(schedule_cron)

    log_level_raw = os.environ.get("LOG_LEVEL", "INFO").upper()
    if log_level_raw not in _VALID_LOG_LEVELS:
        raise ValueError(
            f"LOG_LEVEL must be one of {sorted(_VALID_LOG_LEVELS)}, got: {log_level_raw!r}"
        )

    return Config(
        plex_url=plex_url,
        plex_token=plex_token,
        plex_libraries=plex_libraries,
        dry_run=dry_run,
        schedule_cron=schedule_cron,
        log_level=log_level_raw,
    )


def _validate_cron(expr: str) -> None:
    """Validate a cron expression has exactly 5 fields with safe characters."""
    fields = expr.split()
    if len(fields) != 5:
        raise ValueError(
            f"SCHEDULE_CRON must be a 5-field cron expression (e.g. '0 3 * * *'), "
            f"got {len(fields)} field(s): {expr!r}"
        )
    for field in fields:
        if not _CRON_FIELD_RE.match(field):
            raise ValueError(
                f"SCHEDULE_CRON field {field!r} contains invalid characters. "
                f"Only digits, *, -, ,, / are allowed."
            )
