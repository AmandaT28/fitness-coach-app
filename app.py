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
        "age": 43,
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
.sport-icon {{ font-size: 1.2rem; }}
.sport-title {{ font-size: 1.1rem; font-weight: 700; color: {TEXT_PRIMARY}; margin: 0; line-height: 1.2; }}
.device-subtitle {{ font-size: 0.8rem; color: {TEXT_MUTED}; margin: 0; }}
.metrics-flex-group {{ display: flex; gap: 20px; }}
.metric-box {{ display: flex; flex-direction: column; }}
.metric-box-label {{ font-size: 0.75rem; color: {TEXT_MUTED}; margin-bottom: 2px; }}
.metric-box-val {{ font-size: 0.98rem; font-weight: 700; color: {TEXT_PRIMARY}; }}
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
</style>
""", unsafe_allow_html=True)

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

def parse_workout_steps_detailed(description_text: str, declared_ftp: int = 180) -> Dict[str, Any]:
    if not description_text:
        return {"steps": [], "notes": "", "metrics": {}, "zone_times": {}, "total_sec": 0.0}
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
            if not line.startswith("-") and not line.startswith("Warmup") and not line.startswith("Main Set"):
                descriptive_notes.append(line)
                in_repeat = False

    avg_watts = round(weighted_watts_sec / total_sec) if total_sec > 0 else 0
    work_kj = round(weighted_watts_sec / 1000.0) if total_sec > 0 else 0
    np_watts = round(avg_watts * 1.05) if avg_watts > 0 else 0

    return {
        "steps": formatted_steps,
        "notes": " ".join(descriptive_notes),
        "metrics": {"avg_watts": avg_watts, "np_watts": np_watts, "work_kj": work_kj, "duration_min": round(total_sec / 60.0, 1)},
        "zone_times": zone_sec,
        "total_sec": total_sec
    }

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
            if acwr > 1.35: return acwr, "High Spike Risk (>1.35)"
            elif acwr < 0.8: return acwr, "Detraining Risk (<0.8)"
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
            status, rec = "Caution / Adaptation Required", "Prioritize rest or low-intensity Z1 active recovery."
        elif final_score < 75:
            status, rec = "Moderate Readiness", "Proceed with planned session, avoid extra volume."
        else:
            status, rec = "Primed for Work", "High readiness. Execute planned workout targets with confidence."
        return {"score": final_score, "status": status, "recommendation": rec, "risk_factors": risk_factors}

# --- ROBUST AI ENGINE WITH ROLE-ALTERNATION SANITIZATION ---
def gemini_generate(messages_payload: List[Dict[str, Any]], api_key: str, model_name: str, max_tokens: int = 4000) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    payload = {
        "contents": messages_payload,
        "generationConfig": {
            "maxOutputTokens": max_tokens,
            "temperature": 0.7
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
    models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-2.0-flash"]
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
            "device": act.get("device_name") or act.get("source") or "Garmin Device",
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
            return True, f"Successfully synced {len(events_to_post)} workout(s) to Intervals.icu!"
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

    events_formatted = "\n".join([f"- [{e.get('category', 'Event')}] {e.get('title')}: {e.get('start_date')} to {e.get('end_date')}" for e in protected_events]) if protected_events else "No upcoming trips logged."
    planned_formatted = "\n".join([f"- {ev.get('start_date_local', '')[:10]}: {ev.get('name', 'Workout')}" for ev in planned_events_list[:10]]) if planned_events_list else "No structured workouts planned."

    supp_lines = [f"- {s.get('name')}: {s.get('dosage')} ({s.get('timing')})" for s in supps if isinstance(s, dict)]
    supps_formatted = "\n".join(supp_lines) if supp_lines else "None logged"

    system_prompt = f"""You are an elite multi-sport performance coach.
PERSONA: {persona}
ATHLETE: {prof.get('name')} | FTP: {prof.get('declared_ftp')}W | Weight: {prof.get('weight_kg')}kg
GOAL: {goals.get('event_name')} ({goals.get('race_date')}) - {goals.get('target_metric')}
MEMORY & LIMITATIONS: {memory}
SUPPLEMENTS: {supps_formatted}
UPCOMING TRIPS: {events_formatted}

