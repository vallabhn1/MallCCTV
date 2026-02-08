# src/config/queue_rois.py

# Simple rectangular queue zone per camera: (x1, y1, x2, y2)
# NOTE: These coordinates are placeholders; tune them after you see the box on the video.
QUEUE_RECT_ROI = {
    "CAM_001": (200, 300, 800, 720),  # TODO: adjust per your video resolution & queue location
}


def point_in_queue(camera_id: str, x: float, y: float) -> bool:
    """
    Check if point (x, y) lies inside the configured rectangular queue ROI for a camera.
    """
    roi = QUEUE_RECT_ROI.get(camera_id)
    if roi is None:
        return False
    x1, y1, x2, y2 = roi
    return x1 <= x <= x2 and y1 <= y <= y2
