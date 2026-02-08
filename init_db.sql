-- init_db.sql
-- Place your DB schema initialization SQL here.
-- Example: create tables for detections, alerts, analytics, zones

CREATE TABLE IF NOT EXISTS detections (
  id SERIAL PRIMARY KEY,
  camera_id TEXT,
  class_name TEXT,
  confidence REAL,
  bbox TEXT,
  track_id INTEGER,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS alerts (
  id SERIAL PRIMARY KEY,
  alert_type TEXT,
  severity TEXT,
  camera_id TEXT,
  timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  metadata JSONB,
  acknowledged INTEGER DEFAULT 0
);
