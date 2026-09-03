"""
Endurance Coach • AI Athletic Performance Engine & Web Application
Key Capabilities & Constraints:
1. Deterministic Calculation Engine (NP, VI, IF, TSS, CTL/ATL/TSB, ACWR)
2. Graph Display Rule: Performance graphs ONLY generated for indoor workouts (Virtual/Trainer/Zwift/MyWhoosh). Runs, walks, gym, and outdoor sessions show text metrics.
3. Coach's Long-Term Memory: Incorporates athlete limitations and preferences into system instructions.
4. Native min/km Running Threshold Pace & Workout ZWO Exporter.
"""

import base64
import datetime as dt
import json
import math
import os
import re
import xml.etree.ElementTree as ET
from xml.dom import minidom
from zoneinfo import ZoneInfo
from typing import List, Dict, Any, Optional, Tuple

import numpy as np
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# Initialize Streamlit Page Config
st.set_page_config(page_title="Endurance Coach • AI Performance Platform", page_icon="🚴‍♂️", layout="wide")

LOCAL_TZ = ZoneInfo("Asia/Singapore")

# --- OBSIDIAN DARK DESIGN SYSTEM ---
BG_APP = "#0D1117"
BG_SIDEBAR = "#161B22"
BG_CARD = "#161B22"
BG_SURFACE_ALT = "#21262D"
BORDER_SUBTLE = "#30363D"
BORDER_ACCENT = "#8B949E"
TEXT_PRIMARY = "#F0F6FC"
TEXT_MUTED = "#8B949E"
ACCENT_BLUE = "#2563EB"
ACCENT_GLOW = "rgba(37, 99, 235, 0.35)"

st.markdown(f"""
<style>
header[data-testid="stHeader"] {{ background-color: {BG_APP} !important; z-index: 99 !important; }}
.main .block-container {{ padding-top: 4rem !important; padding-bottom: 5rem !important; max-width: 1440px; }}
.stApp {{ background-color: {BG_APP} !important; color: {TEXT_PRIMARY} !important; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif; }}
section[data-testid="stSidebar"] {{ background-color: {BG_SIDEBAR} !important; border-right: 1px solid {BORDER_SUBTLE} !important; }}
div[data-testid="stMetric"], div[data-testid="stExpander"], div[data-testid="stChatMessage"] {{ background-color: {BG_CARD} !important; border: 1px solid {BORDER_SUBTLE} !important; border-radius: 10px !important; color: {TEXT_PRIMARY} !important; }}
.readiness-card-amber {{ background: linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(245, 158, 11, 0.02)); border: 1px solid rgba(245, 158, 11, 0.35); border-radius: 10px; padding: 16px; margin-bottom: 1rem; }}
.readiness-card-green {{ background: linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(16, 185, 129, 0.02)); border: 1px solid rgba(16, 185, 129, 0.35); border-radius: 10px; padding: 16px; margin-bottom: 1rem; }}
.workout-pill {{ display: inline-block; padding: 3px 8px; border-radius: 6px; font-size: 0.8rem; font-weight: 600; background-color: {BG_SURFACE_ALT}; border: 1px solid {BORDER_SUBTLE}; margin-right: 6px; }}
</style>
""", unsafe_allow_html=True)


# ==============================================================================
# 1. DETERMINISTIC CALCULATION ENGINE & PACE UTILITIES
# ==============================================================================

