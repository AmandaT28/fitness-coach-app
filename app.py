"""AI Performance Coach • Elite Multi-User Suite (Inline Mark Completed & Event Management)
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

# --- MULTI-USER PERSISTENCE & ISOLATION ENGINE ---
def load_disk_store() -> Dict[str, Any]:
    if os.path.exists(PERSIST_FILE):
        try:
            with open(PERSIST_FILE, "r") as f:
                return json.load(f)
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

    store = st.session_state.user_store
    try:
        with open(PERSIST_FILE, "w") as f:
            json.dump(store, f, indent=2)
    except Exception:
        pass

    if localS:
        try:
            localS.setItem("athlete_multi_user_store", store)
        except Exception:
            pass

def init_state():
    disk_data = load_disk_store()
    if not isinstance(disk_data, dict):
        disk_data = {}

    if "user_store" not in st.session_state:
        st.session_state.user_store = disk_data

    if "active_user_id" not in st.session_state:
        st.session_state.active_user_id = "owner_primary"

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
        "profile_data": u_data.get("profile_data") or DEFAULT_PROFILE.copy(),
        "coach_memory": u_data.get("coach_memory") or DEFAULT_COACH_MEMORY,
        "user_supplements": u_data.get("user_supplements") or DEFAULT_SUPPLEMENTS.copy(),
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

.date-badge-col {{ width: 50px; text-align: center; padding-top: 6px; flex-shrink: 0; }}
.date-day-name {{ font-size: 0.82rem; color: {TEXT_MUTED}; font-weight: 600; text-transform: capitalize; }}
.date-day-number {{ font-size: 1.5rem; font-weight: 800; color: {TEXT_PRIMARY}; line-height: 1.1; }}
.metrics-flex-group {{ display: flex; flex-wrap: wrap; gap: 20px; margin-top: 8px; }}
.metric-box {{ display: flex; flex-direction: column; }}
.metric-box-label {{ font-size: 0.75rem; color: {TEXT_MUTED}; margin-bottom: 2px; }}
.metric-box-val {{ font-size: 0.98rem; font-weight: 700; color: {TEXT_PRIMARY}; }}
.stButton > button[kind="secondary"] {{ background-color: #000000 !important; color: #FFFFFF !important; border: 1px solid #30363D !important; border-radius: 20px !important; padding: 4px 16px !important; font-size: 0.85rem !important; font-weight: 600 !important; }}
</style>
""", unsafe_allow_html=True)

# --- CREDENTIAL RESOLUTION ---
def get_resolved_credentials() -> Tuple[str, str, str, str]:
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

# --- MULTI-USER AUTHENTICATION & ONBOARDING GATEWAY ---
def render_auth_onboarding_gate():
    st.markdown("##### 🔐 AI Performance Coach • Multi-User Portal")
    
    auth_tab_owner, auth_tab_new = st.tabs(["🔑 Owner Login (Supabase / Secrets)", "👤 New User Onboarding"])

    with auth_tab_owner:
        with st.form("owner_login_form"):
            st.markdown("Authenticate as app owner or load default profile settings.")
            owner_passkey = st.text_input("Owner Supabase / Access Key", type="password")
            if st.form_submit_button("Access Owner Suite", use_container_width=True):
                if supabase_client or owner_passkey.strip() or secret("SUPABASE_KEY"):
                    st.session_state.active_user_id = "owner_primary"
                    
                    u_store = st.session_state.get("user_store", {}).get("owner_primary", {})
                    st.session_state.profile_data = u_store.get("profile_data") or DEFAULT_PROFILE.copy()
                    st.session_state.coach_memory = u_store.get("coach_memory") or DEFAULT_COACH_MEMORY
                    st.session_state.user_supplements = u_store.get("user_supplements") or DEFAULT_SUPPLEMENTS.copy()
                    st.session_state.chat_sessions = u_store.get("chat_sessions") or {"Main Conversation": []}
                    st.session_state.active_session_id = u_store.get("active_session_id", "Main Conversation")
                    st.session_state.messages = st.session_state.chat_sessions.get(st.session_state.active_session_id, [])
                    st.session_state.protected_events = u_store.get("protected_events", [])
                    st.session_state.cached_trend_analyses = u_store.get("cached_trend_analyses", [])

                    st.session_state.user_credentials = {
                        "name": DEFAULT_PROFILE["name"],
                        "icu_key": secret("INTERVALS_API_KEY") or "",
                        "icu_id": secret("INTERVALS_ATHLETE_ID") or "",
                        "mode": "Owner Suite"
                    }
                    save_disk_store()
                    st.success("Owner session initialized successfully!")
                    st.rerun()
                else:
                    st.error("Invalid credentials or Supabase not connected.")

    with auth_tab_new:
        st.markdown("Register your profile and connect your Intervals.icu account for personalized AI coaching.")
        with st.form("new_user_onboarding_form"):
            u_name = st.text_input("Full Name", placeholder="e.g. John Doe")
            u_email = st.text_input("Email Address", placeholder="e.g. john@example.com")
            u_key = st.text_input("Intervals.icu API Key", type="password", placeholder="Paste your Intervals API Key")
            u_id = st.text_input("Intervals.icu Athlete ID", placeholder="e.g. i12345")
            u_ftp = st.number_input("Declared FTP (W)", value=200, step=5)
            u_weight = st.number_input("Weight (kg)", value=65.0, step=0.5)
            
            if st.form_submit_button("Complete Onboarding & Launch Suite", use_container_width=True):
                if u_name.strip() and u_key.strip() and u_id.strip():
                    user_slug = re.sub(r'[^a-zA-Z0-9]', '_', u_email.strip()) or re.sub(r'[^a-zA-Z0-9]', '_', u_name.strip())
                    st.session_state.active_user_id = user_slug
                    
                    custom_profile = DEFAULT_PROFILE.copy()
                    custom_profile["name"] = u_name.strip()
                    custom_profile["declared_ftp"] = int(u_ftp)
                    custom_profile["weight_kg"] = float(u_weight)
                    
                    st.session_state.profile_data = custom_profile
                    st.session_state.coach_memory = DEFAULT_COACH_MEMORY
                    st.session_state.user_supplements = DEFAULT_SUPPLEMENTS.copy()
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
                    st.success(f"Welcome aboard, {u_name.strip()}! Initializing your performance suite...")
                    time.sleep(1)
                    st.rerun()
                else:
                    st.error("Please fill in your Name, Intervals API Key, and Athlete ID.")

INTERVALS_API_KEY, ATHLETE_ID, display_name, auth_mode = get_resolved_credentials()

