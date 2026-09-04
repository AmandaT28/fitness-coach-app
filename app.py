"""AI Performance Coach • Elite Multi-User Suite (Production-Ready & Hardened)
Secrets required: GEMINI_API_KEY, SECONDARY_GEMINI_KEY, TERTIARY_GEMINI_KEY, SUPABASE_URL, SUPABASE_KEY.
"""
import base64
import datetime as dt
import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
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
    page_title="AI Performance Coach • Elite Multi-User Suite",
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

supabase_client = None
if SUPABASE_URL and SUPABASE_KEY and create_client:
    try:
        supabase_client = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        supabase_client = None

GEMINI_KEYS = [
    ("Primary Gemini", secret("GEMINI_API_KEY") or secret("PRIMARY_GEMINI_KEY")),
    ("Secondary Gemini", secret("SECONDARY_GEMINI_KEY")),
    ("Tertiary Gemini", secret("TERTIARY_GEMINI_KEY")),
]

AI_TIMEOUT = 60
INTERVALS_TIMEOUT = 15

NAV_OPTIONS = [
    "☀️ Command Center",
    "🤖 AI Coach & Sparring",
    "📅 Training Calendar",
    "👤 Athlete Profile & Memory"
]

PERSONA_OPTIONS = [
    "Collaborative Peer (Balanced & Brainstorming)",
    "Sports Scientist (Data & Periodization Focus)",
    "Drill Sergeant (Strict & Direct Accountability)"
]

EMPTY_PROFILE = {
    "name": "",
    "gender": "Female",
    "age": 30,
    "weight_kg": 60.0,
    "declared_ftp": 200,
    "estimated_ftp": 200,
    "max_hr": 190,
    "resting_hr": 50,
    "running_threshold_pace_sec": 300,
    "unit_system": "Metric",
    "rest_days": ["Monday"],
    "primary_sports": ["Cycling", "Running"],
    "goals": {
        "event_name": "",
        "target_metric": "",
        "race_date": "2026-12-31"
    }
}

EMPTY_COACH_MEMORY = (
    "• Equipment Setup:\n"
    "  - Bike: (e.g., Cervélo Soloist, carbon wheels, dual power meter)\n"
    "  - Running: (e.g., Shoe rotation, carbon plates)\n\n"
    "• Training Routine & Preferences:\n"
    "  - Weekly pattern: (e.g., Saturday club rides, Wednesday intervals, Sunday recovery)\n"
    "  - Preferred riding/running zones and structures\n\n"
    "• Health Constraints & Limitations:\n"
    "  - Past injuries or joint sensitivities (e.g., knee impact care, lower-back strain in aero)\n"
    "  - Hard limits on training load or mandatory rest days"
)

localS = LocalStorage() if LocalStorage else None

# --- MULTI-USER PERSISTENCE & LOGIN MEMORY ENGINE ---
def load_disk_store() -> Dict[str, Any]:
    if os.path.exists(PERSIST_FILE):
        try:
            with open(PERSIST_FILE, "r") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
    return {}

def save_disk_store():
    active_user = st.session_state.get("active_user_id", "owner_primary")
    if "user_store" not in st.session_state:
        st.session_state.user_store = {}

    active_s_id = st.session_state.get("active_session_id", "Main Conversation")
    if "chat_sessions" not in st.session_state:
        st.session_state.chat_sessions = {active_s_id: st.session_state.get("messages", [])}
    else:
        st.session_state.chat_sessions[active_s_id] = st.session_state.get("messages", [])

    st.session_state.user_store[active_user] = {
        "profile_data": st.session_state.get("profile_data"),
        "coach_persona": st.session_state.get("coach_persona"),
        "coach_memory": st.session_state.get("coach_memory"),
        "user_supplements": st.session_state.get("user_supplements"),
        "chat_sessions": st.session_state.get("chat_sessions", {}),
        "active_session_id": active_s_id,
        "messages": st.session_state.get("messages", []),
        "cached_trend_analyses": st.session_state.get("cached_trend_analyses", []),
        "protected_events": st.session_state.get("protected_events", []),
        "user_credentials": st.session_state.get("user_credentials")
    }

    master_payload = {
        "last_active_user_id": active_user,
        "logged_out_explicitly": st.session_state.get("logged_out_explicitly", False),
        "user_store": st.session_state.user_store
    }

    try:
        with open(PERSIST_FILE, "w") as f:
            json.dump(master_payload, f, indent=2)
    except Exception:
        pass

    if localS:
        try:
            localS.setItem("athlete_multi_user_master", master_payload)
        except Exception:
            pass

