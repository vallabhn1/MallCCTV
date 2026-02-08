# src/agents/queue_agent.py
import asyncio
import logging
import os
from datetime import datetime, timedelta
from typing import List, Dict

from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from sqlalchemy import func, distinct

from src.database.models import Detection, Alert
from src.agents.state import QueueState
from src.config.queue_rois import QUEUE_RECT_ROI, point_in_queue

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DATABASE_URL = (
    f"postgresql+psycopg://{os.getenv('POSTGRES_USER', 'hive_user')}:"
    f"{os.getenv('POSTGRES_PASSWORD', 'hive1234')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5432')}/"
    f"{os.getenv('POSTGRES_DB', 'hive_dynamics')}"
)

# Queue parameters (configurable via .env)
QUEUE_WINDOW_SECONDS = int(os.getenv("QUEUE_WINDOW_SECONDS", 60))  # recent window
QUEUE_BUILDUP_THRESHOLD = int(os.getenv("QUEUE_BUILDUP_THRESHOLD", 10))
QUEUE_CRITICAL_THRESHOLD = int(os.getenv("QUEUE_CRITICAL_THRESHOLD", 20))
QUEUE_WAIT_TIME_HIGH = int(os.getenv("QUEUE_WAIT_TIME_HIGH", 300))  # seconds
QUEUE_SLOW_THROUGHPUT = float(os.getenv("QUEUE_SLOW_THROUGHPUT", 5.0))  # people/min
QUEUE_THROUGHPUT_WINDOW_MINUTES = int(os.getenv("QUEUE_THROUGHPUT_WINDOW_MINUTES", 10))


