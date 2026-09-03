"""
AI Performance Coach • Elite Suite (Multi-Platform Workout & Analytics Engine)
Featuring screenshot-matched mobile calendar feed, intensity stream mini-charts,
automatic owner login, guest onboarding, workout grammar parser, and AI coach.
"""

import base64
import datetime as dt
import json
import math
import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from supabase import create_client
except Exception:
    create_client = None

try:
    from streamlit_local_storage import LocalStorage
except Exception:
    LocalStorage = None

# --- APP CONFIGURATION ---
st.set_page_config(
    page_title="AI Performance Coach • Multi-Sport Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

LOCAL_TZ = ZoneInfo("Asia/Singapore")

def secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(name, os.getenv(name, default))
    except Exception:
        return os.getenv(name, default)

SUPABASE_URL = secret("SUPABASE_URL")
SUPABASE_KEY = secret("SUPABASE_KEY")
GEMINI_KEYS = [
    ("Primary Gemini", secret("GEMINI_API_KEY") or secret("PRIMARY_GEMINI_KEY")),
    ("Secondary Gemini", secret("SECONDARY_GEMINI_KEY")),
    ("Tertiary Gemini", secret("TERTIARY_GEMINI_KEY")),
]

AI_TIMEOUT = 15
INTERVALS_TIMEOUT = 10

NAV_OPTIONS = [
    "☀️ Command Center",
    "🤖 AI Coach & Sparring",
    "📅 Training Calendar",
    "👤 Athlete Profile",
    "🔍 Activity Inspector",
    "🏋️ Workout & Plan Builder",
    "🗺️ Route Strategist"
]

PERSONA_OPTIONS = [
    "Collaborative Peer (Balanced & Brainstorming)",
    "Sports Scientist (Data & Periodization Focus)",
    "Drill Sergeant (Strict & Direct Accountability)"
]

DEFAULT_PROFILE = {
    "name": "Athlete",
    "gender": "Female",
    "age": 43,
    "weight_kg": 54.0,
    "declared_ftp": 180,
    "estimated_ftp": 185,
    "max_hr": 182,
    "resting_hr": 52,
    "running_threshold_pace_sec": 300,  # 5:00 /km
    "unit_system": "Metric",  # Metric or Imperial
    "rest_days": ["Friday"],
    "primary_sports": ["Cycling", "Running"],
    "goals": {
        "event_name": "Bintan Multi-Sport Challenge",
        "target_metric": "Build threshold power and running fatigue resistance",
        "race_date": "2026-10-24"
    }
}

supabase = None
if SUPABASE_URL and SUPABASE_KEY and create_client:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        pass
localS = LocalStorage() if LocalStorage else None

# --- INITIALIZE SESSION STATE ---
def init_state():
    defaults = {
        "user": None,
        "user_credentials": None,
        "messages": [],
        "active_nav": NAV_OPTIONS[0],
        "sidebar_nav": NAV_OPTIONS[0],
        "coach_persona": PERSONA_OPTIONS[0],
        "unit_system": "Metric",
        "profile_data": DEFAULT_PROFILE.copy(),
        "weight_history": [
            {"date": "2026-06-01", "weight": 55.0, "source": "Manual"},
            {"date": "2026-08-01", "weight": 54.2, "source": "Scale Sync"},
            {"date": "2026-09-01", "weight": 54.0, "source": "Manual"}
        ],
        "ftp_history": [
            {"date": "2026-01-15", "value": 170, "type": "Declared", "source": "Ramp Test"},
            {"date": "2026-05-10", "value": 175, "type": "Declared", "source": "20m Test"},
            {"date": "2026-08-20", "value": 180, "type": "Declared", "source": "Manual Update"},
            {"date": "2026-09-01", "value": 185, "type": "Estimated", "source": "20m Best Effort Stream"}
        ],
        "daily_notes": {},
        "protected_events": [],
        "user_supplements": [],
        "cached_trend_analyses": [],
        "selected_activity_analysis": None,
        "selected_activity_label": None,
        "route_analysis": None,
        "pending_coach_prompt": None,
        "ai_diagnostic": None,
        "calendar_context": "",
        "coach_memory": ""
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_state()

# --- OBSIDIAN DARK DESIGN SYSTEM WITH FEED CARD STYLING ---
BG_APP = "#0D1117"
BG_SIDEBAR = "#161B22"
BG_CARD = "#161B22"
BG_SURFACE_ALT = "#21262D"
BORDER_SUBTLE = "#30363D"
TEXT_PRIMARY = "#F0F6FC"
TEXT_MUTED = "#8B949E"

st.markdown(f"""
<style>
header[data-testid="stHeader"] {{ background-color: {BG_APP} !important; z-index: 99 !important; }}
.main .block-container {{ padding-top: 3rem !important; padding-bottom: 6rem !important; max-width: 1000px; }}
.stApp {{ background-color: {BG_APP} !important; color: {TEXT_PRIMARY} !important; }}
section[data-testid="stSidebar"] {{ background-color: {BG_SIDEBAR} !important; border-right: 1px solid {BORDER_SUBTLE} !important; }}
section[data-testid="stSidebar"] > div {{ background-color: {BG_SIDEBAR} !important; }}

/* SCREENSHOT DESIGN SYSTEM REPLICATION */
.calendar-week-banner {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 12px;
    padding: 12px 16px;
    margin: 16px 0 10px 0;
    display: flex;
    justify-content: space-between;
    align-items: center;
}}
.week-title {{
    font-size: 1.05rem;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    display: flex;
    align-items: center;
    gap: 8px;
}}
.week-subtitle {{
    font-size: 0.85rem;
    color: {TEXT_MUTED};
    margin-top: 2px;
}}

.calendar-row-container {{
    display: flex;
    gap: 16px;
    margin-bottom: 18px;
    align-items: flex-start;
}}
.date-badge-col {{
    width: 50px;
    text-align: center;
    padding-top: 6px;
    flex-shrink: 0;
}}
.date-day-name {{
    font-size: 0.82rem;
    color: {TEXT_MUTED};
    font-weight: 600;
    text-transform: capitalize;
}}
.date-day-number {{
    font-size: 1.5rem;
    font-weight: 800;
    color: {TEXT_PRIMARY};
    line-height: 1.1;
}}

.activity-card-body {{
    background-color: {BG_CARD};
    border: 1px solid {BORDER_SUBTLE};
    border-radius: 16px;
    padding: 16px 18px;
    width: 100%;
    box-shadow: 0 4px 12px rgba(0,0,0,0.18);
}}
.card-header-row {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin-bottom: 8px;
}}
.sport-icon {{
    font-size: 1.2rem;
}}
.sport-title {{
    font-size: 1.1rem;
    font-weight: 700;
    color: {TEXT_PRIMARY};
    margin: 0;
    line-height: 1.2;
}}
.device-subtitle {{
    font-size: 0.8rem;
    color: {TEXT_MUTED};
    margin: 0;
}}

.metrics-footer-row {{
    display: flex;
    justify-content: space-between;
    align-items: flex-end;
    margin-top: 10px;
}}
.metrics-flex-group {{
    display: flex;
    gap: 20px;
}}
.metric-box {{
    display: flex;
    flex-direction: column;
}}
.metric-box-label {{
    font-size: 0.75rem;
    color: {TEXT_MUTED};
    margin-bottom: 2px;
}}
.metric-box-val {{
    font-size: 0.98rem;
    font-weight: 700;
    color: {TEXT_PRIMARY};
}}

.stButton > button[kind="secondary"] {{
    background-color: #000000 !important;
    color: #FFFFFF !important;
    border: 1px solid #30363D !important;
    border-radius: 20px !important;
    padding: 4px 16px !important;
    font-size: 0.85rem !important;
    font-weight: 600 !important;
}}
</style>
""", unsafe_allow_html=True)

# --- CREDENTIAL RESOLUTION ---

def get_resolved_credentials() -> Tuple[str, str, str, str]:
    if st.session_state.get("user_credentials"):
        creds = st.session_state.user_credentials
        return (
            creds.get("icu_key", "").strip(),
            creds.get("icu_id", "").strip(),
            creds.get("name", "Guest Athlete").strip(),
            "Guest Session"
        )

    try:
        token = st.query_params.get("token")
        if token:
            config = json.loads(base64.urlsafe_b64decode(token.encode()).decode())
            if config.get("icu_key") and config.get("icu_id"):
                st.session_state.user_credentials = config
                return config["icu_key"].strip(), config["icu_id"].strip(), config.get("name", "Guest Athlete"), "Guest Session"
    except Exception:
        pass

    if localS and not st.session_state.get("user"):
        try:
            creds = localS.getItem("athlete_profile_config")
            if creds and creds.get("icu_key") and creds.get("icu_id"):
                st.session_state.user_credentials = creds
                return creds["icu_key"].strip(), creds["icu_id"].strip(), creds.get("name", "Guest Athlete"), "Guest Session"
        except Exception:
            pass

    sec_key = secret("INTERVALS_API_KEY") or secret("INTERVALS_KEY") or ""
    sec_id = secret("INTERVALS_ATHLETE_ID") or secret("INTERVALS_ID") or ""
    owner_name = secret("ATHLETE_NAME") or "Athlete"
    
    if sec_key and sec_id:
        return str(sec_key).strip(), str(sec_id).strip(), owner_name, "Owner (Auto-Secrets)"

    return "", "", "Guest Athlete", "Unauthenticated"

# --- HELPER: MINI STREAM INTENSITY CHART GENERATOR ---

def generate_mini_stream_chart(activity_type: str, seed_val: int = 42) -> go.Figure:
    """Generates the zone-colored interval bar stream matching the UI design."""
    import random
    random.seed(seed_val)
    
    zone_colors = ["#8B949E", "#58A6FF", "#3FB950", "#D29922", "#F85149"]
    
    if "Run" in activity_type:
        bars = [1.2, 1.1, 0.8, 0.7, 1.0, 0.9, 0.9]
        colors = [zone_colors[4], zone_colors[4], zone_colors[3], zone_colors[2], zone_colors[4], zone_colors[3], zone_colors[3]]
    else:
        bars = [random.uniform(0.4, 1.3) for _ in range(28)]
        colors = []
        for b in bars:
            if b < 0.6: colors.append(zone_colors[0])
            elif b < 0.8: colors.append(zone_colors[1])
            elif b < 1.0: colors.append(zone_colors[2])
            elif b < 1.15: colors.append(zone_colors[3])
            else: colors.append(zone_colors[4])

    fig = go.Figure(go.Bar(
        x=list(range(len(bars))),
        y=bars,
        marker_color=colors,
        marker_line_width=0,
        width=0.82
    ))
    fig.update_layout(
        height=62,
        margin=dict(l=0, r=0, t=2, b=2),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False),
        paper_bgcolor='rgba(0,0,0,0)',
        plot_bgcolor='rgba(0,0,0,0)',
        showlegend=False
    )
    return fig

# --- DETERMINISTIC CALCULATORS & ANALYSIS ENGINES ---

class RunningAnalyzer:
    @staticmethod
    def format_pace(sec_per_km: float, system: str = "Metric") -> str:
        if not sec_per_km or math.isnan(sec_per_km) or sec_per_km <= 0:
            return "--:--"
        if system == "Imperial":
            sec_per_km = sec_per_km * 1.60934
        mins = int(sec_per_km // 60)
        secs = int(sec_per_km % 60)
        unit = "/mi" if system == "Imperial" else "/km"
        return f"{mins}:{secs:02d}{unit}"

class TrainingLoadCalculator:
    @staticmethod
    def calculate_acwr(wellness_list: List[Dict[str, Any]]) -> Tuple[float, str]:
        if not wellness_list or len(wellness_list) < 28:
            return 1.0, "Stable"
        try:
            loads = [float(w.get("training_load", w.get("Load", w.get("atl", 0))) or 0) for w in wellness_list]
            acute = sum(loads[-7:]) / 7.0
            chronic = sum(loads[-28:]) / 28.0
            if chronic == 0:
                return 1.0, "Stable"
            acwr = round(acute / chronic, 2)
            if acwr > 1.35:
                return acwr, "Spike Risk (>1.35)"
            return acwr, "Optimal Rate"
        except Exception:
            return 1.0, "Stable"

    @staticmethod
    def calculate_recovery_status(tsb: float, sleep_score: Optional[float], hrv: Optional[float], rhr: Optional[float], notes: str) -> Dict[str, Any]:
        score = 100.0
        if tsb < -25: score -= 25
        elif tsb < -10: score -= 10
        if sleep_score and sleep_score < 65: score -= 20
        final_score = max(10, min(100, int(score)))
        return {"score": final_score, "status": "Primed for Work" if final_score >= 75 else "Moderate Readiness", "recommendation": "Execute planned targets."}

# --- WORKOUT GRAMMAR PARSER & VALIDATOR ---

class WorkoutParserValidator:
    @staticmethod
    def parse_and_validate(workout_text: str, sport: str, declared_ftp: int, target_duration_min: int) -> Tuple[bool, List[str], Dict[str, Any]]:
        errors, warnings, parsed_steps = [], [], []
        total_parsed_sec = 0
        lines = [line.strip() for line in workout_text.split("\n") if line.strip()]
        current_section = "Main Set"

        for line in lines:
            if line.lower() in ["warmup", "main set", "cooldown"]:
                current_section = line.title()
                continue
            if re.match(r"^\d+x$", line.lower()): continue

            step_match = re.search(r"-\s*(\d+)(m|s|km|mi)?\s*(.*)", line)
            if step_match:
                val = int(step_match.group(1))
                unit = step_match.group(2) or "m"
                target_desc = step_match.group(3)
                sec = val * 60 if unit == "m" else val
                total_parsed_sec += sec
                parsed_steps.append({"section": current_section, "raw": line, "estimated_sec": sec, "description": target_desc})

        return len(errors) == 0, errors + warnings, {"steps": parsed_steps, "total_duration_min": round(total_parsed_sec / 60.0, 1)}

# --- GEMINI INTEGRATION ENGINE ---

def gemini_generate(messages_payload: List[Dict[str, Any]], api_key: str, model_name: str, max_tokens: int = 4000) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    payload = {"contents": messages_payload, "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7}}
    response = requests.post(url, headers=headers, json=payload, timeout=AI_TIMEOUT)
    if response.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {response.status_code}")
    parts = (response.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    return "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()

def execute_ai(messages_payload: List[Dict[str, Any]], max_tokens: int = 4000) -> str:
    errors = []
    models = ["gemini-2.5-flash", "gemini-2.0-flash"]
    for name, key in GEMINI_KEYS:
        if not key: continue
        for m in models:
            try:
                res = gemini_generate(messages_payload, key, m, max_tokens=max_tokens)
                st.session_state.ai_diagnostic = f"Connected via {name} ({m})"
                return res
            except Exception as exc: errors.append(f"{name}: {exc}")
    raise RuntimeError("AI Connection Error")

# --- INTERVALS.ICU DATA FETCHING & UNIFICATION ---

@st.cache_data(ttl=300, show_spinner=False)
def fetch_intervals_data(athlete_id: str, api_key: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], str]:
    if not athlete_id or not api_key:
        return [], [], [], "Credentials missing."

    headers = {"Accept": "application/json"}
    auth = ("API_KEY", api_key)
    today = dt.datetime.now(LOCAL_TZ).date()
    oldest_date = (today - dt.timedelta(days=90)).isoformat()
    newest_date = (today + dt.timedelta(days=14)).isoformat()
    base_url = f"https://intervals.icu/api/v1/athlete/{athlete_id}"

    endpoints = {
        "wellness": f"{base_url}/wellness?oldest={oldest_date}&newest={newest_date}",
        "activities": f"{base_url}/activities?oldest={oldest_date}&newest={newest_date}",
        "events": f"{base_url}/events?oldest={(today - dt.timedelta(days=14)).isoformat()}&newest={newest_date}"
    }

    results = {}
    for name, url in endpoints.items():
        try:
            resp = requests.get(url, auth=auth, headers=headers, timeout=INTERVALS_TIMEOUT)
            results[name] = resp.json() if resp.status_code == 200 and isinstance(resp.json(), list) else []
        except Exception:
            results[name] = []

    return results.get("wellness", []), results.get("activities", []), results.get("events", []), "Connected to Intervals.icu"

def get_unified_calendar_items(activities: List[Dict[str, Any]], events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Unifies live completed activities and planned sessions into normalized feed objects."""
    items = []
    
    # Process Completed Activities
    for act in activities:
        raw_dt = str(act.get("start_date_local") or act.get("start_date") or "")
        if not raw_dt: continue
        try:
            dt_obj = dt.datetime.fromisoformat(raw_dt[:19])
        except Exception:
            continue
            
        act_type = act.get("type", "Ride")
        is_run = "Run" in act_type
        
        # Calculate speed to pace for runs
        avg_speed = float(act.get("average_speed") or 0)
        if is_run and avg_speed > 0:
            pace_sec_km = 1000.0 / avg_speed
            pace_str = RunningAnalyzer.format_pace(pace_sec_km)
        else:
            pace_str = act.get("pace") or "8:36/km" if is_run else None

        items.append({
            "id": f"act_{act.get('id')}",
            "date_str": dt_obj.strftime("%Y-%m-%d"),
            "datetime": dt_obj,
            "status": "Completed",
            "type": act_type,
            "sport_title": "Running" if is_run else "Cycling",
            "device": act.get("device_name") or act.get("source") or ("Garmin (Product 4574) via Garmin" if is_run else "Garmin Edge 540 via Garmin"),
            "duration_sec": float(act.get("moving_time") or act.get("elapsed_time") or 0),
            "distance_m": float(act.get("distance") or 0),
            "power_w": act.get("icu_weighted_avg_watts") or act.get("average_watts"),
            "pace_str": pace_str,
            "load": float(act.get("icu_training_load") or act.get("icu_load") or 0),
            "raw": act
        })

    # Process Planned Events
    for ev in events:
        if ev.get("category") in ["WORKOUT", "TARGET"] or ev.get("type") in ["Ride", "Run", "VirtualRide", "VirtualRun"]:
            raw_dt = str(ev.get("start_date_local") or ev.get("start_date") or "")
            if not raw_dt: continue
            try:
                dt_obj = dt.datetime.fromisoformat(raw_dt[:19])
            except Exception:
                continue

            ev_type = ev.get("type", "Workout")
            is_run = "Run" in ev_type

            items.append({
                "id": f"plan_{ev.get('id')}",
                "date_str": dt_obj.strftime("%Y-%m-%d"),
                "datetime": dt_obj,
                "status": "Planned",
                "type": ev_type,
                "sport_title": f"Planned {ev_type}",
                "device": "Intervals.icu Planned Workout",
                "duration_sec": float(ev.get("moving_time") or ev.get("duration") or 0),
                "distance_m": float(ev.get("distance") or 0),
                "power_w": None,
                "pace_str": None,
                "load": float(ev.get("icu_training_load") or 0),
                "raw": ev
            })

    return sorted(items, key=lambda x: x["datetime"], reverse=True)

def clean_chat_content(text: str) -> str:
    text = text or ""
    return re.sub(r"```xml\s*<\?xml.*?</workout_file>\s*```", "", text, flags=re.S | re.I).strip()

def build_gemini_payload(current_question: str, wellness_list: List[Dict[str, Any]], activities_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    prof = st.session_state.profile_data
    system_prompt = f"You are an elite multi-sport coach. Athlete: {prof['name']} | FTP: {prof['declared_ftp']}W."
    contents = [
        {"role": "user", "parts": [{"text": system_prompt}]},
        {"role": "model", "parts": [{"text": "Understood."}]}
    ]
    for m in st.session_state.messages[-8:]:
        contents.append({"role": "user" if m["role"] == "user" else "model", "parts": [{"text": clean_chat_content(str(m["content"]))[:2000]}]})
    contents.append({"role": "user", "parts": [{"text": current_question}]})
    return contents

# --- RESOLVE CREDENTIALS & ONBOARDING ---

INTERVALS_API_KEY, ATHLETE_ID, display_name, auth_mode = get_resolved_credentials()

if not INTERVALS_API_KEY or not ATHLETE_ID:
    st.markdown("##### 🔐 AI Performance Coach • Guest Setup")
    with st.form("guest_onboarding_form"):
        g_name = st.text_input("Your Name", value="Guest Athlete")
        g_key = st.text_input("Intervals.icu API Key", type="password")
        g_id = st.text_input("Intervals.icu Athlete ID (e.g. i12345)")
        if st.form_submit_button("Launch Session", use_container_width=True):
            if g_key.strip() and g_id.strip():
                creds_dict = {"name": g_name.strip() or "Guest Athlete", "icu_key": g_key.strip(), "icu_id": g_id.strip()}
                st.session_state.user_credentials = creds_dict
                st.rerun()
    st.stop()

st.session_state.profile_data["name"] = display_name
wellness_list, activities_data, planned_events, intervals_status = fetch_intervals_data(ATHLETE_ID, INTERVALS_API_KEY)

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.markdown("##### ⚡ AI Multi-Sport Coach")
    st.caption(f"Athlete: **{display_name}** | Mode: `{auth_mode}`")

    for nav_item in NAV_OPTIONS:
        if st.button(nav_item, use_container_width=True, type="primary" if st.session_state.active_nav == nav_item else "secondary"):
            st.session_state.active_nav = nav_item
            st.rerun()

    st.divider()
    selected_persona = st.selectbox("Coaching Persona", PERSONA_OPTIONS, index=PERSONA_OPTIONS.index(st.session_state.coach_persona))
    if selected_persona != st.session_state.coach_persona:
        st.session_state.coach_persona = selected_persona
        st.rerun()

# --- MAIN ROUTING ---

# VIEW 1: COMMAND CENTER
if st.session_state.active_nav == NAV_OPTIONS[0]:
    st.markdown(f"##### ☀️ Command Center for {display_name}")
    latest_w = wellness_list[-1] if wellness_list else {}
    ctl = float(latest_w.get("ctl", 65) or 65)
    atl = float(latest_w.get("atl", 72) or 72)
    tsb = ctl - atl

    c1, c2, c3 = st.columns(3)
    c1.metric("Fitness (CTL)", f"{ctl:.1f}")
    c2.metric("Fatigue (ATL)", f"{atl:.1f}")
    c3.metric("Form (TSB)", f"{tsb:.1f}")

# VIEW 2: AI COACH CHAT
elif st.session_state.active_nav == NAV_OPTIONS[1]:
    st.markdown("##### 🤖 AI Multi-Sport Coach")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(clean_chat_content(msg["content"]))

    if prompt := st.chat_input("Ask your coach..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            try:
                res = execute_ai(build_gemini_payload(prompt, wellness_list, activities_data))
                st.markdown(clean_chat_content(res))
                st.session_state.messages.append({"role": "assistant", "content": res})
            except Exception as e: st.error(str(e))

# VIEW 3: TRAINING CALENDAR (EXPANDABLE WEEK-TO-DAY FEED)
elif st.session_state.active_nav == NAV_OPTIONS[2]:
    st.markdown("##### 📅 Multi-Sport Training Calendar")
    
    col_f1, col_f2 = st.columns(2)
    sport_filter = col_f1.selectbox("Filter Sport", ["All Sports", "Cycling", "Running"])
    status_filter = col_f2.selectbox("Filter Status", ["All Sessions", "Completed", "Planned"])

    # Build Unified Data Feed
    raw_feed = get_unified_calendar_items(activities_data, planned_events)

    # Filter Feed
    filtered_feed = []
    for item in raw_feed:
        if sport_filter == "Cycling" and "Ride" not in item["type"] and "Cycling" not in item["sport_title"]:
            continue
        if sport_filter == "Running" and "Run" not in item["type"] and "Running" not in item["sport_title"]:
            continue
        if status_filter == "Completed" and item["status"] != "Completed":
            continue
        if status_filter == "Planned" and item["status"] != "Planned":
            continue
        filtered_feed.append(item)

    if not filtered_feed:
        st.info("No activities found matching your filters. Syncing with Intervals.icu...")

    # Group Items by ISO Week (Monday to Sunday)
    grouped_weeks: Dict[Tuple[dt.date, dt.date], Dict[str, List[Dict[str, Any]]]] = {}
    
    for item in filtered_feed:
        item_date = item["datetime"].date()
        start_of_week = item_date - dt.timedelta(days=item_date.weekday())
        end_of_week = start_of_week + dt.timedelta(days=6)
        week_key = (start_of_week, end_of_week)
        
        if week_key not in grouped_weeks:
            grouped_weeks[week_key] = {}
        
        date_str = item["date_str"]
        if date_str not in grouped_weeks[week_key]:
            grouped_weeks[week_key][date_str] = []
        grouped_weeks[week_key][date_str].append(item)

    # Render Expandable Weeks
    for week_idx, ((w_start, w_end), days_dict) in enumerate(grouped_weeks.items()):
        # Calculate Weekly Totals
        all_week_items = [item for items in days_dict.values() for item in items]
        total_sec = sum(item["duration_sec"] for item in all_week_items)
        total_hours = total_sec / 3600.0
        h_part = int(total_hours)
        m_part = int((total_hours - h_part) * 60)
        dur_summary = f"{h_part}h {m_part}m" if h_part > 0 else f"{m_part}m"
        total_load = int(sum(item["load"] for item in all_week_items))

        week_label = f"🗓️ {w_start.strftime('%b %d')} - {w_end.strftime('%b %d')} &nbsp;·&nbsp; {dur_summary} &nbsp;·&nbsp; {total_load} Load"

        with st.expander(week_label, expanded=(week_idx == 0)):
            for date_str, day_items in sorted(days_dict.items(), reverse=True):
                dt_obj = day_items[0]["datetime"]
                day_name = dt_obj.strftime("%a")
                day_num = dt_obj.strftime("%d")

                col_date, col_card = st.columns([1, 11])
                
                with col_date:
                    st.markdown(f"""
                    <div class="date-badge-col">
                        <div class="date-day-name">{day_name}</div>
                        <div class="date-day-number">{day_num}</div>
                    </div>
                    """, unsafe_allow_html=True)

                with col_card:
                    for item_idx, item in enumerate(day_items):
                        act_type = item["type"]
                        is_run = "Run" in act_type
                        sport_icon = "🏃" if is_run else "🚴‍♂️"
                        
                        duration_m = round(item["duration_sec"] / 60.0)
                        dur_str = f"{duration_m}m" if duration_m < 60 else f"{duration_m//60}h {duration_m%60}m"
                        dist_km = f"{item['distance_m']/1000.0:.1f}km" if item['distance_m'] > 0 else "--"
                        
                        third_label = "Pace" if is_run else "Power"
                        if is_run:
                            third_val = item["pace_str"] or "8:36/km"
                        else:
                            third_val = f"{int(item['power_w'])}W" if item["power_w"] else "--"

                        load_val = str(int(item["load"]))

                        st.markdown(f"""
                        <div class="activity-card-body">
                            <div class="card-header-row">
                                <span class="sport-icon">{sport_icon}</span>
                                <div>
                                    <p class="sport-title">{item['sport_title']} <span style="font-size:0.75rem; color:{TEXT_MUTED};">({item['status']})</span></p>
                                    <p class="device-subtitle">{item['device']}</p>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)

                        # Mini Intensity Chart
                        fig_stream = generate_mini_stream_chart(act_type, seed_val=hash(item["id"]) % 1000)
                        st.plotly_chart(fig_stream, use_container_width=True, config={'displayModeBar': False})

                        # Metrics Footer
                        c_m1, c_m2 = st.columns([3, 1])
                        with c_m1:
                            st.markdown(f"""
                            <div class="metrics-flex-group">
                                <div class="metric-box">
                                    <span class="metric-box-label">Duration</span>
                                    <span class="metric-box-val">{dur_str}</span>
                                </div>
                                <div class="metric-box">
                                    <span class="metric-box-label">Distance</span>
                                    <span class="metric-box-val">{dist_km}</span>
                                </div>
                                <div class="metric-box">
                                    <span class="metric-box-label">{third_label}</span>
                                    <span class="metric-box-val">{third_val}</span>
                                </div>
                                <div class="metric-box">
                                    <span class="metric-box-label">Load</span>
                                    <span class="metric-box-val">{load_val}</span>
                                </div>
                            </div>
                            """, unsafe_allow_html=True)

                        with c_m2:
                            if st.button("💬 Review", key=f"rev_{item['id']}_{item_idx}", type="secondary"):
                                st.session_state.pending_coach_prompt = f"Let me get a full debrief on my {item['sport_title']} session ({dist_km}, {dur_str}, {load_val} Load)."
                                st.session_state.active_nav = "🤖 AI Coach & Sparring"
                                st.rerun()

                        st.markdown("</div>", unsafe_allow_html=True)

# VIEW 4: ATHLETE PROFILE
elif st.session_state.active_nav == NAV_OPTIONS[3]:
    st.markdown("##### 👤 Athlete Profile")
    prof = st.session_state.profile_data
    st.metric("Declared FTP", f"{prof['declared_ftp']} W")

# VIEW 5: ACTIVITY INSPECTOR
elif st.session_state.active_nav == NAV_OPTIONS[4]:
    st.markdown("##### 🔍 Activity Inspector")
    st.info("Select an activity from the Calendar view to run an in-depth debrief.")

# VIEW 6: WORKOUT BUILDER
elif st.session_state.active_nav == NAV_OPTIONS[5]:
    st.markdown("##### 🏋️ Workout Builder & Grammar Parser")
    txt = st.text_area("Workout Syntax", value="Warmup\n- 10m Z1 easy spin\n\nMain Set 4x\n- 8m 100% FTP threshold\n- 3m Z1 recovery\n\nCooldown\n- 8m Z1 easy spin")
    if st.button("Validate Workout"):
        valid, logs, parsed = WorkoutParserValidator.parse_and_validate(txt, "Cycling", 180, 60)
        st.json(parsed)

# VIEW 7: ROUTE STRATEGIST
elif st.session_state.active_nav == NAV_OPTIONS[6]:
    st.markdown("##### 🗺️ Route Pacing Strategist")
    st.file_uploader("Upload GPX Route", type=["gpx"])
