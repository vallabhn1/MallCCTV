import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import os
import cv2
import ast
import asyncio
import threading
import numpy as np
import pandas as pd
import streamlit as st
from pathlib import Path
from datetime import datetime

UPLOAD_DIR = Path("data/uploaded_videos")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


def parse_bbox(raw) -> list:
    try:
        if isinstance(raw, list):
            return [int(v) for v in raw]
        return [int(v) for v in ast.literal_eval(str(raw))]
    except:
        return [0, 0, 0, 0]


def annotate_frame(frame: np.ndarray, detections: list) -> np.ndarray:
    out = frame.copy()
    for det in detections:
        try:
            x1, y1, x2, y2 = parse_bbox(det.get("bbox"))
            tid  = det.get("track_id", "?")
            conf = float(det.get("confidence", 0))
            cv2.rectangle(out, (x1, y1), (x2, y2), (0, 255, 80), 2)
            cv2.putText(out, f"ID:{tid} {conf:.0%}",
                        (x1, max(y1 - 8, 12)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 80), 1)
        except:
            continue
    cv2.putText(out, datetime.now().strftime("%H:%M:%S"),
                (10, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 255), 2)
    return out


def generate_heatmap(frame: np.ndarray, detections: list) -> np.ndarray:
    h, w = frame.shape[:2]
    heat = np.zeros((h, w), dtype=np.float32)
    for det in detections:
        try:
            x1, y1, x2, y2 = parse_bbox(det.get("bbox"))
            cx, cy = (x1 + x2) // 2, (y1 + y2) // 2
            radius = max(50, (x2 - x1))
            Y, X   = np.ogrid[:h, :w]
            blob   = np.exp(-((X - cx)**2 + (Y - cy)**2) / (2 * (radius / 2.0)**2))
            heat  += blob
        except:
            continue
    if heat.max() > 0:
        heat = (heat / heat.max() * 255).astype(np.uint8)
    else:
        heat = heat.astype(np.uint8)
    colored   = cv2.applyColorMap(heat, cv2.COLORMAP_JET)
    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
    blended   = cv2.addWeighted(frame_bgr, 0.5, colored, 0.5, 0)
    return cv2.cvtColor(blended, cv2.COLOR_BGR2RGB)


def _proc_worker(video_path: str, camera_id: str, log_list: list, done_event):
    from src.cv_pipeline.video_processor import VideoProcessor
    try:
        log_list.append(f"[{datetime.now().strftime('%H:%M:%S')}] ▶ VideoProcessor starting...")
        vp = VideoProcessor(camera_id=camera_id, source=video_path, save_video=True)
        vp.run(save_to_db=True)
        log_list.append(f"[{datetime.now().strftime('%H:%M:%S')}] ✅ Done! Detections saved to DB.")
    except Exception as e:
        log_list.append(f"[{datetime.now().strftime('%H:%M:%S')}] ❌ Error: {e}")
    finally:
        done_event.set()


def run_agent_sync(agent_name: str, camera_id: str) -> list:
    if agent_name == "Peak Hour Agent":
        from src.agents.peak_hour_agent import PeakHourAgent
        return asyncio.run(PeakHourAgent().run(camera_id))

    elif agent_name == "Overcrowding Agent":
        from src.agents.overcrowding_agent import OvercrowdingAgent
        return asyncio.run(OvercrowdingAgent().run([camera_id]))

    elif agent_name == "Loitering Agent":
        import src.agents.loitering_agent as la
        la.CAMERAS_TO_CHECK = [camera_id]
        la.main()
        return [{"severity": "info", "message": "✅ Loitering agent finished. Check DB Alerts tab."}]

    elif agent_name == "Fire/Smoke Agent":
        import src.agents.fire_agent as fa
        fa.CAMERA_ID = camera_id
        fa.run_fire_agent()
        return [{"severity": "critical", "message": "🔥 Fire/Smoke agent finished. Check DB Alerts tab."}]

    return []