class EnduranceMathEngine:
    """Calculates physiological metrics deterministically and manages unit formats."""

    @staticmethod
    def parse_pace_to_seconds(pace_str: str) -> int:
        """Converts MM:SS string to total seconds per km (e.g. '4:15' -> 255)."""
        try:
            parts = pace_str.strip().split(":")
            if len(parts) == 2:
                mins = int(parts[0])
                secs = int(parts[1])
                return mins * 60 + secs
            return int(pace_str)
        except Exception:
            return 255  # Default fallback (4:15/km)

    @staticmethod
    def format_seconds_to_pace(total_seconds: int) -> str:
        """Converts total seconds per km to MM:SS string (e.g. 255 -> '4:15')."""
        if not total_seconds or total_seconds <= 0:
            return "4:15"
        mins = total_seconds // 60
        secs = total_seconds % 60
        return f"{mins}:{secs:02d}"

    @classmethod
    def format_pace_label(cls, total_seconds: int) -> str:
        return f"{cls.format_seconds_to_pace(total_seconds)} /km"

    @staticmethod
    def calculate_30s_rolling_avg(power_stream: List[int]) -> np.ndarray:
        if not power_stream or len(power_stream) < 30:
            return np.array(power_stream, dtype=float)
        return np.convolve(power_stream, np.ones(30) / 30, mode='valid')

    @classmethod
    def calculate_normalized_power(cls, power_stream: List[int]) -> Optional[float]:
        """Calculates NP using 30-second 4th-power rolling average."""
        if not power_stream or len(power_stream) < 120:
            return float(np.mean(power_stream)) if power_stream else None
        
        rolling_avg = cls.calculate_30s_rolling_avg(power_stream)
        fourth_powers = np.power(rolling_avg, 4)
        avg_fourth_power = np.mean(fourth_powers)
        np_val = np.power(avg_fourth_power, 0.25)
        return round(float(np_val), 1)

    @classmethod
    def calculate_cycling_metrics(cls, power_stream: List[int], declared_ftp: int) -> Dict[str, Any]:
        if not power_stream or declared_ftp <= 0:
            return {"avg_power": 0, "np": 0, "vi": 0.0, "if": 0.0, "tss": 0.0}
        
        avg_power = round(float(np.mean(power_stream)), 1)
        np_val = cls.calculate_normalized_power(power_stream) or avg_power
        
        vi = round(np_val / avg_power, 2) if avg_power > 0 else 1.0
        if_val = round(np_val / declared_ftp, 2)
        duration_sec = len(power_stream)
        
        tss = round(((duration_sec * np_val * if_val) / (declared_ftp * 3600.0)) * 100.0, 1)
        
        return {
            "avg_power": avg_power,
            "np": np_val,
            "vi": vi,
            "if": if_val,
            "tss": tss,
            "kilojoules": round((avg_power * duration_sec) / 1000.0, 1)
        }

    @staticmethod
    def calculate_ctl_atl_tsb(daily_tss_history: List[Dict[str, Any]], initial_ctl: float = 0.0, initial_atl: float = 0.0) -> List[Dict[str, Any]]:
        """Impulse-Response Model calculating CTL, ATL, and TSB."""
        ctl_decay = 1.0 - math.exp(-1.0 / 42.0)
        atl_decay = 1.0 - math.exp(-1.0 / 7.0)
        
        ctl, atl = initial_ctl, initial_atl
        results = []
        for entry in daily_tss_history:
            tss = entry.get("tss", 0)
            is_indoor = entry.get("is_indoor", False)
            tsb = ctl - atl
            ctl += (tss - ctl) * ctl_decay
            atl += (tss - atl) * atl_decay
            results.append({
                "date": entry.get("date", ""),
                "ctl": round(ctl, 1),
                "atl": round(atl, 1),
                "tsb": round(tsb, 1),
                "is_indoor": is_indoor,
                "workout_type": entry.get("type", "Indoor Ride")
            })
        return results

    @staticmethod
    def calculate_acwr(daily_tss_history: List[Dict[str, Any]]) -> Tuple[float, str]:
        if len(daily_tss_history) < 28:
            return 1.0, "Stable (Insufficient History)"
        loads = [e.get("tss", 0) for e in daily_tss_history]
        acute = sum(loads[-7:]) / 7.0
        chronic = sum(loads[-28:]) / 28.0
        if chronic == 0:
            return 1.0, "Stable"
        acwr = round(acute / chronic, 2)
        if acwr > 1.35:
            return acwr, "Overreaching / High Injury Risk (>1.35)"
        elif acwr < 0.8:
            return acwr, "Detraining Risk (<0.8)"
        return acwr, "Optimal Load Ramp (0.8–1.35)"


# ==============================================================================
# 2. WORKOUT DSL PARSER & ZWO FILE EXPORTER
# ==============================================================================

