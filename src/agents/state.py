from typing import TypedDict, List, Dict, Annotated
from langchain_core.messages import BaseMessage
import operator

class PeakHourState(TypedDict):
    camera_id: str
    hour: int
    person_count: int
    hourly_counts: List[int]
    is_peak: bool
    is_low: bool
    forecast: str
    alerts: Annotated[List[Dict], operator.add]
    messages: Annotated[List[BaseMessage], operator.add]

class OvercrowdingState(TypedDict):
    camera_id: str
    zone_name: str
    person_count: int
    zone_threshold: int
    severity: str
    alerts: Annotated[List[Dict], operator.add]
    messages: Annotated[List[BaseMessage], operator.add]

class QueueState(TypedDict):
    camera_id: str
    queue_line_roi: List[List[int]]  # polygon-like list: [[x1,y1],[x2,y1],[x2,y2],[x1,y2]]
    people_in_queue: int
    queue_length: float
    avg_wait_time: float
    current_throughput: float
    queue_status: str  # "short", "medium", "long", "critical"
    alerts: List[Dict]
    messages: List[BaseMessage]