if not INTERVALS_API_KEY or not ATHLETE_ID:
    render_auth_onboarding_gate()
    st.stop()

# --- BULLETPROOF WELLNESS & METRICS ENGINE ---
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

    wellness_raw = results.get("wellness", [])
    normalized_wellness = []
    
    for rec in wellness_raw:
        if not isinstance(rec, dict):
            continue
        rec_date = rec.get("id") or rec.get("date") or rec.get("start_date")
        if not rec_date:
            continue
        
        date_str = str(rec_date)[:10]
        
        ctl_val = float(rec.get("ctl") or rec.get("CTL") or rec.get("Fitness") or rec.get("fitness") or 0.0)
        atl_val = float(rec.get("atl") or rec.get("ATL") or rec.get("Fatigue") or rec.get("fatigue") or 0.0)
        
        tsb_val = rec.get("tsb") or rec.get("TSB") or rec.get("Form") or rec.get("form")
        if tsb_val is not None:
            tsb_val = float(tsb_val)
        else:
            tsb_val = ctl_val - atl_val

        sleep_val = float(
            rec.get("sleepScore") or rec.get("sleep_score") or rec.get("sleep") or 
            rec.get("sleepDuration") or rec.get("sleep_duration") or rec.get("dur") or 0.0
        )
        hrv_val = float(rec.get("hrv") or rec.get("HRV") or rec.get("rmssd") or rec.get("sdnn") or 0.0)
        rhr_val = float(rec.get("restingHR") or rec.get("rhr") or rec.get("resting_hr") or 0.0)
        load_val = float(rec.get("training_load") or rec.get("Load") or rec.get("load") or rec.get("icu_training_load") or 0.0)

        normalized_wellness.append({
            "date": date_str,
            "ctl": ctl_val,
            "atl": atl_val,
            "tsb": tsb_val,
            "sleepScore": sleep_val,
            "hrv": hrv_val,
            "restingHR": rhr_val,
            "training_load": load_val,
            "raw": rec
        })

    normalized_wellness = sorted(normalized_wellness, key=lambda x: x["date"])
    return normalized_wellness, results.get("activities", []), results.get("events", []), "Connected to Intervals.icu"

wellness_list, activities_data, planned_events, intervals_status = fetch_intervals_data_90days(ATHLETE_ID, INTERVALS_API_KEY)

def get_latest_valid_wellness(wellness_list: List[Dict[str, Any]]) -> Dict[str, float]:
    today_str = dt.datetime.now(LOCAL_TZ).date().isoformat()
    past_records = [w for w in wellness_list if w.get("date", "") <= today_str]
    if not past_records:
        past_records = wellness_list

    if not past_records:
        return {"ctl": 0.0, "atl": 0.0, "tsb": 0.0, "sleepScore": 0.0, "hrv": 0.0, "restingHR": 0.0}

    for rec in reversed(past_records):
        if rec.get("sleepScore", 0) > 0 or rec.get("hrv", 0) > 0 or rec.get("ctl", 0) > 0:
            return rec

    return past_records[-1]

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
        if sleep_score and sleep_score > 0 and sleep_score < 65:
            score -= 20
            risk_factors.append(f"Suboptimal Sleep ({sleep_score:.0f}/100)")
        if hrv and hrv > 0 and hrv < 50:
            score -= 15
            risk_factors.append(f"Suppressed HRV ({hrv:.0f} ms)")
        if rhr and rhr > 0 and rhr > 58:
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
        raise RuntimeError(f"Gemini API returned empty response: {data}")
        
    parts = candidates[0].get("content", {}).get("parts", [])
    return "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()

