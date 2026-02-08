# LANGGRAPH WORKFLOWS FOR TIER 1 FEATURES
# Complete Visual Architecture with Parallel Execution

## Feature 1: PEAK AND LOW HOUR DETECTION WORKFLOW

```
╔═════════════════════════════════════════════════════════════════════════╗
║                  LANGGRAPH: PEAK HOUR DETECTION                         ║
╚═════════════════════════════════════════════════════════════════════════╝

STATE FLOW:
                          ┌─────────────────────────────────────┐
                          │   HiveState                         │
                          │ ├─ camera_id: str                  │
                          │ ├─ detections: List[Dict]          │
                          │ ├─ hourly_counts: List[int]        │
                          │ ├─ is_peak: bool                   │
                          │ ├─ alerts: List[Dict]              │
                          │ └─ messages: List[BaseMessage]     │
                          └─────────────────────────────────────┘
                                       │
                                       ▼
        ┌──────────────────────────────────────────────────────────┐
        │ START: AGGREGATE_HOURLY_COUNT Node                       │
        ├──────────────────────────────────────────────────────────┤
        │ ├─ Query detections from last 1 hour                     │
        │ ├─ Count unique person detections                        │
        │ ├─ Store hourly count in state                           │
        │ └─ Fetch last 24 hours for trend analysis                │
        │                                                           │
        │ Execution: Sequential (CPU-bound)                        │
        │ Parallelizable: YES (per camera)                         │
        └──────────────────────────────────────────────────────────┘
                                       │
                                       ▼
        ┌──────────────────────────────────────────────────────────┐
        │ DETECT_PEAKS Node                                        │
        ├──────────────────────────────────────────────────────────┤
        │ ├─ Calculate 24-hour average                             │
        │ ├─ Compare current vs average                            │
        │ ├─ Check: current > peak_threshold (100)? → is_peak     │
        │ └─ Check: current < low_threshold (20)? → is_low        │
        │                                                           │
        │ ┌────────────────────┬──────────────────┐                │
        │ │ Peak? (>100)       │ Low? (<20)       │ Normal         │
        │ ├────────────────────┼──────────────────┤                │
        │ │ HIGH    (>150)     │ LOW (<10)        │ MEDIUM         │
        │ │ MEDIUM  (100-150)  │ MODERATE (10-20) │ 20-100 ppl     │
        │ └────────────────────┴──────────────────┘                │
        │                                                           │
        │ Execution: Stateless computation                         │
        │ Parallelizable: YES (no dependencies)                    │
        └──────────────────────────────────────────────────────────┘
                                       │
                    ┌──────────────────┼──────────────────┐
                    │                  │                  │
                    ▼                  ▼                  ▼
        ┌─────────────────┐  ┌──────────────┐  ┌──────────────┐
        │ FORECAST Node   │  │ NO ACTION    │  │ TRIGGER_ALERT│
        │ (Peak/Low only) │  │   (Normal)   │  │ (Peak/Low)   │
        └─────────────────┘  └──────────────┘  └──────────────┘
                  │                  │                │
                  └──────────────────┼────────────────┘
                                     │
                                     ▼
        ┌──────────────────────────────────────────────────────────┐
        │ TRIGGER_ALERTS Node                                      │
        ├──────────────────────────────────────────────────────────┤
        │ if is_peak:                                              │
        │   ├─ Alert Type: "peak_hour"                             │
        │   ├─ Severity: "high" / "critical"                       │
        │   ├─ Message: "Peak hour! {count} visitors"              │
        │   ├─ Recommendation: "Activate additional staff"         │
        │   └─ Redis: INCREMENT stats:peak_hours:{date}            │
        │                                                           │
        │ if is_low:                                               │
        │   ├─ Alert Type: "low_hour"                              │
        │   ├─ Severity: "low"                                     │
        │   ├─ Message: "Low traffic: {count} visitors"            │
        │   └─ Recommendation: "Energy-saving mode"                │
        │                                                           │
        │ Execution: Branching (conditional edges)                 │
        │ Parallelizable: YES (write to Redis only)                │
        └──────────────────────────────────────────────────────────┘
                                       │
                                       ▼
                                 ╔═══════╗
                                 ║  END  ║
                                 ╚═══════╝

DETAILED STATE TRANSITIONS:

Normal Flow (10-100 people):
  aggregate_hourly_count() → detect_peaks() → [NO_ACTION] → END

Peak Detection Flow (>100 people):
  aggregate_hourly_count() → detect_peaks() → calculate_severity() 
  → trigger_alerts() → END

Low Detection Flow (<20 people):
  aggregate_hourly_count() → detect_peaks() → calculate_severity() 
  → trigger_alerts() → END

CHECKPOINTING (PostgreSQL-backed):
  ├─ Save state after each node execution
  ├─ Enable recovery from failures
  ├─ Store thread history (configurable: thread_id: "peak_hour_CAM_001")
  └─ Query past executions for trend analysis
```

