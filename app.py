import base64
import datetime as dt
import json
import math
import os
import re
import time
from typing import Dict, List, Any, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
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
PERSIST_FILE = "athlete_store.json"

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
    "👤 Athlete Profile & Memory",
    "🏋️ Workout Builder & MyWhoosh Sync",
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
    "running_threshold_pace_sec": 300,
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
    "• Key Focus Areas: Build sustained FTP density, maintain aerobic efficiency, protect joint recovery on running sessions.\n"
    "• Athlete Limitations & Health Constraints: Protect joint impact during run sessions (monitor high ground contact/knee load); "
    "avoid high fatigue spikes (ACWR > 1.35); protect strict rest days (Fridays); manage neck/lower-back loading in prolonged aero positions.\n"
    "• Platforms: Intervals.icu primary hub, auto-synced to MyWhoosh for indoor virtual cycling."
)

localS = LocalStorage() if LocalStorage else None

# --- LOCAL FILE & BROWSER PERSISTENCE ENGINE ---
def load_disk_store() -> Dict[str, Any]:
    if os.path.exists(PERSIST_FILE):
        try:
            with open(PERSIST_FILE, "r") as f:
                return json.load(f)
        except Exception:
            pass
    return {}

def save_disk_store():
    if "chat_sessions" in st.session_state and "active_session_id" in st.session_state:
        st.session_state.chat_sessions[st.session_state.active_session_id] = st.session_state.get("messages", [])

    store = {
        "profile_data": st.session_state.get("profile_data"),
        "coach_persona": st.session_state.get("coach_persona"),
        "coach_memory": st.session_state.get("coach_memory"),
        "user_supplements": st.session_state.get("user_supplements"),
        "chat_sessions": st.session_state.get("chat_sessions", {}),
        "active_session_id": st.session_state.get("active_session_id", "Main Conversation"),
        "messages": st.session_state.get("messages", []),
        "cached_trend_analyses": st.session_state.get("cached_trend_analyses", []),
        "protected_events": st.session_state.get("protected_events", []),
    }
    try:
        with open(PERSIST_FILE, "w") as f:
            json.dump(store, f, indent=2)
    except Exception:
        pass

    if localS:
        for k, v in store.items():
            try:
                localS.setItem(f"athlete_{k}", v)
            except Exception:
                pass

