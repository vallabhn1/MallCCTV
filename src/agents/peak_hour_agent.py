# src/agents/peak_hour_agent.py
import asyncio
import logging
from datetime import datetime, timedelta
from typing import List, Dict

import os
from dotenv import load_dotenv
from langgraph.graph import StateGraph, END
from sqlalchemy import create_engine, func, distinct
from sqlalchemy.orm import sessionmaker

from src.database.models import Detection, PeakHourAnalytics, Alert
from src.agents.state import PeakHourState
from src.agents.hf_llm import SimpleHFLLM  # wrapper using InferenceClient

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# PostgreSQL connection URL
DATABASE_URL = (
    f"postgresql+psycopg://{os.getenv('POSTGRES_USER', 'hive_user')}:"
    f"{os.getenv('POSTGRES_PASSWORD', 'hive1234')}@"
    f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
    f"{os.getenv('POSTGRES_PORT', '5432')}/"
    f"{os.getenv('POSTGRES_DB', 'hive_dynamics')}"
)


class PeakHourAgent:
    """
    Peak / low hour detection using UNIQUE people per hour (distinct track_id)
    plus optional next-hour forecasting using a Hugging Face LLM.

    - Reads from: detections (class_name='person')
    - Writes to: peak_hour_analytics, alerts
    """

    def __init__(self):
        self.engine = create_engine(DATABASE_URL)
        self.Session = sessionmaker(bind=self.engine)

        # Thresholds
        self.peak_threshold = int(os.getenv("PEAK_HOUR_THRESHOLD", 100))
        self.low_threshold = int(os.getenv("LOW_HOUR_THRESHOLD", 20))

        # Hugging Face LLM (can be disabled by not setting token)
        hf_model = os.getenv("HF_MODEL_ID", "mistralai/Mistral-7B-Instruct-v0.2")
        hf_token = os.getenv("HUGGINGFACE_API_KEY")
        if not hf_token:
            logger.warning("⚠️  HUGGINGFACE_API_KEY not set; forecast will use heuristic only.")

        self.llm = SimpleHFLLM(model_id=hf_model, api_token=hf_token) if hf_token else None

        logger.info(
            "✅ PeakHourAgent initialized - peak_threshold=%d, low_threshold=%d",
            self.peak_threshold,
            self.low_threshold,
        )

    # 1) AGGREGATION NODE
    def aggregate_hourly_count(self, state: PeakHourState) -> PeakHourState:
        """
        Aggregate UNIQUE person count for the current hour,
        and build a 24-hour history of unique counts.
        """
        session = self.Session()

        now = datetime.utcnow()
        hour_start = now.replace(minute=0, second=0, microsecond=0)
        hour_end = hour_start + timedelta(hours=1)

        # Unique people this hour: count distinct track_id
        count = (
            session.query(func.count(distinct(Detection.track_id)))
            .filter(
                Detection.camera_id == state["camera_id"],
                Detection.class_name == "person",
                Detection.timestamp >= hour_start,
                Detection.timestamp < hour_end,
            )
            .scalar()
        )

        state["person_count"] = count or 0
        state["hour"] = hour_start.hour

        # Unique people per hour for the last 24 hours (history)
        last_24h: List[int] = []
        for i in range(24):
            h_start = hour_start - timedelta(hours=i + 1)
            h_end = h_start + timedelta(hours=1)
            hourly_count = (
                session.query(func.count(distinct(Detection.track_id)))
                .filter(
                    Detection.camera_id == state["camera_id"],
                    Detection.class_name == "person",
                    Detection.timestamp >= h_start,
                    Detection.timestamp < h_end,
                )
                .scalar()
            )
            last_24h.insert(0, hourly_count or 0)

        state["hourly_counts"] = last_24h
        avg_24 = sum(last_24h) / 24 if last_24h else 0

        logger.info(
            "[%s] Hour %02d: unique_count=%d, avg_24h=%.1f",
            state["camera_id"],
            state["hour"],
            state["person_count"],
            avg_24,
        )

        session.close()
        return state

    # 2) PEAK / LOW CLASSIFICATION NODE
    def detect_peaks(self, state: PeakHourState) -> PeakHourState:
        """Classify current hour as peak / low / normal based on unique person count."""
        current = state["person_count"]
        state["is_peak"] = current > self.peak_threshold
        state["is_low"] = current < self.low_threshold

        logger.info(
            "[%s] is_peak=%s, is_low=%s, unique_count=%d",
            state["camera_id"],
            state["is_peak"],
            state["is_low"],
            current,
        )
        return state

    # 3) FORECAST NODE
    def forecast_next_hour(self, state: PeakHourState) -> PeakHourState:
        """
        Forecast next hour's unique person count.
        Uses HF LLM if available, otherwise falls back to last 3-hour average.
        """
        if len(state["hourly_counts"]) < 3:
            state["forecast"] = "0"
            return state

        avg_last_3h = sum(state["hourly_counts"][-3:]) / 3
        current_hour = datetime.utcnow().hour
        dow = datetime.utcnow().strftime("%A")
        trend = (
            "increasing"
            if state["hourly_counts"][-1] > state["hourly_counts"][-2]
            else "decreasing"
        )

        # Default heuristic forecast if LLM is not configured
        if self.llm is None:
            state["forecast"] = str(int(avg_last_3h))
            logger.info(
                "[%s] Heuristic forecast (no LLM): %s",
                state["camera_id"],
                state["forecast"],
            )
            return state

        prompt = (
            "You are a mall traffic forecasting assistant.\n\n"
            f"Day: {dow}\n"
            f"Current hour: {current_hour}:00\n"
            f"Current unique visitors (track-based): {state['person_count']}\n"
            f"Last 24h unique counts: {state['hourly_counts']}\n"
            f"Trend: {trend}\n\n"
            "Predict ONLY the number of unique visitors for the next hour as a single integer.\n"
            "Answer with just the number, for example: 145"
        )

        try:
            text = self.llm.invoke(prompt).strip()
            import re

            numbers = re.findall(r"\d+", text)
            forecast = numbers[0] if numbers else str(int(avg_last_3h))
            state["forecast"] = forecast
            logger.info(
                "[%s] HF forecast next hour (unique visitors): %s",
                state["camera_id"],
                state["forecast"],
            )
        except Exception as e:
            state["forecast"] = str(int(avg_last_3h))
            logger.warning("HF forecast error: %s, using avg_last_3h", e)

        return state

    # 4) ALERT & ANALYTICS NODE
    def trigger_alerts(self, state: PeakHourState) -> PeakHourState:
        """Write alerts and analytics to DB based on unique person count."""
        session = self.Session()
        alerts: List[Dict] = []

        now = datetime.utcnow()
        hour_start = now.replace(minute=0, second=0, microsecond=0)

        if state["is_peak"]:
            severity = "high" if state["person_count"] > (self.peak_threshold * 1.5) else "medium"
            alert_record = Alert(
                alert_type="peak_hour",
                severity=severity,
                camera_id=state["camera_id"],
                timestamp=now,
                extra={
                    "unique_person_count": state["person_count"],
                    "threshold": self.peak_threshold,
                    "forecast_next": state.get("forecast", "N/A"),
                    "mode": "unique_track_based",
                },
                acknowledged=False,
            )
            session.add(alert_record)

            alerts.append(
                {
                    "type": "peak_hour",
                    "severity": severity,
                    "camera_id": state["camera_id"],
                    "count": state["person_count"],
                    "message": (
                        f"🚨 PEAK HOUR (unique): {state['person_count']} visitors "
                        f"(threshold: {self.peak_threshold})"
                    ),
                    "recommendation": (
                        "Activate additional staff, open all checkout counters, "
                        "enable express lanes"
                    ),
                }
            )
            logger.warning("[%s] %s", state["camera_id"], alerts[-1]["message"])

        elif state["is_low"]:
            alert_record = Alert(
                alert_type="low_hour",
                severity="low",
                camera_id=state["camera_id"],
                timestamp=now,
                extra={
                    "unique_person_count": state["person_count"],
                    "threshold": self.low_threshold,
                    "mode": "unique_track_based",
                },
                acknowledged=False,
            )
            session.add(alert_record)

            alerts.append(
                {
                    "type": "low_hour",
                    "severity": "low",
                    "camera_id": state["camera_id"],
                    "count": state["person_count"],
                    "message": (
                        f"📉 LOW HOUR (unique): {state['person_count']} visitors "
                        f"(below {self.low_threshold})"
                    ),
                    "recommendation": "Energy-saving mode, minimal staff required",
                }
            )
            logger.info("[%s] %s", state["camera_id"], alerts[-1]["message"])

        # Persist hourly analytics
        analytics = PeakHourAnalytics(
            camera_id=state["camera_id"],
            hour=hour_start,
            person_count=state["person_count"],  # unique visitors per hour
            is_peak=bool(state["is_peak"]),
            forecast_next=int(state["forecast"]) if state["forecast"].isdigit() else 0,
        )
        session.add(analytics)
        session.commit()
        session.close()

        state["alerts"].extend(alerts)
        return state

    # 5) BUILD & RUN WORKFLOW
    def build_workflow(self) -> StateGraph:
        wf = StateGraph(PeakHourState)

        wf.add_node("aggregate", self.aggregate_hourly_count)
        wf.add_node("detect_peaks", self.detect_peaks)
        wf.add_node("forecast_node", self.forecast_next_hour)  # node name != state key "forecast"
        wf.add_node("trigger_alerts", self.trigger_alerts)

        wf.set_entry_point("aggregate")
        wf.add_edge("aggregate", "detect_peaks")
        wf.add_edge("detect_peaks", "forecast_node")
        wf.add_edge("forecast_node", "trigger_alerts")
        wf.add_edge("trigger_alerts", END)
        return wf

    async def run(self, camera_id: str):
        wf = self.build_workflow()
        app = wf.compile()

        config = {
            "configurable": {
                "thread_id": f"peak_hour_unique_{camera_id}_{datetime.now().strftime('%Y%m%d')}"
            }
        }

        result = await asyncio.to_thread(
            app.invoke,
            {
                "camera_id": camera_id,
                "hour": 0,
                "person_count": 0,
                "hourly_counts": [],
                "is_peak": False,
                "is_low": False,
                "forecast": "",
                "alerts": [],
                "messages": [],
            },
            config,
        )
        return result["alerts"]


if __name__ == "__main__":
    agent = PeakHourAgent()
    alerts = asyncio.run(agent.run("CAM_001"))
    print(f"\n✅ Generated {len(alerts)} alerts")
    for alert in alerts:
        print(f"  {alert['severity'].upper()}: {alert['message']}")
