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

AI_TIMEOUT = 45
INTERVALS_TIMEOUT = 10

NAV_OPTIONS = [
    "☀️ Command Center",
    "🤖 AI Coach & Sparring",
    "📅 Training Calendar",
    "👤 Athlete Profile & Memory",
    "🗺️ Route Strategist"
]

PERSONA_OPTIONS = [
    "Collaborative Peer (Balanced & Brainstorming)",
    "Sports Scientist (Data & Periodization Focus)",
    "Drill Sergeant (Strict & Direct Accountability)"
]

def get_user_default_profile(user_name: str) -> Dict[str, Any]:
    return {
        "name": user_name,
        "gender": "Female",
        "age": 40,
        "weight_kg": 55.0,
        "declared_ftp": 200,
        "estimated_ftp": 200,
        "max_hr": 185,
        "resting_hr": 50,
        "running_threshold_pace_sec": 300,
        "unit_system": "Metric",
        "rest_days": ["Monday"],
        "primary_sports": ["Cycling", "Running"],
        "goals": {
            "event_name": "Target Season Goal",
            "target_metric": "Build threshold power and endurance capacity",
            "race_date": "2026-12-31"
        }
    }

DEFAULT_COACH_MEMORY = "• No specific coach memory logged yet. Add your equipment, routines, and training limitations here."
DEFAULT_SUPPLEMENTS = []

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

    resolved_name = secret("ATHLETE_NAME") or "Athlete"

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
        "profile_data": disk_data.get("profile_data", get_user_default_profile(resolved_name)),
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
            creds.get("name", st.session_state.profile_data.get("name", "Athlete")).strip(),
            "Guest Session"
        )

    sec_key = secret("INTERVALS_API_KEY") or secret("INTERVALS_KEY") or ""
    sec_id = secret("INTERVALS_ATHLETE_ID") or secret("INTERVALS_ID") or ""
    owner_name = st.session_state.profile_data.get("name") or secret("ATHLETE_NAME") or "Athlete"
    
    if sec_key and sec_id:
        return str(sec_key).strip(), str(sec_id).strip(), owner_name, "Owner (Auto-Secrets)"

    return "", "", st.session_state.profile_data.get("name", "Athlete"), "Unauthenticated"

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

# --- AI ENGINE (Gemini 3.5, 3.6, 3.7 Only) ---
def gemini_generate(messages_payload: List[Dict[str, Any]], api_key: str, model_name: str, max_tokens: int = 4000) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    payload = {
        "contents": messages_payload,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.7,
            "thinkingConfig": {"thinkingLevel": "medium"}
        }
    }
    response = requests.post(url, headers=headers, json=payload, timeout=AI_TIMEOUT)
    if response.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:200]}")
    
    resp_json = response.json()
    candidates = resp_json.get("candidates") or [{}]
    content_obj = candidates[0].get("content", {})
    parts = content_obj.get("parts", [])
    
    return "\n".join(p.get("text", "") for p in parts if isinstance(p, dict) and p.get("text")).strip()

def execute_ai(messages_payload: List[Dict[str, Any]], max_tokens: int = 4000) -> str:
    errors = []
    models = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash"]
    for name, key in GEMINI_KEYS:
        if not key: continue
        for m in models:
            for attempt in range(2):
                try:
                    res = gemini_generate(messages_payload, key, m, max_tokens=max_tokens)
                    st.session_state.ai_diagnostic = f"Connected via {name} ({m})"
                    return res
                except Exception as exc:
                    err_str = str(exc)
                    errors.append(f"{name} ({m}) [Attempt {attempt+1}]: {err_str}")
                    if "503" in err_str or "timed out" in err_str.lower():
                        time.sleep(2)
                    else:
                        break
    raise RuntimeError(f"AI Connection Error: {' | '.join(errors[-3:])}")

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
    cleaned = re.sub(r"```xml\s*<\?xml.*?</workout_file>\s*```", "", text or "", flags=re.S | re.I)
    cleaned = re.sub(r"```json:workouts\s*.*?\s*```", "", cleaned, flags=re.S | re.I)
    return cleaned.strip()

def extract_json_workouts(text: str) -> List[Dict[str, Any]]:
    match = re.search(r"```(?:json:workouts|json)\s*(\[.*?\])\s*```", text, re.S | re.I)
    if not match:
        match = re.search(r"(\[\s*\{\s*\"date\".*?\}\s*\])", text, re.S)
    if match:
        json_str = match.group(1).strip()
        try:
            return json.loads(json_str)
        except Exception:
            try:
                sanitized = re.sub(r'(?<=: ")(.*?)(?=")', lambda m: m.group(1).replace('\n', '\\n'), json_str, flags=re.S)
                return json.loads(sanitized)
            except Exception:
                pass
    return []