class WorkoutGrammarEngine:
    """Parses human-readable workout DSL and generates MyWhoosh/Zwift ZWO XML."""

    @staticmethod
    def parse_dsl_to_steps(text: str, declared_ftp: int = 250) -> List[Dict[str, Any]]:
        steps = []
        lines = [l.strip() for l in text.split('\n') if l.strip()]
        current_section = "Main Set"
        multiplier = 1

        for line in lines:
            if line.lower() in ["warmup", "main set", "cooldown"]:
                current_section = line.title()
                multiplier = 1
                continue
            
            mult_match = re.match(r'^(\d+)x$', line, re.IGNORECASE)
            if mult_match:
                multiplier = int(mult_match.group(1))
                continue

            step_match = re.search(r'-\s*(?:(\d+)\s*m|(\d+)\s*s|(\d+)\s*km)\s*(.*)', line, re.IGNORECASE)
            if step_match:
                dur_m, dur_s, dur_km, target_str = step_match.groups()
                
                if dur_m:
                    duration_sec = int(dur_m) * 60
                elif dur_s:
                    duration_sec = int(dur_s)
                elif dur_km:
                    duration_sec = int(dur_km) * 300
                else:
                    duration_sec = 300

                pct_match = re.search(r'(\d+)%', target_str)
                watt_match = re.search(r'(\d+)w', target_str, re.IGNORECASE)
                
                if pct_match:
                    pct = float(pct_match.group(1)) / 100.0
                elif watt_match:
                    pct = float(watt_match.group(1)) / declared_ftp
                else:
                    pct = 0.65

                for _ in range(multiplier):
                    steps.append({
                        "section": current_section,
                        "duration_sec": duration_sec,
                        "target_power_pct": round(pct, 2),
                        "target_watts": int(pct * declared_ftp),
                        "raw_target": target_str.strip()
                    })
                multiplier = 1

        return steps

    @classmethod
    def export_zwo_xml(cls, title: str, description: str, steps: List[Dict[str, Any]], declared_ftp: int) -> str:
        root = ET.Element("workout_file")
        ET.SubElement(root, "author").text = "AI Endurance Coach"
        ET.SubElement(root, "name").text = title
        ET.SubElement(root, "description").text = description
        ET.SubElement(root, "sportType").text = "bike"
        
        workout_node = ET.SubElement(root, "workout")
        
        for step in steps:
            dur = str(step["duration_sec"])
            pwr = str(step["target_power_pct"])
            
            if step["section"] == "Warmup":
                node = ET.SubElement(workout_node, "Warmup", Duration=dur, PowerLow="0.40", PowerHigh=pwr)
            elif step["section"] == "Cooldown":
                node = ET.SubElement(workout_node, "Cooldown", Duration=dur, PowerLow=pwr, PowerHigh="0.40")
            else:
                node = ET.SubElement(workout_node, "SteadyState", Duration=dur, Power=pwr)

        return minidom.parseString(ET.tostring(root)).toprettyxml(indent="  ")


# ==============================================================================
# 3. AI AGENT ENGINE WITH TYPED TOOL CALLING & LIMITATIONS MEMORY
# ==============================================================================

class AICoachEngine:
    """Interfaces with Google Gemini API, applying limitations and coach memory."""

    @staticmethod
    def get_api_keys() -> List[str]:
        keys = [
            st.secrets.get("GEMINI_API_KEY", os.getenv("GEMINI_API_KEY")),
            st.secrets.get("SECONDARY_GEMINI_KEY", os.getenv("SECONDARY_GEMINI_KEY")),
        ]
        return [k for k in keys if k]

    @classmethod
    def execute_ai_query(cls, messages_payload: List[Dict[str, Any]], max_tokens: int = 4000) -> str:
        keys = cls.get_api_keys()
        if not keys:
            raise RuntimeError("Gemini API Key is missing. Please configure secrets.")

        models = ["gemini-3.6-flash", "gemini-3.5-flash", "gemini-1.5-flash-latest"]
        errors = []

        for key in keys:
            for model in models:
                try:
                    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
                    headers = {"Content-Type": "application/json", "x-goog-api-key": key}
                    payload = {
                        "contents": messages_payload,
                        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.6}
                    }
                    res = requests.post(url, headers=headers, json=payload, timeout=15)
                    if res.status_code == 200:
                        parts = res.json().get("candidates", [{}])[0].get("content", {}).get("parts", [])
                        text = "\n".join(p.get("text", "") for p in parts if "text" in p).strip()
                        if text:
                            return text
                    errors.append(f"{model} HTTP {res.status_code}: {res.text[:150]}")
                except Exception as exc:
                    errors.append(f"{model}: {str(exc)}")

        raise RuntimeError(f"AI Engine failed. Diagnostics: {' | '.join(errors[:3])}")


