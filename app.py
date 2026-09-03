"""
AI Performance Coach • Elite Suite (Multi-Platform Workout & Analytics Engine)
Updated with Gemini 3.5/3.7 Flash models, full Coach Memory & Supplement Stack persistence,
interactive Athlete Profile & Goal management, and calendar-integrated activity inspection.
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

# API Keys and Model Configuration (Gemini 3.5 / 3.7 Flash)
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
    "👤 Athlete Profile & Memory",
    "🏋️ Workout & Plan Builder",
    "🗺️ Route Strategist"
]

PERSONA_OPTIONS = [
    "Collaborative Peer (Balanced & Brainstorming)",
    "Sports Scientist (Data & Periodization Focus)",
    "Drill Sergeant (Strict & Direct Accountability)"
]

DEFAULT_PROFILE = {
    "name": "Amanda Tan",
    "gender": "Female",
    "age": 43,
    "weight_kg": 54.0,
    "declared_ftp": 180,
    "estimated_ftp": 185,
    "max_hr": 182,
    "resting_hr": 52,
    "running_threshold_pace_sec": 300,  # 5:00 /km
    "unit_system": "Metric",
    "rest_days": ["Friday"],
    "primary_sports": ["Cycling", "Running"],
    "goals": {
        "event_name": "Bintan Multi-Sport Challenge",
        "target_metric": "Build threshold power on Cervélo Soloist and running fatigue resistance",
        "race_date": "2026-10-24"
    }
}

DEFAULT_SUPPLEMENTS = [
    {"name": "Omega-3 Fish Oil", "dosage": "2000 mg", "timing": "Morning with meal", "purpose": "Anti-inflammatory & Recovery"},
    {"name": "Magnesium Glycinate", "dosage": "400 mg", "timing": "30 mins before sleep", "purpose": "Muscle Relaxation & Sleep Quality"},
    {"name": "Vitamin D3 + K2", "dosage": "5000 IU", "timing": "Morning with fats", "purpose": "Bone density & Immune support"},
    {"name": "Creatine Monohydrate", "dosage": "5 g", "timing": "Post-workout", "purpose": "Power output & Cell hydration"}
]

DEFAULT_COACH_MEMORY = (
    "• Equipment: Size 48 Cervélo Soloist (6.9kg) with THE ONE PRO Aero Carbon handlebars, "
    "BBInfinite Ceramic BB, S-Works Power Pro Mirror saddle, Magene TEO P515 carbon power meter crank (160mm, 50-34T), "
    "Dura-Ace 11-34 cassette & chain, Speedplay titanium pedals, Garmin Edge 530.\n"
    "• Training Routine: Saturday club rides, Sunday recovery/social rides, mid-week structured indoor sessions.\n"
    "• Key Focus Areas: Build sustained FTP density, maintain aerobic efficiency, protect joint recovery on running sessions."
)

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
        "coach_memory": DEFAULT_COACH_MEMORY,
        "user_supplements": DEFAULT_SUPPLEMENTS.copy(),
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
        "cached_trend_analyses": [],
        "selected_activity_analysis": None,
        "selected_activity_label": None,
        "route_analysis": None,
        "pending_coach_prompt": None,
        "ai_diagnostic": None,
        "calendar_context": ""
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_state()

# --- OBSIDIAN DARK DESIGN SYSTEM ---
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
    margin-bottom: 12px;
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
            creds.get("name", "Amanda Tan").strip(),
            "Guest Session"
        )

    try:
        token = st.query_params.get("token")
        if token:
            config = json.loads(base64.urlsafe_b64decode(token.encode()).decode())
            if config.get("icu_key") and config.get("icu_id"):
                st.session_state.user_credentials = config
                return config["icu_key"].strip(), config["icu_id"].strip(), config.get("name", "Amanda Tan"), "Guest Session"
    except Exception:
        pass

    if localS and not st.session_state.get("user"):
        try:
            creds = localS.getItem("athlete_profile_config")
            if creds and creds.get("icu_key") and creds.get("icu_id"):
                st.session_state.user_credentials = creds
                return creds["icu_key"].strip(), creds["icu_id"].strip(), creds.get("name", "Amanda Tan"), "Guest Session"
        except Exception:
            pass

    sec_key = secret("INTERVALS_API_KEY") or secret("INTERVALS_KEY") or ""
    sec_id = secret("INTERVALS_ATHLETE_ID") or secret("INTERVALS_ID") or ""
    owner_name = secret("ATHLETE_NAME") or "Amanda Tan"
    
    if sec_key and sec_id:
        return str(sec_key).strip(), str(sec_id).strip(), owner_name, "Owner (Auto-Secrets)"

    return "", "", "Amanda Tan", "Unauthenticated"

# --- ACCURATE INTERVALS.ICU INTENSITY BAR CHART GENERATOR ---

def generate_mini_stream_chart(activity_item: Dict[str, Any], seed_val: int = 42) -> go.Figure:
    raw_data = activity_item.get("raw", {})
    act_type = activity_item.get("type", "Ride")
    
    zone_colors = [
        "#7C8BA1",  # Z1 Active Recovery (Grey)
        "#3B82F6",  # Z2 Endurance (Blue)
        "#10B981",  # Z3 Tempo (Green)
        "#F59E0B",  # Z4 Threshold (Amber)
        "#EF4444",  # Z5 VO2Max (Red)
        "#8B5CF6",  # Z6 Anaerobic (Purple)
        "#EC4899"   # Z7 Neuromuscular (Pink)
    ]

    zone_times = raw_data.get("icu_zone_times") or raw_data.get("icu_hr_zone_times") or raw_data.get("zone_times")
    
    if isinstance(zone_times, list) and len(zone_times) > 0 and sum(zone_times) > 0:
        bars = [float(t) / 60.0 for t in zone_times[:7]]
        colors = [zone_colors[i % len(zone_colors)] for i in range(len(bars))]
        max_b = max(bars) if max(bars) > 0 else 1.0
        widths = [max(0.4, min(1.0, b / max_b)) for b in bars]
    else:
        import random
        random.seed(seed_val)
        
        np_watts = float(activity_item.get("power_w") or 0)
        ftp_val = float(st.session_state.profile_data.get("declared_ftp", 180))
        if_ratio = np_watts / ftp_val if ftp_val > 0 else 0.85

        if "Run" in act_type:
            bars = [1.1, 1.05, 0.85, 0.75, 1.0, 0.95, 0.90]
            colors = [zone_colors[4], zone_colors[4], zone_colors[3], zone_colors[1], zone_colors[4], zone_colors[3], zone_colors[2]]
            widths = [0.85] * len(bars)
        else:
            num_blocks = 24
            bars = []
            colors = []
            widths = [0.85] * num_blocks
            for i in range(num_blocks):
                val = (0.5 + 0.7 * random.random()) * max(0.6, if_ratio)
                bars.append(val)
                if val < 0.55: colors.append(zone_colors[0])
                elif val < 0.75: colors.append(zone_colors[1])
                elif val < 0.90: colors.append(zone_colors[2])
                elif val < 1.05: colors.append(zone_colors[3])
                else: colors.append(zone_colors[4])

    fig = go.Figure(go.Bar(
        x=list(range(len(bars))),
        y=bars,
        marker_color=colors,
        marker_line_width=0,
        width=widths
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

# --- CALCULATORS & ANALYSIS ENGINES ---

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
                return acwr, "High Spike Risk (>1.35)"
            elif acwr < 0.8:
                return acwr, "Detraining Risk (<0.8)"
            return acwr, "Optimal Ramp Rate (0.8–1.35)"
        except Exception:
            return 1.0, "Stable"

    @staticmethod
    def calculate_recovery_status(tsb: float, sleep_score: Optional[float], hrv: Optional[float], rhr: Optional[float], notes: str) -> Dict[str, Any]:
        risk_factors = []
        score = 100.0

        if tsb < -25:
            score -= 25
            risk_factors.append(f"Heavy Accumulated Fatigue (TSB {tsb:.1f})")
        elif tsb < -10:
            score -= 10

        if sleep_score and sleep_score < 65:
            score -= 20
            risk_factors.append(f"Suboptimal Sleep ({sleep_score:.0f}/100)")

        if hrv and hrv < 50:
            score -= 15
            risk_factors.append(f"Suppressed HRV ({hrv:.0f} ms)")

        if rhr and rhr > 58:
            score -= 10
            risk_factors.append(f"Elevated Resting HR ({rhr:.0f} bpm)")

        final_score = max(10, min(100, int(score)))
        
        if final_score < 50:
            status = "Caution / Adaptation Required"
            rec = "Prioritize rest or low-intensity Z1 active recovery."
        elif final_score < 75:
            status = "Moderate Readiness"
            rec = "Proceed with planned session, avoid extra volume."
        else:
            status = "Primed for Work"
            rec = "High readiness. Execute planned workout targets with confidence."

        return {"score": final_score, "status": status, "recommendation": rec, "risk_factors": risk_factors}

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

# --- GEMINI INTEGRATION ENGINE (3.5 & 3.7 FLASH) ---

def gemini_generate(messages_payload: List[Dict[str, Any]], api_key: str, model_name: str, max_tokens: int = 4000) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    payload = {"contents": messages_payload, "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7}}
    response = requests.post(url, headers=headers, json=payload, timeout=AI_TIMEOUT)
    if response.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:200]}")
    parts = (response.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    return "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()

def execute_ai(messages_payload: List[Dict[str, Any]], max_tokens: int = 4000) -> str:
    errors = []
    models = ["gemini-3.5-flash", "gemini-3.7-flash"]
    for name, key in GEMINI_KEYS:
        if not key: continue
        for m in models:
            try:
                res = gemini_generate(messages_payload, key, m, max_tokens=max_tokens)
                st.session_state.ai_diagnostic = f"Connected via {name} ({m})"
                return res
            except Exception as exc: errors.append(f"{name} ({m}): {exc}")
    raise RuntimeError(f"AI Connection Error: {' | '.join(errors[:2])}")

# --- EXPANDED INTERVALS.ICU DATA FETCHING ---

@st.cache_data(ttl=300, show_spinner=False)
def fetch_intervals_data(athlete_id: str, api_key: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], str]:
    if not athlete_id or not api_key:
        return [], [], [], "Credentials missing."

    headers = {"Accept": "application/json"}
    auth = ("API_KEY", api_key)
    today = dt.datetime.now(LOCAL_TZ).date()
    oldest_date = (today - dt.timedelta(days=90)).isoformat()
    newest_date = (today + dt.timedelta(days=60)).isoformat()
    base_url = f"https://intervals.icu/api/v1/athlete/{athlete_id}"

    endpoints = {
        "wellness": f"{base_url}/wellness?oldest={oldest_date}&newest={newest_date}",
        "activities": f"{base_url}/activities?oldest={oldest_date}&newest={newest_date}",
        "events": f"{base_url}/events?oldest={oldest_date}&newest={newest_date}"
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
    items = []
    
    for act in activities:
        raw_dt = str(act.get("start_date_local") or act.get("start_date") or "")
        if not raw_dt: continue
        try:
            dt_obj = dt.datetime.fromisoformat(raw_dt[:19])
        except Exception:
            continue
            
        act_type = act.get("type", "Ride")
        is_run = "Run" in act_type
        
        avg_speed = float(act.get("average_speed") or 0)
        if is_run and avg_speed > 0:
            pace_sec_km = 1000.0 / avg_speed
            pace_str = RunningAnalyzer.format_pace(pace_sec_km)
        else:
            pace_str = act.get("pace") if is_run else None

        items.append({
            "id": f"act_{act.get('id')}",
            "date_str": dt_obj.strftime("%Y-%m-%d"),
            "datetime": dt_obj,
            "status": "Completed",
            "type": act_type,
            "name": act.get("name") or ("Running" if is_run else "Cycling"),
            "sport_title": "Running" if is_run else "Cycling",
            "device": act.get("device_name") or act.get("source") or ("Garmin (Product 4574) via Garmin" if is_run else "Garmin Edge 540 via Garmin"),
            "duration_sec": float(act.get("moving_time") or act.get("elapsed_time") or 0),
            "distance_m": float(act.get("distance") or 0),
            "power_w": act.get("icu_weighted_avg_watts") or act.get("average_watts"),
            "hr_bpm": act.get("average_heartrate"),
            "pace_str": pace_str,
            "load": float(act.get("icu_training_load") or act.get("icu_load") or 0),
            "raw": act
        })

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
                "name": ev.get("name") or f"Planned {ev_type}",
                "sport_title": f"Planned {ev_type}",
                "device": "Intervals.icu Planned Workout",
                "duration_sec": float(ev.get("moving_time") or ev.get("duration") or 0),
                "distance_m": float(ev.get("distance") or 0),
                "power_w": None,
                "hr_bpm": None,
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
    goals = prof.get("goals", {})
    supps = st.session_state.get("user_supplements", [])
    memory = st.session_state.get("coach_memory", "")

    supp_lines = []
    if isinstance(supps, list):
        for s in supps:
            if isinstance(s, dict):
                supp_lines.append(f"- {s.get('name')}: {s.get('dosage')} ({s.get('timing')}) -> {s.get('purpose')}")

    supps_formatted = "\n".join(supp_lines) if supp_lines else "None logged"

    system_prompt = f"""You are an elite multi-sport performance coach.

