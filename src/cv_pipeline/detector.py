import os
from ultralytics import YOLO
import cv2
import numpy as np
from typing import List, Dict
import logging

logger = logging.getLogger(__name__)

class YOLOHFDetector:
    """
    Object detector using Ultralytics YOLO11 weights from Hugging Face Hub.
    Models are automatically downloaded from Ultralytics/YOLO11 on first load.
    """

    def __init__(self, model_id: str | None = None, conf_threshold: float = 0.5):
        """
        Args:
            model_id: e.g., 'yolo11n.pt', 'yolo11s.pt', 'yolo11m.pt'
                      Automatically fetched from Ultralytics/YOLO11 on HF Hub
            conf_threshold: Confidence threshold for detections
        """
        model_id = model_id or os.getenv("DETECTION_MODEL_ID", "yolo11s.pt")
        
        try:
            # Ultralytics YOLO automatically pulls from HF Hub if not local
            self.model = YOLO(model_id)
            self.conf_threshold = conf_threshold
            logger.info(f"✅ YOLO11 (HF) loaded: {model_id}")
        except Exception as e:
            logger.error(f"❌ Failed to load YOLO model: {e}")
            raise

    def detect(self, frame: np.ndarray) -> List[Dict]:
        """
        Run detection on frame.
        
        Returns:
            List of detections with bbox, class, confidence, class_id
        """
        try:
            results = self.model.predict(frame, conf=self.conf_threshold, verbose=False)[0]
            
            detections: List[Dict] = []
            for box in results.boxes:
                cls_id = int(box.cls)
                cls_name = self.model.names[cls_id]
                detections.append({
                    'class': cls_name,
                    'confidence': float(box.conf),
                    'bbox': box.xyxy[0].cpu().numpy().tolist(),
                    'class_id': cls_id
                })
            
            return detections
        except Exception as e:
            logger.error(f"Detection error: {e}")
            return []

    def draw_detections(self, frame: np.ndarray, detections: List[Dict]) -> np.ndarray:
        """Draw bounding boxes and labels on frame"""
        annotated = frame.copy()
        
        for det in detections:
            x1, y1, x2, y2 = map(int, det['bbox'])
            label = f"{det['class']} {det['confidence']:.2f}"
            
            cv2.rectangle(annotated, (x1, y1), (x2, y2), (0, 255, 0), 2)
            cv2.putText(annotated, label, (x1, max(0, y1 - 8)),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
        
        return annotated

# Test
if __name__ == "__main__":
    detector = YOLOHFDetector(model_id="yolo11s.pt")
    test_image = cv2.imread("data/test_frame.jpg")
    if test_image is not None:
        detections = detector.detect(test_image)
        print(f"✅ Detected {len(detections)} objects")
        for det in detections:
            print(f"  - {det['class']}: {det['confidence']:.2f}")