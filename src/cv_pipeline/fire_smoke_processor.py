# src/cv_pipeline/fire_smoke_processor.py

import cv2
import json
import time
from datetime import datetime, timezone
from typing import List, Dict
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from ultralytics import YOLO

from src.database.models import Detection

load_dotenv()

DATABASE_URL = (
    f"postgresql://{os.getenv('POSTGRES_USER')}:"
    f"{os.getenv('POSTGRES_PASSWORD')}@"
    f"{os.getenv('POSTGRES_HOST')}:"
    f"{os.getenv('POSTGRES_PORT')}/"
    f"{os.getenv('POSTGRES_DB')}"
)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)


class FireSmokeDetector:
    """
    YOLOv10 fire & smoke detector using Hugging Face weights.
    Model repo: TommyNgx/YOLOv10-Fire-and-Smoke-Detection
    """

    def __init__(self, weights_path: str, conf_threshold: float = 0.5):
        self.model = YOLO(weights_path)
        self.conf_threshold = conf_threshold

    def detect(self, frame) -> List[Dict]:
        """
        Returns detections as:
        [
          {"class_name": "fire", "confidence": 0.92, "bbox": [x1,y1,x2,y2], "color": (0,0,255)},
          {"class_name": "smoke", "confidence": 0.88, "bbox": [...],        "color": (255,255,0)},
          ...
        ]
        """
        results = self.model(frame, conf=self.conf_threshold, verbose=False)
        detections: List[Dict] = []

        for r in results:
            boxes = r.boxes
            names = r.names  # {class_id: name}

            for box in boxes:
                cls_id = int(box.cls.item())
                cls_name = names.get(cls_id, "object").lower()
                conf = float(box.conf.item())
                x1, y1, x2, y2 = box.xyxy[0].tolist()

                if cls_name in ["fire", "flame", "open_flame"]:
                    cls_norm = "fire"
                    color = (0, 0, 255)   # red
                elif cls_name in ["smoke"]:
                    cls_norm = "smoke"
                    color = (255, 255, 0) # cyan/yellow
                else:
                    continue

                detections.append(
                    {
                        "class_name": cls_norm,
                        "confidence": conf,
                        "bbox": [x1, y1, x2, y2],
                        "color": color,
                    }
                )

        return detections


def process_stream(camera_id: str, source: str, fps: float = 1.0):
    cap = cv2.VideoCapture(source)
    if not cap.isOpened():
        raise RuntimeError(f"Cannot open video source: {source}")

    weights = os.getenv("FIRE_SMOKE_WEIGHTS", "models/fire_smoke_yolov10.pt")
    conf = float(os.getenv("FIRE_SMOKE_CONF", 0.5))

    detector = FireSmokeDetector(weights_path=weights, conf_threshold=conf)
    session = SessionLocal()

    # Prepare annotated video writer -> data/output/<CAM_ID>_fire_annotated.mp4
    fourcc = cv2.VideoWriter_fourcc(*"mp4v")
    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
    height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))

    output_dir = os.path.join("data", "output")
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, f"{camera_id}_fire_annotated.mp4")

    writer = cv2.VideoWriter(out_path, fourcc, fps, (width, height))

    frame_interval = 1.0 / fps
    last_time = 0.0

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            now = time.time()
            if now - last_time < frame_interval:
                continue
            last_time = now

            detections = detector.detect(frame)
            ts = datetime.now(timezone.utc)

            annotated = frame.copy()

            for det in detections:
                x1, y1, x2, y2 = det["bbox"]
                color = det["color"]
                label = f"{det['class_name']} {det['confidence']:.2f}"

                # Insert into detections table
                row = Detection(
                    camera_id=camera_id,
                    timestamp=ts,
                    class_name=det["class_name"],   # 'fire' or 'smoke'
                    confidence=det["confidence"],
                    bbox=json.dumps(det["bbox"]),
                    track_id=None,                  # or 0 if NOT NULL
                )
                session.add(row)

                # Draw on frame
                p1 = (int(x1), int(y1))
                p2 = (int(x2), int(y2))
                cv2.rectangle(annotated, p1, p2, color, 2)
                cv2.putText(
                    annotated,
                    label,
                    (p1[0], max(0, p1[1] - 10)),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    color,
                    2,
                    cv2.LINE_AA,
                )

            session.commit()
            writer.write(annotated)

    finally:
        session.close()
        cap.release()
        writer.release()
        print(f"Annotated fire/smoke video saved to: {out_path}")


if __name__ == "__main__":
    cam_id = os.getenv("FIRE_SMOKE_CAMERA_ID", "CAM_001")
    video_src = os.getenv("FIRE_SMOKE_VIDEO", "data/CAM_001_fire_test.mp4")
    fps = float(os.getenv("FIRE_SMOKE_FPS", 1.0))
    process_stream(camera_id=cam_id, source=video_src, fps=fps)