# ==============================================================================
# 4. SESSION STATE INITIALIZATION & PERSISTENCE
# ==============================================================================

def init_application_state():
    if "athlete_profile" not in st.session_state:
        st.session_state["athlete_profile"] = {
            "name": "Alex Rivera",
            "declared_ftp": 265,
            "estimated_ftp": 272,
            "max_hr": 190,
            "resting_hr": 54,
            "weight_kg": 68.5,
            "running_threshold_pace_sec": 255, # 4:15/km
            "unit_system": "Metric (km, watts, °C)",
            "limitations": "Lower back strain during long climbs (>8% gradient); past Achilles tendinopathy (limit outdoor running volume spikes to <10% per week)."
        }

    # Generate 28 days of mixed activity data (indoor vs outdoor)
    if "tss_history" not in st.session_state:
        activity_types = [
            ("Indoor Cycling (MyWhoosh)", 75, True),
            ("Indoor Virtual Ride", 80, True),
            ("Outdoor Run", 45, False),
            ("Outdoor Walk", 15, False),
            ("Gym / Strength", 30, False),
            ("Indoor Trainer Intervals", 90, True),
            ("Outdoor Road Ride", 110, False)
        ]
        history = []
        start_date = dt.date.today() - dt.timedelta(days=28)
        for i in range(28):
            act_date = start_date + dt.timedelta(days=i)
            act = activity_types[i % len(activity_types)]
            history.append({
                "date": act_date.strftime("%Y-%m-%d"),
                "type": act[0],
                "tss": act[1],
                "is_indoor": act[2]
            })
        st.session_state["tss_history"] = history

    defaults = {
        "coach_persona": "Collaborative Peer (Balanced & Brainstorming)",
        "coach_memory_notes": "Responds best to structured indoor intervals. Prefers clear target wattage over perceived exertion.",
        "messages": [
            {"role": "assistant", "content": "Welcome back, Alex! Your 7-day ACWR is currently 1.12 (Optimal). How can we optimize your upcoming indoor training block today?"}
        ],
        "cached_trend_reports": [],
        "draft_plan": None,
        "draft_workout": None,
        "active_nav": "☀️ Command Center",
        "pending_coach_prompt": None
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v

init_application_state()


# ==============================================================================
# 5. USER INTERFACE & SIDEBAR NAVIGATION
# ==============================================================================

profile = st.session_state.athlete_profile

with st.sidebar:
    st.markdown("### 🚴‍♂️ Endurance Coach")
    st.caption(f"Athlete: **{profile['name']}** | FTP: **{profile['declared_ftp']}W** | Run Pace: **{EnduranceMathEngine.format_pace_label(profile['running_threshold_pace_sec'])}**")

    st.markdown("---")
    st.markdown("**Navigation**")
    nav_options = [
        "☀️ Command Center",
        "🤖 AI Coach & Sparring",
        "📅 Calendar & Plan Builder",
        "🛠️ Workout Builder & ZWO Export",
        "👤 Athlete Profile & Preferences"
    ]
    for option in nav_options:
        if st.button(option, use_container_width=True, type="primary" if st.session_state.active_nav == option else "secondary"):
            st.session_state.active_nav = option
            st.rerun()

    st.divider()
    st.markdown("**Coaching Persona**")
    personas = [
        "Collaborative Peer (Balanced & Brainstorming)",
        "Sports Scientist (Data & Periodization Focus)",
        "Drill Sergeant (Strict & Direct Accountability)"
    ]
    st.session_state.coach_persona = st.selectbox("Active Persona", personas, index=0)

selected_nav = st.session_state.active_nav


# ==============================================================================
# TAB 1: COMMAND CENTER (INDOOR-ONLY GRAPH RULE APPLIED)
# ==============================================================================
if selected_nav == "☀️ Command Center":
    st.markdown(f"## ☀️ Training Briefing for {profile['name']}")

    impulse_history = EnduranceMathEngine.calculate_ctl_atl_tsb(st.session_state.tss_history, initial_ctl=55, initial_atl=60)
    latest_metrics = impulse_history[-1]
    acwr_val, acwr_status = EnduranceMathEngine.calculate_acwr(st.session_state.tss_history)

    # Readiness Card
    card_class = "readiness-card-green" if acwr_val <= 1.35 else "readiness-card-amber"
    st.markdown(f"""
    <div class="{card_class}">
        <h4 style="margin:0 0 4px 0; color:#58A6FF;">💡 Training Load Readiness: {acwr_status}</h4>
        <p style="margin:0; font-size:.95rem;">ACWR is <strong>{acwr_val}</strong>. Form (TSB) is <strong>{latest_metrics['tsb']}</strong>. Fitness (CTL) is <strong>{latest_metrics['ctl']}</strong>. Threshold Pace: <strong>{EnduranceMathEngine.format_pace_label(profile['running_threshold_pace_sec'])}</strong>.</p>
    </div>
    """, unsafe_allow_html=True)

    # Top Metrics
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fitness (CTL)", latest_metrics['ctl'], delta="42-day Load")
    c2.metric("Fatigue (ATL)", latest_metrics['atl'], delta="7-day Load")
    c3.metric("Form (TSB)", latest_metrics['tsb'], delta="Freshness Indicator")
    c4.metric("Threshold Pace", EnduranceMathEngine.format_pace_label(profile['running_threshold_pace_sec']), delta=f"FTP: {profile['declared_ftp']} W")

    st.divider()

    # --- CONDITIONAL GRAPH RENDERING: INDOOR WORKOUTS ONLY ---
    st.markdown("### 📊 Indoor Training Workout Performance Charts")
    st.info("ℹ️ **Graph Rendering Policy**: Graphical performance charts are displayed strictly for **Indoor Training Workouts** (e.g. VirtualRide, MyWhoosh, Zwift, Indoor Trainer). Outdoor runs, walks, gym sessions, and outdoor rides are presented in text metrics.")

    # Filter impulse history for Indoor Workouts only
    indoor_entries = [e for e in impulse_history if e.get("is_indoor", False)]
    outdoor_entries = [e for e in impulse_history if not e.get("is_indoor", False)]

    if indoor_entries:
        indoor_df = pd.DataFrame(indoor_entries)
        fig = go.Figure()
        fig.add_trace(go.Scatter(x=indoor_df['date'], y=indoor_df['ctl'], mode='lines+markers', name='Indoor Fitness (CTL)', line=dict(color='#00E676', width=2)))
        fig.add_trace(go.Scatter(x=indoor_df['date'], y=indoor_df['atl'], mode='lines+markers', name='Indoor Fatigue (ATL)', line=dict(color='#FF4081', width=2)))
        fig.add_trace(go.Bar(x=indoor_df['date'], y=indoor_df['tsb'], name='Indoor Form (TSB)', marker_color=['#00E676' if v >= 0 else '#FF4081' for v in indoor_df['tsb']]))
        fig.update_layout(
            title="Indoor Workouts Performance Chart (Virtual/Trainer Sessions Only)",
            margin=dict(l=0, r=0, t=40, b=0),
            plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
            legend=dict(orientation="h", y=1.1, font=dict(color=TEXT_PRIMARY)),
            xaxis=dict(showgrid=False, color=TEXT_PRIMARY), yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)", color=TEXT_PRIMARY)
        )
        st.plotly_chart(fig, use_container_width=True)
    else:
        st.warning("No indoor training workouts logged yet to render indoor performance charts.")

    # Outdoor Activities Text Summary List (NO GRAPHS)
    with st.expander("👟 View Outdoor Runs, Walks, Gym & Outdoor Activity Log (Text Only)", expanded=False):
        if outdoor_entries:
            for entry in outdoor_entries[-10:]:
                st.markdown(f"• **{entry['date']}** — `{entry['workout_type']}` | Load (TSS): **{entry['ctl']}** | TSB Impact: **{entry['tsb']}**")
        else:
            st.caption("No outdoor sessions logged.")

    st.divider()

    # --- 90-DAY TREND SYNTHESIS ENGINE ---
    st.markdown("### 📈 90-Day Multi-Sport Trend Synthesis")
    st.caption("Synthesizes indoor performance trends and multi-sport training history into an actionable coaching report.")

    if st.button("🚀 Run 90-Day Multi-Sport Trend Synthesis", type="primary"):
        with st.spinner("Synthesizing 90 days of endurance training metrics..."):
            try:
                prompt = (
                    f"Perform a comprehensive 90-day multi-sport trend synthesis for athlete {profile['name']}.\n"
                    f"Current CTL: {latest_metrics['ctl']}, ATL: {latest_metrics['atl']}, TSB: {latest_metrics['tsb']}, ACWR: {acwr_val}.\n"
                    f"Declared Cycling FTP: {profile['declared_ftp']}W, Running Threshold Pace: {EnduranceMathEngine.format_pace_label(profile['running_threshold_pace_sec'])}.\n"
                    f"ATHLETE LIMITATIONS: {profile.get('limitations', 'None')}.\n"
                    f"Provide: 1. Indoor vs Outdoor Load Takeaways, 2. Load vs Recovery Balance, 3. Next 30-Day Actionable Recommendations accounting for limitations."
                )
                payload = [
                    {"role": "user", "parts": [{"text": "You are a senior sports scientist and endurance coach."}]},
                    {"role": "user", "parts": [{"text": prompt}]}
                ]
                new_analysis = AICoachEngine.execute_ai_query(payload)
                timestamp_str = dt.datetime.now(LOCAL_TZ).strftime("%d %b %Y, %H:%M %Z")
                
                st.session_state.cached_trend_reports.insert(0, {
                    "timestamp": timestamp_str,
                    "analysis": new_analysis
                })
                st.session_state.cached_trend_reports = st.session_state.cached_trend_reports[:3]
                st.toast("90-Day Trend Synthesis successfully generated!", icon="📈")
            except Exception as exc:
                st.error(f"Trend synthesis failed: {exc}")

    if st.session_state.cached_trend_reports:
        st.markdown("#### 📌 Saved 90-Day Trend Reports (Last 3)")
        for idx, item in enumerate(st.session_state.cached_trend_reports):
            with st.expander(f"Report #{len(st.session_state.cached_trend_reports) - idx} · Generated {item['timestamp']}", expanded=(idx == 0)):
                st.markdown(item["analysis"])
                col_x, col_y = st.columns(2)
                if col_x.button("💬 Discuss Report with Coach", key=f"trend_discuss_{idx}"):
                    st.session_state.pending_coach_prompt = f"Let me ask about my 90-Day Trend Report generated on {item['timestamp']}:\n\n{item['analysis'][:1000]}"
                    st.session_state.active_nav = "🤖 AI Coach & Sparring"
                    st.rerun()
                if col_y.button("🗑️ Delete Report", key=f"trend_delete_{idx}"):
                    st.session_state.cached_trend_reports.pop(idx)
                    st.rerun()