---

## Feature 2: OVERCROWDING ALERTS WORKFLOW

```
╔═════════════════════════════════════════════════════════════════════════╗
║              LANGGRAPH: REAL-TIME OVERCROWDING DETECTION                ║
╚═════════════════════════════════════════════════════════════════════════╝

TRIGGER: Detection Event (ByteTrack output every frame)

STATE SCHEMA:
  OvercrowdingState:
    ├─ camera_id: str
    ├─ person_count: int (estimated from detections)
    ├─ zone_threshold: int (configurable per zone type)
    ├─ severity: str (low, medium, high, critical)
    ├─ alerts: List[Dict]
    └─ messages: List[BaseMessage]

EXECUTION FLOW:

                        ┌────────────────────────────┐
                        │ REAL-TIME TRIGGER          │
                        │ ├─ ByteTrack Output (30fps)│
                        │ ├─ Frame #{frame_num}      │
                        │ └─ Track IDs: [1,2,3...]   │
                        └────────────────────────────┘
                                    │
                                    ▼
        ┌───────────────────────────────────────────────────────┐
        │ COUNT_CURRENT_PEOPLE Node (Latency: ~50ms)           │
        ├───────────────────────────────────────────────────────┤
        │ ├─ Query detections from last 5 seconds               │
        │ │  SELECT COUNT(*) WHERE:                             │
        │ │    camera_id = {cam}                                │
        │ │    class_name = "person"                            │
        │ │    timestamp >= (NOW() - 5sec)                      │
        │ │                                                      │
        │ ├─ Estimate unique people (count / 3)                 │
        │ │  → Rationale: ~3 detections per person per 5 sec    │
        │ │                                                      │
        │ └─ Update state.person_count                          │
        │                                                        │
        │ Zone Thresholds:                                       │
        │   ├─ Entrance: 150 people                             │
        │   ├─ Food Court: 200 people                           │
        │   ├─ Checkout: 50 people                              │
        │   └─ Main Hall: 300 people                            │
        │                                                        │
        │ Parallelizable: YES (database indexed queries)         │
        └───────────────────────────────────────────────────────┘
                                    │
                    ┌───────────────┴───────────────┐
                    │                               │
        Condition: CHECK_THRESHOLD               │
            IF person_count > zone_threshold      │
               → "crowded" → next node            │
            ELSE                                   │
               → "normal" → END                    │
                    │                               │
                    ▼                               ▼
        ┌────────────────────────┐    ┌──────────────────┐
        │ CALCULATE_SEVERITY     │    │ END (Normal)     │
        │ (Crowded Branch)       │    └──────────────────┘
        └────────────────────────┘
                    │
        ┌───────────┴─────────────┐
        │ Severity Calculation    │
        │                         │
        │ ratio = count / threshold
        │                         │
        │ ratio > 2.0  → CRITICAL │
        │ ratio > 1.5  → HIGH     │
        │ ratio > 1.0  → MEDIUM   │
        │ ratio ≤ 1.0  → LOW      │
        │                         │
        └───────────┬─────────────┘
                    │
                    ▼
        ┌───────────────────────────────────────────────────────┐
        │ GENERATE_ALERT Node (Latency: ~30ms)                │
        ├───────────────────────────────────────────────────────┤
        │ ├─ Create Alert record:                               │
        │ │  ├─ alert_type: "overcrowding"                      │
        │ │  ├─ severity: {HIGH/MEDIUM/CRITICAL}                │
        │ │  ├─ camera_id: {camera_id}                          │
        │ │  ├─ timestamp: NOW()                                │
        │ │  ├─ metadata: {                                      │
        │ │  │    person_count: {count}                         │
        │ │  │    threshold: {threshold}                        │
        │ │  │    ratio: {count/threshold}                      │
        │ │  │ }                                                 │
        │ │  └─ acknowledged: 0                                 │
        │ │                                                      │
        │ ├─ INSERT into PostgreSQL.alerts table                │
        │ │                                                      │
        │ ├─ Redis: INCREMENT alert counter                     │
        │ │  "stats:overcrowding:{date}"                        │
        │ │                                                      │
        │ └─ Add to state.alerts List                           │
        │                                                        │
        │ Total Latency: ~100ms (acceptable for real-time)     │
        │ Parallelizable: YES (database writes indexed)        │
        └───────────────────────────────────────────────────────┘
                                    │
                                    ▼
                        ┌─────────────────────┐
                        │ TRIGGER EXTERNAL    │
                        │ ACTIONS (Async)     │
                        ├─────────────────────┤
                        │ ├─ AWS SNS Publish  │
                        │ ├─ Twilio SMS Alert │
                        │ ├─ Email Notif.     │
                        │ └─ Slack Message    │
                        └─────────────────────┘
                                    │
                                    ▼
                              ╔═══════╗
                              ║  END  ║
                              ╚═══════╝

EXECUTION TIMING:
  ├─ Trigger to Alert: ~150ms (50ms count + 30ms generate + 70ms external)
  ├─ Real-time: YES (sub-200ms acceptable for alerts)
  └─ Batching: Optional (group alerts every 5 sec to avoid alert spam)

PARALLEL INSTANCES:
  ├─ Camera 1 Overcrowding Agent (independent thread)
  ├─ Camera 2 Overcrowding Agent (independent thread)
  ├─ ...
  └─ Camera N Overcrowding Agent (independent thread)

  All running concurrently with PostgreSQL checkpointing!
```