def execute_ai(messages_payload: List[Dict[str, Any]], max_tokens: int = 9000) -> str:
    errors = []
    models = ["gemini-3.1-pro-preview", "gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash"]
    
    for name, key in GEMINI_KEYS:
        if not key: 
            continue
        for m in models:
            try:
                res = gemini_generate(messages_payload, key, m, max_tokens=max_tokens)
                if res:
                    st.session_state.ai_diagnostic = f"Connected via {name} ({m})"
                    return res
            except Exception as exc:
                err_str = str(exc)
                errors.append(f"{name} ({m}): {err_str}")
                if "429" in err_str or "503" in err_str or "timed out" in err_str.lower():
                    time.sleep(1)
                continue
                
    error_summary = " | ".join(errors[-3:]) if errors else "No API keys configured or all models rejected request."
    raise RuntimeError(f"AI Coach Communication Error. Details: {error_summary}")

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
        
        sport_category = "Run" if is_run else ("Ride" if "Ride" in act_type or "VirtualRide" in act_type else act_type)
        completed_date_sports.add((date_str, sport_category))

        completed_items.append({
            "id": f"act_{act.get('id')}",
            "date_str": date_str,
            "datetime": dt_obj,
            "status": "Completed",
            "type": act_type,
            "name": act.get("name") or ("Running" if is_run else "Cycling"),
            "sport_title": "Running" if is_run else "Cycling",
            "device": act.get("device_name") or act.get("source") or ("Garmin via Intervals" if is_run else "Garmin Edge / MyWhoosh"),
            "duration_sec": float(act.get("moving_time") or act.get("elapsed_time") or 0),
            "distance_m": float(act.get("distance") or 0),
            "power_w": act.get("icu_weighted_avg_watts") or act.get("average_watts"),
            "hr_bpm": act.get("average_heartrate"),
            "pace_str": pace_str,
            "load": float(act.get("icu_training_load") or act.get("icu_load") or 0),
            "raw": act
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

            raw_end = str(ev.get("end_date_local") or ev.get("end_date") or raw_start)
            try:
                end_dt = dt.datetime.fromisoformat(raw_end[:19])
            except Exception:
                end_dt = start_dt

            curr_dt = start_dt.date()
            final_end_date = end_dt.date()
            while curr_dt <= final_end_date:
                dt_obj = dt.datetime(curr_dt.year, curr_dt.month, curr_dt.day, start_dt.hour, start_dt.minute, start_dt.second)
                ev_type = str(ev.get("type", "Workout"))
                is_note = ev.get("category") == "NOTE"
                date_str = dt_obj.strftime("%Y-%m-%d")
                
                ev_sport_category = "Run" if "Run" in ev_type else ("Ride" if "Ride" in ev_type or "VirtualRide" in ev_type else ev_type)
                
                if not is_note and (date_str, ev_sport_category) in completed_date_sports:
                    curr_dt += dt.timedelta(days=1)
                    continue

                planned_items.append({
                    "id": f"plan_{ev.get('id')}_{date_str}",
                    "date_str": date_str,
                    "datetime": dt_obj,
                    "status": "Planned" if not is_note else "Event / Trip",
                    "type": ev_type,
                    "name": ev.get("name") or f"Planned {ev_type}",
                    "sport_title": f"Planned {ev_type}" if not is_note else ev.get("name", "Event / Trip"),
                    "device": ev.get("description") or "Intervals.icu Planned Workout",
                    "duration_sec": float(ev.get("moving_time") or ev.get("duration") or 0),
                    "distance_m": float(ev.get("distance") or 0),
                    "power_w": None,
                    "hr_bpm": None,
                    "pace_str": None,
                    "load": float(ev.get("icu_training_load") or 0),
                    "raw": ev
                })
                curr_dt += dt.timedelta(days=1)

    protected_items = []
    for idx, p_ev in enumerate(protected_events):
        raw_start = str(p_ev.get("start_date") or dt.datetime.now(LOCAL_TZ).strftime("%Y-%m-%d"))
        raw_end = str(p_ev.get("end_date") or raw_start)
        try:
            start_date = dt.date.fromisoformat(raw_start[:10])
            end_date = dt.date.fromisoformat(raw_end[:10])
        except Exception:
            continue

        curr_dt = start_date
        while curr_dt <= end_date:
            dt_obj = dt.datetime(curr_dt.year, curr_dt.month, curr_dt.day, 8, 0, 0)
            protected_items.append({
                "id": f"prot_{idx}_{curr_dt.isoformat()}",
                "date_str": dt_obj.strftime("%Y-%m-%d"),
                "datetime": dt_obj,
                "status": "Event / Trip",
                "type": p_ev.get("category", "Event / Trip"),
                "name": p_ev.get("title", "Event / Sickness / Travel"),
                "sport_title": p_ev.get("category", "Event / Trip"),
                "device": p_ev.get("notes") or "Logged in App",
                "duration_sec": 0.0,
                "distance_m": 0.0,
                "power_w": None,
                "hr_bpm": None,
                "pace_str": None,
                "load": 0.0,
                "raw": p_ev
            })
            curr_dt += dt.timedelta(days=1)

    all_items = completed_items + planned_items + protected_items
    return sorted(all_items, key=lambda x: x["datetime"], reverse=True)

def clean_chat_content(text: str) -> str:
    cleaned = re.sub(r"```xml\s*<\?xml.*?</workout_file>\s*```", "", text or "", flags=re.S | re.I)
    cleaned = re.sub(r"```(?:json:workouts|json)\s*\[.*?\]\s*```", "", cleaned, flags=re.S | re.I)
    cleaned = re.sub(r"<icu_weekly_plan>.*?</icu_weekly_plan>", "", cleaned, flags=re.S | re.I)
    cleaned = re.sub(r"<icu_workout>.*?</icu_workout>", "", cleaned, flags=re.S | re.I)
    return cleaned.strip()

def extract_json_workouts(text: str) -> List[Dict[str, Any]]:
    plan_match = re.search(r"<icu_weekly_plan>\s*(\[.*?\])\s*</icu_weekly_plan>", text, re.S | re.I)
    if plan_match:
        try:
            return json.loads(plan_match.group(1).strip())
        except Exception:
            pass

    match = re.search(r"```(?:json:workouts|json)\s*(\[.*?\])\s*```", text, re.S | re.I)
    if not match:
        match = re.search(r"(\[\s*\{\s*\"date\".*?\}\s*\])", text, re.S)
    if match:
        json_str = match.group(1).strip()
        try:
            return json.loads(json_str)
        except Exception:
            try:
                sanitized = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', json_str)
                sanitized = re.sub(r'(?<=: ")(.*?)(?=")', lambda m: m.group(1).replace('\n', '\\n').replace('\r', ''), sanitized, flags=re.S)
                return json.loads(sanitized)
            except Exception:
                pass
    return []

def push_workouts_to_intervals(events_list: List[Dict[str, Any]], athlete_id: str, api_key: str) -> Tuple[bool, str]:
    if not athlete_id or not api_key:
        return False, "Missing API key or Athlete ID."
    
    events_to_post = []
    for item in events_list:
        raw_date = str(item.get("date") or item.get("start_date_local") or dt.datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")).strip()
        start_local = f"{raw_date}T08:00:00" if "T" not in raw_date else raw_date

        events_to_post.append({
            "category": "WORKOUT",
            "type": item.get("type", "Ride"),
            "name": item.get("title") or item.get("name", "Planned Session"),
            "description": str(item.get("description", "")).replace("\\n", "\n"),
            "start_date_local": start_local
        })

    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events/bulk?upsert=true"
    auth = ("API_KEY", api_key)
    
    try:
        resp = requests.post(url, auth=auth, json=events_to_post, timeout=15)
        if resp.status_code in [200, 201]:
            return True, f"Successfully synced {len(events_to_post)} structured workout(s) to Intervals.icu calendar!"
        return False, f"Intervals.icu HTTP {resp.status_code}: {resp.text[:250]}"
    except Exception as e:
        return False, f"Connection error during sync: {str(e)}"

def build_gemini_payload(current_question, wellness_list, gpx_content: Optional[str] = None):
    today = dt.datetime.now(LOCAL_TZ).date()
    next_monday = today + dt.timedelta(days=(0 - today.weekday()) % 7)
    if next_monday == today: next_monday += dt.timedelta(days=7)
    next_monday_str = next_monday.isoformat()
    today_str = today.isoformat()

    try:
        race_dt = dt.date.fromisoformat(st.session_state.profile_data['goals']['race_date'])
        weeks_to_race = max(0, (race_dt - today).days // 7)
    except Exception:
        weeks_to_race = 12

    if weeks_to_race > 12:
        periodization_phase = "BASE BUILDING (Focus on aerobic endurance, multi-sport volume, and structural resilience)."
    elif weeks_to_race > 4:
        periodization_phase = "BUILD PHASE (Focus on threshold intervals, brick sessions, and run/ride progression)."
    else:
        periodization_phase = "TAPER & PEAK PHASE (Focus on reducing volume while maintaining intensity, prioritizing recovery and race freshness)."

    latest_w = get_latest_valid_wellness(wellness_list)
    ctl = float(latest_w.get("ctl", 0.0))
    atl = float(latest_w.get("atl", 0.0))
    tsb = float(latest_w.get("tsb", ctl - atl))
    sleep_score = float(latest_w.get("sleepScore", 80.0))
    hrv = float(latest_w.get("hrv", 0.0))
    rhr = float(latest_w.get("restingHR", 0.0))

    acwr_val, acwr_status = TrainingLoadCalculator.calculate_acwr(wellness_list)
    
    gatekeeper_active = (tsb < -20) or (0 < sleep_score < 60) or (acwr_val > 1.35)
    if gatekeeper_active:
        gatekeeper_directive = (
            f"⚠️ MULTI-SPORT LOAD & RECOVERY GATEKEEPER ⚠️\n"
            f"Current TSB is {tsb:.1f}, Sleep Score is {sleep_score:.0f}/100, HRV is {hrv:.0f}ms, and ACWR is {acwr_val} ({acwr_status}).\n"
            f"MANDATORY RULE: Differentiate between mechanical running impact fatigue and indoor cycling load. If recovery metrics are suppressed, proactively safeguard orthopedic joints and nervous system by suggesting low-impact cross-training or rest."
        )
    else:
        gatekeeper_directive = f"Readiness Status: CLEAR (TSB: {tsb:.1f}, Sleep: {sleep_score:.0f}, HRV: {hrv:.0f}ms, ACWR: {acwr_val})."

    trend_reports = st.session_state.get('cached_trend_analyses', [])
    trend_ctx = (trend_reports[0]['analysis'] if trend_reports else 'No Trend Analysis.')[:1200]
    memory_ctx = st.session_state.get('coach_memory') or 'No long-term memory logged yet.'
    supplements_str = json.dumps(st.session_state.user_supplements, ensure_ascii=False) if st.session_state.user_supplements else 'N/A'

    gpx_injection = ""
    if gpx_content:
        gpx_injection = f"\n\n📂 ATTACHED GPX ROUTE DATA FOR ANALYSIS:\n{gpx_content[:15000]}\n(Analyze route elevation profile, climbs, descents, and provide precise pacing, gear strategy, and nutrition timing relative to FTP.)"

    system_instructions = (
        f"You are an elite multi-sport (cycling and running) coach with full calendar integration and GPX route analysis capabilities.\n"
        f"Persona: {st.session_state.coach_persona}\n"
        f"Athlete: {st.session_state.profile_data.get('name', 'Athlete')} | Discipline Focus: Cycling & Running\n"
        f"Today: {today_str} | Next Monday: {next_monday_str}\n"
        f"Goal: {st.session_state.profile_data['goals']['target_metric']} ({st.session_state.profile_data['goals']['event_name']} on {st.session_state.profile_data['goals']['race_date']})\n"
        f"Current Periodization Phase: {periodization_phase} ({weeks_to_race} weeks to event)\n"
        f"{gatekeeper_directive}\n"
        f"LONG-TERM COACHING MEMORY & ATHLETE PROFILE:\n{memory_ctx}\n\n"
        f"Supplements & Fueling: {supplements_str}\n"
        f"90-DAY TREND SYNTHESIS:\n{trend_ctx}\n"
        f"{gpx_injection}\n\n"
        "CRITICAL INTERVALS.ICU WORKOUT SYNTAX FOR MYWHOOSH (INDOOR CYCLING) AND GARMIN (RUNNING):\n"
        "To ensure workouts parse correctly into structured step graphs on Intervals.icu:\n"
        "1. Section headers (Warmup, Main Set, Cooldown) must be on their own separate lines.\n"
        "2. Repeat blocks must use native syntax where multiplier is declared followed by steps starting with '-'.\n"
        "MANDATORY: IF PRESCRIBING WORKOUTS FOR CALENDAR SYNC, ALWAYS INCLUDE A VALID JSON ARRAY inside <icu_weekly_plan> tags like this:\n"
        "<icu_weekly_plan>\n"
        "[\n"
        "  {\n"
        f"    \"name\": \"MyWhoosh Threshold Intervals\",\n"
        f"    \"type\": \"Ride\",\n"
        f"    \"date\": \"{next_monday_str}\",\n"
        f"    \"description\": \"Warmup\\n- 10m 50%\\n- 5m 70%\\n\\nMain Set 4x\\n- 5m 100%\\n- 3m 50%\\n\\nCooldown\\n- 10m 50%\"\n"
        "  }\n"
        "]\n"
        "</icu_weekly_plan>"
    )

    contents = [
        {"role": "user", "parts": [{"text": f"SYSTEM CONFIGURATION & CONTEXT:\n{system_instructions}\n\nPlease acknowledge you understand my parameters."}]},
        {"role": "model", "parts": [{"text": "Understood. I will include the <icu_weekly_plan> JSON block whenever prescribing workouts so they can be synced directly to Intervals.icu, and I am ready to analyze uploaded GPX route files."}]}
    ]

    for m in st.session_state.messages[-15:]:
        role = "user" if m["role"] == "user" else "model"
        msg_text = clean_chat_content(str(m["content"])) if role == "model" else str(m["content"])
        contents.append({"role": role, "parts": [{"text": msg_text[:2500]}]})

    contents.append({"role": "user", "parts": [{"text": str(current_question)[:2000]}]})
    return contents

# --- SIDEBAR NAVIGATION & CHAT THREAD MANAGER ---
with st.sidebar:
    st.markdown("##### ⚡ AI Multi-Sport Coach")
    st.caption(f"Athlete: {st.session_state.profile_data.get('name') or display_name or 'Not Set'} | Mode: {auth_mode}")

    for idx, nav_item in enumerate(NAV_OPTIONS):
        is_active = st.session_state.get("active_nav") == nav_item
        btn_type = "primary" if is_active else "secondary"
        if st.button(nav_item, key=f"nav_btn_{idx}", use_container_width=True, type=btn_type):
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

    col_t_new, col_t_del = st.columns(2)
    with col_t_new:
        with st.popover("➕ New Thread", use_container_width=True):
            with st.form("create_thread_form"):
                new_thread_title = st.text_input("Thread Title", placeholder="e.g. Bintan Prep")
                if st.form_submit_button("Create", use_container_width=True):
                    title_clean = new_thread_title.strip()
                    if title_clean:
                        if title_clean not in st.session_state.chat_sessions:
                            st.session_state.chat_sessions[st.session_state.active_session_id] = st.session_state.messages
                            st.session_state.chat_sessions[title_clean] = []
                            st.session_state.active_session_id = title_clean
                            st.session_state.messages = []
                            save_disk_store()
                            st.success(f"Created '{title_clean}'")
                            time.sleep(0.5)
                            st.rerun()
                        else:
                            st.error("Already exists.")
                    else:
                        st.error("Enter a title.")

    with col_t_del:
        if st.button("🗑️ Delete Thread", use_container_width=True, type="secondary", key="sidebar_del_thread_btn"):
            current_thread = st.session_state.active_session_id
            if len(st.session_state.chat_sessions) <= 1:
                st.toast("Cannot delete the last remaining thread!", icon="⚠️")
            else:
                st.session_state.chat_sessions.pop(current_thread, None)
                remaining_keys = list(st.session_state.chat_sessions.keys())
                st.session_state.active_session_id = remaining_keys[0]
                st.session_state.messages = st.session_state.chat_sessions[remaining_keys[0]]
                save_disk_store()
                st.toast(f"Deleted thread '{current_thread}'!", icon="🗑️")
                st.rerun()

    st.divider()
    persona_index = PERSONA_OPTIONS.index(st.session_state.coach_persona) if st.session_state.coach_persona in PERSONA_OPTIONS else 0
    selected_persona = st.selectbox("Coaching Persona", PERSONA_OPTIONS, index=persona_index, key="sidebar_persona_select")
    if selected_persona != st.session_state.coach_persona:
        st.session_state.coach_persona = selected_persona
        save_disk_store()
        st.rerun()

    st.divider()
    if st.button("🧹 Clear Active Thread History", use_container_width=True, key="sidebar_clear_thread_btn"):
        st.session_state.messages = []
        if st.session_state.active_session_id in st.session_state.chat_sessions:
            st.session_state.chat_sessions[st.session_state.active_session_id] = []
        save_disk_store()
        st.toast("Active thread history cleared!", icon="🧹")
        st.rerun()

    if st.button("🔄 Switch User / Logout", use_container_width=True, key="sidebar_logout_btn"):
        st.session_state.user_credentials = None
        st.session_state.active_user_id = "default_user"
        save_disk_store()
        st.rerun()

    if st.button("🧪 Test AI Connection", use_container_width=True, key="sidebar_test_ai_btn"):
        with st.spinner("Testing API connectivity..."):
            try:
                test_resp = execute_ai([{"role": "user", "parts": [{"text": "Respond with the single word: OK"}]}], max_tokens=20)
                st.success(f"AI Operational! {st.session_state.ai_diagnostic}")
            except Exception as test_err:
                st.error(f"AI Connection Failed: {str(test_err)}")

# --- MAIN ROUTING ---

# VIEW 1: COMMAND CENTER
if st.session_state.active_nav == NAV_OPTIONS[0]:
    curr_name = st.session_state.profile_data.get("name") or display_name
    today_str_ui = dt.datetime.now(LOCAL_TZ).strftime("%A, %B %d, %Y")
    st.markdown(f"##### ☀️ Command Center — {today_str_ui}")
    prof = st.session_state.profile_data

    latest_w = get_latest_valid_wellness(wellness_list)
    ctl = float(latest_w.get("ctl", 0.0))
    atl = float(latest_w.get("atl", 0.0))
    tsb = float(latest_w.get("tsb", ctl - atl))
    sleep = float(latest_w.get("sleepScore", 0.0))
    hrv = float(latest_w.get("hrv", 0.0))
    rhr = float(latest_w.get("restingHR", 0.0))

    rec = TrainingLoadCalculator.calculate_recovery_status(tsb, sleep if sleep > 0 else 82, hrv if hrv > 0 else 65, rhr if rhr > 0 else 52, "")
    acwr, acwr_status = TrainingLoadCalculator.calculate_acwr(wellness_list)

    card_border = "#10B981" if rec["score"] >= 75 else ("#F59E0B" if rec["score"] >= 50 else "#EF4444")
    st.markdown(f"""
    <div style="background:{BG_CARD}; border:1px solid {card_border}; border-radius:10px; padding:14px; margin-bottom:15px;">
        <h5 style="margin:0; color:{card_border};">💡 {rec['status']} (Readiness Index: {rec['score']}/100)</h5>
        <p style="margin:4px 0 0 0; font-size:0.9rem;"><strong>Recommendation:</strong> {rec['recommendation']}</p>
        <p style="margin:2px 0 0 0; font-size:0.8rem; color:{TEXT_MUTED};">ACWR: {acwr} ({acwr_status}) | TSB: {tsb:.1f} | Sleep: {int(sleep) if sleep > 0 else 'N/A'}/100 | HRV: {int(hrv) if hrv > 0 else 'N/A'}ms | RHR: {int(rhr) if rhr > 0 else 'N/A'}bpm</p>
    </div>
    """, unsafe_allow_html=True)

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fitness (CTL)", f"{ctl:.1f}", delta="Aerobic Base")
    m2.metric("Fatigue (ATL)", f"{atl:.1f}", delta="Recent Load")
    m3.metric("Form (TSB)", f"{tsb:.1f}", delta="Freshness")
    m4.metric("Declared FTP", f"{prof['declared_ftp']} W", delta=f"{prof['declared_ftp']/prof['weight_kg']:.2f} W/kg" if prof.get('weight_kg') else "")

    st.divider()

    if st.button("⚡ I missed a workout / Life got in the way — Rebalance my week", use_container_width=True, key="cmd_missed_workout_btn"):
        st.session_state.pending_coach_prompt = "I missed a workout today due to life circumstances. Please rebalance my training week safely while preserving rest days."
        st.session_state.active_nav = NAV_OPTIONS[1]
        st.rerun()

    st.divider()

    st.markdown("###### 📊 90-Day Performance Management Chart (CTL / ATL / TSB)")
    with st.expander("📖 Guide: How to Read the PMC Chart", expanded=False):
        st.markdown("""
        * **Fitness (CTL):** A 42-day rolling average representing long-term aerobic base.
        * **Fatigue (ATL):** A 7-day rolling average reflecting recent multi-sport stress.
        * **Form (TSB):** Fitness minus Fatigue (Freshness vs Stress balance).
        """)

    if wellness_list:
        df_w = pd.DataFrame(wellness_list)
        if 'date' in df_w.columns and not df_w.empty:
            df_w['date_parsed'] = pd.to_datetime(df_w['date'], errors='coerce')
            df_w = df_w.dropna(subset=['date_parsed']).sort_values('date_parsed')
            
            ctl_s = pd.to_numeric(df_w['ctl'], errors='coerce').fillna(0.0)
            atl_s = pd.to_numeric(df_w['atl'], errors='coerce').fillna(0.0)
            tsb_s = pd.to_numeric(df_w['tsb'], errors='coerce').fillna(ctl_s - atl_s)

            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_w['date_parsed'], y=ctl_s, name="Fitness (CTL)", line=dict(color="#10B981", width=2)))
            fig.add_trace(go.Scatter(x=df_w['date_parsed'], y=atl_s, name="Fatigue (ATL)", line=dict(color="#EF4444", width=2)))
            fig.add_trace(go.Bar(x=df_w['date_parsed'], y=tsb_s, name="Form (TSB)", marker_color=["#10B981" if val >= 0 else "#EF4444" for val in tsb_s]))
            fig.update_layout(
                height=280,
                margin=dict(l=10, r=10, t=10, b=10),
                paper_bgcolor="rgba(0,0,0,0)",
                plot_bgcolor="rgba(0,0,0,0)",
                font=dict(color=TEXT_PRIMARY, size=11),
                legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
            )
            st.plotly_chart(fig, use_container_width=True, key="cmd_center_pmc_chart")

    st.divider()

    if st.button("🚀 Run 90-Day Multi-Sport Trend Synthesis", type="primary", use_container_width=True, key="cmd_run_trend_btn"):
        payload_text = f"Analyze this multi-sport athlete's 90-day training trend window. CTL {ctl:.1f}; ATL {atl:.1f}; TSB {tsb:.1f}. HRV: {hrv}ms. Sleep: {sleep}/100. ACWR: {acwr}. Goal: {prof['goals']['target_metric']}."
        with st.spinner("Analyzing 90 days of multi-sport training data..."):
            try:
                new_analysis = execute_ai([{"role": "user", "parts": [{"text": payload_text}]}], max_tokens=9000)
                timestamp_str = dt.datetime.now(LOCAL_TZ).strftime("%d %b %Y, %H:%M %Z")
                st.session_state.cached_trend_analyses.insert(0, {"timestamp": timestamp_str, "analysis": new_analysis})
                st.session_state.cached_trend_analyses = st.session_state.cached_trend_analyses[:3]
                save_disk_store()
                st.toast("90-day trend synthesis complete!", icon="📈")
            except Exception as exc: st.error(str(exc))

    if st.session_state.cached_trend_analyses:
        st.markdown("###### 📈 Saved Trend Reports")
        for idx, item in enumerate(st.session_state.cached_trend_analyses):
            with st.expander(f"📌 Trend Report #{len(st.session_state.cached_trend_analyses) - idx} · Generated {item['timestamp']}", expanded=(idx == 0)):
                st.markdown(item['analysis'])
                if st.button("💬 Discuss with Coach", key=f"trend_discuss_{idx}"):
                    st.session_state.pending_coach_prompt = f"Let me discuss my 90-Day Trend Synthesis from {item['timestamp']}:\n\n{item['analysis']}"
                    st.session_state.active_nav = NAV_OPTIONS[1]
                    st.rerun()

# VIEW 2: AI COACH CHAT
elif st.session_state.active_nav == NAV_OPTIONS[1]:
    st.markdown(f"##### 🤖 AI Multi-Sport Coach <span style='font-size:0.85rem; color:{TEXT_MUTED};'>({st.session_state.active_session_id})</span>", unsafe_allow_html=True)

    with st.expander("🗺️ Attach GPX Route for Strategy & Pacing Analysis", expanded=False):
        uploaded_gpx = st.file_uploader("Upload course GPX file", type=["gpx"], key="chat_gpx_upload")
        gpx_extracted_text = None
        if uploaded_gpx is not None:
            try:
                gpx_extracted_text = uploaded_gpx.read().decode("utf-8", errors="ignore")
                st.success(f"Loaded '{uploaded_gpx.name}' successfully! Type your prompt below and send to analyze.")
            except Exception as e:
                st.error(f"Error reading GPX file: {str(e)}")

    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            content_clean = clean_chat_content(msg["content"])
            st.markdown(content_clean)
            
            if msg["role"] == "assistant":
                proposed_workouts = extract_json_workouts(msg["content"])
                if proposed_workouts:
                    st.markdown("---")
                    st.markdown(f"###### 📋 Plan Approved! Ready for Calendar Sync ({len(proposed_workouts)} Workout{'s' if len(proposed_workouts)>1 else ''})")
                    
                    for w_item in proposed_workouts:
                        st.caption(f"📅 **{w_item.get('date', w_item.get('start_date_local', ''))}** | {w_item.get('type', 'Ride')} — **{w_item.get('title', w_item.get('name', 'Workout'))}**")

                    btn_key = f"approve_sync_{idx}"
                    if st.button("🚀 Sync Bulk Workouts Directly to Intervals.icu Calendar", key=btn_key, type="primary", use_container_width=True):
                        with st.spinner("Pushing bulk workouts directly to Intervals.icu calendar..."):
                            ok, result_msg = push_workouts_to_intervals(
                                proposed_workouts, ATHLETE_ID, INTERVALS_API_KEY
                            )
                            if ok:
                                st.success(result_msg)
                                st.toast("Synced workouts to Intervals.icu calendar!", icon="✅")
                            else:
                                st.error(result_msg)

                col_save_b, _ = st.columns([2, 5])
                if col_save_b.button("🧠 Save to Permanent Coach Memory", key=f"save_to_mem_{idx}", type="secondary"):
                    snippet = content_clean[:250].replace("\n", " ")
                    st.session_state.coach_memory += f"\n• Coach Advice ({dt.datetime.now(LOCAL_TZ).strftime('%b %d, %Y')}): {snippet}..."
                    save_disk_store()
                    st.toast("Saved advice to Long-Term Coach Memory!", icon="🧠")

    if st.session_state.get("pending_coach_prompt"):
        prompt_to_send = st.session_state.pending_coach_prompt
        st.session_state.pending_coach_prompt = None

        st.session_state.messages.append({"role": "user", "content": prompt_to_send})
        save_disk_store()

        with st.chat_message("user"):
            st.markdown(prompt_to_send)

        with st.chat_message("assistant"):
            with st.spinner("🤖 Coach is analyzing..."):
                try:
                    res = execute_ai(build_gemini_payload(prompt_to_send, wellness_list), max_tokens=9000)
                    st.markdown(clean_chat_content(res))
                    st.session_state.messages.append({"role": "assistant", "content": res})
                    save_disk_store()
                except Exception as e:
                    st.error(str(e))
        st.rerun()

    if prompt := st.chat_input("Ask your coach or request route strategy..."):
        full_prompt = prompt
        if uploaded_gpx is not None and 'gpx_extracted_text' in locals() and gpx_extracted_text:
            full_prompt = f"{prompt}\n\n[Attached GPX File: {uploaded_gpx.name}]\n{gpx_extracted_text}"

        st.session_state.messages.append({"role": "user", "content": prompt})
        save_disk_store()

        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("🤖 Coach is analyzing your request and route profile..."):
                try:
                    res = execute_ai(build_gemini_payload(full_prompt, wellness_list), max_tokens=9000)
                    st.markdown(clean_chat_content(res))
                    st.session_state.messages.append({"role": "assistant", "content": res})
                    save_disk_store()
                except Exception as e:
                    st.error(str(e))
        st.rerun()

# VIEW 3: TRAINING CALENDAR
elif st.session_state.active_nav == NAV_OPTIONS[2]:
    st.markdown("##### 📅 Multi-Sport Training Calendar & Life Event Planner")

    with st.expander("📝 Log New Workout / Event / Travel", expanded=False):
        with st.form("sickness_travel_form"):
            status_type = st.selectbox("Category", ["Workout / Gym / Strength", "Race / Event", "Illness / Sickness", "Travel / Away", "Soreness / Fatigue", "Forced Rest Day"])
            event_title_input = st.text_input("Workout / Event Name", placeholder="e.g., Leg Strength & Core / Bintan Triathlon")
            c_d1, c_d2 = st.columns(2)
            start_d = c_d1.date_input("Start Date", value=dt.datetime.now(LOCAL_TZ).date())
            end_d = c_d2.date_input("End Date", value=dt.datetime.now(LOCAL_TZ).date())
            status_notes = st.text_area("Details / Exercises / Coach Instructions", placeholder="e.g., Squats 4x8, Deadlifts 3x5, Lunges.")
            
            if st.form_submit_button("Log to App & Intervals.icu", use_container_width=True):
                final_title = event_title_input.strip() or f"[{status_type}]"
                cat_tag = "WORKOUT" if "Workout" in status_type else "NOTE"
                payload = {
                    "category": cat_tag,
                    "type": "WeightTraining" if "Workout" in status_type else "Note",
                    "start_date_local": start_d.isoformat() + "T08:00:00",
                    "end_date_local": end_d.isoformat() + "T08:00:00",
                    "name": final_title,
                    "description": status_notes or status_type
                }
                res = requests.post(f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events", json=payload, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
                
                if cat_tag == "NOTE":
                    st.session_state.protected_events.append({
                        "title": final_title,
                        "category": status_type,
                        "start_date": start_d.isoformat(),
                        "end_date": end_d.isoformat(),
                        "notes": status_notes
                    })
                save_disk_store()

                if res.status_code in [200, 201]:
                    st.success(f"Successfully logged '{final_title}' to Intervals.icu calendar!")
                else:
                    st.warning(f"Saved locally/partially, Intervals.icu sync returned HTTP {res.status_code}")
                
                time.sleep(1)
                st.rerun()

    col_f1, col_f2 = st.columns(2)
    sport_filter = col_f1.selectbox("Filter Sport", ["All Sports", "Cycling", "Running", "Gym / Strength", "Events & Trips"])
    status_filter = col_f2.selectbox("Filter Status", ["All Sessions", "Completed", "Planned", "Event / Trip"])

    raw_feed = get_unified_calendar_items(activities_data, planned_events, st.session_state.get("protected_events", []))

    filtered_feed = []
    for item in raw_feed:
        t_lower = str(item["type"]).lower()
        if sport_filter == "Cycling" and "ride" not in t_lower and "cycling" not in item["sport_title"].lower():
            continue
        if sport_filter == "Running" and "run" not in t_lower and "running" not in item["sport_title"].lower():
            continue
        if sport_filter == "Gym / Strength" and "weight" not in t_lower and "strength" not in item["name"].lower() and "gym" not in item["name"].lower():
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

    grouped_months = {}
    today_date = dt.datetime.now(LOCAL_TZ).date()

    feed_by_date = {}
    for item in filtered_feed:
        d_str = item["date_str"]
        if d_str not in feed_by_date:
            feed_by_date[d_str] = []
        feed_by_date[d_str].append(item)

    start_range = today_date - dt.timedelta(days=30)
    end_range = today_date + dt.timedelta(days=60)

    curr_loop_date = start_range
    while curr_loop_date <= end_range:
        date_str = curr_loop_date.isoformat()
        month_key = (curr_loop_date.year, curr_loop_date.month)
        
        start_of_week = curr_loop_date - dt.timedelta(days=curr_loop_date.weekday())
        end_of_week = start_of_week + dt.timedelta(days=6)
        week_key = (start_of_week, end_of_week)
        
        if month_key not in grouped_months:
            grouped_months[month_key] = {}
        if week_key not in grouped_months[month_key]:
            grouped_months[month_key][week_key] = {}
            
        if date_str not in grouped_months[month_key][week_key]:
            grouped_months[month_key][week_key][date_str] = feed_by_date.get(date_str, [])

        curr_loop_date += dt.timedelta(days=1)

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
                        dt_obj = dt.date.fromisoformat(date_str)
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
                            if not day_items:
                                is_past_rest = dt_obj < today_date
                                rest_opacity = "0.65" if is_past_rest else "1.0"
                                st.markdown(f"""
                                <div style="background:{BG_CARD}; border:1px solid {BORDER_SUBTLE}; border-radius:12px; padding:10px 16px; margin-bottom:10px; opacity: {rest_opacity};">
                                    <div style="display: flex; align-items: center; gap: 10px;">
                                        <span>🛋️</span>
                                        <div>
                                            <p style="margin:0; font-weight:600; color:{TEXT_MUTED}; font-size:0.95rem;">Rest Day / Nothing Logged</p>
                                        </div>
                                    </div>
                                </div>
                                """, unsafe_allow_html=True)
                            else:
                                for item_idx, item in enumerate(day_items):
                                    item_date = item["datetime"].date()
                                    is_past = item_date < today_date
                                    is_event = (item["status"] == "Event / Trip")
                                    is_incomplete = (item["status"] == "Planned") or (item.get("status") in ["Missed", "Incomplete"])
                                    is_past_incomplete = is_past and is_incomplete and not is_event

                                    act_type = str(item["type"])
                                    is_run = "Run" in act_type
                                    is_gym = "Weight" in act_type or "Gym" in item["name"] or "Strength" in item["name"]
                                    sport_icon = "🏁" if is_event and ("Race" in item.get("sport_title", "") or "Race" in item.get("name", "")) else ("✈️" if is_event else ("🏋️" if is_gym else ("🏃" if is_run else "🚴‍♂️")))
                                    
                                    duration_m = round(item["duration_sec"] / 60.0)
                                    dur_str = f"{duration_m}m" if duration_m < 60 else f"{duration_m//60}h {duration_m%60}m"
                                    dist_km = f"{item['distance_m']/1000.0:.1f}km" if item['distance_m'] > 0 else "--"
                                    
                                    third_label = "Pace" if is_run else "Power"
                                    if is_event:
                                        third_val = "Event Block"
                                        third_label = "Type"
                                    elif is_run:
                                        third_val = item["pace_str"] or "--"
                                    elif is_gym:
                                        third_val = "Strength"
                                        third_label = "Focus"
                                    else:
                                        if item["power_w"]:
                                            third_val = f"{int(item['power_w'])}W"
                                        elif item.get("hr_bpm"):
                                            third_val = f"{int(item['hr_bpm'])} bpm"
                                            third_label = "Avg HR"
                                        else:
                                            third_val = "--"

                                    load_val = str(int(item["load"]))
                                    status_label = "Trip / Event" if is_event else ("Incomplete" if is_past_incomplete else item['status'])

                                    expander_title = f"{sport_icon}  {item['name']}  ·  {status_label}  ·  {dur_str if not is_event else 'All Day'}"
                                    
                                    with st.expander(expander_title, expanded=False):
                                        st.markdown(f"<p style='margin:0 0 6px 0; font-size:0.85rem; color:{TEXT_MUTED};'><strong>Device/Source:</strong> {item['device']}</p>", unsafe_allow_html=True)
                                        
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

                                        if workout_details["steps"]:
                                            st.markdown("---")
                                            st.markdown("###### 📋 Structured Workout Steps")
                                            for step_line in workout_details["steps"]:
                                                st.markdown(step_line)

                                        if raw_desc and not workout_details["steps"]:
                                            st.markdown("---")
                                            st.markdown(f"**Notes:** {raw_desc}")

                                        # --- INLINE ACTION BUTTONS (MARK COMPLETED & DELETE) ---
                                        st.markdown("---")
                                        col_act_comp, col_act_del, _ = st.columns([2, 2, 2])
                                        raw_id_str = str(item.get("raw", {}).get("id", ""))
                                        
                                        if item["status"] == "Planned" and raw_id_str:
                                            comp_btn_key = f"comp_planned_{item['id']}_{m_year}_{m_month}_{week_idx}_{item_idx}"
                                            if col_act_comp.button("💪 Mark Completed", key=comp_btn_key, type="primary"):
                                                try:
                                                    # Post completed activity status to Intervals.icu activities endpoint
                                                    act_payload = {
                                                        "start_date_local": item["raw"].get("start_date_local") or f"{item['date_str']}T08:00:00",
                                                        "type": item["raw"].get("type", "WeightTraining"),
                                                        "name": item["name"],
                                                        "moving_time": item["raw"].get("moving_time") or 3600,
                                                        "icu_training_load": item["raw"].get("icu_training_load") or 50,
                                                        "description": raw_desc
                                                    }
                                                    post_res = requests.post(f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities", json=act_payload, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
                                                    if post_res.status_code in [200, 201]:
                                                        st.toast("Workout marked completed and synced to Intervals.icu!", icon="✅")
                                                        time.sleep(0.8)
                                                        st.rerun()
                                                    else:
                                                        st.error(f"Failed to mark completed (HTTP {post_res.status_code})")
                                                except Exception as exc:
                                                    st.error(f"Error syncing completed workout: {exc}")

                                            del_btn_key = f"del_planned_{item['id']}_{m_year}_{m_month}_{week_idx}_{item_idx}"
                                            if col_act_del.button("🗑️ Delete Workout", key=del_btn_key, type="secondary"):
                                                try:
                                                    del_res = requests.delete(f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events/{raw_id_str}", auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
                                                    if del_res.status_code in [200, 204]:
                                                        st.toast("Workout deleted from Intervals.icu!", icon="🗑️")
                                                        time.sleep(0.8)
                                                        st.rerun()
                                                    else:
                                                        st.error(f"Failed to delete (HTTP {del_res.status_code})")
                                                except Exception as exc:
                                                    st.error(f"Error deleting workout: {exc}")
                                                    
                                        elif item["status"] == "Event / Trip" and item.get("id", "").startswith("prot_"):
                                            prot_idx_match = re.search(r"prot_(\d+)_", item["id"])
                                            if prot_idx_match:
                                                p_target_idx = int(prot_idx_match.group(1))
                                                del_prot_key = f"del_prot_{p_target_idx}_{m_year}_{m_month}_{week_idx}_{item_idx}"
                                                if col_act_del.button("🗑️ Delete Event", key=del_prot_key, type="secondary"):
                                                    if p_target_idx < len(st.session_state.protected_events):
                                                        st.session_state.protected_events.pop(p_target_idx)
                                                        save_disk_store()
                                                        st.toast("Logged event deleted!", icon="🗑️")
                                                        time.sleep(0.8)
                                                        st.rerun()

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
        with st.form("form_biometrics"):
            c1, c2 = st.columns(2)
            name_val = c1.text_input("Name", value=prof.get("name", ""))
            gender_val = c2.selectbox("Gender", ["Female", "Male", "Other"], index=0 if prof.get("gender") == "Female" else 1)
            
            c3, c4, c5 = st.columns(3)
            age_val = c3.number_input("Age", value=int(prof.get("age", 30)))
            weight_val = c4.number_input("Weight (kg)", value=float(prof.get("weight_kg", 65.0)), step=0.5)
            ftp_val = c5.number_input("Declared FTP (W)", value=int(prof.get("declared_ftp", 200)))
            
            c6, c7 = st.columns(2)
            max_hr_val = c6.number_input("Max Heart Rate (bpm)", value=int(prof.get("max_hr", 190)))
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
        with st.form("form_goals"):
            ev_name = st.text_input("Target Event Name", value=goals.get("event_name", "Target Event"))
            ev_date = st.text_input("Race Date (YYYY-MM-DD)", value=goals.get("race_date", dt.datetime.now(LOCAL_TZ).strftime("%Y-%m-%d")))
            ev_target = st.text_area("Primary Objective / Target Metric", value=goals.get("target_metric", "Improve performance"))
            
            if st.form_submit_button("Save Target Goals"):
                st.session_state.profile_data["goals"] = {
                    "event_name": ev_name, "race_date": ev_date, "target_metric": ev_target
                }
                save_disk_store()
                st.success("Target goals saved persistently!")
                st.rerun()

    with tab_memory:
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
        supps = st.session_state.user_supplements
        for idx, s in enumerate(supps):
            col_s1, col_s2, col_s3, col_s4 = st.columns([2, 1, 2, 1])
            col_s1.markdown(f"**{s['name']}**")
            col_s2.caption(s.get('dosage', s.get('timing', '')))
            col_s3.caption(f"🕒 {s.get('timing', '')}")
            if col_s4.button("❌", key=f"del_supp_{idx}"):
                st.session_state.user_supplements.pop(idx)
                save_disk_store()
                st.rerun()

        st.divider()
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
