import logging
from datetime import datetime

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from tzlocal import get_localzone_name

from ..config import RuntimeContext
from ..portfolio.updater import update_portfolio_once

logger = logging.getLogger(__name__)


def _job(ctx: RuntimeContext) -> None:
    logger.info("Starting scheduled portfolio update")
    update_portfolio_once(ctx)
    logger.info("Finished scheduled portfolio update")


def start_scheduler(ctx: RuntimeContext) -> None:
    schedule = ctx.settings.schedule
    timezone_name = schedule.timezone or get_localzone_name()

    scheduler = BackgroundScheduler(timezone=timezone_name)
    trigger = CronTrigger(day=schedule.day_of_month, hour=schedule.hour, minute=schedule.minute)

    scheduler.add_job(_job, trigger=trigger, args=[ctx], name="monthly-portfolio-update", replace_existing=True)

    logger.info(
        "Scheduler started: day=%s hour=%s minute=%s tz=%s",
        schedule.day_of_month,
        schedule.hour,
        schedule.minute,
        timezone_name,
    )

    scheduler.start()

    try:
        # Keep running
        import time

        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
    finally:
        scheduler.shutdown()