---

## Feature 3: QUEUE MONITORING WORKFLOW

```
╔═════════════════════════════════════════════════════════════════════════╗
║                    LANGGRAPH: QUEUE MONITORING                          ║
╚═════════════════════════════════════════════════════════════════════════╝

ARCHITECTURE: OpenCV Line Detection + LangGraph Analytics

DETECTION FLOW:
  YOLO11 Detection ─→ ByteTrack ─→ OpenCV Line Crossing ─→ LangGraph
  
  Per Frame (30fps):
    ├─ Detect people positions
    ├─ Assign track IDs
    ├─ Check if track crosses queue line
    └─ Count crossings in both directions

LANGGRAPH WORKFLOW:

STATE:
  QueueState:
    ├─ camera_id: str
    ├─ queue_line_roi: List[List[int]] (polygon)
    ├─ people_in_queue: int
    ├─ queue_length: float (estimated line length)
    ├─ avg_wait_time: float (seconds)
    ├─ current_throughput: float (people/min)
    ├─ queue_status: str (short, medium, long, critical)
    ├─ alerts: List[Dict]
    └─ messages: List[BaseMessage]

WORKFLOW NODES:

        ┌────────────────────────────────┐
        │ DETECT_QUEUE_LINE Node         │
        ├────────────────────────────────┤
        │ ├─ Load ROI polygon from config │
        │ ├─ Run line crossing detection  │
        │ └─ Get people currently in line │
        │   (via point-in-polygon test)   │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ ESTIMATE_WAIT_TIME Node        │
        ├────────────────────────────────┤
        │ ├─ Query historical throughput  │
        │ ├─ Calculate: wait_time = len/  │
        │ │             throughput        │
        │ └─ Trending: increasing/stable/ │
        │              decreasing         │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ CHECK_ALERT_THRESHOLD Node     │
        ├────────────────────────────────┤
        │ IF queue_length > threshold:   │
        │    severity = HIGH → alert     │
        │ ELIF throughput < min:         │
        │    severity = MEDIUM → alert   │
        │ ELSE:                          │
        │    NO_ACTION → END             │
        └────────────────────────────────┘
                        │
          ┌─────────────┴─────────────┐
          │                           │
          ▼                           ▼
    [ALERT]                    [NO ACTION]
      │                             │
      ▼                             ▼
   [END]                         [END]

TRIGGERS & ALERTS:

  Queue Alert Types:
  ├─ "queue_buildup" (30+ people)
  │   └─ Recommendation: Open additional checkout
  │
  ├─ "wait_time_high" (>5 minutes)
  │   └─ Recommendation: Activate queue management
  │
  ├─ "queue_moving_slow" (throughput < 5/min)
  │   └─ Recommendation: Expedite current transactions
  │
  └─ "queue_critical" (>50 people)
      └─ Recommendation: Full incident response

PARALLEL EXECUTION:
  ├─ Multiple checkout lines monitored simultaneously
  ├─ Each line has independent LangGraph agent
  ├─ Agents share detection data, separate state
  └─ PostgreSQL checkpointing per queue
```

