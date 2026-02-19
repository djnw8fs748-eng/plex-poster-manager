import logging
import sys

from cleaner import PosterCleaner
from config import Config, load_config
from plex_client import PlexClient


def setup_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level, logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
        stream=sys.stdout,
    )


def run_once(config: Config, client: PlexClient) -> None:
    PosterCleaner(client, config).run()


def main() -> None:
    try:
        config = load_config()
    except ValueError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        sys.exit(1)

    setup_logging(config.log_level)
    log = logging.getLogger(__name__)

    if config.dry_run:
        log.info("DRY RUN mode enabled — no posters will be deleted")

    client = PlexClient(config.plex_url, config.plex_token)

    if config.schedule_cron:
        from apscheduler.schedulers.blocking import BlockingScheduler
        from apscheduler.triggers.cron import CronTrigger

        scheduler = BlockingScheduler()
        trigger = CronTrigger.from_crontab(config.schedule_cron)
        scheduler.add_job(run_once, trigger, args=[config, client])

        log.info(f"Scheduler started — cron: '{config.schedule_cron}'")
        log.info("Running initial pass before waiting for next scheduled run...")
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
