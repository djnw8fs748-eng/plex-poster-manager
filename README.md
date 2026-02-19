# Plex Poster Manager

A Docker container that connects to your Plex Media Server and automatically deletes old, unused posters for media items in your libraries — keeping only the currently selected poster for each item.

---

## How It Works

Plex accumulates posters over time as you upload artwork, refresh metadata, or change posters. Each media item can store many posters, but only one is displayed. This tool:

1. Connects to your Plex server over HTTP using a personal auth token
2. Iterates over your configured libraries (or all libraries by default)
3. For each media item, fetches the full list of posters via the Plex API
4. Deletes every poster **except** the currently selected one
5. Logs all actions — with a dry-run mode so you can preview changes safely

### Plex API endpoints used

| Action | Method | Endpoint |
|---|---|---|
| List libraries | GET | `/library/sections` |
| List items | GET | `/library/sections/{id}/all` |
| Get posters | GET | `/library/metadata/{ratingKey}/posters` |
| Delete poster | DELETE | `/library/metadata/{ratingKey}/posters?url={key}` |

All requests use the `X-Plex-Token` header for authentication.

---

## Configuration

Copy `.env.example` to `.env` and fill in your values:

```bash
cp .env.example .env
```

| Variable | Required | Default | Description |
|---|---|---|---|
| `PLEX_URL` | Yes | — | Base URL of your Plex server, e.g. `http://192.168.1.10:32400` |
| `PLEX_TOKEN` | Yes | — | Your Plex auth token ([how to find it](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/)) |
| `PLEX_LIBRARIES` | No | all | Comma-separated library names or IDs to process. Leave empty for all libraries. |
| `DRY_RUN` | No | `false` | Set to `true` to log what would be deleted without deleting anything |
| `SCHEDULE_CRON` | No | — | Cron expression for scheduled runs (e.g. `0 3 * * *`). If unset, runs once and exits. |
| `LOG_LEVEL` | No | `INFO` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR` |

---

## Ports

This container makes **outbound** HTTP requests to your Plex server — it does not listen on any port and does not need any ports exposed. Your Plex server should be accessible from the container at the address you set in `PLEX_URL` (Plex default port: `32400`).

---

## Deploying with Docker

### One-shot (run once and exit)

Suitable for use with an external scheduler such as host cron, Kubernetes CronJob, or Unraid user scripts.

```bash
# Build
docker build -t plex-poster-manager .

# Run
docker run --rm --env-file .env plex-poster-manager
```

### Scheduled (container stays running)

Set `SCHEDULE_CRON` in your `.env` and use Docker Compose. The container will run an initial pass on startup, then repeat on the defined schedule.

```bash
# Start
docker compose up -d

# View logs
docker compose logs -f

# Stop
docker compose down
```

**Example `.env` for nightly runs at 3am:**
```env
PLEX_URL=http://192.168.1.10:32400
PLEX_TOKEN=your_token_here
DRY_RUN=false
SCHEDULE_CRON=0 3 * * *
LOG_LEVEL=INFO
```

---

## Dry Run (recommended first step)

Always test with `DRY_RUN=true` before running for real. This logs every poster that would be deleted without making any changes:

```bash
docker run --rm \
  -e PLEX_URL=http://192.168.1.10:32400 \
  -e PLEX_TOKEN=your_token_here \
  -e DRY_RUN=true \
  plex-poster-manager
```

---

## Building Locally

Requires Python 3.12+ and the dependencies in `requirements.txt`.

```bash
pip install -r requirements.txt

# Run with env vars
PLEX_URL=http://... PLEX_TOKEN=... python src/main.py
```

---

## Safety

- **The selected poster is never deleted.** Only posters not currently selected are removed.
- **Dry-run mode** lets you audit all planned deletions before committing.
- All deletions are logged with the item name, poster key, and timestamp.