---

## Feature 4: DEMOGRAPHIC ANALYTICS WORKFLOW

```
╔═════════════════════════════════════════════════════════════════════════╗
║                 LANGGRAPH: DEMOGRAPHIC ANALYTICS                        ║
╚═════════════════════════════════════════════════════════════════════════╝

BATCH PROCESSING: Hourly aggregation (not real-time)

WORKFLOW NODES:

        ┌────────────────────────────────┐
        │ COLLECT_DETECTIONS Node        │
        ├────────────────────────────────┤
        │ Query detections from last hour │
        │ WHERE class_name = "person"     │
        │ LIMIT 10,000 per hour           │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ CROP_FACES Node                │
        ├────────────────────────────────┤
        │ FOR each detection:             │
        │   ├─ Extract bounding box       │
        │   ├─ Crop face region from orig │
        │   │   video frame               │
        │   └─ Cache in memory            │
        │                                 │
        │ Parallel: YES (per detection)   │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ CLASSIFY_DEMOGRAPHICS Node     │
        ├────────────────────────────────┤
        │ FOR each cropped face:          │
        │   ├─ DeepFace: [age, gender]   │
        │   │   (99.65% accuracy)         │
        │   └─ FairFace: [ethnicity]     │
        │       (better diversity)        │
        │                                 │
        │ Models: Async batch processing  │
        │ Latency: 100ms per 32 faces     │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ APPLY_PRIVACY_FILTER Node      │
        ├────────────────────────────────┤
        │ K-anonymity aggregation:        │
        │ ├─ Age groups: [18-25, 26-35,  │
        │ │              36-50, 50+]     │
        │ ├─ Gender: [M, F]              │
        │ └─ NO individual tracking      │
        │   (compliant GDPR/privacy)      │
        │                                 │
        │ Result: Aggregated counts only  │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ AGGREGATE_HOURLY Node          │
        ├────────────────────────────────┤
        │ GROUP by:                       │
        │ ├─ hour (timestamp)             │
        │ ├─ age_group                    │
        │ ├─ gender                       │
        │ ├─ zone_id                      │
        │ └─ camera_id                    │
        │                                 │
        │ Output: demographics table      │
        │ {                               │
        │   hour: "14:00",                │
        │   age_18_25_M: 45,              │
        │   age_18_25_F: 38,              │
        │   age_26_35_M: 62,              │
        │   age_26_35_F: 51,              │
        │   ...                           │
        │ }                               │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ STORE_ANALYTICS Node           │
        ├────────────────────────────────┤
        │ INSERT into PostgreSQL.         │
        │ demographic_analytics table     │
        │ with time-series index          │
        │ for fast queries                │
        └────────────────────────────────┘
                        │
                        ▼
                      [END]

EXECUTION SCHEDULE:
  ├─ Trigger: Hourly (00:00, 01:00, ..., 23:00)
  ├─ Duration: ~30 seconds per hour's data
  ├─ Parallelization: Batch processing (32 concurrent face classifications)
  └─ Checkpointing: PostgreSQL (recovery from failures)

OUTPUT EXAMPLES:
  Hour 14:00 Demographics:
  ├─ Age 18-25: 83 people (45M, 38F)
  ├─ Age 26-35: 113 people (62M, 51F)
  ├─ Age 36-50: 67 people (38M, 29F)
  └─ Age 50+: 42 people (25M, 17F)

  Total: 305 unique people hour 14:00
  Gender ratio: 170M : 135F (55.7% : 44.3%)
```

