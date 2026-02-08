"""
src/agents/loitering_agent.py - Detects loitering from track_states → creates Alerts.
Uses your POSTGRES_* .env vars. Runs once, exits clean like fire_agent.
"""

import os
import logging
from datetime import datetime, timedelta
from typing import List, Dict, Any

from dotenv import load_dotenv
from sqlalchemy import create_engine, func, and_, text
from sqlalchemy.orm import sessionmaker

from src.database.models import TrackState, Alert

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("loitering_agent")

# Your .env POSTGRES_* vars
DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@"
    f"{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"
)

# Config (tune for mall)
LOITER_THRESHOLD_SEC = 2  # 2+ min dwell
MIN_DETECTIONS = 5
WINDOW_MINUTES = 15
CAMERAS_TO_CHECK = ["CAM_001"]  # Add your cameras

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def get_loitering_tracks(session) -> List[Dict[str, Any]]:
    """Query active tracks with long dwell time."""
    cutoff = datetime.utcnow() - timedelta(minutes=WINDOW_MINUTES)
    
    tracks = session.query(
        TrackState.camera_id,
        TrackState.track_id,
        TrackState.zone_id,
        TrackState.class_name,
        func.max(TrackState.last_time).label("last_seen"),
        func.max(TrackState.total_dwell_sec).label("dwell_sec"),
        func.max(TrackState.detection_count).label("det_count"),
        func.avg(TrackState.avg_speed).label("avg_speed")
    ).filter(
        and_(
            TrackState.last_time >= cutoff,
            TrackState.total_dwell_sec >= LOITER_THRESHOLD_SEC,
            TrackState.detection_count >= MIN_DETECTIONS,
            TrackState.status == "active"
        )
    ).group_by(
        TrackState.camera_id, TrackState.track_id, 
        TrackState.zone_id, TrackState.class_name
    ).order_by(
        text("dwell_sec DESC")
    ).all()
    
    result = []
    for row in tracks:
        result.append({
            "camera_id": row.camera_id,
            "track_id": row.track_id,
            "zone_id": row.zone_id,
            "class_name": row.class_name,
            "last_seen": row.last_seen,
            "total_loiter_sec": row.dwell_sec,
            "det_count": row.det_count,
            "avg_speed_pxs": float(row.avg_speed or 0)
        })
    
    return result


def create_loitering_alert(session, track: Dict[str, Any]):
    """Create Alert row (idempotent)."""
    alert = Alert(
        camera_id=track["camera_id"],
        alert_type="loitering",
        severity="medium",
        description=(
            f"Loitering: track {track['track_id']} ({track['class_name']}) "
            f"zone {track['zone_id'] or 'none'}, {track['total_loiter_sec']}s dwell, "
            f"{track['det_count']} dets, speed {track['avg_speed_pxs']:.1f}px/s"
        ),
        confidence=0.9,
        track_id=track["track_id"]
    )
    session.add(alert)
    logger.info(
        "🚨 LOITERING: %s track=%d zone=%s dwell=%ds speed=%.1f",
        track["camera_id"], track["track_id"], track["zone_id"],
        track["total_loiter_sec"], track["avg_speed_pxs"]
    )


def main():
    logger.info("🔍 Loitering agent started - scanning track_states...")
    
    with SessionLocal() as session:
        loiterers = get_loitering_tracks(session)
        logger.info("Found %d loitering tracks (threshold %ds)", len(loiterers), LOITER_THRESHOLD_SEC)
        
        for track in loiterers:
            logger.info("Suspicious: %s", track)
            create_loitering_alert(session, track)
        
        session.commit()
    
    logger.info("✅ Loitering agent finished - check alerts table")


if __name__ == "__main__":
    main()