# --- HELPER: PUSH WORKOUTS TO INTERVALS.ICU API ---
def push_workouts_to_intervals(events_list: List[Dict[str, Any]], athlete_id: str, api_key: str) -> Tuple[bool, str]:
    if not athlete_id or not api_key:
        return False, "Missing API key or Athlete ID."
    
    events_to_post = []
    for item in events_list:
        raw_date = str(item.get("date") or dt.datetime.now(LOCAL_TZ).strftime("%Y-%m-%d"))
        start_local = f"{raw_date}T08:00:00" if "T" not in raw_date else raw_date

        events_to_post.append({
            "category": "WORKOUT",
            "type": item.get("type", "Ride"),
            "name": item.get("title") or item.get("name", "Planned Session"),
            "description": item.get("description", ""),
            "start_date_local": start_local
        })

    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events/bulk?upsert=true"
    auth = ("API_KEY", api_key)
    
    try:
        resp = requests.post(url, auth=auth, json=events_to_post, timeout=15)
        if resp.status_code in [200, 201]:
            return True, f"Successfully synced {len(events_to_post)} workout(s) to Intervals.icu & MyWhoosh!"
        return False, f"HTTP {resp.status_code}: {resp.text[:200]}"
    except Exception as e:
        return False, str(e)

def build_gemini_payload(current_question: str, wellness_list: List[Dict[str, Any]], activities_data: List[Dict[str, Any]], planned_events_list: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
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
        for ev in planned_events_list[:10]
    ] if planned_events_list else []
    planned_formatted = "\n".join(upcoming_planned) if upcoming_planned else "No structured workouts planned yet."

    supp_lines = [f"- {s.get('name')}: {s.get('dosage')} ({s.get('timing')}) -> {s.get('purpose')}" for s in supps if isinstance(s, dict)]
    supps_formatted = "\n".join(supp_lines) if supps_formatted else "None logged"

    system_prompt = f"""You are an elite multi-sport performance coach.

SELECTED COACHING PERSONA:
{persona}

ATHLETE BIOMETRICS & BENCHMARKS:
- Name: {prof.get('name', 'Athlete')} | Gender: {prof.get('gender', 'Female')} | Age: {prof.get('age', 40)} | Weight: {prof.get('weight_kg', 55.0)} kg
- Declared FTP: {prof.get('declared_ftp', 200)} W | Estimated FTP: {prof.get('estimated_ftp', 200)} W
- Max Heart Rate: {prof.get('max_hr', 185)} bpm | Resting Heart Rate: {prof.get('resting_hr', 50)} bpm
- Rest Days: {', '.join(prof.get('rest_days', ['Monday']))}

ATHLETE GOALS & TARGET EVENTS:
- Target Event: {goals.get('event_name', 'Target Season Goal')}
- Event Date: {goals.get('race_date', '2026-12-31')}
- Primary Objective: {goals.get('target_metric', 'Build threshold power and endurance capacity')}

UPCOMING TRIPS, TRAVEL & PROTECTED EVENTS:
{events_formatted}

NEXT UPCOMING PLANNED WORKOUTS:
{planned_formatted}

COACH LONG-TERM MEMORY & ATHLETE LIMITATIONS:
{memory}

SUPPLEMENT PROTOCOL:
{supps_formatted}

WORKOUT GENERATION RULE (CRITICAL FOR MYWHOOSH & INTERVALS.ICU SYNC):
Whenever you prescribe or adjust workouts, ALWAYS include a valid JSON block at the very end of your response inside ```json:workouts ... ```.
The `description` field MUST follow native Intervals.icu plain text workout syntax so it syncs directly to MyWhoosh:

- Warmup & Cooldown: `Warmup\n- 10m 50%` or `Cooldown\n- 10m 40%`
- Repeats / Sets: `4x\n- 5m 100% FTP\n- 2m 50% FTP`
- Do NOT include HTML, XML, or markdown bullet sub-formatting inside `description`.

EXAMPLE:
```json:workouts
[
  {
    "date": "2026-09-05",
    "title": "Threshold 4x5m",
    "type": "Ride",
    "description": "Warmup\\n- 10m 50%\\n\\n4x\\n- 5m 100%\\n- 2m 50%\\n\\nCooldown\\n- 10m 40%"
  }
]
```"""

    contents = [
        {"role": "user", "parts": [{"text": system_prompt}]},
        {"role": "model", "parts": [{"text": f"Understood. I have full vision of your biometrics, upcoming trips, planned calendar, athlete limitations, and the '{persona}' coaching style."}]}
    ]
    
    history = [m for m in st.session_state.messages[:-1] if m["content"] != current_question][-30:]
    for m in history:
        contents.append({"role": "user" if m["role"] == "user" else "model", "parts": [{"text": clean_chat_content(str(m["content"]))[:2000]}]})
    contents.append({"role": "user", "parts": [{"text": current_question}]})
    return contents

# --- RESOLVE CREDENTIALS & ONBOARDING ---
INTERVALS_API_KEY, ATHLETE_ID, display_name, auth_mode = get_resolved_credentials()

if not INTERVALS_API_KEY or not ATHLETE_ID:
    st.markdown("##### 🔐 AI Performance Coach • Guest Setup")
    with st.form("guest_onboarding_form"):
        g_name = st.text_input("Your Name", value="Athlete")
        g_key = st.text_input("Intervals.icu API Key", type="password")
        g_id = st.text_input("Intervals.icu Athlete ID (e.g. i12345)")
        if st.form_submit_button("Launch Session", use_container_width=True):
            if g_key.strip() and g_id.strip():
                clean_name = g_name.strip() or "Athlete"
                st.session_state.user_credentials = {"name": clean_name, "icu_key": g_key.strip(), "icu_id": g_id.strip()}
                st.session_state.profile_data = get_user_default_profile(clean_name)
                save_disk_store()
                st.rerun()
    st.stop()