---

## Feature 5: AREA POPULARITY ANALYTICS WORKFLOW

```
╔═════════════════════════════════════════════════════════════════════════╗
║               LANGGRAPH: AREA POPULARITY ANALYTICS                      ║
╚═════════════════════════════════════════════════════════════════════════╝

REAL-TIME + HOURLY BATCH PROCESSING

WORKFLOW NODES:

        ┌────────────────────────────────┐
        │ DEFINE_ZONES Node              │
        ├────────────────────────────────┤
        │ Load zone polygons:             │
        │ ├─ Entrance (1)                 │
        │ ├─ Food Court (2)               │
        │ ├─ Clothing Store (3)           │
        │ ├─ Electronics (4)              │
        │ └─ ... (configurable)           │
        │                                 │
        │ Store in Redis for fast lookup  │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ DETECT_ZONE_PRESENCE Node      │
        ├────────────────────────────────┤
        │ FOR each detection (x,y):      │
        │   ├─ Shapely Point-in-Polygon  │
        │   │   test for all zones       │
        │   ├─ Assign to zone with       │
        │   │   confidence score         │
        │   └─ Track zone transitions    │
        │                                 │
        │ Parallel: YES (per detection)   │
        │ Latency: <10ms per detection    │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ COUNT_PER_ZONE Node            │
        ├────────────────────────────────┤
        │ Real-time counter (5-sec window):
        │                                 │
        │ Zone 1 (Entrance): 45 people   │
        │ Zone 2 (Food Court): 67 people │
        │ Zone 3 (Clothing): 23 people   │
        │ Zone 4 (Electronics): 12 people│
        │ ...                             │
        │                                 │
        │ Update Redis every 5 seconds    │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ RANK_POPULARITY Node           │
        ├────────────────────────────────┤
        │ Rank zones by visitor count:   │
        │                                 │
        │ 1. Food Court: 67 ⭐⭐⭐⭐⭐      │
        │ 2. Entrance: 45 ⭐⭐⭐⭐        │
        │ 3. Clothing: 23 ⭐⭐           │
        │ 4. Electronics: 12 ⭐          │
        │                                 │
        │ Insights:                       │
        │ ├─ Peak zone: Food Court       │
        │ └─ Recommendation: Increase    │
        │    vendor presence             │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ GENERATE_HEATMAP Node          │
        ├────────────────────────────────┤
        │ CREATE visual representation:  │
        │ ├─ 2D histogram of zone counts  │
        │ ├─ Color intensity = popularity│
        │ │   Red (hot): high traffic    │
        │ │   Blue (cold): low traffic   │
        │ └─ Overlay on mall floor plan   │
        │                                 │
        │ Export: PNG/JSON for dashboard  │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ HOURLY_AGGREGATION Node        │
        ├────────────────────────────────┤
        │ (Cron: hourly)                  │
        │ ├─ Aggregate zone counts       │
        │ ├─ Calculate dwell times       │
        │ ├─ Identify trends             │
        │ └─ Store in TimescaleDB        │
        │                                 │
        │ Result: zone_analytics table   │
        └────────────────────────────────┘
                        │
                        ▼
        ┌────────────────────────────────┐
        │ TENANT_REPORTS Node            │
        ├────────────────────────────────┤
        │ Generate zone-specific insights:
        │                                 │
        │ Food Court Report:              │
        │ ├─ Avg hourly visitors: 65     │
        │ ├─ Peak hour: 14:00            │
        │ ├─ Low hour: 06:00             │
        │ └─ Trend: +15% vs last week    │
        │                                 │
        │ Send to tenant dashboards       │
        └────────────────────────────────┘
                        │
                        ▼
                      [END]

PARALLEL EXECUTION INSTANCES:

  Active Parallel Agents:
  ├─ Zone Counter (Real-time, every 5 sec)
  ├─ Heatmap Generator (Hourly)
  ├─ Trend Analysis (Daily)
  └─ Tenant Report Generator (Daily)

  All with independent PostgreSQL state!
```

