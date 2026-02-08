import numpy as np
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

class ByteTracker:
    def __init__(self, track_thresh: float = 0.5, match_thresh: float = 0.8, max_age: int = 30):
        self.track_thresh = track_thresh
        self.match_thresh = match_thresh
        self.tracks = {}
        self.next_id = 1
        self.max_age = max_age
        logger.info("✅ ByteTracker initialized")

    def update(self, detections: List[Dict], frame_id: int) -> List[Dict]:
        high_conf = [d for d in detections if d["confidence"] > self.track_thresh]
        tracked_objects = []

        for detection in high_conf:
            best_match_id = None
            best_iou = 0.0

            for track_id, track in list(self.tracks.items()):
                iou = self._calculate_iou(detection["bbox"], track["bbox"])
                if iou > self.match_thresh and iou > best_iou:
                    best_iou = iou
                    best_match_id = track_id

            if best_match_id:
                self.tracks[best_match_id]["bbox"] = detection["bbox"]
                self.tracks[best_match_id]["last_seen"] = frame_id
                track_id = best_match_id
            else:
                track_id = self.next_id
                self.tracks[track_id] = {"bbox": detection["bbox"], "last_seen": frame_id}
                self.next_id += 1

            tracked_objects.append({**detection, "track_id": track_id})

        self.tracks = {
            tid: track
            for tid, track in self.tracks.items()
            if frame_id - track["last_seen"] < self.max_age
        }
        return tracked_objects

    def _calculate_iou(self, box1: List[float], box2: List[float]) -> float:
        x1_1, y1_1, x2_1, y2_1 = box1
        x1_2, y1_2, x2_2, y2_2 = box2

        x1_i = max(x1_1, x1_2)
        y1_i = max(y1_1, y1_2)
        x2_i = min(x2_1, x2_2)
        y2_i = min(y2_1, y2_2)

        if x2_i < x1_i or y2_i < y1_i:
            return 0.0

        intersection = (x2_i - x1_i) * (y2_i - y1_i)
        area1 = (x2_1 - x1_1) * (y2_1 - y1_1)
        area2 = (x2_2 - x1_2) * (y2_2 - y1_2)
        union = area1 + area2 - intersection
        return intersection / union if union > 0 else 0.0