class QueueAgent:
    """
    LangGraph-based Queue Monitoring Agent for a single camera.

    Uses detections in queue ROI to compute:
      - people_in_queue (unique track_ids in ROI recently)
      - current_throughput (customers/min leaving queue)
      - avg_wait_time (approx)
    Writes queue-related alerts into `alerts` table.
    """

    def __init__(self):
        self.engine = create_engine(DATABASE_URL)
        self.Session = sessionmaker(bind=self.engine)
        logger.info(
            "✅ QueueAgent initialized: window=%ds, buildup=%d, critical=%d",
            QUEUE_WINDOW_SECONDS,
            QUEUE_BUILDUP_THRESHOLD,
            QUEUE_CRITICAL_THRESHOLD,
        )

    # NODE 1: DETECT_QUEUE_LINE
    def detect_queue_line(self, state: QueueState) -> QueueState:
        """
        Load ROI for camera and count unique persons currently inside queue area
        using recent detections.
        """
        session = self.Session()
        now = datetime.utcnow()
        window_start = now - timedelta(seconds=QUEUE_WINDOW_SECONDS)

        camera_id = state["camera_id"]
        roi_tuple = QUEUE_RECT_ROI.get(camera_id)
        if not roi_tuple:
            logger.warning("No queue ROI configured for %s", camera_id)
            state["people_in_queue"] = 0
            state["queue_length"] = 0.0
            session.close()
            return state

        x1, y1, x2, y2 = roi_tuple
        # Store ROI as polygon-like list for completeness
        state["queue_line_roi"] = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]

        # Fetch recent detections in window
        detections = (
            session.query(
                Detection.track_id,
                Detection.bbox,
            )
            .filter(
                Detection.camera_id == camera_id,
                Detection.class_name == "person",
                Detection.timestamp >= window_start,
                Detection.timestamp <= now,
            )
            .all()
        )

        # Unique track_ids whose bottom-center point lies in ROI
        queue_ids = set()
        for tid, bbox in detections:
            if tid is None or bbox is None:
                continue
            x1b, y1b, x2b, y2b = bbox
            cx = (x1b + x2b) / 2.0
            cy = y2b  # bottom center
            if point_in_queue(camera_id, cx, cy):
                queue_ids.add(tid)

        people_in_queue = len(queue_ids)
        state["people_in_queue"] = people_in_queue

        # Rough queue length estimate: assume 0.75m per person
        state["queue_length"] = people_in_queue * 0.75

        logger.info(
            "[%s] Queue detect: people_in_queue=%d, est_length=%.2fm",
            camera_id,
            people_in_queue,
            state["queue_length"],
        )

        session.close()
        return state

    # NODE 2: ESTIMATE_WAIT_TIME
    def estimate_wait_time(self, state: QueueState) -> QueueState:
        """
        Estimate throughput and wait time using historical detections.
        Simplified: approximate throughput from unique IDs in queue over a longer window.
        """
        session = self.Session()
        camera_id = state["camera_id"]

        now = datetime.utcnow()
        t_start = now - timedelta(minutes=QUEUE_THROUGHPUT_WINDOW_MINUTES)

        # Fetch detections in longer window
        detections = (
            session.query(Detection.track_id, Detection.bbox)
            .filter(
                Detection.camera_id == camera_id,
                Detection.class_name == "person",
                Detection.timestamp >= t_start,
                Detection.timestamp <= now,
            )
            .all()
        )

        unique_ids = set()
        for tid, bbox in detections:
            if tid is None or bbox is None:
                continue
            x1b, y1b, x2b, y2b = bbox
            cx = (x1b + x2b) / 2.0
            cy = y2b
            if point_in_queue(camera_id, cx, cy):
                unique_ids.add(tid)

        total_customers = len(unique_ids)
        minutes = max(QUEUE_THROUGHPUT_WINDOW_MINUTES, 1)
        throughput = total_customers / minutes  # people per minute

        state["current_throughput"] = throughput

        if throughput > 0:
            state["avg_wait_time"] = state["people_in_queue"] / throughput * 60.0
        else:
            state["avg_wait_time"] = float(QUEUE_WAIT_TIME_HIGH * 2)

        logger.info(
            "[%s] Throughput=%.2f ppl/min, avg_wait_time≈%.1fs",
            camera_id,
            state["current_throughput"],
            state["avg_wait_time"],
        )

        session.close()
        return state

    # NODE 3: CHECK_ALERT_THRESHOLD
    def check_alert_threshold(self, state: QueueState) -> QueueState:
        """
        Decide queue_status and write queue alerts if thresholds are exceeded.
        """
        session = self.Session()
        camera_id = state["camera_id"]
        now = datetime.utcnow()

        people = state["people_in_queue"]
        wait_time = state["avg_wait_time"]
        throughput = state["current_throughput"]

        alerts: List[Dict] = []
        status = "short"
        alert_type = None
        severity = None
        recommendation = ""

        if people >= QUEUE_CRITICAL_THRESHOLD:
            status = "critical"
            alert_type = "queue_critical"
            severity = "high"
            recommendation = "Open all counters and deploy staff to manage queue."
        elif people >= QUEUE_BUILDUP_THRESHOLD:
            status = "long"
            alert_type = "queue_buildup"
            severity = "medium"
            recommendation = "Open additional checkout counter or redirect customers."
        elif wait_time >= QUEUE_WAIT_TIME_HIGH:
            status = "long"
            alert_type = "wait_time_high"
            severity = "medium"
            recommendation = "Activate proactive queue management and announcements."
        elif throughput < QUEUE_SLOW_THROUGHPUT and people > 0:
            status = "medium"
            alert_type = "queue_moving_slow"
            severity = "low"
            recommendation = "Expedite current transactions; check for blockers."
        else:
            status = "short"

        state["queue_status"] = status

        if alert_type and severity:
            alert_record = Alert(
                alert_type="queue",
                severity=severity,
                camera_id=camera_id,
                timestamp=now,
                extra={
                    "queue_alert_type": alert_type,
                    "people_in_queue": people,
                    "avg_wait_time": round(wait_time, 1),
                    "current_throughput": round(throughput, 2),
                    "window_seconds": QUEUE_WINDOW_SECONDS,
                    "status": status,
                },
                acknowledged=False,
            )
            session.add(alert_record)
            session.commit()

            msg = (
                f"QUEUE ALERT [{status.upper()}]: {people} in queue, "
                f"wait≈{wait_time:.1f}s, thr≈{throughput:.2f}/min"
            )
            alerts.append(
                {
                    "type": alert_type,
                    "severity": severity,
                    "camera_id": camera_id,
                    "message": msg,
                    "recommendation": recommendation,
                }
            )
            logger.warning("[%s] %s", camera_id, msg)
        else:
            session.commit()
            logger.info(
                "[%s] Queue normal: people=%d, wait≈%.1fs, thr≈%.2f/min",
                camera_id,
                people,
                wait_time,
                throughput,
            )

        session.close()
        state["alerts"].extend(alerts)
        return state

    # BUILD WORKFLOW
    def build_workflow(self) -> StateGraph:
        wf = StateGraph(QueueState)
        wf.add_node("detect_queue_line", self.detect_queue_line)
        wf.add_node("estimate_wait_time", self.estimate_wait_time)
        wf.add_node("check_alert_threshold", self.check_alert_threshold)

        wf.set_entry_point("detect_queue_line")
        wf.add_edge("detect_queue_line", "estimate_wait_time")
        wf.add_edge("estimate_wait_time", "check_alert_threshold")
        wf.add_edge("check_alert_threshold", END)
        return wf

    async def run(self, camera_id: str):
        wf = self.build_workflow()
        app = wf.compile()

        config = {
            "configurable": {
                "thread_id": f"queue_{camera_id}_{datetime.now().strftime('%Y%m%d%H%M%S')}"
            }
        }

        result = await asyncio.to_thread(
            app.invoke,
            {
                "camera_id": camera_id,
                "queue_line_roi": [],
                "people_in_queue": 0,
                "queue_length": 0.0,
                "avg_wait_time": 0.0,
                "current_throughput": 0.0,
                "queue_status": "short",
                "alerts": [],
                "messages": [],
            },
            config,
        )
        return result["alerts"]


if __name__ == "__main__":
    agent = QueueAgent()
    alerts = asyncio.run(agent.run("CAM_001"))
    print(f"\n✅ Generated {len(alerts)} queue alerts")
    for a in alerts:
        print(f"  {a['severity'].upper()}: {a['message']}")
        print(f"     → {a['recommendation']}")
