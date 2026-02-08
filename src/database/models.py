"""
Database models for hive-dynamics CCTV surveillance system.
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, JSON, Boolean, func, UniqueConstraint
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()

class Detection(Base):
    __tablename__ = "detections"
    
    id = Column(Integer, primary_key=True)
    camera_id = Column(String(50), index=True)
    timestamp = Column(DateTime, index=True, default=datetime.utcnow)
    class_name = Column(String(50))
    confidence = Column(Float)
    bbox = Column(JSON)  # {"x1":10,"y1":20,"x2":100,"y2":200}
    track_id = Column(Integer, nullable=True)

class Alert(Base):
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True)
    alert_type = Column(String(50))
    severity = Column(String(20))
    camera_id = Column(String(50))
    timestamp = Column(DateTime, default=datetime.utcnow)
    extra = Column(JSON)
    acknowledged = Column(Boolean, default=False)

class PeakHourAnalytics(Base):
    __tablename__ = "peakhouranalytics"
    
    id = Column(Integer, primary_key=True)
    camera_id = Column(String(50), index=True)
    hour = Column(DateTime, index=True)
    person_count = Column(Integer)
    is_peak = Column(Boolean)
    forecast_next = Column(Integer)

class Zone(Base):
    __tablename__ = "zones"
    
    id = Column(Integer, primary_key=True)
    name = Column(String(100), unique=True)
    zone_type = Column(String(50))
    polygon = Column(JSON)  # [[x1,y1],[x2,y2]...]

class TrackState(Base):
    """
    Computed track state for anomaly detection (loitering, trajectory).
    Updated by track_state_processor.py.
    """
    __tablename__ = "track_states"
    
    id = Column(Integer, primary_key=True)
    camera_id = Column(String(50), index=True)
    track_id = Column(Integer, index=True)
    zone_id = Column(Integer, index=True, nullable=True)  # from zones table
    class_name = Column(String(50), index=True)  # person, vehicle
    enter_time = Column(DateTime, index=True)
    last_time = Column(DateTime, index=True)
    total_dwell_sec = Column(Integer)  # (last_time - enter_time).seconds
    detection_count = Column(Integer)
    avg_speed = Column(Float, nullable=True)  # pixels/sec or m/s
    avg_bbox_area = Column(Float, nullable=True)
    status = Column(String(20), default="active")  # active, loitering, exited
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('camera_id', 'track_id', 'zone_id', name='unique_track_zone'),
    )

print("✅ All models loaded - ready for video_processor")
