# Plex Poster Manager — Claude Code Guide

## Project Overview

A Docker container that connects to a Plex Media Server and automatically deletes old, unused posters for each media item, keeping only the currently selected poster. Configurable entirely through environment variables.

## Project Structure

```
plex-poster-manager/
├── src/
│   ├── main.py          # Entry point — loads config, sets up logging, runs once or on schedule
│   ├── config.py        # Reads and validates environment variables into a Config dataclass
│   ├── plex_client.py   # HTTP client wrapping all Plex API calls (GET/DELETE)
│   └── cleaner.py       # Iterates libraries/items, identifies and deletes non-selected posters
├── requirements.txt     # Hash-locked dependencies for Linux/Docker (Python 3.12)
├── Dockerfile           # python:3.12-slim, runs as non-root appuser
├── docker-compose.yml   # For scheduled (long-running) mode
└── .env.example         # Template for required and optional environment variables
```

## Local Development Setup

Requires Python 3.12+. The `requirements.txt` is hash-locked for the Linux/Docker platform — on Linux it works directly; on macOS install direct deps without hash verification:

```bash
# Linux
pip install -r requirements.txt

# macOS (hash check would fail for platform-specific wheels)
pip install requests==2.32.5 apscheduler==3.10.4 python-dotenv==1.0.1
```

Set up your environment:

```bash
cp .env.example .env
# Edit .env — set PLEX_URL and PLEX_TOKEN at minimum
```

Run the app locally:

```bash
PYTHONPATH=src python src/main.py
# Or with .env loaded automatically by python-dotenv:
python src/main.py
```

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PLEX_URL` | Yes | — | Base URL of Plex server, e.g. `http://192.168.1.10:32400` |
| `PLEX_TOKEN` | Yes | — | Plex account auth token (`X-Plex-Token`) |
| `PLEX_LIBRARIES` | No | all | Comma-separated library names or IDs to process |
| `DRY_RUN` | No | `false` | Log what would be deleted without deleting |
| `SCHEDULE_CRON` | No | — | 5-field cron expression (e.g. `0 3 * * *`). If unset, runs once. |
| `LOG_LEVEL` | No | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` |

## Docker Commands

```bash
# Build and run once
docker build -t plex-poster-manager .
docker run --rm --env-file .env plex-poster-manager

# Dry run (safe preview — no deletions)
docker run --rm -e PLEX_URL=... -e PLEX_TOKEN=... -e DRY_RUN=true plex-poster-manager

# Scheduled mode (stays running, runs on cron)
docker compose up -d --build
docker compose logs -f
docker compose down
```

## Architecture Notes

- **`config.py`** — `load_config()` reads env vars, validates cron syntax and log level, returns a frozen `Config` dataclass. No external dependencies.
- **`plex_client.py`** — `PlexClient` wraps a `requests.Session` with the auth token in headers. All Plex IDs are validated as numeric (`_safe_id`) and poster keys are validated as internal paths or HTTP(S) URLs (`_safe_poster_key`) to prevent injection. Logs paths only — never full URLs or headers (which would expose the token).
- **`cleaner.py`** — `PosterCleaner.run()` fetches all library sections, optionally filters to configured libraries, then for each item fetches its poster list and deletes all non-selected posters. Auth failures (HTTP 401/403) abort immediately; other errors are logged and skipped.
- **`main.py`** — Orchestrates: load config → setup logging → warn on HTTP → instantiate client → run once or start `BlockingScheduler`.

## Plex API Endpoints Used

| Action | Method | Endpoint |
|---|---|---|
| List libraries | GET | `/library/sections` |
| List items | GET | `/library/sections/{id}/all` |
| Get posters | GET | `/library/metadata/{ratingKey}/posters` |
| Delete poster | DELETE | `/library/metadata/{ratingKey}/posters?url={key}` |

All requests use the `X-Plex-Token` header. Responses are `Accept: application/json`.

## Security Considerations

- **Never commit `.env`** — it is in `.gitignore`. Verify with `git status` before pushing.
- **Use `DRY_RUN=true`** before the first real run to audit planned deletions.
- The selected poster is **never** deleted — only non-selected posters are removed.
- The Dockerfile runs as a non-root user (`appuser`) to limit blast radius.
- `requirements.txt` uses hash verification for supply-chain integrity.

## Updating Dependencies

```bash
# Download new package for Linux/Python 3.12
pip download <package>==<version> \
  -d /tmp/pkgs \
  --platform manylinux2014_x86_64 \
  --only-binary=:all: \
  --python-version 3.12

# Generate hashes
pip hash /tmp/pkgs/*

# Update requirements.txt, then verify
docker build -t plex-poster-manager .
```

## No Tests or Linter Configured

There are currently no automated tests or linter configuration in this repository.
