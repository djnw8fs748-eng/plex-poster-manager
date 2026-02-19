# Plex Poster Manager

A Docker container that connects to your Plex Media Server and automatically deletes old, unused posters for media items in your libraries — keeping only the currently selected poster for each item.

---

## Prerequisites

- [Docker](https://docs.docker.com/get-docker/) (v20.10+)
- [Docker Compose](https://docs.docker.com/compose/install/) (v2.0+ — included with Docker Desktop)
- A running Plex Media Server reachable over HTTP
- A Plex auth token ([how to find yours](https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/))

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

### 1. Clone the repository

```bash
git clone https://github.com/djnw8fs748-eng/plex-poster-manager.git
cd plex-poster-manager
```

### 2. Configure your environment

```bash
cp .env.example .env
```

Open `.env` and set at minimum `PLEX_URL` and `PLEX_TOKEN`. See the [Configuration](#configuration) table above for all options.

### 3. Build the Docker image

Run this from the repository root (the directory containing the `Dockerfile`):

```bash
docker build -t plex-poster-manager .
```

To confirm the image was built:

```bash
docker images plex-poster-manager
```

---

### One-shot (run once and exit)

Suitable for use with an external scheduler such as host cron, Kubernetes CronJob, or Unraid user scripts.

```bash
docker run --rm --env-file .env plex-poster-manager
```

The `--rm` flag removes the container automatically after it exits.

---

### Scheduled (container stays running)

Set `SCHEDULE_CRON` in your `.env`, then use Docker Compose. The container runs an initial pass on startup and repeats on the defined schedule.

**Example `.env` for nightly runs at 3am:**
```env
PLEX_URL=http://192.168.1.10:32400
PLEX_TOKEN=your_token_here
DRY_RUN=false
SCHEDULE_CRON=0 3 * * *
LOG_LEVEL=INFO
```

```bash
# Build and start in the background
docker compose up -d --build

# Confirm the container is running
docker compose ps

# Stream logs
docker compose logs -f

# Stop the container
docker compose down
```

---

### Rebuilding after changes

If you update your `.env` or pull new code, rebuild and restart:

```bash
docker compose down
docker compose up -d --build
```

Or for a plain `docker run` workflow:

```bash
docker build -t plex-poster-manager .
docker run --rm --env-file .env plex-poster-manager
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

## Running Locally (without Docker)

Requires Python 3.12+ and pip.

```bash
pip install -r requirements.txt

# Run with env vars inline
PLEX_URL=http://192.168.1.10:32400 PLEX_TOKEN=your_token_here python src/main.py

# Or load from a .env file
export $(cat .env | xargs) && python src/main.py
```

---

## Safety

- **The selected poster is never deleted.** Only posters not currently selected are removed.
- **Dry-run mode** lets you audit all planned deletions before committing.
- All deletions are logged with the item name, poster key, and timestamp.