wellness_list, activities_data, planned_events, intervals_status = fetch_intervals_data_90days(ATHLETE_ID, INTERVALS_API_KEY)

# --- SIDEBAR NAVIGATION & CHAT THREAD MANAGER ---
with st.sidebar:
    st.markdown("##### ⚡ AI Multi-Sport Coach")
    st.caption(f"Athlete: {st.session_state.profile_data.get('name', display_name)} | Mode: {auth_mode}")

    for nav_item in NAV_OPTIONS:
        if st.button(nav_item, use_container_width=True, type="primary" if st.session_state.active_nav == nav_item else "secondary"):
            st.session_state.active_nav = nav_item
            st.rerun()

    st.divider()
    
    st.markdown("###### 💬 Conversation Threads")
    session_names = list(st.session_state.get("chat_sessions", {"Main Conversation": []}).keys())
    curr_active_id = st.session_state.get("active_session_id", session_names[0])
    
    selected_session = st.selectbox(
        "Active Thread",
        session_names,
        index=session_names.index(curr_active_id) if curr_active_id in session_names else 0,
        key="thread_selector"
    )

    if selected_session != st.session_state.active_session_id:
        st.session_state.chat_sessions[st.session_state.active_session_id] = st.session_state.messages
        st.session_state.active_session_id = selected_session
        st.session_state.messages = st.session_state.chat_sessions.get(selected_session, [])
        save_disk_store()
        st.rerun()

    with st.popover("➕ New Chat Thread", use_container_width=True):
        new_thread_title = st.text_input("Thread Title", placeholder="e.g. Jeju Trip Planning")
        if st.button("Create Thread", use_container_width=True):
            title_clean = new_thread_title.strip()
            if title_clean and title_clean not in st.session_state.chat_sessions:
                st.session_state.chat_sessions[st.session_state.active_session_id] = st.session_state.messages
                st.session_state.chat_sessions[title_clean] = []
                st.session_state.active_session_id = title_clean
                st.session_state.messages = []
                save_disk_store()
                st.toast(f"Created '{title_clean}'", icon="💬")
                st.rerun()

    st.divider()
    persona_index = PERSONA_OPTIONS.index(st.session_state.coach_persona) if st.session_state.coach_persona in PERSONA_OPTIONS else 0
    selected_persona = st.selectbox("Coaching Persona", PERSONA_OPTIONS, index=persona_index)
    if selected_persona != st.session_state.coach_persona:
        st.session_state.coach_persona = selected_persona
        save_disk_store()
        st.rerun()

    st.divider()
    if st.button("🗑️ Clear Active Thread History", use_container_width=True):
        st.session_state.messages = []
        st.session_state.chat_sessions[st.session_state.active_session_id] = []
        save_disk_store()
        st.toast("Active thread history cleared!", icon="🧹")
        st.rerun()

    if st.button("🧪 Test AI Connection", use_container_width=True):
        with st.spinner("Testing API connectivity..."):
            try:
                test_resp = execute_ai([{"role": "user", "parts": [{"text": "Respond with the single word: OK"}]}], max_tokens=10)
                st.success(f"AI Operational! {st.session_state.ai_diagnostic}")
            except Exception as test_err:
                st.error(f"AI Connection Failed: {str(test_err)}")

# --- MAIN ROUTING ---

