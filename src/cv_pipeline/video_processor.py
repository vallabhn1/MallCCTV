"""
video_processor.py - N unique people → N detections (1 row/track_id).
Clean data for ALL agents + loitering.
"""

import os
import time
import cv2
from datetime import datetime
from typing import Set

from src.cv_pipeline.detector import YOLOHFDetector
from src.cv_pipeline.tracker import ByteTracker
from src.database.init_db import get_db_session
from src.database.models import Detection
from src.config.queue_rois import QUEUE_RECT_ROI

import logging
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)

class VideoProcessor:
    def __init__(self, camera_id: str, source: str, save_video: bool = True):
        self.camera_id = camera_id
        self.source = source
        self.save_video = save_video
        self.detector = YOLOHFDetector(conf_threshold=0.5)  # Clean detections
        self.tracker = ByteTracker()
        self.frame_id = 0

    def run(self, save_to_db: bool = True):
        print(f"🎯 N unique people → N detections: {self.source}")
        cap = cv2.VideoCapture(self.source)
        if not cap.isOpened():
            print(f"❌ Cannot open: {self.source}")
            return
        
        fps = cap.get(cv2.CAP_PROP_FPS) or 25
        width, height = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)), int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        
        db = get_db_session() if save_to_db else None
        
        # VIDEO OUTPUT
        writer = None
        if self.save_video:
            os.makedirs("data/output", exist_ok=True)
            out_path = f"data/output/{self.camera_id}_unique.mp4"
            fourcc = cv2.VideoWriter_fourcc(*'mp4v')
            writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))
            print(f"💾 {out_path}")
        
        # UNIQUE TRACKS ONLY (N people = N rows)
        unique_tracks: Set[int] = set()
        total_unique = 0
        
        logger.info(f"Processing {self.camera_id} - unique only")
        
        while cap.isOpened():
            ret, frame = cap.read()
            if not ret:
                break
            
            self.frame_id += 1
            
            # DETECT → TRACK
            dets = self.detector.detect(frame)
            tracked = self.tracker.update(dets, self.frame_id)
            
            # SAVE UNIQUE PEOPLE ONLY (1 row/track_id)
            if db and tracked:
                for obj in tracked:
                    if obj.get('class') != 'person':
                        continue
                        
                    tid = int(obj.get('track_id') or 0)
                    if tid == 0 or tid in unique_tracks:
                        continue  # Already saved this person
                    
                    unique_tracks.add(tid)
                    total_unique += 1
                    
                    # 1 ROW PER UNIQUE PERSON
                    rec = Detection(
                        camera_id=self.camera_id,
                        timestamp=datetime.utcnow(),
                        class_name='person',
                        confidence=float(obj['confidence']),
                        bbox=str(obj['bbox']),  # List [x1,y1,x2,y2]
                        track_id=tid
                    )
                    db.add(rec)
                
                db.commit()
            
            # VISUALIZE
            vis = self.detector.draw_detections(frame, tracked)
            
            # STATS
            cv2.putText(vis, f"Unique: {total_unique}", (10, 30), 
                       cv2.FONT_HERSHEY_SIMPLEX, 1, (0,255,0), 2)
            
            # ROI
            roi = QUEUE_RECT_ROI.get(self.camera_id)
            if roi:
                x1,y1,x2,y2 = roi
                cv2.rectangle(vis, (x1,y1), (x2,y2), (255,0,0), 2)
            
            if writer:
                writer.write(vis)
            cv2.imshow(f"Hive-{self.camera_id}", vis)
            
            if cv2.waitKey(1) & 0xFF == ord('q'):
                break
            time.sleep(1/fps)
        
        cap.release()
        if writer:
            writer.release()
        cv2.destroyAllWindows()
        if db:
            db.close()
        
        print(f"✅ {total_unique} UNIQUE people → {total_unique} detections")


if __name__ == "__main__":
    vp = VideoProcessor("CAM_001", "data/videos/test.mp4", save_video=True)
    vp.run()