When prescribing workouts, include a valid JSON block at the end inside ```json:workouts ... ``` following Intervals.icu plain text syntax.
```json:workouts
[
  {{
    "date": "2026-09-05",
    "title": "Threshold 4x5m",
    "type": "Ride",
    "description": "Warmup\\n- 10m 50%\\n\\n4x\\n- 5m 100%\\n- 2m 50%\\n\\nCooldown\\n- 10m 40%"
  }}
]
```"""

    contents = [
        {"role": "user", "parts": [{"text": system_prompt}]},
        {"role": "model", "parts": [{"text": "Understood. I have loaded your biometric profile, memory, and coaching persona."}]}
    ]

    # Enforce strict role alternation & prevent consecutive same-role errors
    history = [m for m in st.session_state.messages[:-1] if m.get("content")]
    last_role = "model"
    for m in history[-20:]:
        role = "user" if m["role"] == "user" else "model"
        if role == last_role:
            role = "model" if last_role == "user" else "user"
        contents.append({"role": role, "parts": [{"text": clean_chat_content(str(m["content"]))[:2000]}]})
        last_role = role

    if last_role == "user":
        contents.append({"role": "model", "parts": [{"text": "Acknowledged. Standing by for your question."}]})

    contents.append({"role": "user", "parts": [{"text": current_question}]})
    return contents

# --- AUTH & ONBOARDING ---
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

# --- SIDEBAR NAVIGATION ---
with st.sidebar:
    st.markdown("##### ⚡ AI Multi-Sport Coach")
    st.caption(f"Athlete: {st.session_state.profile_data.get('name', display_name)} | Mode: {auth_mode}")

    for nav_item in NAV_OPTIONS:
        if st.button(nav_item, use_container_width=True, type="primary" if st.session_state.active_nav == nav_item else "secondary"):
            st.session_state.active_nav = nav_item
            st.rerun()

    st.divider()
    session_names = list(st.session_state.get("chat_sessions", {"Main Conversation": []}).keys())
    curr_active_id = st.session_state.get("active_session_id", session_names[0])
    selected_session = st.selectbox("Active Thread", session_names, index=session_names.index(curr_active_id) if curr_active_id in session_names else 0)

    if selected_session != st.session_state.active_session_id:
        st.session_state.chat_sessions[st.session_state.active_session_id] = st.session_state.messages
        st.session_state.active_session_id = selected_session
        st.session_state.messages = st.session_state.chat_sessions.get(selected_session, [])
        save_disk_store()
        st.rerun()

    if st.button("🗑️ Clear Active Thread History", use_container_width=True):
        st.session_state.messages = []
        st.session_state.chat_sessions[st.session_state.active_session_id] = []
        save_disk_store()
        st.toast("Active thread cleared!", icon="🧹")
        st.rerun()

# --- MAIN VIEW ROUTER ---
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
        <p style="margin:4px 0 0 0; font-size:0.85rem; color:{TEXT_MUTED};">ACWR: {acwr} ({acwr_status}) | TSB: {tsb:.1f} | Sleep: {sleep:.0f}/100</p>
    </div>
    """, unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fitness (CTL)", f"{ctl:.1f}", delta="Aerobic Base")
    m2.metric("Fatigue (ATL)", f"{atl:.1f}", delta="Recent Load")
    m3.metric("Form (TSB)", f"{tsb:.1f}", delta="Freshness")
    m4.metric("Declared FTP", f"{prof['declared_ftp']} W", delta=f"{prof['declared_ftp']/prof['weight_kg']:.2f} W/kg")

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
                    for w_item in proposed_workouts:
                        st.caption(f"📅 **{w_item.get('date')}** | {w_item.get('type', 'Ride')} — **{w_item.get('title')}**")
                    if st.button("🚀 Push Workouts to Intervals.icu", key=f"approve_sync_{idx}", type="primary"):
                        ok, res_msg = push_workouts_to_intervals(proposed_workouts, ATHLETE_ID, INTERVALS_API_KEY)
                        if ok: st.success(res_msg)
                        else: st.error(res_msg)

    if st.session_state.pending_coach_prompt:
        prompt_to_send = st.session_state.pending_coach_prompt
        st.session_state.pending_coach_prompt = None
        st.session_state.messages.append({"role": "user", "content": prompt_to_send})
        save_disk_store()
        st.rerun()

    if prompt := st.chat_input("Ask your coach..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        save_disk_store()
        with st.chat_message("user"):
            st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.status("🧠 Coach is thinking...", expanded=True) as status_box:
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

elif st.session_state.active_nav == NAV_OPTIONS[2]:
    st.markdown("##### 📅 Multi-Sport Training Calendar & Life Event Planner")
    st.info("Calendar management view active. Use sidebar to switch views.")

elif st.session_state.active_nav == NAV_OPTIONS[3]:
    st.markdown("##### 👤 Athlete Profile, Memory & Supplement Protocol")
    prof = st.session_state.profile_data
    with st.form("form_biometrics"):
        c1, c2 = st.columns(2)
        name_val = c1.text_input("Name", value=prof.get("name", "Athlete"))
        ftp_val = c2.number_input("Declared FTP (W)", value=int(prof.get("declared_ftp", 200)))
        if st.form_submit_button("Save Biometrics"):
            st.session_state.profile_data.update({"name": name_val, "declared_ftp": ftp_val})
            save_disk_store()
            st.success("Saved persistently!")
            st.rerun()

elif st.session_state.active_nav == NAV_OPTIONS[4]:
    st.markdown("##### 🗺️ Route Pacing Strategist")
    uploaded_file = st.file_uploader("Upload GPX Route", type=["gpx"])
    if uploaded_file:
        st.success(f"Loaded {uploaded_file.name}")