---

## PARALLEL EXECUTION SUMMARY

```
TIER 1 AGENTS - SIMULTANEOUS EXECUTION:

┌─────────────────────────────────────────────────────────────┐
│                  DOCKER CONTAINER                          │
│              (Multiple CV Workers)                          │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  YOLO11 Detection (GPU)                                     │
│      ├─ CAM_001 stream                                      │
│      ├─ CAM_002 stream                                      │
│      └─ CAM_N stream                                        │
│             │                                               │
│             ▼                                               │
│      ByteTrack Processor                                    │
│             │                                               │
│             ▼                                               │
│  ┌──────────┴──────────┐                                   │
│  │ Detection Async Buffer │                                 │
│  └──────────┬──────────┘                                   │
│             │                                               │
└─────────────┼─────────────────────────────────────────────┘
              │
    ┌─────────┴─────────────────────────────────────────────┐
    │                                                        │
    ├──ℹ 5 PARALLEL LANGGRAPH AGENTS                        │
    │                                                        │
    ▼                                                        ▼
┌─────────────────────┐                        ┌──────────────────┐
│ PEAK HOUR AGENT     │                        │ OVERCROWDING     │
│ (Hourly Scheduler)  │                        │ AGENT            │
│ ├─ Aggregates       │                        │ (Real-time)      │
│ ├─ Predicts trends  │                        │ ├─ Counts people │
│ └─ Forecasts        │                        │ ├─ Checks thresh │
└─────────────────────┘                        │ └─ Alerts SNS    │
                                                └──────────────────┘

    ├──────────────────────┬──────────────────────────┤
    │                      │                          │
    ▼                      ▼                          ▼
┌──────────────┐  ┌────────────────┐  ┌──────────────────┐
│ QUEUE        │  │ DEMOGRAPHIC    │  │ AREA POPULARITY  │
│ MONITORING   │  │ ANALYTICS      │  │ ANALYTICS        │
│ AGENT        │  │ AGENT          │  │ AGENT            │
│              │  │                │  │                  │
│ ├─ Line      │  │ ├─ Face crop   │  │ ├─ Zone counter  │
│ │  detection │  │ ├─ DeepFace    │  │ ├─ Ranking       │
│ └─ Wait time │  │ │  classify    │  │ └─ Heatmaps      │
│              │  │ └─ Privacy     │  │                  │
│              │  │    filter      │  │                  │
└──────────────┘  └────────────────┘  └──────────────────┘

All 5 Agents Execution Modes:
├─ REAL-TIME: Overcrowding (instant on new detections)
├─ HOURLY: Peak Hour + Zone Analytics + Demographics
├─ CONTINUOUS: Queue Monitoring (30fps processing)
├─ ON-DEMAND: API-triggered heatmap generation
└─ BATCH: Daily aggregations and report generation

PostgreSQL Checkpointing:
├─ Each agent has independent state storage
├─ Thread ID: {agent_type}_{camera_id}_{thread_num}
├─ Automatic recovery on restart
└─ Query historical states: SELECT FROM langgraph.checkpoint...
```

---

## DOCKER DEPLOYMENT VISUALIZATION