def render_video_tab(query_fn):
    st.subheader("📹 Video Analysis Pipeline")

    # ── 1. UPLOAD ────────────────────────
    st.markdown("### 1️⃣ Upload Video")
    uploaded  = st.file_uploader("Upload .mp4 / .avi", type=["mp4", "avi", "mov"])
    camera_id = st.text_input("Camera ID", value="CAM_UPLOAD_001")

    if uploaded:
        vpath = UPLOAD_DIR / uploaded.name
        with open(vpath, "wb") as f:
            f.write(uploaded.read())
        st.success(f"✅ Saved → `{vpath}`")
        st.session_state["proc_video_path"] = str(vpath)
        st.session_state["proc_camera_id"]  = camera_id
        st.session_state["proc_done"]       = False

    # ── 2. PROCESS ───────────────────────
    if st.session_state.get("proc_video_path"):
        st.markdown("### 2️⃣ Run Video Processor")

        start = st.button("▶ Process Video", type="primary",
                          disabled=bool(st.session_state.get("proc_running")))

        if start:
            log_list   = []
            done_event = threading.Event()
            st.session_state["proc_running"] = True
            st.session_state["proc_done"]    = False
            st.session_state["proc_log"]     = log_list
            st.session_state["_done_event"]  = done_event

            t = threading.Thread(
                target=_proc_worker,
                args=(st.session_state["proc_video_path"],
                      st.session_state["proc_camera_id"],
                      log_list, done_event),
                daemon=True,
            )
            t.start()
            st.session_state["_proc_thread"] = t

        if st.session_state.get("proc_running"):
            done_event = st.session_state.get("_done_event")
            log_box    = st.empty()
            import time

            while done_event and not done_event.is_set():
                log_box.code("\n".join(st.session_state["proc_log"][-20:]) or "Starting...")
                time.sleep(1.5)
                st.rerun()

            log_box.code("\n".join(st.session_state.get("proc_log", [])))
            logs_str = "\n".join(st.session_state.get("proc_log", []))

            if "❌" in logs_str:
                st.error("Processing failed. Check logs above.")
            else:
                st.success("✅ Video processing complete!")
                st.session_state["proc_done"] = True

            st.session_state["proc_running"] = False

    # ── 3. VIEWER ────────────────────────
    if st.session_state.get("proc_done"):
        st.markdown("### 3️⃣ Playback + Heatmap")

        view_mode = st.radio(
            "View Mode",
            ["📹 Annotated Frames", "🌡 Heatmap Overlay", "⬛ Raw Video"],
            horizontal=True
        )

        det_df = query_fn(f"""
            SELECT track_id, bbox, confidence
            FROM detections
            WHERE camera_id = '{st.session_state["proc_camera_id"]}'
            ORDER BY timestamp
        """)
        detections = det_df.to_dict("records") if not det_df.empty else []

        cap          = cv2.VideoCapture(st.session_state["proc_video_path"])
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        seek         = st.slider("🎞 Scrub Frame", 0, max(total_frames - 1, 1), 0)
        cap.set(cv2.CAP_PROP_POS_FRAMES, seek)
        ret, frame = cap.read()
        cap.release()

        if ret:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

            if view_mode == "🌡 Heatmap Overlay":
                display = generate_heatmap(frame_rgb, detections)
                caption = f"Heatmap — {len(detections)} total detections"
            elif view_mode == "📹 Annotated Frames":
                display = annotate_frame(frame_rgb, detections)
                caption = f"Frame {seek}/{total_frames} — {len(detections)} unique tracks"
            else:
                display = frame_rgb
                caption = f"Raw Frame {seek}/{total_frames}"

            st.image(display, use_column_width=True, caption=caption)

            c1, c2, c3 = st.columns(3)
            c1.metric("🎞 Total Frames",     total_frames)
            c2.metric("👥 Unique Detections", len(detections))
            c3.metric("📷 Camera",            st.session_state["proc_camera_id"])

            out_path = f"data/output/{st.session_state['proc_camera_id']}_unique.mp4"
            if os.path.exists(out_path):
                with open(out_path, "rb") as fv:
                    st.download_button("⬇ Download Annotated Video", fv,
                                       file_name=os.path.basename(out_path),
                                       mime="video/mp4")
        else:
            st.warning("⚠️ Could not read frame.")

        # ── 4. AGENT ─────────────────────
        st.divider()
        st.markdown("### 4️⃣ Run Agent")

        agent_choice = st.selectbox("Select Agent", [
            "Peak Hour Agent",
            "Overcrowding Agent",
            "Loitering Agent",
            "Fire/Smoke Agent",
        ])

        if st.button(f"🤖 Run {agent_choice}", type="primary"):
            with st.spinner(f"Running {agent_choice}..."):
                try:
                    alerts = run_agent_sync(agent_choice, st.session_state["proc_camera_id"])
                    st.success(f"✅ {agent_choice} done — {len(alerts)} alert(s).")
                    st.session_state["agent_done"]   = agent_choice
                    st.session_state["agent_alerts"] = alerts
                except Exception as e:
                    st.error(f"❌ Agent failed: {e}")

        # ── 5. RESULTS ───────────────────
        if st.session_state.get("agent_done"):
            st.markdown("### 5️⃣ Results & Alerts")

            agent      = st.session_state["agent_done"]
            raw_alerts = st.session_state.get("agent_alerts", [])
            cam        = st.session_state["proc_camera_id"]

            r1, r2 = st.tabs(["🚨 Live Agent Alerts", "📊 DB Analytics"])

            with r1:
                if raw_alerts:
                    for a in raw_alerts:
                        sev = str(a.get("severity", "info")).lower()
                        msg = a.get("message", str(a))
                        if sev in ("high", "critical"):
                            st.error(f"🔴 {msg}")
                        elif sev in ("medium", "warning"):
                            st.warning(f"🟠 {msg}")
                        else:
                            st.info(f"🟢 {msg}")
                else:
                    st.info("No alerts returned.")

            with r2:
                if agent == "Peak Hour Agent":
                    df = query_fn(f"""
                        SELECT hour, person_count, is_peak, forecast_next
                        FROM peak_hour_analytics WHERE camera_id='{cam}'
                        ORDER BY hour DESC LIMIT 24
                    """)
                    if not df.empty:
                        st.bar_chart(df.set_index("hour")["person_count"])
                        st.dataframe(df, use_container_width=True)
                    else:
                        st.info("No peak hour rows found.")

                elif agent == "Overcrowding Agent":
                    df = query_fn(f"""
                        SELECT DATE_TRUNC('minute', timestamp) as minute,
                               COUNT(DISTINCT track_id) as people
                        FROM detections WHERE camera_id='{cam}'
                        GROUP BY 1 ORDER BY 1
                    """)
                    if not df.empty:
                        st.line_chart(df.set_index("minute")["people"])
                    else:
                        st.info("No detection data.")

                elif agent == "Loitering Agent":
                    df = query_fn(f"""
                        SELECT track_id, total_dwell_sec, status, zone_id
                        FROM track_states WHERE camera_id='{cam}'
                          AND status='loitering'
                        ORDER BY total_dwell_sec DESC
                    """)
                    if not df.empty:
                        st.dataframe(df, use_container_width=True)
                    else:
                        st.info("No loitering tracks found.")

                elif agent == "Fire/Smoke Agent":
                    df = query_fn(f"""
                        SELECT timestamp, alert_type, severity, extra
                        FROM alerts WHERE camera_id='{cam}'
                          AND (alert_type='fire' OR alert_type='smoke')
                        ORDER BY timestamp DESC LIMIT 50
                    """)
                    if not df.empty:
                        st.error(f"🔥 {len(df)} fire/smoke alert(s) detected!")
                        st.dataframe(df, use_container_width=True)
                    else:
                        st.success("✅ No fire/smoke detected in this video.")

                st.markdown("#### All DB Alerts — this Camera")
                adf = query_fn(f"""
                    SELECT alert_type, severity, timestamp, extra
                    FROM alerts WHERE camera_id='{cam}'
                    ORDER BY timestamp DESC LIMIT 50
                """)
                if not adf.empty:
                    st.dataframe(adf, use_container_width=True)
                else:
                    st.info("No DB alerts.")