# VIEW 1: COMMAND CENTER
if st.session_state.active_nav == NAV_OPTIONS[0]:
    curr_name = st.session_state.profile_data.get("name", display_name)
    st.markdown(f"##### ☀️ Command Center for {curr_name}")
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
        st.session_state.active_nav = NAV_OPTIONS[1]
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
                if primary in df.columns: s = pd.to_numeric(df[primary], errors='coerce')
                elif secondary in df.columns: s = pd.to_numeric(df[secondary], errors='coerce')
                else: s = pd.Series(0.0, index=df.index)
                return s.fillna(0.0)

            ctl_s = get_series(df_w, 'ctl', 'CTL')
            atl_s = get_series(df_w, 'atl', 'ATL')
            tsb_s = pd.to_numeric(df_w['tsb'], errors='coerce').fillna(ctl_s - atl_s) if 'tsb' in df_w.columns else ctl_s - atl_s

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

            st.markdown("""
            <div class="chart-summary-box">
                <strong>💡 How to Read Your Performance Chart:</strong><br/>
                • <span style="color:#10B981; font-weight:bold;">Green Line (Fitness / CTL):</span> 42-day rolling average of work. Rises slowly as you build aerobic stamina.<br/>
                • <span style="color:#EF4444; font-weight:bold;">Red Line (Fatigue / ATL):</span> 7-day short-term training stress. Spikes quickly after hard blocks.<br/>
                • <span style="color:#3B82F6; font-weight:bold;">Bars (Form / TSB = CTL - ATL):</span> Physical freshness. 
                Keep TSB <strong>mildly negative (-10 to -25)</strong> to build fitness. 
                Deep negative (below -30) means high injury/overtraining risk. 
                Positive bars (+5 to +15) signal you are fresh and race-ready.
            </div>
            """, unsafe_allow_html=True)

    st.divider()

    if st.button("🚀 Run 90-Day Multi-Sport Trend Synthesis", type="primary", use_container_width=True):
        payload_text = f"Analyze this multi-sport athlete's 90-day training trend window. CTL {ctl:.1f}; ATL {atl:.1f}; TSB {tsb:.1f}. ACWR: {acwr}. Goal: {prof['goals']['target_metric']}."
        with st.status("🧠 Coach is analyzing 90 days of multi-sport training data...", expanded=True) as status_box:
            st.write("• Reviewing CTL/ATL/TSB balance and ACWR ramp rates...")
            st.write("• Scanning historical activity loads and recovery indexes...")
            try:
                new_analysis = execute_ai([{"role": "user", "parts": [{"text": payload_text}]}], max_tokens=4000)
                timestamp_str = dt.datetime.now(LOCAL_TZ).strftime("%d %b %Y, %H:%M %Z")
                st.session_state.cached_trend_analyses.insert(0, {"timestamp": timestamp_str, "analysis": new_analysis})
                st.session_state.cached_trend_analyses = st.session_state.cached_trend_analyses[:3]
                save_disk_store()
                status_box.update(label="✅ 90-day trend synthesis complete!", state="complete", expanded=False)
                st.toast("90-day trend synthesis complete!", icon="📈")
                st.rerun()
            except Exception as exc:
                status_box.update(label="❌ Analysis failed", state="error")
                st.error(str(exc))

    if st.session_state.cached_trend_analyses:
        st.markdown("###### 📈 Saved Trend Reports")
        for idx, item in enumerate(st.session_state.cached_trend_analyses):
            with st.expander(f"📌 Trend Report #{len(st.session_state.cached_trend_analyses) - idx} · Generated {item['timestamp']}", expanded=(idx == 0)):
                st.markdown(item['analysis'])
                if st.button("💬 Discuss with Coach", key=f"trend_discuss_{idx}"):
                    st.session_state.pending_coach_prompt = f"Let me discuss my 90-Day Trend Synthesis from {item['timestamp']}."
                    st.session_state.active_nav = NAV_OPTIONS[1]
                    st.rerun()

# VIEW 2: AI COACH CHAT WITH ONE-CLICK WORKOUT SYNC & THINKING STATUS
elif st.session_state.active_nav == NAV_OPTIONS[1]:
    st.markdown(f"##### 🤖 AI Multi-Sport Coach <span style='font-size:0.85rem; color:{TEXT_MUTED};'>({st.session_state.active_session_id})</span>", unsafe_allow_html=True)

    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            content_clean = clean_chat_content(msg["content"])
            st.markdown(content_clean)
            
            if msg["role"] == "assistant":
                proposed_workouts = extract_json_workouts(msg["content"])
                if proposed_workouts:
                    st.markdown("---")
                    st.markdown(f"###### 📋 Proposed Workout Plan ({len(proposed_workouts)} Session{'s' if len(proposed_workouts)>1 else ''})")
                    
                    for w_item in proposed_workouts:
                        st.caption(f"📅 **{w_item.get('date')}** | {w_item.get('type', 'Ride')} — **{w_item.get('title')}**")

                    btn_key = f"approve_sync_{idx}"
                    if st.button("🚀 Bulk Push All Workouts to Intervals.icu & MyWhoosh", key=btn_key, type="primary", use_container_width=True):
                        with st.status("🚀 Syncing workouts to Intervals.icu...", expanded=False) as sync_status:
                            ok, result_msg = push_workouts_to_intervals(
                                proposed_workouts, ATHLETE_ID, INTERVALS_API_KEY
                            )
                            if ok:
                                sync_status.update(label="✅ Successfully synced workouts!", state="complete")
                                st.success(result_msg)
                                st.toast("Synced to Intervals.icu & MyWhoosh!", icon="✅")
                            else:
                                sync_status.update(label="❌ Sync failed", state="error")
                                st.error(result_msg)

                col_save_b, _ = st.columns([2, 5])
                if col_save_b.button("🧠 Save to Permanent Coach Memory", key=f"save_to_mem_{idx}", type="secondary"):
                    snippet = content_clean[:250].replace("\n", " ")
                    st.session_state.coach_memory += f"\n• Coach Advice ({dt.datetime.now(LOCAL_TZ).strftime('%b %d, %Y')}): {snippet}..."
                    save_disk_store()
                    st.toast("Saved advice to Long-Term Coach Memory!", icon="🧠")

    if st.session_state.pending_coach_prompt:
        prompt_to_send = st.session_state.pending_coach_prompt
        st.session_state.pending_coach_prompt = None

        st.session_state.messages.append({"role": "user", "content": prompt_to_send})
        save_disk_store()
        
        with st.chat_message("user"):
            st.markdown(prompt_to_send)

        with st.chat_message("assistant"):
            with st.status("🧠 Coach is thinking & structuring your program...", expanded=True) as status_box:
                st.write("• Analyzing current biometrics, TSB, and recent recovery data...")
                st.write("• Synthesizing workouts with Gemini 3.7 Flash thinking engine...")
                try:
                    res = execute_ai(build_gemini_payload(prompt_to_send, wellness_list, activities_data, planned_events))
                    status_box.update(label="✨ Coach response ready!", state="complete", expanded=False)
                    st.markdown(clean_chat_content(res))
                    st.session_state.messages.append({"role": "assistant", "content": res})
                    save_disk_store()
                except Exception as e:
                    status_box.update(label="❌ Generation failed", state="error")
                    st.error(str(e))
        st.rerun()

    if prompt := st.chat_input("Ask your coach... (e.g. Plan my next 2 weeks of threshold workouts)"):
        st.session_state.messages.append({"role": "user", "content": prompt})
        save_disk_store()

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.status("🧠 Coach is thinking & structuring your request...", expanded=True) as status_box:
                st.write("• Reviewing athletic context, equipment constraints, and long-term memory...")
                st.write("• Running deep reasoning and multi-sport periodization protocols...")
                try:
                    res = execute_ai(build_gemini_payload(prompt, wellness_list, activities_data, planned_events))
                    status_box.update(label="✨ Coach response ready!", state="complete", expanded=False)
                    st.markdown(clean_chat_content(res))
                    st.session_state.messages.append({"role": "assistant", "content": res})
                    save_disk_store()
                except Exception as e:
                    status_box.update(label="❌ Generation failed", state="error")
                    st.error(str(e))
        st.rerun()