```
╔══════════════════════════════════════════════════════════════╗
║               DOCKER ORCHESTRATION DIAGRAM                  ║
╚══════════════════════════════════════════════════════════════╝

DEVELOPMENT MACHINE (docker-compose up -d)

┌──────────────────────────────────────────────────────────────┐
│                    DOCKER NETWORK                            │
│                   (hive-network)                             │
├──────────────────────────────────────────────────────────────┤
│                                                               │
│  ┌────────────────┐                    ┌─────────────────┐  │
│  │ cv-worker-1   │──────┐              │ cv-worker-2    │  │
│  │ (GPU)         │      │              │ (GPU)          │  │
│  │ CAM_001       │      │              │ CAM_002        │  │
│  └────────────────┘      │              └─────────────────┘  │
│                          │                                   │
│                          ▼                                   │
│          ┌─────────────────────────────┐                    │
│          │  agent-orchestrator         │                    │
│          │  (LangGraph Runtime)        │                    │
│          │  ├─ Peak Hour Agent         │                    │
│          │  ├─ Overcrowding Agent      │                    │
│          │  ├─ Queue Agent             │                    │
│          │  ├─ Demographic Agent       │                    │
│          │  └─ Popularity Agent        │                    │
│          └─────────────────────────────┘                    │
│                    │           │                             │
│                    ▼           ▼                             │
│          ┌──────────────┐  ┌──────────┐                     │
│          │ postgres     │  │ redis    │                     │
│          │ TimescaleDB  │  │ (cache)  │                     │
│          │ (detections, │  │          │                     │
│          │  alerts,     │  │          │                     │
│          │  analytics)  │  │          │                     │
│          └──────────────┘  └──────────┘                     │
│                    │                                         │
│                    ▼                                         │
│          ┌──────────────────────┐                           │
│          │ api-server           │                           │
│          │ FastAPI              │                           │
│          │ :8000/docs           │                           │
│          └──────────────────────┘                           │
│                    │                                         │
│                    ▼                                         │
│          ┌──────────────────────┐                           │
│          │ dashboard            │                           │
│          │ Streamlit            │                           │
│          │ :8501                │                           │
│          └──────────────────────┘                           │
│                                                               │
│  ┌────────────────────────────────┐                         │
│  │  progress-tracker              │                         │
│  │  (Daily logs + JSON metrics)   │                         │
│  │  Logs: /logs/progress_*.log    │                         │
│  └────────────────────────────────┘                         │
│                                                               │
│  ┌────────────────────────────────┐                         │
│  │  pgadmin                        │                         │
│  │  Database GUI                  │                         │
│  │  :5050                          │                         │
│  └────────────────────────────────┘                         │
│                                                               │
└──────────────────────────────────────────────────────────────┘

GPU ACCESS:
├─ cv-worker-1: GPU:0 (RTX 3060 or similar)
├─ cv-worker-2: GPU:0 (Shared or different GPU)
└─ Note: Requires nvidia-docker and docker-compose GPU support

VOLUME MOUNTS:
├─ ./models → /app/models (YOLO weights)
├─ ./logs → /app/logs (daily progress logs)
├─ ./config → /app/config (agent configurations)
└─ ./data → /app/data (video cache)

DATA FLOW:
  Video Streams (RTSP)
       ↓
  cv-worker (YOLO11 + ByteTrack)
       ↓
  Detections → PostgreSQL + Redis
       ↓
  Parallel LangGraph Agents
       ↓
  Alerts → SNS/Twilio/Email
  Analytics → Dashboard
  Progress Logs → /logs/
```

This comprehensive guide covers:
✅ Feature 1: Peak Hour Detection (Hourly + Forecasting)
✅ Feature 2: Overcrowding Alerts (Real-time)
✅ Feature 3: Queue Monitoring (Continuous 30fps)
✅ Feature 4: Demographic Analytics (Hourly batch)
✅ Feature 5: Area Popularity (Real-time + Hourly)

All running in parallel with Docker orchestration and daily progress tracking!