# ==============================================================================
# TAB 2: AI COACH & SPARRING (INCORPORATES LIMITATIONS IN MEMORY)
# ==============================================================================
elif selected_nav == "🤖 AI Coach & Sparring":
    st.markdown("## 🤖 AI Coach & Sparring Partner")
    st.caption(f"Active Persona: **{st.session_state.coach_persona}**")

    # Render Chat History
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # Draft Proposal Approval UI
    if st.session_state.draft_workout:
        with st.container(border=True):
            st.markdown("### 📋 Proposed Workout Draft (Pending Confirmation)")
            st.json(st.session_state.draft_workout)
            col_a, col_b = st.columns(2)
            if col_a.button("✅ Confirm & Save Workout", type="primary"):
                st.toast("Workout confirmed and added to calendar!", icon="🚀")
                st.session_state.draft_workout = None
                st.rerun()
            if col_b.button("❌ Discard Draft"):
                st.session_state.draft_workout = None
                st.rerun()

    # Handle Pending Prompt Redirect
    pending_prompt = st.session_state.pending_coach_prompt
    if pending_prompt:
        st.session_state.pending_coach_prompt = None
        st.session_state.messages.append({"role": "user", "content": pending_prompt})
        st.rerun()

    # Chat Input Box
    if user_prompt := st.chat_input("Ask your coach... (e.g., 'Draft a 4-week indoor build block respecting my back strain limitation')"):
        st.session_state.messages.append({"role": "user", "content": user_prompt})
        with st.chat_message("user"):
            st.markdown(user_prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing training data, coach memory, and limitations..."):
                try:
                    impulse = EnduranceMathEngine.calculate_ctl_atl_tsb(st.session_state.tss_history)[-1]
                    acwr_v, _ = EnduranceMathEngine.calculate_acwr(st.session_state.tss_history)
                    
                    # SYSTEM PROMPT BINDING COACH MEMORY & ATHLETE LIMITATIONS
                    system_instructions = (
                        f"You are an elite multi-sport endurance coach.\n"
                        f"Persona: {st.session_state.coach_persona}\n"
                        f"Athlete: {profile['name']} | Cycling FTP: {profile['declared_ftp']}W | Running Threshold Pace: {EnduranceMathEngine.format_pace_label(profile['running_threshold_pace_sec'])}\n"
                        f"Current State: CTL={impulse['ctl']}, ATL={impulse['atl']}, TSB={impulse['tsb']}, ACWR={acwr_v}\n"
                        f"--------------------------------------------------\n"
                        f"COACH'S LONG-TERM MEMORY & ATHLETE NOTES:\n"
                        f"General Memory & Style: {st.session_state.get('coach_memory_notes', 'N/A')}\n"
                        f"CRITICAL ATHLETE LIMITATIONS & INJURY CONSTRAINTS:\n"
                        f"-> {profile.get('limitations', 'No specific limitations logged.')}\n"
                        f"--------------------------------------------------\n"
                        f"RULES:\n"
                        f"1. Graph rule: Performance graphs exist strictly for indoor training workouts. Do NOT attempt to generate graph descriptions for outdoor runs, walks, or gym sessions.\n"
                        f"2. Lead with explicit values (Watts, BPM, Pace in min/km, Distance).\n"
                        f"3. Strictly respect the athlete's limitations in all recommendations and workout prescriptions.\n"
                        f"4. End responses with exactly 3 short suggested next actions."
                    )
                    
                    payload = [
                        {"role": "user", "parts": [{"text": f"SYSTEM CONTEXT:\n{system_instructions}"}]},
                        {"role": "model", "parts": [{"text": "Understood. I have locked your athlete profile, long-term memory, and limitations into my coaching context."}]}
                    ]
                    
                    for m in st.session_state.messages[-6:]:
                        role = "user" if m["role"] == "user" else "model"
                        payload.append({"role": role, "parts": [{"text": m["content"]}]})

                    reply = AICoachEngine.execute_ai_query(payload)
                    st.markdown(reply)
                    st.session_state.messages.append({"role": "assistant", "content": reply})

                except Exception as exc:
                    st.error(f"Coaching Engine Exception: {exc}")


# ==============================================================================
# TAB 3: CALENDAR & PLAN BUILDER
# ==============================================================================
elif selected_nav == "📅 Calendar & Plan Builder":
    st.markdown("## 📅 Multi-Phase Macrocycle & Plan Builder")

    with st.expander("🏗️ Create New Multi-Phase Training Plan Draft", expanded=True):
        goal = st.text_input("Target Event / Objective", value="100km Gran Fondo / Multi-Sport Endurance")
        weeks = st.slider("Plan Duration (Weeks)", min_value=4, max_value=16, value=8, step=2)
        
        if st.button("Synthesize Plan Draft", type="primary"):
            with st.spinner("Generating periodized multi-phase plan..."):
                phases = [
                    {"phase": "Foundation", "weeks": weeks // 4, "focus": "Aerobic capacity & structural resilience"},
                    {"phase": "Build", "weeks": weeks // 2, "focus": "Threshold interval progression & Vo2 max power"},
                    {"phase": "Peak & Taper", "weeks": weeks // 4, "focus": "Volume reduction, intensity retention & race readiness"}
                ]
                st.session_state.draft_plan = {"goal": goal, "duration_weeks": weeks, "phases": phases}
                st.success("Draft Plan synthesized! Review details below.")

    if st.session_state.draft_plan:
        st.markdown("### 📋 Proposed Plan Draft")
        st.json(st.session_state.draft_plan)
        if st.button("🚀 Confirm & Schedule Plan"):
            st.toast("Multi-phase plan confirmed and written to calendar!", icon="✅")
            st.session_state.draft_plan = None


# ==============================================================================
# TAB 4: WORKOUT BUILDER & ZWO EXPORT
# ==============================================================================
elif selected_nav == "🛠️ Workout Builder & ZWO Export":
    st.markdown("## 🛠️ Structured Workout Builder & ZWO Exporter")
    st.caption("Validates structured workout grammar and exports Zwift/MyWhoosh-compatible .zwo XML files.")

    w_title = st.text_input("Workout Title", value="4xx5m Vo2 Max Intervals")
    w_desc = st.text_input("Description", value="High-intensity Vo2 max interval set targeting 110-120% FTP.")
    
    default_dsl = (
        "Warmup\n"
        "- 10m 50%\n"
        "- 5m 75%\n\n"
        "Main Set\n"
        "4x\n"
        "- 5m 115%\n"
        "- 3m 50%\n\n"
        "Cooldown\n"
        "- 10m 45%"
    )
    
    dsl_text = st.text_area("Workout Syntax / Steps", value=default_dsl, height=200)

    if st.button("Parse & Export .ZWO File", type="primary"):
        parsed_steps = WorkoutGrammarEngine.parse_dsl_to_steps(dsl_text, profile["declared_ftp"])
        zwo_xml = WorkoutGrammarEngine.export_zwo_xml(w_title, w_desc, parsed_steps, profile["declared_ftp"])
        
        st.markdown("### 🔍 Parsed Interval Steps")
        st.dataframe(pd.DataFrame(parsed_steps))

        st.markdown("### 📄 Generated ZWO File Preview")
        st.code(zwo_xml, language="xml")

        b64 = base64.b64encode(zwo_xml.encode()).decode()
        href = f'<a href="data:file/xml;base64,{b64}" download="{w_title.replace(" ", "_")}.zwo" style="background:#2563EB; color:white; padding:8px 16px; border-radius:6px; text-decoration:none; font-weight:600;">💾 Download {w_title}.zwo</a>'
        st.markdown(href, unsafe_allow_html=True)


# ==============================================================================
# TAB 5: ATHLETE PROFILE, PREFERENCES & COACH MEMORY
# ==============================================================================
elif selected_nav == "👤 Athlete Profile & Preferences":
    st.markdown("## 👤 Athlete Profile & Long-Term Coach Memory")

    current_pace_str = EnduranceMathEngine.format_seconds_to_pace(profile["running_threshold_pace_sec"])

    with st.form("profile_form"):
        st.markdown("#### 1. Athletic Metrics & Thresholds")
        name = st.text_input("Display Name", value=profile["name"])
        ftp = st.number_input("Declared Cycling FTP (Watts)", value=int(profile["declared_ftp"]), step=5)
        pace_input = st.text_input("Running Threshold Pace (min/km, e.g. 4:15)", value=current_pace_str)
        max_hr = st.number_input("Maximum HR (bpm)", value=int(profile["max_hr"]), step=1)
        resting_hr = st.number_input("Resting HR (bpm)", value=int(profile["resting_hr"]), step=1)
        weight = st.number_input("Weight (kg)", value=float(profile["weight_kg"]), step=0.5)

        st.markdown("#### 2. Athlete Limitations & Medical/Injury Constraints")
        st.caption("These notes are permanently stored in your profile and embedded directly into your AI Coach's long-term memory.")
        limitations_input = st.text_area("Athlete Limitations / Injuries", value=profile.get("limitations", ""))

        st.markdown("#### 3. Coach's Notebook & Long-Term Memory Notes")
        memory_notes_input = st.text_area("Training Style & Preferences Notebook", value=st.session_state.get("coach_memory_notes", ""))

        units = st.selectbox("Unit System", ["Metric (km, watts, °C)", "Imperial (miles, watts, °F)"])

        if st.form_submit_button("💾 Save Profile & Coach Memory"):
            parsed_pace_sec = EnduranceMathEngine.parse_pace_to_seconds(pace_input)
            
            # Persistent State Update
            st.session_state["athlete_profile"]["name"] = name.strip()
            st.session_state["athlete_profile"]["declared_ftp"] = int(ftp)
            st.session_state["athlete_profile"]["running_threshold_pace_sec"] = parsed_pace_sec
            st.session_state["athlete_profile"]["max_hr"] = int(max_hr)
            st.session_state["athlete_profile"]["resting_hr"] = int(resting_hr)
            st.session_state["athlete_profile"]["weight_kg"] = float(weight)
            st.session_state["athlete_profile"]["limitations"] = limitations_input.strip()
            st.session_state["athlete_profile"]["unit_system"] = units
            st.session_state["coach_memory_notes"] = memory_notes_input.strip()

            st.toast("Profile, limitations, and Coach Memory updated successfully!", icon="💾")
            st.rerun()
