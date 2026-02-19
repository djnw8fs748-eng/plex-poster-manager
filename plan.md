# Plex Poster Manager — Plan

## Overview

A Docker container that connects to a Plex Media Server over HTTP using an account auth token, scans configured libraries, and deletes old/unwanted posters from media items, retaining only the currently selected poster.

---

## Goals

- Connect to Plex Media Server via its local HTTP API using a user-supplied `X-Plex-Token`
- Iterate over one or more configured Plex libraries (movies, TV shows, etc.)
- For each media item, fetch all uploaded posters
- Delete all posters except the currently selected one
- Run on a schedule or as a one-shot container
- Be fully configurable via environment variables — no code changes required

---

## Plex API Endpoints Used

| Purpose | Method | Endpoint |
|---|---|---|
| List libraries | GET | `/library/sections` |
| List items in library | GET | `/library/sections/{sectionId}/all` |
| Get posters for item | GET | `/library/metadata/{ratingKey}/posters` |
| Delete a poster | DELETE | `/library/metadata/{ratingKey}/posters?url={posterUrl}` |

All requests include the header `X-Plex-Token: <token>` and `Accept: application/json`.

---

## Architecture

```
plex-poster-manager/
├── Dockerfile
├── docker-compose.yml
├── .env.example
├── src/
│   ├── main.py           # Entry point, orchestrates the run
│   ├── plex_client.py    # HTTP client wrapping Plex API calls
│   ├── cleaner.py        # Logic to identify and delete old posters
│   └── config.py         # Loads and validates environment variables
└── requirements.txt
```

### Components

**`config.py`**
- Reads environment variables
- Validates required values are present
- Exposes a single `Config` dataclass

**`plex_client.py`**
- Wraps `requests` (or `httpx`) for all Plex HTTP calls
- Handles auth token injection on every request
- Returns parsed JSON responses

**`cleaner.py`**
- For each library section → each media item → fetch posters
- Identifies the selected poster (marked `selected="1"` in the API response)
- Deletes all other posters via the DELETE endpoint
- Logs what is deleted and what is kept

**`main.py`**
- Loads config
- Instantiates client and cleaner
- Runs once or loops on a schedule based on `SCHEDULE_CRON` env var

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `PLEX_URL` | Yes | — | Base URL of Plex server, e.g. `http://192.168.1.10:32400` |
| `PLEX_TOKEN` | Yes | — | Plex account auth token (`X-Plex-Token`) |
| `PLEX_LIBRARIES` | No | all | Comma-separated library names or IDs to process. Defaults to all libraries. |
| `DRY_RUN` | No | `false` | If `true`, log what would be deleted without actually deleting |
| `SCHEDULE_CRON` | No | — | Cron expression to run on a schedule (e.g. `0 3 * * *`). If unset, runs once and exits. |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Docker

**Dockerfile**
- Base image: `python:3.12-slim`
- Install dependencies from `requirements.txt`
- Copy `src/` into the image
- `CMD ["python", "src/main.py"]`

**docker-compose.yml**
- Mounts `.env` for easy local configuration
- Restarts unless stopped (suitable for scheduled mode)

---

## Runtime Modes

### One-shot
Container runs, processes all libraries, then exits. Suitable for use with an external scheduler (e.g. cron, Kubernetes CronJob).

```bash
docker run --env-file .env plex-poster-manager
```

### Scheduled
Set `SCHEDULE_CRON` and the container stays running, executing on the defined schedule.

```yaml
environment:
  SCHEDULE_CRON: "0 3 * * *"
```

---

## Safety

- `DRY_RUN=true` mode logs all actions without making any DELETE calls — always test with this first
- The selected poster is never deleted; only non-selected posters are removed
- All deletions are logged with the item name, poster URL, and timestamp

---

## Dependencies

- `requests` or `httpx` — HTTP calls to Plex
- `python-dotenv` — Load `.env` in local dev
- `apscheduler` — Scheduling support
- `pydantic` — Config validation (optional, can use dataclasses)

---

## Out of Scope (v1)

- HTTPS / TLS verification (communicates over HTTP as specified)
- Plex Pass features or managed users
- Poster backup before deletion
- Web UI or dashboard