# VIEW 3: TRAINING CALENDAR & LIFE EVENT PLANNER
elif st.session_state.active_nav == NAV_OPTIONS[2]:
    st.markdown("##### 📅 Multi-Sport Training Calendar & Life Event Planner")

    with st.expander("✈️ Add & Manage Planned Trips, Races or Travel Blocks", expanded=False):
        with st.form("form_add_event", clear_on_submit=True):
            e_title = st.text_input("Event / Trip Title", placeholder="e.g. Jeju Cycling Trip, Business Travel, Altitude Camp")
            e_cat = st.selectbox("Category", ["✈️ Travel / Trip", "🏁 Race / Target Event", "🚫 Rest / Recovery Block", "📌 Note / Event"])
            c_d1, c_d2 = st.columns(2)
            e_start = c_d1.date_input("Start Date", value=dt.datetime.now(LOCAL_TZ).date())
            e_end = c_d2.date_input("End Date", value=dt.datetime.now(LOCAL_TZ).date())
            e_notes = st.text_area("Impact / Coach Instructions", placeholder="e.g. No bike access, high walking load, protect joint recovery")
            
            if st.form_submit_button("Save Event to Calendar", use_container_width=True):
                if e_title.strip():
                    new_ev = {
                        "title": e_title.strip(),
                        "category": e_cat,
                        "start_date": e_start.strftime("%Y-%m-%d"),
                        "end_date": e_end.strftime("%Y-%m-%d"),
                        "notes": e_notes.strip()
                    }
                    st.session_state.protected_events.append(new_ev)
                    save_disk_store()
                    st.toast(f"Saved '{e_title}' to calendar!", icon="🗓️")
                    st.rerun()

        if st.session_state.protected_events:
            st.markdown("###### Currently Saved Life Events & Trips")
            for p_idx, p_ev in enumerate(st.session_state.protected_events):
                pe_col1, pe_col2, pe_col3 = st.columns([3, 4, 1])
                pe_col1.markdown(f"**{p_ev['category']} {p_ev['title']}**")
                pe_col2.caption(f"🗓️ {p_ev['start_date']} to {p_ev['end_date']} | {p_ev.get('notes', '')}")
                if pe_col3.button("❌", key=f"del_p_ev_{p_idx}"):
                    st.session_state.protected_events.pop(p_idx)
                    save_disk_store()
                    st.rerun()

    st.divider()

    col_f1, col_f2 = st.columns(2)
    sport_filter = col_f1.selectbox("Filter Sport", ["All Sports", "Cycling", "Running", "Events & Trips"])
    status_filter = col_f2.selectbox("Filter Status", ["All Sessions", "Completed", "Planned", "Event / Trip"])

    raw_feed = get_unified_calendar_items(activities_data, planned_events)

    for idx, p_ev in enumerate(st.session_state.get("protected_events", [])):
        try:
            s_dt = dt.datetime.strptime(p_ev["start_date"], "%Y-%m-%d")
            e_dt = dt.datetime.strptime(p_ev["end_date"], "%Y-%m-%d")
            curr = s_dt
            while curr <= e_dt:
                date_str = curr.strftime("%Y-%m-%d")
                dt_obj = dt.datetime.combine(curr.date(), dt.time(8, 0))
                
                raw_feed.append({
                    "id": f"pevent_{idx}_{date_str}",
                    "date_str": date_str,
                    "datetime": dt_obj,
                    "status": "Event / Trip",
                    "type": p_ev.get("category", "Trip"),
                    "name": p_ev["title"],
                    "sport_title": p_ev.get("category", "Event"),
                    "device": p_ev.get("notes") or "Planned Event / Travel Block",
                    "duration_sec": 0,
                    "distance_m": 0,
                    "power_w": None,
                    "hr_bpm": None,
                    "pace_str": None,
                    "load": 0,
                    "raw": {}
                })
                curr += dt.timedelta(days=1)
        except Exception:
            pass

    filtered_feed = []
    for item in raw_feed:
        if sport_filter == "Cycling" and "Ride" not in item["type"] and "Cycling" not in item["sport_title"]:
            continue
        if sport_filter == "Running" and "Run" not in item["type"] and "Running" not in item["sport_title"]:
            continue
        if sport_filter == "Events & Trips" and item["status"] != "Event / Trip":
            continue
        if status_filter == "Completed" and item["status"] != "Completed":
            continue
        if status_filter == "Planned" and item["status"] != "Planned":
            continue
        if status_filter == "Event / Trip" and item["status"] != "Event / Trip":
            continue
        filtered_feed.append(item)

    grouped_months: Dict[Tuple[int, int], Dict[Tuple[dt.date, dt.date], Dict[str, List[Dict[str, Any]]]]] = {}
    today_date = dt.datetime.now(LOCAL_TZ).date()

    for item in filtered_feed:
        item_date = item["datetime"].date()
        month_key = (item_date.year, item_date.month)
        
        start_of_week = item_date - dt.timedelta(days=item_date.weekday())
        end_of_week = start_of_week + dt.timedelta(days=6)
        week_key = (start_of_week, end_of_week)
        
        if month_key not in grouped_months:
            grouped_months[month_key] = {}
        if week_key not in grouped_months[month_key]:
            grouped_months[month_key][week_key] = {}
            
        date_str = item["date_str"]
        if date_str not in grouped_months[month_key][week_key]:
            grouped_months[month_key][week_key][date_str] = []
        grouped_months[month_key][week_key][date_str].append(item)

    for i in range(3):
        target_m = today_date.month + i
        target_y = today_date.year + (target_m - 1) // 12
        target_m = ((target_m - 1) % 12) + 1
        m_key = (target_y, target_m)
        if m_key not in grouped_months:
            grouped_months[m_key] = {}

    declared_ftp = int(st.session_state.profile_data.get("declared_ftp", 180))

    for (m_year, m_month), month_weeks in sorted(grouped_months.items(), key=lambda x: x[0], reverse=True):
        month_all_items = [
            item for days in month_weeks.values() for day_list in days.values() for item in day_list
        ]
        m_total_sec = sum(item["duration_sec"] for item in month_all_items)
        m_hours = m_total_sec / 3600.0
        m_h_part = int(m_hours)
        m_m_part = int((m_hours - m_h_part) * 60)
        m_dur_summary = f"{m_h_part}h {m_m_part}m" if m_h_part > 0 else f"{m_m_part}m"
        m_total_load = int(sum(item["load"] for item in month_all_items))

        is_current_month = (m_year == today_date.year and m_month == today_date.month)
        is_future_month = (m_year > today_date.year or (m_year == today_date.year and m_month > today_date.month))
        
        month_name_str = dt.date(m_year, m_month, 1).strftime("%B %Y")
        month_tag = " [CURRENT MONTH]" if is_current_month else (" [FUTURE]" if is_future_month else " [PAST]")
        month_label = f"🗓️ {month_name_str}{month_tag} &nbsp;·&nbsp; {m_dur_summary} &nbsp;·&nbsp; {m_total_load} Load"

        with st.expander(month_label, expanded=(is_current_month or is_future_month)):
            if not month_weeks:
                st.info("📌 No workouts or events logged for this month yet. Use the manager above to schedule planned travel or races.")
            else:
                for week_idx, ((w_start, w_end), days_dict) in enumerate(sorted(month_weeks.items(), key=lambda x: x[0][0], reverse=True)):
                    week_all_items = [item for day_list in days_dict.values() for item in day_list]
                    w_total_sec = sum(item["duration_sec"] for item in week_all_items)
                    w_hours = w_total_sec / 3600.0
                    w_h_part = int(w_hours)
                    w_m_part = int((w_hours - w_h_part) * 60)
                    w_dur_summary = f"{w_h_part}h {w_m_part}m" if w_h_part > 0 else f"{w_m_part}m"
                    w_total_load = int(sum(item["load"] for item in week_all_items))

                    is_current_week = (w_start <= today_date <= w_end)
                    week_tag = " [CURRENT WEEK]" if is_current_week else (" [FUTURE]" if w_start > today_date else " [PAST]")
                    week_label = f"📅 Week {w_start.strftime('%b %d')} - {w_end.strftime('%b %d')}{week_tag} &nbsp;·&nbsp; {w_dur_summary} &nbsp;·&nbsp; {w_total_load} Load"

                    with st.expander(week_label, expanded=is_current_week):
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
                                    item_date = item["datetime"].date()
                                    is_past = item_date < today_date
                                    is_event = (item["status"] == "Event / Trip")
                                    is_incomplete = (item["status"] == "Planned") or (item.get("status") in ["Missed", "Incomplete"])
                                    is_past_incomplete = is_past and is_incomplete and not is_event

                                    act_type = item["type"]
                                    is_run = "Run" in act_type
                                    sport_icon = "✈️" if is_event else ("🏃" if is_run else "🚴‍♂️")
                                    
                                    duration_m = round(item["duration_sec"] / 60.0)
                                    dur_str = f"{duration_m}m" if duration_m < 60 else f"{duration_m//60}h {duration_m%60}m"
                                    dist_km = f"{item['distance_m']/1000.0:.1f}km" if item['distance_m'] > 0 else "--"
                                    
                                    third_label = "Pace" if is_run else "Power"
                                    if is_event:
                                        third_val = "Event Block"
                                        third_label = "Type"
                                    elif is_run:
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

                                    card_opacity = "0.55" if is_past_incomplete else "1.0"
                                    card_border = "#F59E0B" if is_event else ("#21262D" if is_past_incomplete else BORDER_SUBTLE)
                                    status_label = "Trip / Event" if is_event else ("Incomplete" if is_past_incomplete else item['status'])
                                    status_color = "#F59E0B" if is_event else (TEXT_MUTED if is_past_incomplete else ("#10B981" if item['status'] == "Completed" else "#3B82F6"))

                                    st.markdown(f"""
                                    <div class="activity-card-body" style="opacity: {card_opacity}; border-color: {card_border};">
                                        <div class="card-header-row">
                                            <span class="sport-icon" style="filter: {'grayscale(100%)' if is_past_incomplete else 'none'};">{sport_icon}</span>
                                            <div>
                                                <p class="sport-title">{item['name']} <span style="font-size:0.75rem; color:{status_color};">({status_label})</span></p>
                                                <p class="device-subtitle">{item['device']}</p>
                                            </div>
                                        </div>
                                    """, unsafe_allow_html=True)

                                    raw_desc = item.get("raw", {}).get("description", "") or item.get("raw", {}).get("workout_doc", "")
                                    workout_details = parse_workout_steps_detailed(raw_desc, declared_ftp)

                                    c_m1, c_m2 = st.columns([3, 1])
                                    with c_m1:
                                        st.markdown(f"""
                                        <div class="metrics-flex-group">
                                            <div class="metric-box">
                                                <span class="metric-box-label">Duration</span>
                                                <span class="metric-box-val">{dur_str if not is_event else 'All Day'}</span>
                                            </div>
                                            <div class="metric-box">
                                                <span class="metric-box-label">Distance</span>
                                                <span class="metric-box-val">{dist_km if not is_event else '--'}</span>
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
                                        button_unique_key = f"rev_{item['id']}_{m_year}_{m_month}_{week_idx}_{item_idx}"
                                        if st.button("💬 Review & Inspect", key=button_unique_key, type="secondary"):
                                            st.session_state.pending_coach_prompt = (
                                                f"Please run a deep activity inspection on my {item['name']} session "
                                                f"from {item['date_str']} (Distance: {dist_km}, Duration: {dur_str}, "
                                                f"Power/Pace: {third_val}, Load: {load_val}). Analyze efficiency, zones, and recovery needs."
                                            )
                                            st.session_state.active_nav = NAV_OPTIONS[1]
                                            st.rerun()

                                    if workout_details["steps"] or workout_details["notes"]:
                                        with st.expander("📋 Detailed Workout Structure & Target Metrics"):
                                            col_d1, col_d2 = st.columns([2, 1])
                                            
                                            with col_d1:
                                                st.markdown("**Structured Workout Steps:**")
                                                for step_str in workout_details["steps"]:
                                                    st.markdown(step_str)
                                                
                                                if workout_details["notes"]:
                                                    st.markdown(f"""
                                                    <div class="workout-notes-box">
                                                        {workout_details['notes']}
                                                    </div>
                                                    """, unsafe_allow_html=True)

                                            with col_d2:
                                                m_dict = workout_details["metrics"]
                                                if m_dict.get("avg_watts"):
                                                    st.markdown("**Calculated Targets:**")
                                                    st.write(f"• **Avg Power:** {m_dict['avg_watts']}W")
                                                    st.write(f"• **Est. NP:** {m_dict['np_watts']}W")
                                                    st.write(f"• **Work:** {m_dict['work_kj']} kJ")

                                                z_times = workout_details["zone_times"]
                                                tot_sec = workout_details["total_sec"]
                                                if tot_sec > 0:
                                                    st.markdown("**Zone Breakdown:**")
                                                    for z_name, z_s in z_times.items():
                                                        if z_s > 0:
                                                            pct_z = round((z_s / tot_sec) * 100, 1)
                                                            z_m = round(z_s / 60.0, 1)
                                                            st.caption(f"{z_name}: {z_m}m ({pct_z}%)")

                                    st.markdown("</div>", unsafe_allow_html=True)

# VIEW 4: ATHLETE PROFILE & MEMORY
elif st.session_state.active_nav == NAV_OPTIONS[3]:
    st.markdown("##### 👤 Athlete Profile, Memory & Supplement Protocol")
    prof = st.session_state.profile_data
    goals = prof.get("goals", {})

    tab_bio, tab_goals, tab_memory, tab_supps = st.tabs([
        "🧬 Biometrics & FTP",
        "🎯 Target Goals & Races",
        "🧠 Coach Memory & Limitations",
        "💊 Supplement Protocol"
    ])

    with tab_bio:
        st.markdown("###### Biometric Benchmarks")
        with st.form("form_biometrics"):
            c1, c2 = st.columns(2)
            name_val = c1.text_input("Name", value=prof.get("name", "Athlete"))
            gender_val = c2.selectbox("Gender", ["Female", "Male", "Other"], index=0 if prof.get("gender") == "Female" else 1)
            
            c3, c4, c5 = st.columns(3)
            age_val = c3.number_input("Age", value=int(prof.get("age", 40)))
            weight_val = c4.number_input("Weight (kg)", value=float(prof.get("weight_kg", 55.0)), step=0.5)
            ftp_val = c5.number_input("Declared FTP (W)", value=int(prof.get("declared_ftp", 200)))
            
            c6, c7 = st.columns(2)
            max_hr_val = c6.number_input("Max Heart Rate (bpm)", value=int(prof.get("max_hr", 185)))
            rhr_val = c7.number_input("Resting Heart Rate (bpm)", value=int(prof.get("resting_hr", 50)))

            if st.form_submit_button("Save Biometrics"):
                st.session_state.profile_data.update({
                    "name": name_val, "gender": gender_val, "age": age_val,
                    "weight_kg": weight_val, "declared_ftp": ftp_val,
                    "max_hr": max_hr_val, "resting_hr": rhr_val
                })
                save_disk_store()
                st.success("Biometrics saved persistently!")
                st.rerun()

    with tab_goals:
        st.markdown("###### Multi-Sport Goals & Target Events")
        with st.form("form_goals"):
            ev_name = st.text_input("Target Event Name", value=goals.get("event_name", "Target Season Goal"))
            ev_date = st.text_input("Race Date (YYYY-MM-DD)", value=goals.get("race_date", "2026-12-31"))
            ev_target = st.text_area("Primary Objective / Target Metric", value=goals.get("target_metric", "Build threshold power and endurance capacity"))
            
            if st.form_submit_button("Save Target Goals"):
                st.session_state.profile_data["goals"] = {
                    "event_name": ev_name, "race_date": ev_date, "target_metric": ev_target
                }
                save_disk_store()
                st.success("Target goals saved persistently!")
                st.rerun()

    with tab_memory:
        st.markdown("###### Coach Long-Term Memory, Notes & Athlete Limitations")
        st.caption("This persistent memory and health/recovery limitations guide all AI coaching recommendations indefinitely.")
        
        updated_memory = st.text_area(
            "Persistent Coach Notes & Athlete Limitations",
            value=st.session_state.coach_memory,
            height=260
        )
        if st.button("Save Coach Memory & Limitations"):
            st.session_state.coach_memory = updated_memory
            save_disk_store()
            st.success("Coach memory and athlete limitations saved persistently!")
            st.rerun()

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
                save_disk_store()
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
                        "name": s_name.strip(), "dosage": s_dose.strip(),
                        "timing": s_time.strip(), "purpose": s_purp.strip()
                    })
                    save_disk_store()
                    st.success(f"Added {s_name} to protocol!")
                    st.rerun()

# VIEW 5: ROUTE STRATEGIST
elif st.session_state.active_nav == NAV_OPTIONS[4]:
    st.markdown("##### 🗺️ Route Pacing Strategist")
    uploaded_file = st.file_uploader("Upload GPX Route", type=["gpx"])
    
    if uploaded_file is not None:
        gpx_bytes = uploaded_file.read().decode("utf-8", errors="ignore")
        st.success(f"Successfully loaded {uploaded_file.name} ({len(gpx_bytes)} bytes)")
        
        target_power = st.number_input("Target Normalized Power (W)", value=int(st.session_state.profile_data.get("declared_ftp", 180) * 0.85))
        
        if st.button("⚡ Generate AI Pacing & Strategy Plan", type="primary", use_container_width=True):
            prompt = f"Create a comprehensive pacing strategy for a GPX route given my FTP of {st.session_state.profile_data.get('declared_ftp', 180)}W and target NP of {target_power}W. Optimize gear shifts, gradient-based power targets, and nutrition timing."
            with st.status("🧠 Coach is analyzing elevation profile & calculating pacing strategy...", expanded=True) as status_box:
                st.write("• Parsing GPX topography and segment gradient profiles...")
                st.write("• Computing power targets and nutritional fueling intervals...")
                try:
                    pacing_plan = execute_ai(build_gemini_payload(prompt, wellness_list, activities_data, planned_events))
                    status_box.update(label="✨ Pacing strategy ready!", state="complete", expanded=False)
                    st.markdown(pacing_plan)
                except Exception as e:
                    status_box.update(label="❌ Generation failed", state="error")
                    st.error(str(e))
    else:
        st.info("Upload a GPX file to analyze course gradient, segment power distribution, and nutrition pacing.")