# --- INITIALIZE SESSION STATE WITH PERSISTENCE ---
def init_state():
    disk_data = load_disk_store()

    default_sessions = disk_data.get("chat_sessions", {})
    if not default_sessions:
        default_sessions = {"Main Conversation": disk_data.get("messages", [])}

    active_id = disk_data.get("active_session_id", list(default_sessions.keys())[0])
    active_msgs = default_sessions.get(active_id, [])

    defaults = {
        "user": None,
        "user_credentials": None,
        "chat_sessions": default_sessions,
        "active_session_id": active_id,
        "messages": active_msgs,
        "active_nav": NAV_OPTIONS[0],
        "sidebar_nav": NAV_OPTIONS[0],
        "coach_persona": disk_data.get("coach_persona", PERSONA_OPTIONS[0]),
        "unit_system": "Metric",
        "profile_data": disk_data.get("profile_data", DEFAULT_PROFILE.copy()),
        "coach_memory": disk_data.get("coach_memory", DEFAULT_COACH_MEMORY),
        "user_supplements": disk_data.get("user_supplements", DEFAULT_SUPPLEMENTS.copy()),
        "daily_notes": {},
        "protected_events": disk_data.get("protected_events", []),
        "cached_trend_analyses": disk_data.get("cached_trend_analyses", []),
        "pending_coach_prompt": None,
        "ai_diagnostic": None,
        "persistent_loaded": True
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

.chart-summary-box {{
    background-color: {BG_SURFACE_ALT};
    border: 1px solid {BORDER_SUBTLE};
    border-left: 3px solid #10B981;
    border-radius: 8px;
    padding: 12px 16px;
    margin-top: 10px;
    margin-bottom: 15px;
    font-size: 0.88rem;
    line-height: 1.45;
}}

.workout-notes-box {{
    margin-top: 10px;
    font-style: italic;
    color: {TEXT_MUTED};
    border-left: 2px solid #3B82F6;
    padding-left: 8px;
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
            creds.get("name", st.session_state.profile_data.get("name", "Amanda Tan")).strip(),
            "Guest Session"
        )

    sec_key = secret("INTERVALS_API_KEY") or secret("INTERVALS_KEY") or ""
    sec_id = secret("INTERVALS_ATHLETE_ID") or secret("INTERVALS_ID") or ""
    owner_name = st.session_state.profile_data.get("name") or secret("ATHLETE_NAME") or "Amanda Tan"
    
    if sec_key and sec_id:
        return str(sec_key).strip(), str(sec_id).strip(), owner_name, "Owner (Auto-Secrets)"

    return "", "", st.session_state.profile_data.get("name", "Amanda Tan"), "Unauthenticated"

# --- ADVANCED WORKOUT DETAILS PARSER ENGINE ---
def parse_workout_steps_detailed(description_text: str, declared_ftp: int = 180) -> Dict[str, Any]:
    if not description_text:
        return {"steps": [], "notes": "", "metrics": {}, "zone_times": {}}

    lines = [l.strip() for l in description_text.split("\n") if l.strip()]
    
    formatted_steps = []
    descriptive_notes = []
    zone_sec = {"Z1": 0.0, "Z2": 0.0, "Z3": 0.0, "Z4": 0.0, "Z5": 0.0, "Z6": 0.0}
    
    total_sec = 0.0
    weighted_watts_sec = 0.0
    
    repeat_count = 1
    in_repeat = False

    for line in lines:
        rep_m = re.search(r"^(\d+)x$", line, re.IGNORECASE)
        if rep_m:
            repeat_count = int(rep_m.group(1))
            in_repeat = True
            formatted_steps.append(f"**{repeat_count}x Set:**")
            continue

        step_m = re.search(r"^(?:-\s*)?(\d+)(m|s|h)?\s+([0-9]+)(?:-[0-9]+)?%?\s*(.*)$", line, re.IGNORECASE)
        if step_m:
            dur_val = float(step_m.group(1))
            unit = (step_m.group(2) or "m").lower()
            pct_ftp = float(step_m.group(3))
            label = step_m.group(4).strip() if step_m.group(4) else ""

            dur_sec = dur_val * 60.0 if unit == "m" else (dur_val * 3600.0 if unit == "h" else dur_val)
            dur_disp = f"{int(dur_val)}m" if unit == "m" else (f"{int(dur_val)}s" if unit == "s" else f"{dur_val}h")
            
            watts = round(declared_ftp * (pct_ftp / 100.0))
            
            step_bullet = f"• {dur_disp} {int(pct_ftp)}% ({watts}W) {label}".strip()
            if in_repeat:
                step_bullet = f"&nbsp;&nbsp;&nbsp;&nbsp;{step_bullet}"
            formatted_steps.append(step_bullet)

            effective_sec = dur_sec * (repeat_count if in_repeat else 1)
            total_sec += effective_sec
            weighted_watts_sec += watts * effective_sec

            if pct_ftp < 55: zone_sec["Z1"] += effective_sec
            elif pct_ftp <= 75: zone_sec["Z2"] += effective_sec
            elif pct_ftp <= 90: zone_sec["Z3"] += effective_sec
            elif pct_ftp <= 105: zone_sec["Z4"] += effective_sec
            elif pct_ftp <= 120: zone_sec["Z5"] += effective_sec
            else: zone_sec["Z6"] += effective_sec
        else:
            if not line.startswith("-") and not line.startswith("Warmup") and not line.startswith("Main Set") and not line.startswith("Cooldown"):
                descriptive_notes.append(line)
                in_repeat = False

    avg_watts = round(weighted_watts_sec / total_sec) if total_sec > 0 else 0
    work_kj = round((weighted_watts_sec) / 1000.0) if total_sec > 0 else 0
    np_watts = round(avg_watts * 1.05) if avg_watts > 0 else 0

    return {
        "steps": formatted_steps,
        "notes": " ".join(descriptive_notes),
        "metrics": {
            "avg_watts": avg_watts,
            "np_watts": np_watts,
            "work_kj": work_kj,
            "duration_min": round(total_sec / 60.0, 1)
        },
        "zone_times": zone_sec,
        "total_sec": total_sec
    }

# --- CALCULATORS ---
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

# --- AI ENGINE WITH FAST FAILOVER ---
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
    models = ["gemini-2.5-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    for name, key in GEMINI_KEYS:
        if not key: continue
        for m in models:
            try:
                res = gemini_generate(messages_payload, key, m, max_tokens=max_tokens)
                st.session_state.ai_diagnostic = f"Connected via {name} ({m})"
                return res
            except Exception as exc:
                err_str = str(exc)
                errors.append(f"{name} ({m}): {err_str}")
                continue
    raise RuntimeError(f"AI Connection Error: {' | '.join(errors[-2:])}")

# --- 90-DAY PAST + 60-DAY FUTURE DATA FETCHING ---
@st.cache_data(ttl=300, show_spinner=False)
def fetch_intervals_data_90days(athlete_id: str, api_key: str) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]], List[Dict[str, Any]], str]:
    if not athlete_id or not api_key:
        return [], [], [], "Credentials missing."

    headers = {"Accept": "application/json"}
    auth = ("API_KEY", api_key)
    today = dt.datetime.now(LOCAL_TZ).date()
    
    oldest_date = (today - dt.timedelta(days=90)).isoformat()
    newest_date = (today + dt.timedelta(days=62)).isoformat()
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
        pace_str = RunningAnalyzer.format_pace(1000.0 / avg_speed) if (is_run and avg_speed > 0) else None

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
            items.append({
                "id": f"plan_{ev.get('id')}",
                "date_str": dt_obj.strftime("%Y-%m-%d"),
                "datetime": dt_obj,
                "status": "Planned",
                "type": ev_type,
                "name": ev.get("name") or f"Planned {ev_type}",
                "sport_title": f"Planned {ev_type}",
                "device": "Intervals.icu / MyWhoosh Planned Workout",
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
    return re.sub(r"```xml\s*<\?xml.*?</workout_file>\s*```", "", text or "", flags=re.S | re.I).strip()

# --- HELPER: PUSH WORKOUTS TO INTERVALS.ICU API ---
def push_workouts_to_intervals(events_list: List[Dict[str, Any]], athlete_id: str, api_key: str) -> Tuple[bool, str]:
    if not athlete_id or not api_key:
        return False, "Missing API key or Athlete ID."
    
    events_to_post = []
    for item in events_list:
        events_to_post.append({
            "category": "WORKOUT",
            "type": item.get("type", "Ride"),
            "name": item.get("title", "Planned Session"),
            "description": item.get("description", ""),
            "start_date_local": f"{item.get('date')}T08:00:00"
        })

    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events/bulk?upsert=true"
    auth = ("API_KEY", api_key)
    
    try:
        resp = requests.post(url, auth=auth, json=events_to_post, timeout=15)
        if resp.status_code in [200, 201]:
            return True, f"Successfully synced {len(events_to_post)} workout(s) to Intervals.icu!"
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, str(e)

def build_gemini_payload(current_question: str, wellness_list: List[Dict[str, Any]], activities_data: List[Dict[str, Any]], planned_events: Optional[List[Dict[str, Any]]] = None) -> List[Dict[str, Any]]:
    prof = st.session_state.profile_data
    goals = prof.get("goals", {})
    supps = st.session_state.get("user_supplements", [])
    memory = st.session_state.get("coach_memory", "")
    persona = st.session_state.get("coach_persona", PERSONA_OPTIONS[0])
    protected_events = st.session_state.get("protected_events", [])

    if protected_events:
        event_lines = [
            f"- [{e.get('category', 'Event')}] {e.get('title')}: {e.get('start_date')} to {e.get('end_date')} (Notes: {e.get('notes', 'None')})"
            for e in protected_events
        ]
        events_formatted = "\n".join(event_lines)
    else:
        events_formatted = "No upcoming trips or travel blocks logged."

    upcoming_planned = [
        f"- {ev.get('start_date_local', '')[:10]}: {ev.get('name', 'Workout')} ({ev.get('type', 'Ride')})"
        for ev in (planned_events or [])[:10]
    ]
    planned_formatted = "\n".join(upcoming_planned) if upcoming_planned else "No structured workouts planned yet."

    supp_lines = [f"- {s.get('name')}: {s.get('dosage')} ({s.get('timing')}) -> {s.get('purpose')}" for s in supps if isinstance(s, dict)]
    supps_formatted = "\n".join(supp_lines) if supps_lines else "None logged"

    system_prompt = f"""You are an elite multi-sport performance coach.

SELECTED COACHING PERSONA: {persona}

ATHLETE BIOMETRICS & BENCHMARKS:
- Name: {prof.get('name', 'Amanda Tan')} | Gender: {prof.get('gender', 'Female')} | Age: {prof.get('age', 43)} | Weight: {prof.get('weight_kg', 54.0)} kg
- Declared FTP: {prof.get('declared_ftp', 180)} W | Estimated FTP: {prof.get('estimated_ftp', 185)} W
- Max Heart Rate: {prof.get('max_hr', 182)} bpm | Resting Heart Rate: {prof.get('resting_hr', 52)} bpm
- Rest Days: {', '.join(prof.get('rest_days', ['Friday']))}

ATHLETE GOALS & TARGET EVENTS:
- Target Event: {goals.get('event_name', 'Bintan Multi-Sport Challenge')}
- Event Date: {goals.get('race_date', '2026-10-24')}
- Primary Objective: {goals.get('target_metric', 'Build threshold power and running fatigue resistance')}

UPCOMING TRIPS, TRAVEL & PROTECTED EVENTS:
{events_formatted}

NEXT UPCOMING PLANNED WORKOUTS:
{planned_formatted}

COACH LONG-TERM MEMORY & ATHLETE LIMITATIONS:
{memory}

SUPPLEMENT PROTOCOL:
{supps_formatted}

CONDITIONAL WORKOUT JSON RULE:
ONLY if the user explicitly asks for a workout plan, session recommendations, schedule adjustments, or week rebalancing, you MUST append a raw JSON block at the very end of your response inside ```json:workouts ... ``` like this:

```json:workouts
[
  {{
    "date": "2026-09-05",
    "title": "Threshold 4x5m",
    "type": "Ride",
    "description": "Warmup\\n- 10m 50-60% FTP\\nMain Set 4x\\n- 5m 100% FTP\\n- 2m 50% FTP\\nCooldown\\n- 10m 40% FTP"
  }}
]
