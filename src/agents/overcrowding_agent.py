import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import Dict, List

from dotenv import load_dotenv
from sqlalchemy import create_engine, func, distinct
from sqlalchemy.orm import sessionmaker

from src.database.models import Detection, Alert

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PostgreSQL URL (same style as peak_hour_agent)
DATABASE_URL = (
    f"postgresql+psycopg://{os.getenv('POSTGRES_USER', 'hive_user')}:"
    f"{os.getenv('POSTGRES_PASSWORD', 'hive1234')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5432')}/"
    f"{os.getenv('POSTGRES_DB', 'hive_dynamics')}"
)

# Simple per-camera capacity config (unique people allowed in window)
CAMERA_CAPACITY: Dict[str, int] = {
    "CAM_001": int(os.getenv("CAM_001_MAX_OCCUPANCY", 40)),
    # add more cameras here
}

WINDOW_MINUTES = int(os.getenv("OVERCROWDING_WINDOW_MINUTES", 10))
HIGH_RATIO = float(os.getenv("OVERCROWDING_HIGH_RATIO", 1.5))
MEDIUM_RATIO = float(os.getenv("OVERCROWDING_MEDIUM_RATIO", 1.0))


class OvercrowdingAgent:
    """
    Checks recent unique occupancy per camera and raises overcrowding alerts.

    - Window: last N minutes (WINDOW_MINUTES)
    - Unique people: COUNT(DISTINCT track_id) from detections
    - Threshold: per-camera capacity from CAMERA_CAPACITY
    """

    def __init__(self):
        self.engine = create_engine(DATABASE_URL)
        self.Session = sessionmaker(bind=self.engine)
        logger.info(
            "✅ OvercrowdingAgent initialized: window=%d min, high_ratio=%.2f, medium_ratio=%.2f",
            WINDOW_MINUTES,
            HIGH_RATIO,
            MEDIUM_RATIO,
        )

    def check_camera(self, camera_id: str) -> List[Dict]:
        session = self.Session()
        now = datetime.utcnow()
        window_start = now - timedelta(minutes=WINDOW_MINUTES)

        capacity = CAMERA_CAPACITY.get(camera_id)
        if capacity is None:
            logger.warning("No capacity configured for %s, skipping.", camera_id)
            session.close()
            return []

        # Unique people in the recent window
        unique_count = (
            session.query(func.count(distinct(Detection.track_id)))
            .filter(
                Detection.camera_id == camera_id,
                Detection.class_name == "person",
                Detection.timestamp >= window_start,
                Detection.timestamp <= now,
            )
            .scalar()
        ) or 0

        ratio = unique_count / capacity if capacity > 0 else 0.0
        alerts: List[Dict] = []

        logger.info(
            "[%s] overcrowding window=%d min, unique=%d, capacity=%d, ratio=%.2f",
            camera_id,
            WINDOW_MINUTES,
            unique_count,
            capacity,
            ratio,
        )

        severity = None
        if ratio >= HIGH_RATIO:
            severity = "high"
        elif ratio >= MEDIUM_RATIO:
            severity = "medium"

        if severity:
            alert_record = Alert(
                alert_type="overcrowding",
                severity=severity,
                camera_id=camera_id,
                timestamp=now,
                extra={
                    "unique_person_count": unique_count,
                    "capacity": capacity,
                    "window_minutes": WINDOW_MINUTES,
                    "ratio": round(ratio, 2),
                    "mode": "unique_track_based",
                },
                acknowledged=False,
            )
            session.add(alert_record)
            session.commit()

            alerts.append(
                {
                    "type": "overcrowding",
                    "severity": severity,
                    "camera_id": camera_id,
                    "unique_person_count": unique_count,
                    "capacity": capacity,
                    "ratio": ratio,
                    "message": (
                        f"⚠️ OVERCROWDING: {unique_count} / {capacity} "
                        f"({ratio:.2f}x) in last {WINDOW_MINUTES} min"
                    ),
                }
            )
            logger.warning("[%s] %s", camera_id, alerts[-1]["message"])
        else:
            session.commit()

        session.close()
        return alerts

    async def run(self, camera_ids: List[str]) -> List[Dict]:
        all_alerts: List[Dict] = []
        for cam in camera_ids:
            alerts = self.check_camera(cam)
            all_alerts.extend(alerts)
        return all_alerts


if __name__ == "__main__":
    agent = OvercrowdingAgent()
    alerts = asyncio.run(agent.run(["CAM_001"]))
    print(f"\n✅ Generated {len(alerts)} overcrowding alerts")
    for a in alerts:
        print(f"  {a['severity'].upper()}: {a['message']}")