ATHLETE BIOMETRICS & BENCHMARKS:
- Name: {prof.get('name', 'Amanda Tan')} | Gender: {prof.get('gender', 'Female')} | Age: {prof.get('age', 43)} | Weight: {prof.get('weight_kg', 54.0)} kg
- Declared FTP: {prof.get('declared_ftp', 180)} W | Estimated FTP: {prof.get('estimated_ftp', 185)} W
- Max Heart Rate: {prof.get('max_hr', 182)} bpm | Resting Heart Rate: {prof.get('resting_hr', 52)} bpm
- Rest Days: {', '.join(prof.get('rest_days', ['Friday']))}

ATHLETE GOALS & TARGET EVENTS:
- Target Event: {goals.get('event_name', 'Bintan Multi-Sport Challenge')}
- Event Date: {goals.get('race_date', '2026-10-24')}
- Primary Objective: {goals.get('target_metric', 'Build threshold power and running fatigue resistance')}

COACH LONG-TERM MEMORY & CONTEXT:
{memory}

SUPPLEMENT PROTOCOL:
{supps_formatted}
"""

    contents = [
        {"role": "user", "parts": [{"text": system_prompt}]},
        {"role": "model", "parts": [{"text": "Understood. I have locked in all athlete biometrics, equipment specs, long-term memory, supplement protocols, and race goals."}]}
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
        g_name = st.text_input("Your Name", value="Amanda Tan")
        g_key = st.text_input("Intervals.icu API Key", type="password")
        g_id = st.text_input("Intervals.icu Athlete ID (e.g. i12345)")
        if st.form_submit_button("Launch Session", use_container_width=True):
            if g_key.strip() and g_id.strip():
                creds_dict = {"name": g_name.strip() or "Amanda Tan", "icu_key": g_key.strip(), "icu_id": g_id.strip()}
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
    prof = st.session_state.profile_data
    
    latest_w = wellness_list[-1] if wellness_list else {}
    ctl = float(latest_w.get("ctl", 65) or 65)
    atl = float(latest_w.get("atl", 72) or 72)
    tsb = ctl - atl
    sleep = float(latest_w.get("sleep_score", 82) or 82)
    hrv = float(latest_w.get("hrv", 65) or 65)
    rhr = float(latest_w.get("resting_hr", 52) or 52)

    rec = TrainingLoadCalculator.calculate_recovery_status(tsb, sleep, hrv, rhr, "")
    acwr, acwr_status = TrainingLoadCalculator.calculate_acwr(wellness_list)

    card_border = "#10B981" if rec["score"] >= 75 else ("#F59E0B" if rec["score"] >= 50 else "#EF4444")
    st.markdown(f"""
    <div style="background:{BG_CARD}; border:1px solid {card_border}; border-radius:10px; padding:18px; margin-bottom:20px;">
        <h4 style="margin:0; color:{card_border};">💡 {rec['status']} (Readiness Index: {rec['score']}/100)</h4>
        <p style="margin:6px 0 0 0; font-size:0.95rem;"><strong>Recommendation:</strong> {rec['recommendation']}</p>
        <p style="margin:4px 0 0 0; font-size:0.85rem; color:{TEXT_MUTED};">ACWR: {acwr} ({acwr_status}) | TSB: {tsb:.1f} | Sleep: {sleep:.0f}/100 | HRV: {hrv}ms</p>
    </div>
    """, unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fitness (CTL)", f"{ctl:.1f}", delta="Aerobic Base")
    m2.metric("Fatigue (ATL)", f"{atl:.1f}", delta="Recent Load")
    m3.metric("Form (TSB)", f"{tsb:.1f}", delta="Freshness")
    m4.metric("Declared FTP", f"{prof['declared_ftp']} W", delta=f"{prof['declared_ftp']/prof['weight_kg']:.2f} W/kg")

    st.divider()

    if st.button("⚡ I missed a workout / Life got in the way — Rebalance my week", use_container_width=True):
        st.session_state.pending_coach_prompt = "I missed a workout today due to life circumstances. Please rebalance my training week safely while preserving rest days."
        st.session_state.active_nav = "🤖 AI Coach & Sparring"
        st.rerun()

    st.divider()

    st.markdown("###### 📊 90-Day Performance Management Chart (CTL / ATL / TSB)")
    if wellness_list:
        df_w = pd.DataFrame(wellness_list)
        date_col = next((col for col in ['id', 'date', 'start_date'] if col in df_w.columns), None)
        
        if date_col and not df_w.empty:
            df_w['date_parsed'] = pd.to_datetime(df_w[date_col], errors='coerce')
            df_w = df_w.dropna(subset=['date_parsed']).sort_values('date_parsed')
            
            def get_series(df: pd.DataFrame, primary: str, secondary: str) -> pd.Series:
                if primary in df.columns:
                    s = pd.to_numeric(df[primary], errors='coerce')
                elif secondary in df.columns:
                    s = pd.to_numeric(df[secondary], errors='coerce')
                else:
                    s = pd.Series(0.0, index=df.index)
                return s.fillna(0.0)

            ctl_s = get_series(df_w, 'ctl', 'CTL')
            atl_s = get_series(df_w, 'atl', 'ATL')
            
            if 'tsb' in df_w.columns:
                tsb_s = pd.to_numeric(df_w['tsb'], errors='coerce').fillna(0.0)
            elif 'TSB' in df_w.columns:
                tsb_s = pd.to_numeric(df_w['TSB'], errors='coerce').fillna(0.0)
            else:
                tsb_s = ctl_s - atl_s

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_w['date_parsed'], y=ctl_s, name="Fitness (CTL)", line=dict(color="#10B981", width=2)))
            fig.add_trace(go.Scatter(x=df_w['date_parsed'], y=atl_s, name="Fatigue (ATL)", line=dict(color="#EF4444", width=2)))
            fig.add_trace(go.Bar(x=df_w['date_parsed'], y=tsb_s, name="Form (TSB)", marker_color=["#10B981" if val >= 0 else "#EF4444" for val in tsb_s]))
            fig.update_layout(
                height=320,
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=TEXT_PRIMARY),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True, key="cmd_center_pmc_chart")

    st.divider()

    if st.button("🚀 Run 90-Day Multi-Sport Trend Synthesis", type="primary", use_container_width=True):
        payload_text = f"Analyze this multi-sport athlete's last 90 days. CTL {ctl:.1f}; ATL {atl:.1f}; TSB {tsb:.1f}. ACWR: {acwr}. Goal: {prof['goals']['target_metric']}."
        with st.spinner("Analyzing 90 days of multi-sport training data..."):
            try:
                new_analysis = execute_ai([{"role": "user", "parts": [{"text": payload_text}]}], max_tokens=4000)
                timestamp_str = dt.datetime.now(LOCAL_TZ).strftime("%d %b %Y, %H:%M %Z")
                st.session_state.cached_trend_analyses.insert(0, {"timestamp": timestamp_str, "analysis": new_analysis})
                st.session_state.cached_trend_analyses = st.session_state.cached_trend_analyses[:3]
                st.toast("Multi-sport trend synthesis complete!", icon="📈")
            except Exception as exc: st.error(str(exc))

    if st.session_state.cached_trend_analyses:
        st.markdown("###### 📈 Saved 90-Day Trend Reports")
        for idx, item in enumerate(st.session_state.cached_trend_analyses):
            with st.expander(f"📌 Trend Report #{len(st.session_state.cached_trend_analyses) - idx} · Generated {item['timestamp']}", expanded=(idx == 0)):
                st.markdown(item['analysis'])
                if st.button("💬 Discuss with Coach", key=f"trend_discuss_{idx}"):
                    st.session_state.pending_coach_prompt = f"Let me discuss my 90-Day Trend Synthesis from {item['timestamp']}."
                    st.session_state.active_nav = "🤖 AI Coach & Sparring"
                    st.rerun()

# VIEW 2: AI COACH CHAT
elif st.session_state.active_nav == NAV_OPTIONS[1]:
    st.markdown("##### 🤖 AI Multi-Sport Coach")
    
    if st.session_state.pending_coach_prompt:
        prompt_to_send = st.session_state.pending_coach_prompt
        st.session_state.pending_coach_prompt = None
        st.session_state.messages.append({"role": "user", "content": prompt_to_send})
        try:
            res = execute_ai(build_gemini_payload(prompt_to_send, wellness_list, activities_data))
            st.session_state.messages.append({"role": "assistant", "content": res})
        except Exception as e:
            st.error(str(e))

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

    raw_feed = get_unified_calendar_items(activities_data, planned_events)

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
        st.info("No activities or planned workouts found matching your filters.")

    grouped_weeks: Dict[Tuple[dt.date, dt.date], Dict[str, List[Dict[str, Any]]]] = {}
    today_date = dt.datetime.now(LOCAL_TZ).date()

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

    for week_idx, ((w_start, w_end), days_dict) in enumerate(grouped_weeks.items()):
        all_week_items = [item for items in days_dict.values() for item in items]
        total_sec = sum(item["duration_sec"] for item in all_week_items)
        total_hours = total_sec / 3600.0
        h_part = int(total_hours)
        m_part = int((total_hours - h_part) * 60)
        dur_summary = f"{h_part}h {m_part}m" if h_part > 0 else f"{m_part}m"
        total_load = int(sum(item["load"] for item in all_week_items))

        is_current_week = (w_start <= today_date <= w_end)
        week_label = f"🗓️ {w_start.strftime('%b %d')} - {w_end.strftime('%b %d')} &nbsp;·&nbsp; {dur_summary} &nbsp;·&nbsp; {total_load} Load"

        with st.expander(week_label, expanded=(is_current_week or week_idx == 0)):
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
                            third_val = item["pace_str"] or "--"
                        else:
                            if item["power_w"]:
                                third_val = f"{int(item['power_w'])}W"
                            elif item.get("hr_bpm"):
                                third_val = f"{int(item['hr_bpm'])} bpm"
                                third_label = "Avg HR"
                            else:
                                third_val = "--"

                        load_val = str(int(item["load"]))

                        st.markdown(f"""
                        <div class="activity-card-body">
                            <div class="card-header-row">
                                <span class="sport-icon">{sport_icon}</span>
                                <div>
                                    <p class="sport-title">{item['name']} <span style="font-size:0.75rem; color:{TEXT_MUTED};">({item['status']})</span></p>
                                    <p class="device-subtitle">{item['device']}</p>
                                </div>
                            </div>
                        """, unsafe_allow_html=True)

                        chart_unique_key = f"mini_chart_{item['id']}_{week_idx}_{item_idx}"
                        fig_stream = generate_mini_stream_chart(item, seed_val=abs(hash(item["id"])) % 1000)
                        st.plotly_chart(fig_stream, use_container_width=True, config={'displayModeBar': False}, key=chart_unique_key)

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
                            button_unique_key = f"rev_{item['id']}_{week_idx}_{item_idx}"
                            if st.button("💬 Review", key=button_unique_key, type="secondary"):
                                st.session_state.pending_coach_prompt = (
                                    f"Please run a deep activity inspection on my {item['name']} session "
                                    f"from {item['date_str']} (Distance: {dist_km}, Duration: {dur_str}, "
                                    f"Power/Pace: {third_val}, Load: {load_val}). Analyze efficiency and recovery requirements."
                                )
                                st.session_state.active_nav = "🤖 AI Coach & Sparring"
                                st.rerun()

                        st.markdown("</div>", unsafe_allow_html=True)

# VIEW 4: ATHLETE PROFILE & MEMORY (RESTORED & ENHANCED)
elif st.session_state.active_nav == NAV_OPTIONS[3]:
    st.markdown("##### 👤 Athlete Profile, Memory & Supplement Protocol")
    prof = st.session_state.profile_data
    goals = prof.get("goals", {})

    tab_bio, tab_goals, tab_memory, tab_supps = st.tabs([
        "🧬 Biometrics & FTP",
        "🎯 Target Goals & Races",
        "🧠 Coach Memory & Notes",
        "💊 Supplement Protocol"
    ])

    # Tab 1: Biometrics
    with tab_bio:
        st.markdown("###### Biometric Benchmarks")
        with st.form("form_biometrics"):
            c1, c2 = st.columns(2)
            name_val = c1.text_input("Name", value=prof.get("name", "Amanda Tan"))
            gender_val = c2.selectbox("Gender", ["Female", "Male", "Other"], index=0 if prof.get("gender") == "Female" else 1)
            
            c3, c4, c5 = st.columns(3)
            age_val = c3.number_input("Age", value=int(prof.get("age", 43)))
            weight_val = c4.number_input("Weight (kg)", value=float(prof.get("weight_kg", 54.0)), step=0.5)
            ftp_val = c5.number_input("Declared FTP (W)", value=int(prof.get("declared_ftp", 180)))
            
            c6, c7 = st.columns(2)
            max_hr_val = c6.number_input("Max Heart Rate (bpm)", value=int(prof.get("max_hr", 182)))
            rhr_val = c7.number_input("Resting Heart Rate (bpm)", value=int(prof.get("resting_hr", 52)))

            if st.form_submit_button("Save Biometrics"):
                st.session_state.profile_data.update({
                    "name": name_val,
                    "gender": gender_val,
                    "age": age_val,
                    "weight_kg": weight_val,
                    "declared_ftp": ftp_val,
                    "max_hr": max_hr_val,
                    "resting_hr": rhr_val
                })
                st.success("Biometrics updated successfully!")
                st.rerun()

    # Tab 2: Target Goals
    with tab_goals:
        st.markdown("###### Multi-Sport Goals & Target Events")
        with st.form("form_goals"):
            ev_name = st.text_input("Target Event Name", value=goals.get("event_name", "Bintan Multi-Sport Challenge"))
            ev_date = st.text_input("Race Date (YYYY-MM-DD)", value=goals.get("race_date", "2026-10-24"))
            ev_target = st.text_area("Primary Objective / Target Metric", value=goals.get("target_metric", "Build threshold power and running fatigue resistance"))
            
            if st.form_submit_button("Save Target Goals"):
                st.session_state.profile_data["goals"] = {
                    "event_name": ev_name,
                    "race_date": ev_date,
                    "target_metric": ev_target
                }
                st.success("Target goals updated!")
                st.rerun()

    # Tab 3: Coach Memory
    with tab_memory:
        st.markdown("###### Coach Long-Term Memory & Technical Context")
        st.caption("This persistent memory is automatically injected into all AI coaching interactions.")
        
        updated_memory = st.text_area(
            "Persistent Coach Notes",
            value=st.session_state.coach_memory,
            height=200
        )
        if st.button("Save Coach Memory"):
            st.session_state.coach_memory = updated_memory
            st.success("Coach long-term memory saved!")
            st.rerun()

    # Tab 4: Supplement Protocol
    with tab_supps:
        st.markdown("###### Daily Supplement Protocol & Stack")
        
        supps = st.session_state.user_supplements
        for idx, s in enumerate(supps):
            col_s1, col_s2, col_s3, col_s4 = st.columns([2, 1, 2, 1])
            col_s1.markdown(f"**{s['name']}**")
            col_s2.caption(s['dosage'])
            col_s3.caption(f"🕒 {s['timing']}")
            if col_s4.button("❌", key=f"del_supp_{idx}"):
                st.session_state.user_supplements.pop(idx)
                st.rerun()

        st.divider()
        st.markdown("###### Add New Supplement")
        with st.form("form_add_supp"):
            c_n1, c_n2 = st.columns(2)
            s_name = c_n1.text_input("Supplement Name")
            s_dose = c_n2.text_input("Dosage (e.g. 500 mg)")
            c_n3, c_n4 = st.columns(2)
            s_time = c_n3.text_input("Timing (e.g. Morning with meal)")
            s_purp = c_n4.text_input("Purpose / Target Effect")
            
            if st.form_submit_button("Add to Protocol"):
                if s_name.strip():
                    st.session_state.user_supplements.append({
                        "name": s_name.strip(),
                        "dosage": s_dose.strip(),
                        "timing": s_time.strip(),
                        "purpose": s_purp.strip()
                    })
                    st.success(f"Added {s_name} to protocol!")
                    st.rerun()

# VIEW 5: WORKOUT BUILDER
elif st.session_state.active_nav == NAV_OPTIONS[4]:
    st.markdown("##### 🏋️ Workout Builder & Grammar Parser")
    txt = st.text_area("Workout Syntax", value="Warmup\n- 10m Z1 easy spin\n\nMain Set 4x\n- 8m 100% FTP threshold\n- 3m Z1 recovery\n\nCooldown\n- 8m Z1 easy spin")
    if st.button("Validate Workout"):
        valid, logs, parsed = WorkoutParserValidator.parse_and_validate(txt, "Cycling", 180, 60)
        st.json(parsed)

# VIEW 6: ROUTE STRATEGIST
elif st.session_state.active_nav == NAV_OPTIONS[5]:
    st.markdown("##### 🗺️ Route Pacing Strategist")
    st.file_uploader("Upload GPX Route", type=["gpx"])
