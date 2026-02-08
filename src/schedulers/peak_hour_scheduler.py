import asyncio
import logging
import time

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger

from src.agents.peak_hour_agent import PeakHourAgent

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def run_peak_agent_for_all_cameras():
    agent = PeakHourAgent()
    cameras = ["CAM_001"]  # later: load from DB/config

    for cam_id in cameras:
        alerts = asyncio.run(agent.run(cam_id))
        logger.info("PeakHourAgent run for %s → %d alerts", cam_id, len(alerts))


if __name__ == "__main__":
    scheduler = BackgroundScheduler(timezone="Asia/Kolkata")
    # Run at the start of every hour
    scheduler.add_job(
        run_peak_agent_for_all_cameras,
        CronTrigger(minute=0),
        id="peak_hour_job",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("🔁 Peak hour scheduler started (runs every hour at :00)")

    try:
        while True:
            time.sleep(5)
    except (KeyboardInterrupt, SystemExit):
        scheduler.shutdown()
        logger.info("⏹️ Scheduler stopped")
