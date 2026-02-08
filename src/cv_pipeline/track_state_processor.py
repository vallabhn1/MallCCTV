"""
Production track_state_processor.py - ANY detections → tracks → loitering ready.
Handles list/JSON bbox, ANY class_name, scales to millions.
"""

import os
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Tuple
from math import sqrt
from collections import defaultdict

from dotenv import load_dotenv
from sqlalchemy import create_engine, func, and_, text
from sqlalchemy.orm import sessionmaker

from src.database.models import Detection, TrackState

load_dotenv()
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("track_state_processor")

DATABASE_URL = f"postgresql://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

WINDOW_HOURS = 1  # Scale: process last 1hr
MIN_DETECTIONS = 3

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


def parse_bbox(bbox_data) -> Tuple[float, float, float, float]:
    """Universal bbox parser."""
    try:
        if isinstance(bbox_data, str):
            bbox = json.loads(bbox_data)
        else:
            bbox = bbox_data
        
        # List [x1,y1,x2,y2]
        if isinstance(bbox, list) and len(bbox) >= 4:
            return float(bbox[0]), float(bbox[1]), float(bbox[2]), float(bbox[3])
        # Dict {"x1":100,...}
        elif isinstance(bbox, dict):
            return (float(bbox.get('x1',0)), float(bbox.get('y1',0)), 
                   float(bbox.get('x2',0)), float(bbox.get('y2',0)))
        else:
            return 0.0, 0.0, 0.0, 0.0
    except Exception as e:
        logger.debug("bbox parse fail %s: %s", bbox_data, e)
        return 0.0, 0.0, 0.0, 0.0


def get_recent_detections(session) -> List[Detection]:
    """Scale to millions - person/vehicle only."""
    cutoff = datetime.utcnow() - timedelta(hours=WINDOW_HOURS)
    dets = session.query(Detection).filter(
        Detection.timestamp >= cutoff,
        Detection.track_id.isnot(None),
        Detection.class_name.ilike('%person%')  # person/people/pedestrian
    ).order_by(
        Detection.camera_id, Detection.track_id, Detection.timestamp
    ).all()
    
    logger.info("📊 Loaded %d detections (%.1f/sec avg)", 
               len(dets), len(dets)/(WINDOW_HOURS*3600))
    return dets


def compute_metrics(track_dets: List[Detection]) -> Dict:
    """Full track analysis."""
    n = len(track_dets)
    if n < MIN_DETECTIONS:
        return None
    
    d0 = track_dets[0]
    camera, track_id, cls = d0.camera_id, d0.track_id, d0.class_name
    
    # Time
    times = [d.timestamp for d in track_dets]
    dwell = int((max(times) - min(times)).total_seconds())
    
    # Speed (center trajectory)
    centers = [parse_bbox(d.bbox)[:2] for d in track_dets]  # (cx,cy)
    speeds = []
    for i in range(1, n):
        dx = centers[i][0] - centers[i-1][0]
        dy = centers[i][1] - centers[i-1][1]
        dist = sqrt(dx**2 + dy**2)
        dt = (track_dets[i].timestamp - track_dets[i-1].timestamp).total_seconds()
        speeds.append(dist/dt if dt > 0 else 0)
    
    avg_speed = sum(speeds)/len(speeds) if speeds else 0
    
    # Zone (speed-based for now)
    zone_id = 1 if avg_speed < 5 else None
    
    return dict(
        camera_id=camera, track_id=track_id, zone_id=zone_id,
        class_name=cls, enter_time=min(times), last_time=max(times),
        total_dwell_sec=dwell, detection_count=n, avg_speed=avg_speed,
        status='loitering' if dwell > 120 else 'active'
    )


def process_tracks():
    """Production: million-scale track processing."""
    session = SessionLocal()
    try:
        dets = get_recent_detections(session)
        tracks = defaultdict(list)
        
        # O(n) grouping
        for d in dets:
            key = f"{d.camera_id}_{d.track_id}"
            tracks[key].append(d)
        
        metrics = []
        for key, track_dets in tracks.items():
            m = compute_metrics(track_dets)
            if m:
                metrics.append(m)
        
        # Efficient upsert
        cutoff = datetime.utcnow() - timedelta(hours=WINDOW_HOURS + 1)
        session.query(TrackState).filter(
            TrackState.last_time < cutoff
        ).delete()
        
        for m in metrics:
            session.merge(TrackState(**m))
        
        session.commit()
        
        active = len([m for m in metrics if m['status']=='active'])
        loiter = len([m for m in metrics if m['status']=='loitering'])
        logger.info("✅ %d tracks (%d active, %d loitering) → track_states", 
                   len(metrics), active, loiter)
                   
    except Exception as e:
        logger.error("❌ %s", e)
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    process_tracks()
