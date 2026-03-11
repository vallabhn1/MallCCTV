import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import os
import logging
import pandas as pd
import streamlit as st
from datetime import datetime
from sqlalchemy import create_engine, text
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)

st.set_page_config(
    page_title="Hive Dynamics – Mall CCTV",
    page_icon="🐝",
    layout="wide",
    initial_sidebar_state="expanded",
)

@st.cache_resource
def get_engine():
    url = (
        f"postgresql+psycopg://{os.getenv('POSTGRES_USER', 'hive_user')}:"
        f"{os.getenv('POSTGRES_PASSWORD', 'hive1234')}@"
        f"{os.getenv('POSTGRES_HOST', 'localhost')}:"
        f"{os.getenv('POSTGRES_PORT', '5432')}/"
        f"{os.getenv('POSTGRES_DB', 'hive_dynamics')}"
    )
    return create_engine(url)

def query(sql: str) -> pd.DataFrame:
    try:
        with get_engine().connect() as conn:
            return pd.read_sql(text(sql), conn)
    except Exception as e:
        st.error(f"DB error: {e}")
        return pd.DataFrame()

# SESSION STATE
for key in ["proc_done", "proc_running", "agent_done",
            "proc_camera_id", "proc_video_path", "proc_log",
            "agent_alerts", "_proc_thread", "_done_event"]:
    if key not in st.session_state:
        st.session_state[key] = None

# SIDEBAR
with st.sidebar:
    st.image("https://img.icons8.com/fluency/96/honey-bee.png", width=60)
    st.title("Hive Dynamics")
    st.caption("Mall CCTV Intelligence Platform")
    st.divider()

    cameras = query("SELECT DISTINCT camera_id FROM detections ORDER BY camera_id")
    cam_list = cameras["camera_id"].tolist() if not cameras.empty else ["CAM_001"]
    selected_cam = st.selectbox("📷 Camera", ["All"] + cam_list)
    cam_filter = f"= '{selected_cam}'" if selected_cam != "All" else "IS NOT NULL"

    st.divider()
    time_window = st.selectbox("⏱ Time Window", ["1 hour", "6 hours", "24 hours", "7 days"])
    tw = time_window

    st.divider()
    if st.button("🔄 Refresh Dashboard"):
        st.rerun()
    st.caption(f"🕐 {datetime.now().strftime('%d %b %Y, %H:%M:%S')}")

# HEADER
st.markdown("# 🐝 Hive Dynamics – Mall Intelligence")
st.divider()

# TABS
tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
    "📊 Overview", "👥 Overcrowding", "🚶 Loitering",
    "⏰ Peak Hours", "🚨 Alerts", "📹 Video Analysis",
])

# ══════════════════════════════════════════
# TAB 1: OVERVIEW
# ══════════════════════════════════════════
with tab1:
    st.subheader("📊 Overview")
    total_df  = query(f"SELECT COUNT(DISTINCT track_id) as total FROM detections WHERE camera_id {cam_filter}")
    alert_df  = query(f"SELECT COUNT(*) as total FROM alerts WHERE camera_id {cam_filter} AND acknowledged = false")
    peak_df   = query(f"SELECT COUNT(*) as total FROM peak_hour_analytics WHERE camera_id {cam_filter} AND is_peak = true")
    loiter_df = query(f"SELECT COUNT(*) as total FROM track_states WHERE camera_id {cam_filter} AND status = 'loitering'")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("👥 Unique People",  total_df["total"].iloc[0]  if not total_df.empty  else 0)
    c2.metric("🚨 Active Alerts",  alert_df["total"].iloc[0]  if not alert_df.empty  else 0)
    c3.metric("⏰ Peak Hours",     peak_df["total"].iloc[0]   if not peak_df.empty   else 0)
    c4.metric("🚶 Loiterers",      loiter_df["total"].iloc[0] if not loiter_df.empty else 0)

    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        st.markdown("#### 👥 People per Hour")
        hourly = query(f"""
            SELECT DATE_TRUNC('hour', timestamp) as hour, COUNT(DISTINCT track_id) as people
            FROM detections
            WHERE camera_id {cam_filter}
              AND timestamp > NOW() - INTERVAL '{tw}'
            GROUP BY 1 ORDER BY 1
        """)
        if not hourly.empty:
            st.bar_chart(hourly.set_index("hour")["people"])
        else:
            st.info("No data.")

    with col2:
        st.markdown("#### 🚨 Alert Types")
        atypes = query(f"""
            SELECT alert_type, COUNT(*) as count FROM alerts
            WHERE camera_id {cam_filter} GROUP BY alert_type ORDER BY count DESC
        """)
        if not atypes.empty:
            st.dataframe(atypes, use_container_width=True)
        else:
            st.info("No alerts.")

