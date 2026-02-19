import logging
import sys

from dotenv import load_dotenv

from cleaner import PosterCleaner
from config import Config, load_config
from plex_client import PlexClient

_VALID_LOG_LEVELS: dict[str, int] = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=_VALID_LOG_LEVELS[level],
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )


def run_once(config: Config, client: PlexClient) -> None:
    PosterCleaner(client, config).run()


def main() -> None:
    # Load .env for local development convenience; no-op when env vars are
    # already set (e.g. via Docker --env-file or docker-compose env_file).
    load_dotenv()

    try:
        config = load_config()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    setup_logging(config.log_level)
    log = logging.getLogger(__name__)

    if config.dry_run:
        log.info("DRY RUN mode enabled — no posters will be deleted")

    if config.plex_url.startswith("http://"):
        log.warning(
            "PLEX_URL is using unencrypted HTTP. Your Plex token will be sent in "
            "plaintext. Use HTTPS (https://) if your Plex server supports it."
        )

    client = PlexClient(config.plex_url, config.plex_token)

    if config.schedule_cron:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger

        try:
            trigger = CronTrigger.from_crontab(config.schedule_cron)
        except ValueError as exc:
            log.error("Invalid SCHEDULE_CRON %r: %s", config.schedule_cron, exc)
            sys.exit(1)

        scheduler = BlockingScheduler()
        scheduler.add_job(run_once, trigger, args=[config, client])

        log.info("Scheduler started — cron: %r", config.schedule_cron)
        log.info("Running initial pass before first scheduled run...")
        run_once(config, client)

        try:
            scheduler.start()
        except (KeyboardInterrupt, SystemExit):
            log.info("Scheduler stopped")
    else:
        log.info("One-shot mode — running once then exiting")
        run_once(config, client)


if __name__ == "__main__":
    main()
