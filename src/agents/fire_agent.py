# src/agents/fire_agent.py

import os
import json
import logging
from datetime import datetime, timedelta, timezone  # time window

from dotenv import load_dotenv
from sqlalchemy import create_engine, func
from sqlalchemy.orm import sessionmaker

from src.database.models import Detection, Alert

load_dotenv()

# --- Logging setup ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
logger = logging.getLogger("fire_agent")

# --- Database setup ---
DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:"
    f"{os.getenv('POSTGRES_PASSWORD')}@"
    f"{os.getenv('POSTGRES_HOST')}:"
    f"{os.getenv('POSTGRES_PORT')}/"
    f"{os.getenv('POSTGRES_DB')}"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

# --- Config ---
MIN_FIRE_COUNT = int(os.getenv("FIRE_AGENT_MIN_FIRE_COUNT", 1))
MIN_SMOKE_COUNT = int(os.getenv("FIRE_AGENT_MIN_SMOKE_COUNT", 1))
WINDOW_SEC = int(os.getenv("FIRE_AGENT_WINDOW_SEC", 120))  # last N seconds
CAMERA_ID = os.getenv("FIRE_AGENT_CAMERA_ID", "CAM_001")


def evaluate_window(session, camera_id: str):
    """
    Count fire/smoke detections for this camera in the last WINDOW_SEC seconds.
    Only recent detections from this run/video are used.
    """
    now = datetime.now(timezone.utc)
    window_start = now - timedelta(seconds=WINDOW_SEC)

    logger.info(
        "Checking detections for camera=%s in window [%s, %s]",
        camera_id,
        window_start.isoformat(),
        now.isoformat(),
    )

    rows = (
        session.query(
            Detection.class_name,
            func.count(Detection.id).label("cnt"),
        )
        .filter(
            Detection.camera_id == camera_id,
            Detection.timestamp >= window_start,
            Detection.timestamp <= now,
            Detection.class_name.in_(["fire", "smoke"]),
        )
        .group_by(Detection.class_name)
        .all()
    )

    if not rows:
        logger.info("No fire/smoke detections in this window.")
        return

    counts = {r.class_name: r.cnt for r in rows}
    logger.info("Window counts for camera %s: %s", camera_id, counts)

    alert_payload = {
        "camera_id": camera_id,
        "counts": counts,
        "window_start": window_start.isoformat(),
        "window_end": now.isoformat(),
        "note": f"Last {WINDOW_SEC} seconds only.",
    }

    fire_count = counts.get("fire", 0)
    smoke_count = counts.get("smoke", 0)

    if fire_count >= MIN_FIRE_COUNT:
        create_alert(
            session=session,
            camera_id=camera_id,
            alert_type="fire",
            severity="critical",
            message=f"Fire detected: {fire_count} fire detections in last {WINDOW_SEC}s.",
            data=alert_payload,
        )

    if smoke_count >= MIN_SMOKE_COUNT:
        create_alert(
            session=session,
            camera_id=camera_id,
            alert_type="smoke",
            severity="warning",
            message=f"Smoke detected: {smoke_count} smoke detections in last {WINDOW_SEC}s.",
            data=alert_payload,
        )


def create_alert(
    session,
    camera_id: str,
    alert_type: str,
    severity: str,
    message: str,
    data: dict,
):
    """
    Insert an alert row using the actual Alert model fields:
    alert_type, severity, camera_id, timestamp, extra, acknowledged.
    """
    now = datetime.now(timezone.utc)

    alert = Alert(
        alert_type=alert_type,
        severity=severity,
        camera_id=camera_id,
        timestamp=now,
        extra={
            "message": message,
            "data": data,
        },
        # acknowledged defaults to False in the model
    )

    session.add(alert)
    session.commit()

    logger.info(
        "Created %s alert (severity=%s) for camera=%s: %s",
        alert_type,
        severity,
        camera_id,
        message,
    )


def run_fire_agent():
    logger.info("Running fire agent once for camera_id=%s", CAMERA_ID)
    logger.info(
        "Config: MIN_FIRE_COUNT=%s, MIN_SMOKE_COUNT=%s, WINDOW_SEC=%s",
        MIN_FIRE_COUNT,
        MIN_SMOKE_COUNT,
        WINDOW_SEC,
    )

    session = SessionLocal()
    try:
        evaluate_window(session, CAMERA_ID)
    except Exception as e:
        logger.exception("Error during evaluation: %s", e)
        session.rollback()
    finally:
        session.close()
        logger.info("Fire agent finished and exited.")


if __name__ == "__main__":
    run_fire_agent()