# ══════════════════════════════════════════
# TAB 2: OVERCROWDING
# ══════════════════════════════════════════
with tab2:
    st.subheader("👥 Overcrowding Analysis")
    df = query(f"""
        SELECT DATE_TRUNC('minute', timestamp) as minute,
               COUNT(DISTINCT track_id) as unique_people
        FROM detections WHERE camera_id {cam_filter}
          AND timestamp > NOW() - INTERVAL '{tw}'
        GROUP BY 1 ORDER BY 1
    """)
    if not df.empty:
        c1, c2 = st.columns(2)
        c1.metric("📈 Peak Count", int(df["unique_people"].max()))
        c2.metric("📊 Average",    f"{df['unique_people'].mean():.1f}")
        st.line_chart(df.set_index("minute")["unique_people"])
    else:
        st.info("No data in window.")

    oc = query(f"""
        SELECT timestamp, severity, extra FROM alerts
        WHERE camera_id {cam_filter} AND alert_type='overcrowding'
        ORDER BY timestamp DESC LIMIT 20
    """)
    if not oc.empty:
        st.dataframe(oc, use_container_width=True)

# ══════════════════════════════════════════
# TAB 3: LOITERING
# ══════════════════════════════════════════
with tab3:
    st.subheader("🚶 Loitering Detection")
    df = query(f"""
        SELECT track_id, zone_id, total_dwell_sec,
               detection_count, avg_speed, status, last_time
        FROM track_states WHERE camera_id {cam_filter} AND status='loitering'
        ORDER BY total_dwell_sec DESC
    """)
    if not df.empty:
        c1, c2 = st.columns(2)
        c1.metric("🚶 Tracks",   len(df))
        c2.metric("⏱ Max Dwell", f"{int(df['total_dwell_sec'].max())}s")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No loitering detected.")

# ══════════════════════════════════════════
# TAB 4: PEAK HOURS
# ══════════════════════════════════════════
with tab4:
    st.subheader("⏰ Peak Hour Analytics")
    df = query(f"""
        SELECT hour, person_count, is_peak, forecast_next
        FROM peak_hour_analytics WHERE camera_id {cam_filter}
        ORDER BY hour DESC LIMIT 48
    """)
    if not df.empty:
        c1, c2, c3 = st.columns(3)
        c1.metric("Hours Analysed",   len(df))
        c2.metric("🔴 Peak Hours",    int(df["is_peak"].sum()))
        c3.metric("🔮 Next Forecast", int(df["forecast_next"].iloc[0]))
        st.bar_chart(df.set_index("hour")["person_count"])
        st.dataframe(df, use_container_width=True)
    else:
        st.info("Run Peak Hour Agent first.")

# ══════════════════════════════════════════
# TAB 5: ALERTS
# ══════════════════════════════════════════
with tab5:
    st.subheader("🚨 All Alerts")
    df = query(f"""
        SELECT id, alert_type, severity, camera_id,
               timestamp, acknowledged, extra
        FROM alerts WHERE camera_id {cam_filter}
        ORDER BY timestamp DESC LIMIT 100
    """)
    if not df.empty:
        sev_map = {"high": "🔴", "medium": "🟡", "low": "🟢",
                   "critical": "🔴", "warning": "🟠"}
        df["severity"] = df["severity"].apply(
            lambda v: f"{sev_map.get(str(v).lower(), '⚪')} {v}")
        st.dataframe(df, use_container_width=True)
    else:
        st.info("No alerts found.")

# ══════════════════════════════════════════
# TAB 6: VIDEO ANALYSIS
# ══════════════════════════════════════════
with tab6:
    from src.dashboard.video_tab import render_video_tab
    render_video_tab(query)