def init_state():
    master_disk = load_disk_store()
    if "user_store" not in master_disk:
        user_store_data = master_disk if master_disk else {}
        last_user = "owner_primary"
        logged_out = False
    else:
        user_store_data = master_disk.get("user_store", {})
        last_user = master_disk.get("last_active_user_id", "owner_primary")
        logged_out = master_disk.get("logged_out_explicitly", False)

    if "user_store" not in st.session_state:
        st.session_state.user_store = user_store_data

    if "logged_out_explicitly" not in st.session_state:
        st.session_state.logged_out_explicitly = logged_out

    if "active_user_id" not in st.session_state:
        st.session_state.active_user_id = last_user

    user_id = st.session_state.active_user_id
    if user_id not in st.session_state.user_store:
        st.session_state.user_store[user_id] = {}

    u_data = st.session_state.user_store[user_id]
    default_sessions = u_data.get("chat_sessions", {})
    if not default_sessions:
        default_sessions = {"Main Conversation": u_data.get("messages", [])}

    active_id = u_data.get("active_session_id", list(default_sessions.keys())[0])
    active_msgs = default_sessions.get(active_id, [])

    defaults = {
        "user_credentials": u_data.get("user_credentials"),
        "chat_sessions": default_sessions,
        "active_session_id": active_id,
        "messages": active_msgs,
        "active_nav": NAV_OPTIONS[0],
        "coach_persona": u_data.get("coach_persona", PERSONA_OPTIONS[0]),
        "profile_data": u_data.get("profile_data") or EMPTY_PROFILE.copy(),
        "coach_memory": u_data.get("coach_memory") or EMPTY_COACH_MEMORY,
        "user_supplements": u_data.get("user_supplements") or [],
        "protected_events": u_data.get("protected_events", []),
        "cached_trend_analyses": u_data.get("cached_trend_analyses", []),
        "pending_coach_prompt": None,
        "ai_diagnostic": None,
        "persistent_loaded": True
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_state()

# --- DESIGN SYSTEM & CSS ---
BG_APP = "#0D1117"
BG_SIDEBAR = "#161B22"
BG_CARD = "#161B22"
BORDER_SUBTLE = "#30363D"
TEXT_PRIMARY = "#F0F6FC"
TEXT_MUTED = "#8B949E"

st.markdown(f"""
<style>
header[data-testid="stHeader"] {{ background-color: {BG_APP} !important; z-index: 99 !important; }}
.main .block-container {{ padding-top: 2rem !important; padding-bottom: 5rem !important; max-width: 1000px; padding-left: 1rem !important; padding-right: 1rem !important; }}
.stApp {{ background-color: {BG_APP} !important; color: {TEXT_PRIMARY} !important; }}
section[data-testid="stSidebar"] {{ background-color: {BG_SIDEBAR} !important; border-right: 1px solid {BORDER_SUBTLE} !important; }}
section[data-testid="stSidebar"] > div {{ background-color: {BG_SIDEBAR} !important; }}
div[data-testid="stMetric"] {{ background-color: {BG_CARD}; border: 1px solid {BORDER_SUBTLE}; padding: 10px 14px; border-radius: 10px; }}
div[data-testid="stMetric"] label {{ font-size: 0.75rem !important; color: {TEXT_MUTED} !important; font-weight: 600 !important; text-transform: uppercase; letter-spacing: 0.04em; }}
div[data-testid="stMetric"] [data-testid="stMetricValue"] {{ font-size: 1.25rem !important; font-weight: 700 !important; color: {TEXT_PRIMARY} !important; }}
.date-badge-col {{ width: 45px; text-align: center; padding-top: 4px; flex-shrink: 0; }}
.date-day-name {{ font-size: 0.75rem; color: {TEXT_MUTED}; font-weight: 600; text-transform: capitalize; }}
.date-day-number {{ font-size: 1.3rem; font-weight: 800; color: {TEXT_PRIMARY}; line-height: 1.1; }}
.metrics-flex-group {{ display: flex; flex-wrap: wrap; gap: 16px; margin-top: 6px; }}
.metric-box {{ display: flex; flex-direction: column; min-width: 70px; }}
.metric-box-label {{ font-size: 0.7rem; color: {TEXT_MUTED}; margin-bottom: 2px; }}
.metric-box-val {{ font-size: 0.92rem; font-weight: 700; color: {TEXT_PRIMARY}; }}
.stButton > button[kind="secondary"] {{ background-color: #000000 !important; color: #FFFFFF !important; border: 1px solid #30363D !important; border-radius: 20px !important; padding: 4px 14px !important; font-size: 0.8rem !important; font-weight: 600 !important; }}
</style>
""", unsafe_allow_html=True)

# --- CREDENTIAL RESOLUTION ---
def get_resolved_credentials() -> Tuple[str, str, str, str]:
    if st.session_state.get("logged_out_explicitly", False):
        return "", "", "", "Unauthenticated"
    if st.session_state.get("user_credentials"):
        creds = st.session_state.user_credentials
        return (
            creds.get("icu_key", "").strip(),
            creds.get("icu_id", "").strip(),
            creds.get("name", st.session_state.profile_data.get("name", "")).strip(),
            creds.get("mode", "User Session")
        )
    sec_key = secret("INTERVALS_API_KEY") or secret("INTERVALS_KEY") or ""
    sec_id = secret("INTERVALS_ATHLETE_ID") or secret("INTERVALS_ID") or ""
    owner_name = st.session_state.profile_data.get("name") or secret("ATHLETE_NAME") or ""
    if sec_key and sec_id:
        return str(sec_key).strip(), str(sec_id).strip(), owner_name, "Owner (Auto-Secrets)"
    return "", "", st.session_state.profile_data.get("name", ""), "Unauthenticated"

def render_auth_onboarding_gate():
    st.markdown("##### 🔐 AI Performance Coach • Multi-User Portal")
    existing_users = list(st.session_state.get("user_store", {}).keys())
    auth_tab_select, auth_tab_owner, auth_tab_new = st.tabs(["👥 Switch Saved Profile", "🔑 Owner Login", "👤 New User Onboarding"])
    with auth_tab_select:
        if existing_users:
            with st.form("quick_select_user_form"):
                chosen_user = st.selectbox("Registered Profiles", existing_users)
                if st.form_submit_button("Resume Selected Profile", use_container_width=True):
                    st.session_state.active_user_id = chosen_user
                    st.session_state.logged_out_explicitly = False
                    u_store = st.session_state.user_store.get(chosen_user, {})
                    st.session_state.profile_data = u_store.get("profile_data") or EMPTY_PROFILE.copy()
                    st.session_state.coach_memory = u_store.get("coach_memory") or EMPTY_COACH_MEMORY
                    st.session_state.user_supplements = u_store.get("user_supplements") or []
                    st.session_state.chat_sessions = u_store.get("chat_sessions") or {"Main Conversation": []}
                    st.session_state.active_session_id = u_store.get("active_session_id", "Main Conversation")
                    st.session_state.messages = st.session_state.chat_sessions.get(st.session_state.active_session_id, [])
                    st.session_state.protected_events = u_store.get("protected_events", [])
                    st.session_state.cached_trend_analyses = u_store.get("cached_trend_analyses", [])
                    st.session_state.user_credentials = u_store.get("user_credentials")
                    save_disk_store()
                    st.success(f"Loaded profile for {chosen_user}!")
                    time.sleep(0.5)
                    st.rerun()
        else:
            st.info("No saved profiles found on this device yet. Please register via New User Onboarding.")
    with auth_tab_owner:
        with st.form("owner_login_form"):
            owner_passkey = st.text_input("Owner Supabase / Access Key", type="password")
            if st.form_submit_button("Access Owner Suite", use_container_width=True):
                st.session_state.active_user_id = "owner_primary"
                st.session_state.logged_out_explicitly = False
                u_store = st.session_state.get("user_store", {}).get("owner_primary", {})
                st.session_state.profile_data = u_store.get("profile_data") or EMPTY_PROFILE.copy()
                st.session_state.coach_memory = u_store.get("coach_memory") or EMPTY_COACH_MEMORY
                st.session_state.user_supplements = u_store.get("user_supplements") or []
                st.session_state.chat_sessions = u_store.get("chat_sessions") or {"Main Conversation": []}
                st.session_state.active_session_id = u_store.get("active_session_id", "Main Conversation")
                st.session_state.messages = st.session_state.chat_sessions.get(st.session_state.active_session_id, [])
                st.session_state.protected_events = u_store.get("protected_events", [])
                st.session_state.cached_trend_analyses = u_store.get("cached_trend_analyses", [])
                st.session_state.user_credentials = {
                    "name": "Owner Athlete",
                    "icu_key": secret("INTERVALS_API_KEY") or "",
                    "icu_id": secret("INTERVALS_ATHLETE_ID") or "",
                    "mode": "Owner Suite"
                }
                save_disk_store()
                st.success("Owner session initialized successfully!")
                st.rerun()
    with auth_tab_new:
        with st.form("new_user_onboarding_form"):
            u_name = st.text_input("Full Name", placeholder="e.g. Alex Mercer")
            u_email = st.text_input("Email Address", placeholder="e.g. alex@example.com")
            u_key = st.text_input("Intervals.icu API Key", type="password", placeholder="Paste your Intervals API Key")
            u_id = st.text_input("Intervals.icu Athlete ID", placeholder="e.g. i12345")
            u_ftp = st.number_input("Declared FTP (W)", value=220, step=5)
            u_weight = st.number_input("Weight (kg)", value=68.0, step=0.5)
            if st.form_submit_button("Complete Onboarding & Launch Suite", use_container_width=True):
                if u_name.strip() and u_key.strip() and u_id.strip():
                    user_slug = re.sub(r'[^a-zA-Z0-9]', '_', u_email.strip()) or re.sub(r'[^a-zA-Z0-9]', '_', u_name.strip())
                    st.session_state.active_user_id = user_slug
                    st.session_state.logged_out_explicitly = False
                    custom_profile = EMPTY_PROFILE.copy()
                    custom_profile["name"] = u_name.strip()
                    custom_profile["declared_ftp"] = int(u_ftp)
                    custom_profile["weight_kg"] = float(u_weight)
                    st.session_state.profile_data = custom_profile
                    st.session_state.coach_memory = EMPTY_COACH_MEMORY
                    st.session_state.user_supplements = []
                    st.session_state.chat_sessions = {"Main Conversation": []}
                    st.session_state.active_session_id = "Main Conversation"
                    st.session_state.messages = []
                    st.session_state.protected_events = []
                    st.session_state.cached_trend_analyses = []
                    st.session_state.user_credentials = {
                        "name": u_name.strip(),
                        "icu_key": u_key.strip(),
                        "icu_id": u_id.strip(),
                        "mode": "User Onboarding"
                    }
                    save_disk_store()
                    st.success(f"Welcome aboard, {u_name.strip()}!")
                    time.sleep(1)
                    st.rerun()

INTERVALS_API_KEY, ATHLETE_ID, display_name, auth_mode = get_resolved_credentials()
if not INTERVALS_API_KEY or not ATHLETE_ID:
    render_auth_onboarding_gate()
    st.stop()

# --- DATA FETCHING & WELLNESS ---
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

    normalized_wellness = []
    for rec in results.get("wellness", []):
        if not isinstance(rec, dict):
            continue
        rec_date = rec.get("id") or rec.get("date") or rec.get("start_date")
        if not rec_date:
            continue
        date_str = str(rec_date)[:10]
        ctl_val = float(rec.get("ctl") or rec.get("CTL") or rec.get("Fitness") or 0.0)
        atl_val = float(rec.get("atl") or rec.get("ATL") or rec.get("Fatigue") or 0.0)
        tsb_val = rec.get("tsb") or rec.get("TSB") or rec.get("Form")
        tsb_val = float(tsb_val) if tsb_val is not None else ctl_val - atl_val
        sleep_val = float(rec.get("sleepScore") or rec.get("sleep_score") or rec.get("sleep") or 0.0)
        hrv_val = float(rec.get("hrv") or rec.get("HRV") or 0.0)
        rhr_val = float(rec.get("restingHR") or rec.get("rhr") or 0.0)
        load_val = float(rec.get("training_load") or rec.get("Load") or 0.0)
        normalized_wellness.append({
            "date": date_str, "ctl": ctl_val, "atl": atl_val, "tsb": tsb_val,
            "sleepScore": sleep_val, "hrv": hrv_val, "restingHR": rhr_val,
            "training_load": load_val, "raw": rec
        })
    return sorted(normalized_wellness, key=lambda x: x["date"]), results.get("activities", []), results.get("events", []), "Connected"

wellness_list, activities_data, planned_events, intervals_status = fetch_intervals_data_90days(ATHLETE_ID, INTERVALS_API_KEY)

def get_latest_valid_wellness(wellness_list: List[Dict[str, Any]]) -> Dict[str, float]:
    today_str = dt.datetime.now(LOCAL_TZ).date().isoformat()
    past_records = [w for w in wellness_list if w.get("date", "") <= today_str] or wellness_list
    if not past_records:
        return {"ctl": 0.0, "atl": 0.0, "tsb": 0.0, "sleepScore": 0.0, "hrv": 0.0, "restingHR": 0.0}
    for rec in reversed(past_records):
        if rec.get("sleepScore", 0) > 0 or rec.get("hrv", 0) > 0 or rec.get("ctl", 0) > 0:
            return rec
    return past_records[-1]

# --- WORKOUT PARSER & VALIDATOR ENGINE ---
class WorkoutParserValidator:
    @staticmethod
    def validate_and_parse_step(line: str, declared_ftp: int) -> Dict[str, Any]:
        line = line.strip()
        if not line or line.startswith(("-", "*")):
            line = line.lstrip("-* ").strip()
        match = re.search(r"^(\d+\.?\d*)(m|s|h|km)?\s+([0-9]+%|[0-9:]+/km)?\s*(.*)$", line, re.IGNORECASE)
        if not match:
            return {"valid": False, "raw": line, "error": "Invalid syntax format"}
        val, unit, target, label = match.groups()
        duration_val = float(val)
        unit = (unit or "m").lower()
        if unit == "m": duration_sec = duration_val * 60
        elif unit == "s": duration_sec = duration_val
        elif unit == "h": duration_sec = duration_val * 3600
        elif unit == "km": duration_sec = duration_val * 300
        else: duration_sec = duration_val * 60

        if duration_sec <= 0:
            return {"valid": False, "raw": line, "error": "Negative or zero duration not allowed."}
        
        target_str = target or ""
        parsed_target = {}
        if "%" in target_str:
            pct = float(target_str.replace("%", ""))
            watts = round(declared_ftp * (pct / 100.0))
            parsed_target = {"type": "power_percent", "value": pct, "calculated_watts": watts}
        elif "/km" in target_str:
            parsed_target = {"type": "running_pace", "value": target_str}
        else:
            parsed_target = {"type": "zone", "value": target_str}

        return {"valid": True, "duration_sec": duration_sec, "target": parsed_target, "label": label, "raw": line}

    @classmethod
    def validate_workout_structure(cls, workout_dict: Dict[str, Any], declared_ftp: int) -> Tuple[bool, List[str]]:
        errors = []
        if not workout_dict.get("name"):
            errors.append("Workout is missing a title.")
        if workout_dict.get("type") not in ["Ride", "Run", "WeightTraining", "Swim"]:
            errors.append(f"Invalid sport type: {workout_dict.get('type')}")
        description = workout_dict.get("description", "")
        lines = description.split("\n")
        total_sec = 0
        for line in lines:
            l_str = line.strip()
            if not l_str or l_str in ["Warmup", "Main Set", "Cooldown"] or "x" in l_str.lower():
                continue
            res = cls.validate_and_parse_step(l_str, declared_ftp)
            if not res["valid"]:
                errors.append(f"Syntax Error in line '{l_str}': {res['error']}")
            else:
                total_sec += res["duration_sec"]
        if total_sec <= 0:
            errors.append("Workout total duration must be greater than zero.")
        return len(errors) == 0, errors

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
    work_kj = round(weighted_watts_sec / 1000.0) if total_sec > 0 else 0
    np_watts = round(avg_watts * 1.05) if avg_watts > 0 else 0
    return {
        "steps": formatted_steps, "notes": " ".join(descriptive_notes),
        "metrics": {"avg_watts": avg_watts, "np_watts": np_watts, "work_kj": work_kj, "duration_min": round(total_sec / 60.0, 1)},
        "zone_times": zone_sec, "total_sec": total_sec
    }

# --- CALCULATORS & SAFETY ---
class RunningAnalyzer:
    @staticmethod
    def format_pace(sec_per_km: float, system: str = "Metric") -> str:
        if not sec_per_km or math.isnan(sec_per_km) or sec_per_km <= 0:
            return "--:--"
        if system == "Imperial":
            sec_per_km = sec_per_km * 1.60934
        mins = int(sec_per_km // 60)
        secs = int(sec_per_km % 60)
        return f"{mins}:{secs:02d}{'/mi' if system == 'Imperial' else '/km'}"

class TrainingLoadCalculator:
    @staticmethod
    def calculate_acwr(wellness_list: List[Dict[str, Any]]) -> Tuple[float, str]:
        if not wellness_list or len(wellness_list) < 7:
            return 1.0, "Stable"
        try:
            loads = [float(w.get("training_load", 0.0) or 0.0) for w in wellness_list]
            acute = sum(loads[-7:]) / min(7.0, float(len(loads[-7:])))
            chronic_window = loads[-28:] if len(loads) >= 28 else loads
            chronic = sum(chronic_window) / min(28.0, float(len(chronic_window)))
            if chronic == 0:
                return 1.0, "Stable"
            acwr = round(acute / chronic, 2)
            if acwr > 1.35: return acwr, "High Spike Risk (>1.35)"
            elif acwr < 0.8: return acwr, "Detraining Risk (<0.8)"
            return acwr, "Optimal Ramp Rate (0.8–1.35)"
        except Exception:
            return 1.0, "Stable"

    @staticmethod
    def calculate_recovery_status(tsb: float, sleep_score: Optional[float], hrv: Optional[float], rhr: Optional[float]) -> Dict[str, Any]:
        risk_factors = []
        score = 100.0
        if tsb < -25:
            score -= 25
            risk_factors.append(f"Heavy Accumulated Fatigue (TSB {tsb:.1f}) — Form is deeply negative.")
        elif tsb < -10:
            score -= 10
        if sleep_score and 0 < sleep_score < 65:
            score -= 20
            risk_factors.append(f"Suboptimal Sleep ({sleep_score:.0f}/100) — Impairs central nervous system recovery.")
        if hrv and 0 < hrv < 50:
            score -= 15
            risk_factors.append(f"Suppressed HRV ({hrv:.0f} ms) — Indicates high autonomic stress.")
        if rhr and 0 < rhr > 58:
            score -= 10
            risk_factors.append(f"Elevated Resting HR ({rhr:.0f} bpm) — Cardiovascular strain detected.")

        final_score = max(10, min(100, int(score)))
        if final_score < 50:
            status = "Caution / Adaptation Required"
            rec = "Prioritize rest or low-intensity Z1 active recovery to protect immune and nervous systems."
        elif final_score < 75:
            status = "Moderate Readiness"
            rec = "Proceed with planned session, avoid extra volume or high-risk intensity spikes."
        else:
            status = "Primed for Work"
            rec = "High readiness. Execute planned workout targets with optimal adaptation capacity."
        return {"score": final_score, "status": status, "recommendation": rec, "risk_factors": risk_factors}

def check_scheduling_safety(target_date_str: str, protected_events: List[Dict[str, Any]]) -> Tuple[bool, str]:
    try:
        target_date = dt.date.fromisoformat(target_date_str)
    except Exception:
        return True, "Date format valid."
    for ev in protected_events:
        try:
            s_date = dt.date.fromisoformat(ev.get("start_date", ""))
            e_date = dt.date.fromisoformat(ev.get("end_date", s_date.isoformat()))
            if s_date <= target_date <= e_date:
                return False, f"Conflict detected: Date {target_date_str} falls under protected event '{ev.get('title', 'Rest/Travel/Illness')}'."
        except Exception:
            continue
    return True, "Date is clear for scheduling."

# --- AI ENGINE ---
def gemini_generate(messages_payload: List[Dict[str, Any]], api_key: str, model_name: str, max_tokens: int = 9000) -> str:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    payload = {"contents": messages_payload, "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7}}
    response = requests.post(url, headers=headers, json=payload, timeout=AI_TIMEOUT)
    if response.status_code == 429:
        raise RuntimeError(f"Quota/Rate Limit exceeded on {model_name}.")
    if response.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:250]}")
    data = response.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError("Gemini API returned empty response.")
    parts = candidates[0].get("content", {}).get("parts", [])
    return "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()

def execute_ai(messages_payload: List[Dict[str, Any]], max_tokens: int = 9000) -> str:
    errors = []
    models = ["gemini-3.1-pro-preview", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash"]
    for name, key in GEMINI_KEYS:
        if not key: continue
        for m in models:
            try:
                res = gemini_generate(messages_payload, key, m, max_tokens=max_tokens)
                if res:
                    st.session_state.ai_diagnostic = f"Connected via {name} ({m})"
                    return res
            except Exception as exc:
                errors.append(f"{name} ({m}): {str(exc)}")
                time.sleep(1)
                continue
    raise RuntimeError(f"AI Communication Error. Details: {' | '.join(errors[-3:])}")

def get_unified_calendar_items(activities: List[Dict[str, Any]], events: List[Dict[str, Any]], protected_events: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    completed_items = []
    completed_date_sports = set()
    for act in activities:
        raw_dt = str(act.get("start_date_local") or act.get("start_date") or "")
        if not raw_dt: continue
        try:
            dt_obj = dt.datetime.fromisoformat(raw_dt[:19])
        except Exception:
            continue
        act_type = str(act.get("type", "Ride"))
        is_run = "Run" in act_type
        avg_speed = float(act.get("average_speed") or 0)
        pace_str = RunningAnalyzer.format_pace(1000.0 / avg_speed) if (is_run and avg_speed > 0) else None
        date_str = dt_obj.strftime("%Y-%m-%d")
        completed_date_sports.add((date_str, "Run" if is_run else ("Ride" if "Ride" in act_type or "VirtualRide" in act_type else act_type)))
        completed_items.append({
            "id": f"act_{act.get('id')}", "date_str": date_str, "datetime": dt_obj, "status": "Completed",
            "type": act_type, "name": act.get("name") or ("Running" if is_run else "Cycling"),
            "sport_title": "Running" if is_run else "Cycling", "device": act.get("device_name") or "Garmin via Intervals",
            "duration_sec": float(act.get("moving_time") or act.get("elapsed_time") or 0),
            "distance_m": float(act.get("distance") or 0), "power_w": act.get("icu_weighted_avg_watts") or act.get("average_watts"),
            "hr_bpm": act.get("average_heartrate"), "pace_str": pace_str, "load": float(act.get("icu_training_load") or 0), "raw": act
        })

    planned_items = []
    for ev in events:
        if ev.get("category") in ["WORKOUT", "TARGET", "NOTE"] or ev.get("type") in ["Ride", "Run", "VirtualRide", "VirtualRun", "WeightTraining", "Workout"]:
            raw_start = str(ev.get("start_date_local") or ev.get("start_date") or "")
            if not raw_start: continue
            try:
                start_dt = dt.datetime.fromisoformat(raw_start[:19])
            except Exception:
                continue
            curr_dt = start_dt.date()
            final_end_date = dt.datetime.fromisoformat(str(ev.get("end_date_local") or raw_start)[:19]).date()
            while curr_dt <= final_end_date:
                dt_obj = dt.datetime(curr_dt.year, curr_dt.month, curr_dt.day, start_dt.hour, start_dt.minute, start_dt.second)
                ev_type = str(ev.get("type", "Workout"))
                is_note = ev.get("category") == "NOTE"
                date_str = dt_obj.strftime("%Y-%m-%d")
                ev_sport_cat = "Run" if "Run" in ev_type else ("Ride" if "Ride" in ev_type else ev_type)
                if not is_note and (date_str, ev_sport_cat) in completed_date_sports:
                    curr_dt += dt.timedelta(days=1)
                    continue
                planned_items.append({
                    "id": f"plan_{ev.get('id')}_{date_str}", "date_str": date_str, "datetime": dt_obj,
                    "status": "Planned" if not is_note else "Event / Trip", "type": ev_type,
                    "name": ev.get("name") or f"Planned {ev_type}", "sport_title": f"Planned {ev_type}" if not is_note else ev.get("name", "Event"),
                    "device": ev.get("description") or "Intervals.icu Planned Workout", "duration_sec": float(ev.get("moving_time") or ev.get("duration") or 0),
                    "distance_m": float(ev.get("distance") or 0), "power_w": None, "hr_bpm": None, "pace_str": None,
                    "load": float(ev.get("icu_training_load") or 0), "raw": ev
                })
                curr_dt += dt.timedelta(days=1)

    protected_items = []
    for idx, p_ev in enumerate(protected_events):
        try:
            start_date = dt.date.fromisoformat(str(p_ev.get("start_date"))[:10])
            end_date = dt.date.fromisoformat(str(p_ev.get("end_date", p_ev.get("start_date")))[:10])
        except Exception:
            continue
        curr_dt = start_date
        while curr_dt <= end_date:
            dt_obj = dt.datetime(curr_dt.year, curr_dt.month, curr_dt.day, 8, 0, 0)
            protected_items.append({
                "id": f"prot_{idx}_{curr_dt.isoformat()}", "date_str": dt_obj.strftime("%Y-%m-%d"), "datetime": dt_obj,
                "status": "Event / Trip", "type": p_ev.get("category", "Event / Trip"), "name": p_ev.get("title", "Protected Event"),
                "sport_title": p_ev.get("category", "Event / Trip"), "device": p_ev.get("notes") or "Logged in App",
                "duration_sec": 0.0, "distance_m": 0.0, "power_w": None, "hr_bpm": None, "pace_str": None, "load": 0.0, "raw": p_ev
            })
            curr_dt += dt.timedelta(days=1)

    return sorted(completed_items + planned_items + protected_items, key=lambda x: x["datetime"], reverse=True)

def clean_chat_content(text: str) -> str:
    cleaned = re.sub(r"```xml\s*<\?xml.*?</workout_file>\s*```", "", text or "", flags=re.S | re.I)
    cleaned = re.sub(r"```(?:json:workouts|json)\s*\[.*?\]\s*```", "", cleaned, flags=re.S | re.I)
    cleaned = re.sub(r"<icu_weekly_plan>.*?</icu_weekly_plan>", "", cleaned, flags=re.S | re.I)
    cleaned = re.sub(r"<icu_workout>.*?</icu_workout>", "", cleaned, flags=re.S | re.I)
    return cleaned.strip()

def extract_json_workouts(text: str) -> List[Dict[str, Any]]:
    if not text: return []
    cleaned_text = re.sub(r"```(?:json|json:workouts)?\s*", "", text, flags=re.I).replace("```", "")
    plan_match = re.search(r"<icu_weekly_plan>\s*(\[.*?\])\s*</icu_weekly_plan>", cleaned_text, re.S | re.I)
    if plan_match:
        try: return json.loads(plan_match.group(1).strip())
        except Exception: pass
    match = re.search(r"(\[\s*\{\s*\"date\".*?\}\s*\])", cleaned_text, re.S)
    if match:
        try: return json.loads(match.group(1).strip())
        except Exception: pass
    return []

def push_workouts_to_intervals(events_list: List[Dict[str, Any]], athlete_id: str, api_key: str, protected_events: List[Dict[str, Any]]) -> Tuple[bool, str]:
    if not athlete_id or not api_key: return False, "Missing credentials."
    events_to_post = []
    for item in events_list:
        raw_date = str(item.get("date") or item.get("start_date_local") or dt.datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")).strip()[:10]
        safe, msg = check_scheduling_safety(raw_date, protected_events)
        if not safe:
            return False, f"Blocked by Safety Rule: {msg}"
        start_local = f"{raw_date}T08:00:00"
        raw_type = item.get("type", "Ride")
        title_lower = str(item.get("title", "")).lower() + str(item.get("name", "")).lower()
        mapped_type = "WeightTraining" if any(k in title_lower for k in ["gym", "strength", "weight"]) or raw_type.lower() in ["weighttraining", "gym"] else raw_type
        events_to_post.append({
            "category": "WORKOUT", "type": mapped_type, "name": item.get("title") or item.get("name", "Planned Session"),
            "description": str(item.get("description", "")).replace("\\n", "\n"), "start_date_local": start_local
        })
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events/bulk?upsert=true"
    try:
        resp = requests.post(url, auth=("API_KEY", api_key), json=events_to_post, timeout=15)
        if resp.status_code in [200, 201]:
            return True, f"Successfully synced {len(events_to_post)} structured workout(s) to Intervals.icu calendar!"
        return False, f"Intervals.icu HTTP {resp.status_code}: {resp.text[:250]}"
    except Exception as e:
        return False, f"Connection error: {str(e)}"

def build_gemini_payload(current_question, wellness_list, gpx_content: Optional[str] = None):
    today = dt.datetime.now(LOCAL_TZ).date()
    next_monday = today + dt.timedelta(days=(0 - today.weekday()) % 7)
    if next_monday == today: next_monday += dt.timedelta(days=7)
    next_monday_str = next_monday.isoformat()
    try:
        weeks_to_race = max(0, (dt.date.fromisoformat(st.session_state.profile_data['goals']['race_date']) - today).days // 7)
    except Exception:
        weeks_to_race = 12

    latest_w = get_latest_valid_wellness(wellness_list)
    ctl, atl, tsb = float(latest_w.get("ctl", 0)), float(latest_w.get("atl", 0)), float(latest_w.get("tsb", 0))
    sleep_score, hrv = float(latest_w.get("sleepScore", 80)), float(latest_w.get("hrv", 0))
    acwr_val, acwr_status = TrainingLoadCalculator.calculate_acwr(wellness_list)

    gatekeeper_active = (tsb < -20) or (0 < sleep_score < 60) or (acwr_val > 1.35)
    gatekeeper_directive = (
        f"⚠️ GATEKEEPER ACTIVE ⚠️ TSB {tsb:.1f}, Sleep {sleep_score}/100, ACWR {acwr_val} ({acwr_status}). "
        "Prioritize safety and structural recovery if metrics are suppressed."
    ) if gatekeeper_active else f"Readiness CLEAR (TSB {tsb:.1f}, Sleep {sleep_score}, ACWR {acwr_val})."

    memory_ctx = st.session_state.get('coach_memory') or 'No memory.'
    supplements_str = json.dumps(st.session_state.user_supplements, ensure_ascii=False) if st.session_state.user_supplements else 'N/A'
    gpx_injection = f"\n\n📂 ATTACHED GPX ROUTE:\n{gpx_content[:15000]}" if gpx_content else ""

    system_instructions = (
        f"You are an elite multi-sport coach. Persona: {st.session_state.coach_persona}\n"
        f"Athlete: {st.session_state.profile_data.get('name', 'Athlete')} | Goal: {st.session_state.profile_data['goals']['target_metric']}\n"
        f"{gatekeeper_directive}\nLONG-TERM MEMORY:\n{memory_ctx}\nSUPPLEMENTS: {supplements_str}{gpx_injection}\n"
        "Return structured workouts in <icu_weekly_plan> JSON blocks when prescribing sessions."
    )

    contents = [
        {"role": "user", "parts": [{"text": f"SYSTEM CONFIG:\n{system_instructions}"}]},
        {"role": "model", "parts": [{"text": "Understood. Ready to assist with workouts and calendar syncs."}]}
    ]
    for m in st.session_state.messages[-15:]:
        contents.append({"role": "user" if m["role"] == "user" else "model", "parts": [{"text": clean_chat_content(str(m["content"])) if m["role"] == "model" else str(m["content"])[:2500]}]})
    contents.append({"role": "user", "parts": [{"text": str(current_question)[:2000]}]})
    return contents

# --- SIDEBAR & NAVIGATION ---
with st.sidebar:
    st.markdown("##### ⚡ AI Multi-Sport Coach")
    st.caption(f"Athlete: {st.session_state.profile_data.get('name') or display_name or 'Not Set'} | Mode: {auth_mode}")

    for idx, nav_item in enumerate(NAV_OPTIONS):
        if st.button(nav_item, key=f"nav_btn_{idx}", use_container_width=True, type="primary" if st.session_state.get("active_nav") == nav_item else "secondary"):
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

    c_s1, c_s2 = st.columns(2)
    with c_s1:
        with st.popover("➕ New", use_container_width=True):
            with st.form("new_th_form"):
                th_title = st.text_input("Title")
                if st.form_submit_button("Create") and th_title.strip():
                    st.session_state.chat_sessions[th_title.strip()] = []
                    st.session_state.active_session_id = th_title.strip()
                    st.session_state.messages = []
                    save_disk_store()
                    st.rerun()
    with c_s2:
        if st.button("🗑️ Delete", use_container_width=True, type="secondary"):
            if len(st.session_state.chat_sessions) > 1:
                st.session_state.chat_sessions.pop(st.session_state.active_session_id, None)
                remaining = list(st.session_state.chat_sessions.keys())
                st.session_state.active_session_id = remaining[0]
                st.session_state.messages = st.session_state.chat_sessions[remaining[0]]
                save_disk_store()
                st.rerun()

    st.divider()
    persona_idx = PERSONA_OPTIONS.index(st.session_state.coach_persona) if st.session_state.coach_persona in PERSONA_OPTIONS else 0
    sel_persona = st.selectbox("Persona", PERSONA_OPTIONS, index=persona_idx)
    if sel_persona != st.session_state.coach_persona:
        st.session_state.coach_persona = sel_persona
        save_disk_store()
        st.rerun()

    if st.button("🔄 Switch User / Logout", use_container_width=True):
        st.session_state.user_credentials = None
        st.session_state.logged_out_explicitly = True
        save_disk_store()
        st.rerun()

# --- MAIN ROUTING ---
if st.session_state.active_nav == NAV_OPTIONS[0]:
    st.markdown(f"##### ☀️ Command Center — {dt.datetime.now(LOCAL_TZ).strftime('%A, %B %d, %Y')}")
    prof = st.session_state.profile_data
    latest_w = get_latest_valid_wellness(wellness_list)
    ctl, atl, tsb = float(latest_w.get("ctl", 0)), float(latest_w.get("atl", 0)), float(latest_w.get("tsb", 0))
    sleep, hrv, rhr = float(latest_w.get("sleepScore", 0)), float(latest_w.get("hrv", 0)), float(latest_w.get("restingHR", 0))
    rec = TrainingLoadCalculator.calculate_recovery_status(tsb, sleep if sleep > 0 else 82, hrv if hrv > 0 else 65, rhr if rhr > 0 else 52)
    acwr, acwr_status = TrainingLoadCalculator.calculate_acwr(wellness_list)

    card_border = "#10B981" if rec["score"] >= 75 else ("#F59E0B" if rec["score"] >= 50 else "#EF4444")
    st.markdown(f"""
    <div style="background:{BG_CARD}; border:1px solid {card_border}; border-radius:10px; padding:14px; margin-bottom:15px;">
        <h5 style="margin:0; color:{card_border};">💡 {rec['status']} (Readiness Index: {rec['score']}/100)</h5>
        <p style="margin:4px 0 0 0; font-size:0.9rem;"><strong>Recommendation:</strong> {rec['recommendation']}</p>
        <p style="margin:2px 0 0 0; font-size:0.8rem; color:{TEXT_MUTED};">ACWR: {acwr} ({acwr_status}) | TSB: {tsb:.1f} (Form Balance) | Sleep: {int(sleep) if sleep > 0 else 'N/A'}/100</p>
    </div>
    """, unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fitness (CTL)", f"{ctl:.1f}", delta="Aerobic Base")
    m2.metric("Fatigue (ATL)", f"{atl:.1f}", delta="Recent Load")
    m3.metric("Form (TSB)", f"{tsb:.1f}", delta="Freshness / Stress")
    m4.metric("Declared FTP", f"{prof['declared_ftp']} W", delta=f"{prof['declared_ftp']/prof['weight_kg']:.2f} W/kg" if prof.get('weight_kg', 0) > 0 else "")

    st.divider()
    if st.button("⚡ I missed a workout / Life got in the way — Rebalance my week", use_container_width=True):
        st.session_state.pending_coach_prompt = "I missed a workout today due to life circumstances. Please rebalance my training week safely while preserving rest days."
        st.session_state.active_nav = NAV_OPTIONS[1]
        st.rerun()

    st.divider()
    st.markdown("###### 📊 90-Day Performance Management Chart (CTL / ATL / TSB)")
    if wellness_list:
        df_w = pd.DataFrame(wellness_list)
        if 'date' in df_w.columns and not df_w.empty:
            df_w['date_parsed'] = pd.to_datetime(df_w['date'], errors='coerce')
            df_w = df_w.dropna(subset=['date_parsed']).sort_values('date_parsed')
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_w['date_parsed'], y=df_w['ctl'], name="Fitness (CTL)", line=dict(color="#10B981", width=2)))
            fig.add_trace(go.Scatter(x=df_w['date_parsed'], y=df_w['atl'], name="Fatigue (ATL)", line=dict(color="#EF4444", width=2)))
            fig.add_trace(go.Bar(x=df_w['date_parsed'], y=df_w['tsb'], name="Form (TSB)", marker_color=["#10B981" if v >= 0 else "#EF4444" for v in df_w['tsb']]))
            fig.update_layout(height=280, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT_PRIMARY, size=11), legend=dict(orientation="h", y=1.02, x=1))
            st.plotly_chart(fig, use_container_width=True)

elif st.session_state.active_nav == NAV_OPTIONS[1]:
    st.markdown(f"##### 🤖 AI Multi-Sport Coach <span style='font-size:0.85rem; color:{TEXT_MUTED};'>({st.session_state.active_session_id})</span>", unsafe_allow_html=True)
    with st.expander("🗺️ Attach GPX Route for Strategy & Pacing Analysis", expanded=False):
        uploaded_gpx = st.file_uploader("Upload course GPX", type=["gpx"])
        gpx_text = uploaded_gpx.read().decode("utf-8", errors="ignore") if uploaded_gpx else None

    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            content_clean = clean_chat_content(msg["content"])
            st.markdown(content_clean)
            if msg["role"] == "assistant":
                workouts = extract_json_workouts(msg["content"])
                if workouts:
                    st.markdown("---")
                    st.markdown(f"###### 📋 Verified Workout Plan Ready ({len(workouts)} Session{'s' if len(workouts)>1 else ''})")
                    for w in workouts:
                        st.caption(f"📅 **{w.get('date', '')}** | {w.get('type')} — **{w.get('title', w.get('name'))}**")
                    if st.button("🚀 Sync Verified Workouts to Intervals.icu Calendar", key=f"sync_{idx}", type="primary", use_container_width=True):
                        with st.spinner("Validating and pushing workouts..."):
                            ok, res_msg = push_workouts_to_intervals(workouts, ATHLETE_ID, INTERVALS_API_KEY, st.session_state.get("protected_events", []))
                            if ok: st.success(res_msg)
                            else: st.error(res_msg)

    if st.session_state.get("pending_coach_prompt"):
        p_text = st.session_state.pending_coach_prompt
        st.session_state.pending_coach_prompt = None
        st.session_state.messages.append({"role": "user", "content": p_text})
        save_disk_store()
        with st.chat_message("user"): st.markdown(p_text)
        with st.chat_message("assistant"):
            with st.spinner("🤖 Coach is analyzing..."):
                res = execute_ai(build_gemini_payload(p_text, wellness_list))
                st.markdown(clean_chat_content(res))
                st.session_state.messages.append({"role": "assistant", "content": res})
                save_disk_store()
        st.rerun()

    if prompt := st.chat_input("Ask your coach..."):
        full_p = f"{prompt}\n\n[Attached GPX: {uploaded_gpx.name}]\n{gpx_text}" if gpx_text else prompt
        st.session_state.messages.append({"role": "user", "content": prompt})
        save_disk_store()
        with st.chat_message("user"): st.markdown(prompt)
        with st.chat_message("assistant"):
            with st.spinner("🤖 Analyzing..."):
                res = execute_ai(build_gemini_payload(full_p, wellness_list))
                st.markdown(clean_chat_content(res))
                st.session_state.messages.append({"role": "assistant", "content": res})
                save_disk_store()
        st.rerun()

elif st.session_state.active_nav == NAV_OPTIONS[2]:
    st.markdown("##### 📅 Multi-Sport Training Calendar & Life Event Planner")
    with st.expander("📝 Log New Workout / Event / Travel", expanded=False):
        with st.form("event_log_form"):
            st_type = st.selectbox("Category", ["Workout / Gym / Strength", "Race / Event", "Illness / Sickness", "Travel / Away", "Soreness / Fatigue", "Forced Rest Day"])
            ev_title = st.text_input("Name", placeholder="e.g., Strength & Core")
            c_d1, c_d2 = st.columns(2)
            start_d = c_d1.date_input("Start Date", value=dt.datetime.now(LOCAL_TZ).date())
            end_d = c_d2.date_input("End Date", value=dt.datetime.now(LOCAL_TZ).date())
            ev_notes = st.text_area("Details / Notes")
            if st.form_submit_button("Log Event", use_container_width=True):
                ftitle = ev_title.strip() or f"[{st_type}]"
                cat_tag = "WORKOUT" if "Workout" in st_type else "NOTE"
                payload = {
                    "category": cat_tag, "type": "WeightTraining" if "Workout" in st_type or "Gym" in st_type else "Note",
                    "start_date_local": start_d.isoformat() + "T08:00:00",
                    "end_date_local": (end_d + dt.timedelta(days=1)).isoformat() + "T08:00:00",
                    "name": ftitle, "description": ev_notes or st_type
                }
                requests.post(f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events", json=payload, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
                if cat_tag == "NOTE":
                    st.session_state.protected_events.append({"title": ftitle, "category": st_type, "start_date": start_d.isoformat(), "end_date": end_d.isoformat(), "notes": ev_notes})
                save_disk_store()
                st.success("Successfully logged event!")
                time.sleep(1)
                st.rerun()

    raw_feed = get_unified_calendar_items(activities_data, planned_events, st.session_state.get("protected_events", []))
    for item in raw_feed[:30]:
        st.markdown(f"• **{item['date_str']}** | {item['sport_title']} — {item['name']} ({item['status']})")

elif st.session_state.active_nav == NAV_OPTIONS[3]:
    st.markdown("##### 👤 Athlete Profile, Memory & Supplement Protocol")
    prof = st.session_state.profile_data
    tab_bio, tab_goals, tab_memory, tab_supps = st.tabs(["🧬 Biometrics", "🎯 Goals", "🧠 Coach Memory", "💊 Supplements"])
    with tab_bio:
        with st.form("bio_form"):
            name_v = st.text_input("Name", value=prof.get("name", ""))
            ftp_v = st.number_input("Declared FTP (W)", value=int(prof.get("declared_ftp", 200)))
            wt_v = st.number_input("Weight (kg)", value=float(prof.get("weight_kg", 60.0)))
            if st.form_submit_button("Save Biometrics"):
                prof.update({"name": name_v, "declared_ftp": ftp_v, "weight_kg": wt_v})
                save_disk_store()
                st.success("Saved successfully!")
                st.rerun()
    with tab_goals:
        with st.form("goals_form"):
            ev_name = st.text_input("Target Event Name", value=prof["goals"].get("event_name", ""))
            ev_date = st.text_input("Race Date (YYYY-MM-DD)", value=prof["goals"].get("race_date", "2026-12-31"))
            ev_target = st.text_area("Objective", value=prof["goals"].get("target_metric", ""))
            if st.form_submit_button("Save Goals"):
                prof["goals"] = {"event_name": ev_name, "race_date": ev_date, "target_metric": ev_target}
                save_disk_store()
                st.success("Saved successfully!")
                st.rerun()
    with tab_memory:
        mem_v = st.text_area("Persistent Coach Notes & Limitations", value=st.session_state.coach_memory, height=250)
        if st.button("Save Memory"):
            st.session_state.coach_memory = mem_v
            save_disk_store()
            st.success("Memory updated!")
            st.rerun()
    with tab_supps:
        for idx, s in enumerate(st.session_state.user_supplements):
            st.markdown(f"**{s['name']}** — {s.get('dosage')} ({s.get('timing')})")
        with st.form("supp_form"):
            s_name = st.text_input("Supplement Name")
            s_dose = st.text_input("Dosage")
            if st.form_submit_button("Add Supplement") and s_name.strip():
                st.session_state.user_supplements.append({"name": s_name.strip(), "dosage": s_dose.strip()})
                save_disk_store()
                st.rerun()
