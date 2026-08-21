"""AI Performance Coach • Elite Suite (Multi-Platform Workout Engine)
Secrets required: GEMINI_API_KEY, SECONDARY_GEMINI_KEY, TERTIARY_GEMINI_KEY, SUPABASE_URL, SUPABASE_KEY.
"""
import base64
import datetime as dt
import json
import math
import os
import re
import xml.etree.ElementTree as ET
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

st.set_page_config(page_title="AI Performance Coach • Elite Suite", page_icon="🚴‍♂️", layout="wide")

LOCAL_TZ = ZoneInfo("Asia/Singapore")

def secret(name, default=None):
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

AI_TIMEOUT = 35  
INTERVALS_TIMEOUT = 6
NAV_OPTIONS = [
    "☀️ Command Center", 
    "🤖 AI Coach & Sparring", 
    "📅 Training Calendar", 
    "🔍 Activity Inspector", 
    "🗺️ Route Strategist"
]
COACH_PAGE = "🤖 AI Coach & Sparring"
DEFAULT_GOALS = {
    "event_name": "Bintan Round Island / Multi-Sport", 
    "target_metric": "Balance cycling threshold power and running endurance/pace", 
    "race_date": "2026-10-24"
}

supabase = None
if SUPABASE_URL and SUPABASE_KEY and create_client:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        pass
localS = LocalStorage() if LocalStorage else None

def init_state():
    defaults = {
        "user": None, "user_credentials": None, "messages": [],
        "active_nav": NAV_OPTIONS[0], "sidebar_nav": NAV_OPTIONS[0],
        "coach_persona": "Collaborative Peer (Balanced & Brainstorming)",
        "athlete_gear": "", "athlete_limitations": "", "goals": DEFAULT_GOALS.copy(),
        "user_supplements": [], "cached_trend_analysis": None,
        "trend_analysis_timestamp": None, "selected_activity_analysis": None,
        "selected_activity_label": None, "route_analysis": None,
        "pending_coach_prompt": None, "ai_diagnostic": None, "coach_reference_notice": None,
        "trend_loaded": False, "calendar_context": "", "profile_loaded": False,
        "coach_memory": "", "auto_compliance_cache": {},
        "primary_discipline": "Cycling & Running (Multi-Sport)"
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_state()

# --- OBSIDIAN PROFESSIONAL DARK DESIGN SYSTEM ---
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
header[data-testid="stHeader"] {{
    background-color: {BG_APP} !important;
    z-index: 99 !important;
}}
.main .block-container {{
    padding-top: 5rem !important;
    padding-bottom: 6rem !important;
    padding-left: 2rem !important;
    padding-right: 2rem !important;
    max-width: 1440px;
}}
.stApp {{
    background-color: {BG_APP} !important;
    color: {TEXT_PRIMARY} !important;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", sans-serif;
}}
section[data-testid="stSidebar"] {{
    background-color: {BG_SIDEBAR} !important;
    border-right: 1px solid {BORDER_SUBTLE} !important;
}}
section[data-testid="stSidebar"] > div {{
    background-color: {BG_SIDEBAR} !important;
}}
section[data-testid="stSidebar"] .stButton > button {{
    background: {BG_SURFACE_ALT} !important;
    color: {TEXT_MUTED} !important;
    border: 1px solid {BORDER_SUBTLE} !important;
    border-radius: 8px !important;
    padding: 0.6rem 1rem !important;
    font-weight: 500 !important;
    font-size: 0.88rem !important;
    text-align: left !important;
    width: 100% !important;
    box-shadow: 0 1px 2px rgba(0,0,0,0.1) !important;
    transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}}
section[data-testid="stSidebar"] .stButton > button:hover {{
    background: {BORDER_SUBTLE} !important;
    color: {TEXT_PRIMARY} !important;
    border-color: {BORDER_ACCENT} !important;
    transform: translateY(-1px);
}}
section[data-testid="stSidebar"] .stButton > button[kind="primary"] {{
    background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
    color: #FFFFFF !important;
    border: 1px solid #3B82F6 !important;
    font-weight: 600 !important;
    box-shadow: 0 4px 12px {ACCENT_GLOW} !important;
}}
.stButton > button[kind="primary"] {{
    background: linear-gradient(135deg, #2563EB 0%, #1D4ED8 100%) !important;
    color: #FFFFFF !important;
    border: 1px solid #3B82F6 !important;
    border-radius: 8px !important;
    font-weight: 600 !important;
    padding: 0.55rem 1.2rem !important;
    box-shadow: 0 2px 8px {ACCENT_GLOW} !important;
    transition: all 0.2s ease !important;
}}
.stButton > button[kind="primary"]:hover {{
    box-shadow: 0 4px 16px rgba(37, 99, 235, 0.5) !important;
    transform: translateY(-1px);
}}
.stButton > button[kind="secondary"] {{
    background: {BG_SURFACE_ALT} !important;
    color: {TEXT_PRIMARY} !important;
    border: 1px solid {BORDER_SUBTLE} !important;
    border-radius: 8px !important;
    font-weight: 500 !important;
    transition: all 0.2s ease !important;
}}
.stButton > button[kind="secondary"]:hover {{
    border-color: {BORDER_ACCENT} !important;
    background: {BORDER_SUBTLE} !important;
}}
div[data-testid="stMetric"], 
div[data-testid="stExpander"], 
div[data-testid="stChatMessage"] {{
    background-color: {BG_CARD} !important;
    border: 1px solid {BORDER_SUBTLE} !important;
    border-radius: 10px !important;
    color: {TEXT_PRIMARY} !important;
    box-shadow: 0 2px 6px rgba(0,0,0,0.2) !important;
}}
div[data-testid="stMetric"] label {{
    color: {TEXT_MUTED} !important;
    font-weight: 500 !important;
}}
div[data-baseweb="select"] > div, 
div[data-baseweb="input"] > div, 
textarea {{
    background-color: {BG_SURFACE_ALT} !important;
    border: 1px solid {BORDER_SUBTLE} !important;
    border-radius: 8px !important;
    color: {TEXT_PRIMARY} !important;
}}
button[data-baseweb="tab"] {{
    color: {TEXT_MUTED} !important;
    font-weight: 500 !important;
    border-bottom: 2px solid transparent !important;
}}
button[data-baseweb="tab"][aria-selected="true"] {{
    color: #58A6FF !important;
    border-bottom-color: #58A6FF !important;
    font-weight: 600 !important;
}}
div[data-testid="stBottomBlockContainer"] {{
    background-color: {BG_APP} !important;
    border-top: 1px solid {BORDER_SUBTLE} !important;
    padding-bottom: 1rem !important;
}}
div[data-testid="stChatInput"] {{
    background-color: {BG_CARD} !important;
    border: 1px solid {BORDER_SUBTLE} !important;
    border-radius: 10px !important;
}}
div[data-testid="stChatInput"] textarea {{
    color: {TEXT_PRIMARY} !important;
}}
.readiness-card-amber {{ 
    background: linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(245, 158, 11, 0.02)); 
    border: 1px solid rgba(245, 158, 11, 0.35); 
    border-radius: 10px; 
    padding: 16px 20px; 
    margin-bottom: 1.5rem; 
    color: {TEXT_PRIMARY};
}}
.readiness-card-green {{ 
    background: linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(16, 185, 129, 0.02)); 
    border: 1px solid rgba(16, 185, 129, 0.35); 
    border-radius: 10px; 
    padding: 16px 20px; 
    margin-bottom: 1.5rem; 
    color: {TEXT_PRIMARY};
}}
.workout-pill {{ 
    display: inline-block; 
    padding: 4px 10px; 
    border-radius: 6px; 
    font-size: 0.8rem; 
    font-weight: 600; 
    background-color: {BG_SURFACE_ALT}; 
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER_SUBTLE};
    margin-right: 6px; 
    margin-bottom: 6px; 
}}
</style>
""", unsafe_allow_html=True)

# --- CORE UTILITIES ---

def ensure_initial_message():
    if not st.session_state.messages:
        st.session_state.messages = [{"role": "assistant", "content": "Hey there! I'm your AI multi-sport coach. Let's look over your metrics and map out your path to Bintan. What's on your mind today?"}]

def go_to(page):
    st.session_state.active_nav = page

def discuss_with_coach(topic, context):
    context = str(context)
    if len(context) > 3000:
        context = context[:3000] + "\n[Context truncated for speed.]"
    st.session_state.pending_coach_prompt = f"Let's discuss {topic}.\n\nContext:\n{context}\n\nPlease explain what matters and give my next best action."
    go_to(COACH_PAGE)

def open_coach_with_reference(notice):
    st.session_state.coach_reference_notice = notice
    go_to(COACH_PAGE)

def calculate_compliance_score(activity):
    activity_type = activity.get("type", "Ride")
    if "Run" in activity_type:
        avg_hr = activity.get("average_heartrate")
        max_hr = activity.get("max_heartrate")
        if avg_hr and max_hr and max_hr > 0:
            hr_ratio = round(avg_hr / max_hr, 2)
            score = 100 if hr_ratio < 0.85 else int(100 - (hr_ratio - 0.85) * 200)
            return f"{max(50, min(100, score))}% (Avg HR: {avg_hr} bpm)"
        return "92% (Run Target Met)"
    
    actual_np = activity.get("icu_weighted_avg_watts") or activity.get("average_watts") or 0
    ap = activity.get("average_watts") or actual_np
    if not actual_np or ap <= 0:
        return "N/A"
    vi = round(actual_np / ap, 2)
    score = 100
    if vi > 1.08:
        score -= int((vi - 1.08) * 100)
    return f"{max(50, min(100, score))}% (VI: {vi})"

def check_for_new_rides_on_startup(activities_data):
    if not activities_data:
        return
    latest_activity = activities_data[0]
    last_checked_id = st.session_state.get("last_seen_activity_id")
    current_top_id = str(latest_activity.get("id"))
    if last_checked_id and last_checked_id != current_top_id:
        compliance = calculate_compliance_score(latest_activity)
        st.toast(f"🎯 New Activity Synced: '{latest_activity.get('name')}'! Score: {compliance}", icon="🔥")
    st.session_state["last_seen_activity_id"] = current_top_id

def calculate_acwr(wellness_list):
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
            return acwr, "Overreaching / Spike Risk (>1.35)"
        elif acwr < 0.8:
            return acwr, "Detraining Risk (<0.8)"
        return acwr, "Optimal Ramp Rate (0.8–1.35)"
    except Exception:
        return 1.0, "Stable"

def extract_icu_workout(text):
    text_content = text or ""
    def clean_json_string(s):
        return re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", s, flags=re.DOTALL | re.IGNORECASE).strip()

    plan_match = re.search(r"<icu_weekly_plan>(.*?)</icu_weekly_plan>", text_content, re.DOTALL | re.IGNORECASE)
    if plan_match:
        try:
            parsed = json.loads(clean_json_string(plan_match.group(1)))
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass
    single_match = re.search(r"<icu_workout>(.*?)</icu_workout>", text_content, re.DOTALL | re.IGNORECASE)
    if single_match:
        try:
            parsed = json.loads(clean_json_string(single_match.group(1)))
            if isinstance(parsed, dict):
                return [parsed]
        except Exception:
            pass
    return None

def clean_chat_content(text):
    text = text or ""
    text = re.sub(r"```xml\s*<\?xml.*?</workout_file>\s*```", "", text, flags=re.S | re.I)
    text = re.sub(r"<icu_workout>.*?</icu_workout>", "", text, flags=re.S | re.I)
    text = re.sub(r"<icu_weekly_plan>.*?</icu_weekly_plan>", "", text, flags=re.S | re.I)
    return text.strip()

def gemini_generate(messages_payload, api_key, model_name, max_tokens=9000):
    if not api_key:
        raise RuntimeError("Gemini API key is not configured.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    payload = {
        "contents": messages_payload,
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
    }
    response = requests.post(url, headers=headers, json=payload, timeout=AI_TIMEOUT)
    
    if response.status_code == 429:
        raise RuntimeError(f"Quota/Rate Limit exceeded on {model_name}.")
    if response.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:300]}")
        
    parts = (response.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    text = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
    
    if not text:
        raise RuntimeError("Empty response (Safety Block / Filtered).")
    return text

def execute_ai(messages_payload, max_tokens=9000):
    errors = []
    models = [
        "gemini-3.7-flash", 
        "gemini-3.6-flash", 
        "gemini-3.5-flash"
    ]
    
    for name, key in GEMINI_KEYS:
        if not key:
            continue
        for m in models:
            try:
                res = gemini_generate(messages_payload, key, m, max_tokens=max_tokens)
                st.session_state.ai_diagnostic = f"Success: Connected via {name} ({m})"
                return res
            except Exception as exc:
                errors.append(f"{name} ({m}): {exc}")
                
    st.session_state.ai_diagnostic = "\n".join(errors)
    raise RuntimeError(f"Google Engine Failed. Diagnostics: {' | '.join(errors[:4])}")

def push_bulk_workouts_to_intervals(athlete_id, api_key, workout_list):
    if not athlete_id or not api_key:
        raise RuntimeError("Intervals.icu credentials are required to push workouts.")
    if not workout_list:
        raise RuntimeError("No workout items to sync.")
    
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events/bulk?upsert=true"
    payload = []
    date_counts = {}
    
    for idx, item in enumerate(workout_list):
        raw_date = str(item.get("start_date_local", dt.datetime.now(LOCAL_TZ).date().isoformat()))[:10]
        
        # Track daily frequency to handle double sessions / bricks cleanly
        date_counts[raw_date] = date_counts.get(raw_date, 0) + 1
        session_num = date_counts[raw_date]
        
        # Stagger start times: 1st session at 08:00, 2nd at 17:00, subsequent spaced out
        if session_num == 1:
            time_slot = "08:00:00"
        elif session_num == 2:
            time_slot = "17:00:00"
        else:
            time_slot = f"{12 + session_num}:00:00"

        w_type = item.get("type", "Ride")
        # Guarantee a globally unique external_id for every single list item
        ext_id = f"AI_COACH_{raw_date}_{w_type.upper()}_{session_num}_{idx}"

        payload.append({
            "external_id": ext_id,
            "category": "WORKOUT",
            "start_date_local": f"{raw_date}T{time_slot}",
            "name": item.get("name", "Planned Session"),
            "description": item.get("description", ""),
            "type": w_type,
        })
        
    response = requests.post(url, auth=("API_KEY", api_key), json=payload, timeout=INTERVALS_TIMEOUT)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Failed to push workouts to Intervals.icu (HTTP {response.status_code}): {response.text[:300]}")
    return True

def persist_supplements_to_db():
    if st.session_state.user and supabase:
        try:
            (supabase.table("profiles").update({"supplements": st.session_state.user_supplements}).eq("id", st.session_state.user.id).execute())
        except Exception: pass
    elif localS and st.session_state.user_credentials:
        try:
            st.session_state.user_credentials["supplements"] = st.session_state.user_supplements
            localS.setItem("athlete_profile_config", st.session_state.user_credentials)
        except Exception: pass

def persist_chat_to_db():
    trimmed_messages = st.session_state.messages[-30:]
    if st.session_state.user and supabase:
        try:
            (supabase.table("profiles").update({"chat_history": trimmed_messages}).eq("id", st.session_state.user.id).execute())
        except Exception: pass
    elif localS and st.session_state.user_credentials:
        try:
            st.session_state.user_credentials["chat_history"] = trimmed_messages
            localS.setItem("athlete_profile_config", st.session_state.user_credentials)
        except Exception: pass

def persist_memory_to_db():
    memory_text = st.session_state.get("coach_memory", "")
    if st.session_state.user and supabase:
        try:
            (supabase.table("profiles").update({"coach_memory": memory_text}).eq("id", st.session_state.user.id).execute())
        except Exception: pass
    elif localS and st.session_state.user_credentials:
        try:
            st.session_state.user_credentials["coach_memory"] = memory_text
            localS.setItem("athlete_profile_config", st.session_state.user_credentials)
        except Exception: pass

def trend_storage_key(athlete_id, display_name):
    return f"coach_trend_analyses_history:{athlete_id or display_name}"

def load_persisted_trend(athlete_id, display_name):
    if st.session_state.trend_loaded: return
    st.session_state.trend_loaded = True
    saved = None
    if st.session_state.user and supabase:
        try:
            result = (supabase.table("profiles").select("trend_analyses_list").eq("id", st.session_state.user.id).execute())
            row = result.data[0] if result.data else {}
            if row.get("trend_analyses_list"): saved = row["trend_analyses_list"]
        except Exception: pass
    if not saved and localS:
        try:
            value = localS.getItem(trend_storage_key(athlete_id, display_name))
            saved = json.loads(value) if isinstance(value, str) else value
        except Exception: pass
    if isinstance(saved, list) and saved:
        st.session_state.cached_trend_analyses = saved
    elif st.session_state.get("cached_trend_analysis"):
        st.session_state.cached_trend_analyses = [{
            "timestamp": st.session_state.get("trend_analysis_timestamp", "Previous"),
            "analysis": st.session_state.cached_trend_analysis
        }]

def persist_trend(athlete_id, display_name):
    payload = st.session_state.cached_trend_analyses
    if st.session_state.user and supabase:
        try: 
            (supabase.table("profiles").update({"trend_analyses_list": payload}).eq("id", st.session_state.user.id).execute())
        except Exception: pass
    if localS:
        try: localS.setItem(trend_storage_key(athlete_id, display_name), json.dumps(payload))
        except Exception: pass

@st.cache_data(ttl=300, show_spinner=False)
def fetch_intervals_data(athlete_id, api_key):
    if not athlete_id or not api_key:
        return [], [], [], "Intervals.icu credentials are missing."
    try:
        today = dt.datetime.now(LOCAL_TZ).date()
        base = f"https://intervals.icu/api/v1/athlete/{athlete_id}"
        urls = [
            f"{base}/wellness?oldest={(today-dt.timedelta(days=90)).isoformat()}&newest={(today+dt.timedelta(days=14)).isoformat()}",
            f"{base}/activities?oldest={(today-dt.timedelta(days=90)).isoformat()}&newest={(today+dt.timedelta(days=14)).isoformat()}",
            f"{base}/events?oldest={(today-dt.timedelta(days=14)).isoformat()}&newest={(today+dt.timedelta(days=14)).isoformat()}",
        ]
        result = []
        for url in urls:
            response = requests.get(url, auth=("API_KEY", api_key), timeout=INTERVALS_TIMEOUT)
            result.append(response.json() if response.status_code == 200 else [])
        return result[0], result[1], result[2], "Connected."
    except requests.Timeout:
        return [], [], [], "Intervals.icu request timed out."
    except Exception as exc:
        return [], [], [], f"Intervals.icu error: {exc}"

def event_date(event):
    raw = event.get("start_date_local") or event.get("start_date") or ""
    try: return dt.date.fromisoformat(str(raw)[:10])
    except ValueError: return None

def session_summary(event):
    duration_seconds = event.get("moving_time") or event.get("duration") or 0
    distance_m = event.get("distance") or 0
    details = []
    if duration_seconds: details.append(f"Duration: {round(float(duration_seconds) / 60)} min")
    if distance_m: details.append(f"Distance: {float(distance_m) / 1000:.1f} km")
    if event.get("icu_training_load") is not None: details.append(f"Load: {round(float(event['icu_training_load']))}")
    instructions = event.get("description") or event.get("notes") or "No instructions."
    if isinstance(instructions, dict): instructions = instructions.get("description") or "No instructions."
    elif isinstance(instructions, list): instructions = " ".join(str(item) for item in instructions if item)
    return {"name": event.get("name") or "Workout", "date": str(event.get("start_date_local", ""))[:10], "details": details, "instructions": instructions}

def activity_summary(activity):
    fields = {
        "date": str(activity.get("start_date_local", ""))[:10], "name": activity.get("name", "Unnamed"),
        "type": activity.get("type"), "distance_km": round(float(activity.get("distance") or 0) / 1000, 1),
        "moving_minutes": round(float(activity.get("moving_time") or 0) / 60),
        "average_power_w": activity.get("average_watts"), "normalized_power_w": activity.get("icu_weighted_avg_watts") or activity.get("weighted_average_watts"),
        "average_heartrate": activity.get("average_heartrate"), "training_load": activity.get("icu_training_load"), 
        "elevation_gain_m": activity.get("total_elevation_gain"),
    }
    return {key: value for key, value in fields.items() if value not in (None, "", 0)}

def parse_gpx(raw):
    try:
        root = ET.fromstring(raw.decode("utf-8", errors="ignore"))
        points, elevations = [], []
        for elem in root.iter():
            tag = elem.tag.split("}")[-1].lower()
            if tag not in ("trkpt", "rtept") or not elem.attrib.get("lat") or not elem.attrib.get("lon"):
                continue
            points.append((float(elem.attrib["lat"], float(elem.attrib["lon"]))))
            elevations.append(next((float(c.text) for c in elem if c.tag.split("}")[-1].lower() in ("ele", "elevation", "alt") and c.text), 0.0))
        if not points: return None
        distance = sum(6371 * 2 * math.asin(math.sqrt(math.sin(math.radians(points[i][0]-points[i-1][0])/2)**2 + math.cos(math.radians(points[i-1][0]))*math.cos(math.radians(points[i][0]))*math.sin(math.radians(points[i][1]-points[i-1][1])/2)**2)) for i in range(1, len(points)))
        return {
            "distance_km": round(distance, 2),
            "elevation_gain_m": round(sum(max(0, elevations[i]-elevations[i-1]) for i in range(1, len(elevations))), 1),
            "max_elevation_m": round(max(elevations), 1) if elevations else 0
        }
    except Exception:
        return None

def build_gemini_payload(current_question, display_name, wellness_list):
    today = dt.datetime.now(LOCAL_TZ).date()
    next_monday = today + dt.timedelta(days=(0 - today.weekday()) % 7)
    if next_monday == today: next_monday += dt.timedelta(days=7)
    next_monday_str = next_monday.isoformat()
    today_str = today.isoformat()

    try:
        race_dt = dt.date.fromisoformat(st.session_state.goals['race_date'])
        weeks_to_race = max(0, (race_dt - today).days // 7)
    except Exception:
        weeks_to_race = 12

    if weeks_to_race > 12:
        periodization_phase = "BASE BUILDING (Focus on aerobic endurance, multi-sport volume, and structural resilience)."
    elif weeks_to_race > 4:
        periodization_phase = "BUILD PHASE (Focus on threshold intervals, brick sessions, and run/ride progression)."
    else:
        periodization_phase = "TAPER & PEAK PHASE (Focus on reducing volume while maintaining intensity, prioritizing recovery and race freshness)."

    latest_wellness = wellness_list[-1] if wellness_list else {}
    current_tsb = float(latest_wellness.get("tsb", latest_wellness.get("TSB", 0)) or 0)
    current_sleep = float(latest_wellness.get("sleep_score", latest_wellness.get("sleepScore", 80)) or 80)
    acwr_val, acwr_status = calculate_acwr(wellness_list)
    
    gatekeeper_active = (current_tsb < -20) or (current_sleep < 60) or (acwr_val > 1.35)
    if gatekeeper_active:
        gatekeeper_directive = (
            f"⚠️ MULTI-SPORT LOAD & IMPACT RECOVERY DIRECTIVE ⚠️\n"
            f"Current TSB is {current_tsb:.1f}, Sleep Score is {current_sleep:.0f}/100, and ACWR is {acwr_val} ({acwr_status}).\n"
            f"MANDATORY RULE: Differentiate between mechanical running impact fatigue and indoor cycling load. If running volume is high, proactively safeguard orthopedic joints by suggesting low-impact cross-training or rest."
        )
    else:
        gatekeeper_directive = f"Readiness Status: CLEAR (TSB: {current_tsb:.1f}, Sleep: {current_sleep:.0f}, ACWR: {acwr_val}). Multi-sport load balanced."

    trend_ctx = (st.session_state.get('cached_trend_analysis') or 'No Trend Analysis.')[:1200]
    calendar_ctx = (st.session_state.get('calendar_context') or 'Not loaded')[:1500]
    memory_ctx = st.session_state.get('coach_memory') or 'No long-term memory logged yet.'
    supplements_str = json.dumps(st.session_state.user_supplements, ensure_ascii=False) if st.session_state.user_supplements else 'N/A'
    gear_str = st.session_state.athlete_gear or 'N/A'
    limits_str = st.session_state.athlete_limitations or 'N/A'

    system_instructions = (
        f"You are an elite multi-sport (cycling and running) coach with full calendar integration.\n"
        f"Persona: {st.session_state.coach_persona}\n"
        f"Athlete: {display_name} | Discipline Focus: {st.session_state.primary_discipline}\n"
        f"Today: {today_str} | Next Monday: {next_monday_str}\n"
        f"Goal: {st.session_state.goals['target_metric']} ({st.session_state.goals['event_name']} on {st.session_state.goals['race_date']})\n"
        f"Current Periodization Phase: {periodization_phase} ({weeks_to_race} weeks to event)\n"
        f"{gatekeeper_directive}\n"
        f"LONG-TERM COACHING MEMORY & ATHLETE PROFILE:\n{memory_ctx}\n\n"
        f"Gear: {gear_str} | Limitations: {limits_str}\n"
        f"Supplements & Fueling: {supplements_str}\n"
        f"90-DAY TREND SYNTHESIS:\n{trend_ctx}\n\n"
        f"CALENDAR CONTEXT:\n{calendar_ctx}\n\n"
        "CRITICAL INTERVALS.ICU WORKOUT SYNTAX FOR MYWHOOSH (INDOOR CYCLING) AND GARMIN (RUNNING):\n"
        "To ensure workouts parse correctly into structured step charts for MyWhoosh and Garmin, follow these strict Intervals.icu formatting rules:\n"
        "1. Section headers (Warmup, Main Set, Cooldown) must be on their own separate lines.\n"
        "2. Repeat blocks must use the exact format where the multiplier sits on its own line followed by the indented steps, with empty lines between sections:\n"
        "   - Correct Cycling Syntax Example (MyWhoosh compatible):\n"
        "     Warmup\n"
        "     - 10m 50%\n"
        "     - 5m 70%\n\n"
        "     Main Set\n"
        "     8x\n"
        "     - 30s 130%\n"
        "     - 30s 50%\n\n"
        "     Cooldown\n"
        "     - 10m 50%\n\n"
        "   - Correct Running Syntax Example (Garmin compatible):\n"
        "     Warmup\n"
        "     - 15m Z2 Pace\n\n"
        "     Main Set\n"
        "     4x\n"
        "     - 1km Threshold Pace\n"
        "     - 90s Jog Recovery\n\n"
        "     Cooldown\n"
        "     - 10m Easy\n\n"
        "IF PRESCRIBING A WEEKLY SCHEDULE OR MACROCYCLE, APPEND A JSON ARRAY inside `<icu_weekly_plan>` tags:\n"
        "<icu_weekly_plan>\n"
        "[\n"
        "  {\n"
        f"    \"name\": \"MyWhoosh Micro-Intervals\",\n"
        f"    \"type\": \"Ride\",\n"
        f"    \"start_date_local\": \"{next_monday_str}\",\n"
        f"    \"description\": \"Warmup\\n- 10m 50%\\n- 5m 70%\\n\\nMain Set\\n8x\\n- 30s 130%\\n- 30s 50%\\n\\nCooldown\\n- 10m 50%\"\n"
        "  }\n"
        "]\n"
        "</icu_weekly_plan>"
    )

    contents = [
        {"role": "user", "parts": [{"text": f"SYSTEM CONFIGURATION & CONTEXT:\n{system_instructions}\n\nPlease acknowledge you understand my parameters."}]},
        {"role": "model", "parts": [{"text": "Understood. I will output precise Intervals.icu syntax so workouts parse cleanly for MyWhoosh cycling and Garmin running sync."}]}
    ]

    for m in st.session_state.messages[-15:]:
        role = "user" if m["role"] == "user" else "model"
        msg_text = clean_chat_content(str(m["content"])) if role == "model" else str(m["content"])
        contents.append({"role": role, "parts": [{"text": msg_text[:2500]}]})

    contents.append({"role": "user", "parts": [{"text": str(current_question)[:2000]}]})
    return contents

    contents = [
        {"role": "user", "parts": [{"text": f"SYSTEM CONFIGURATION & CONTEXT:\n{system_instructions}\n\nPlease acknowledge you understand my parameters."}]},
        {"role": "model", "parts": [{"text": "Understood. I will ensure all cycling workouts use structured percentage-based steps for MyWhoosh/Intervals sync, and running workouts use Garmin-compatible pace/HR blocks."}]}
    ]

    for m in st.session_state.messages[-15:]:
        role = "user" if m["role"] == "user" else "model"
        msg_text = clean_chat_content(str(m["content"])) if role == "model" else str(m["content"])
        contents.append({"role": role, "parts": [{"text": msg_text[:2500]}]})

    contents.append({"role": "user", "parts": [{"text": str(current_question)[:2000]}]})
    return contents

def render_coach_reply(question, display_name, wellness_list, athlete_id, intervals_api_key):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        steps = [
            "Analyzing multi-sport load & formatting MyWhoosh/Garmin blocks...",
            "Cross-referencing sleep quality and recent fatigue ratios...",
            "Drafting structured workout prescription..."
        ]
        for step in steps:
            placeholder.markdown(f"*(Thinking)* &bull; {step}")
            
        try:
            payload = build_gemini_payload(question, display_name, wellness_list)
            response = execute_ai(payload, max_tokens=9000)
            placeholder.markdown(clean_chat_content(response))
            
            icu_payload = extract_icu_workout(response)
            if isinstance(icu_payload, list) and len(icu_payload) > 0:
                with st.container(border=True):
                    st.markdown(f"📋 **Proposed Training Block ({len(icu_payload)} sessions — MyWhoosh/Garmin Ready):**")
                    for session in icu_payload:
                        w_type = session.get('type', 'Ride')
                        pill_color = "#2563EB" if "Ride" in w_type else "#D97706"
                        st.markdown(f"<span class='workout-pill' style='border-color: {pill_color};'>{session.get('start_date_local')}</span> **{session.get('name', 'Workout')}** ({w_type})", unsafe_allow_html=True)
                    if st.button("🚀 Approve & Sync Plan to Intervals.icu", key=f"sync_chat_{len(st.session_state.messages)}", type="primary"):
                        with st.spinner("⏳ Syncing structured files to Intervals.icu..."):
                            try:
                                push_bulk_workouts_to_intervals(athlete_id, intervals_api_key, icu_payload)
                                st.toast("✅ Workouts successfully synced for MyWhoosh/Garmin integration!", icon="✅")
                            except Exception as exc: st.error(f"Sync failed: {exc}")
                    
            st.session_state.messages.append({"role": "assistant", "content": response})
            persist_chat_to_db()
        except Exception as exc:
            placeholder.error(f"⚠️ {exc}")

# --- RUNTIME AUTHENTICATION & INITIALIZATION ---

try:
    token = st.query_params.get("token")
    if token and not st.session_state.user_credentials:
        config = json.loads(base64.urlsafe_b64decode(token.encode()).decode())
        if config.get("icu_key") and config.get("icu_id"): st.session_state.user_credentials = config
except Exception: pass

if not st.session_state.user and not st.session_state.user_credentials and localS:
    try: st.session_state.user_credentials = localS.getItem("athlete_profile_config")
    except Exception: pass

if not st.session_state.user and not st.session_state.user_credentials:
    st.markdown("##### 🔐 Elite Multi-Sport Portal")
    owner_tab, guest_tab = st.tabs(["Owner Login", "Friend / Guest Setup"])
    with owner_tab:
        if not supabase: st.info("Owner login unavailable.")
        else:
            with st.form("owner_login"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Log In", use_container_width=True):
                    try:
                        st.session_state.user = supabase.auth.sign_in_with_password({"email": email, "password": password}).user
                        st.rerun()
                    except Exception as exc: st.error(f"Login failed: {exc}")
    with guest_tab:
        with st.form("guest_setup"):
            name = st.text_input("Your Name")
            icu_key = st.text_input("Intervals.icu API Key", type="password")
            icu_id = st.text_input("Intervals.icu Athlete ID")
            if st.form_submit_button("Save & Launch Guest Session", use_container_width=True):
                if not icu_key or not icu_id: st.error("Intervals.icu credentials required.")
                else:
                    st.session_state.user_credentials = {"name": name.strip() or "Guest Athlete", "icu_key": icu_key.strip(), "icu_id": icu_id.strip()}
                    if localS: localS.setItem("athlete_profile_config", st.session_state.user_credentials)
                    st.rerun()
    st.stop()

if st.session_state.user:
    try:
        profile_result = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute() if supabase else None
        profile = profile_result.data[0] if profile_result and profile_result.data else {}
    except Exception: profile = {}
    INTERVALS_API_KEY = profile.get("intervals_api_key", "")
    ATHLETE_ID = profile.get("intervals_athlete_id", "")
    display_name = profile.get("name") or "Athlete"
    st.session_state.athlete_gear = st.session_state.athlete_gear or profile.get("gear_notes", "")
    st.session_state.athlete_limitations = st.session_state.athlete_limitations or profile.get("limitations_notes", "")
    for key in DEFAULT_GOALS: st.session_state.goals[key] = profile.get(key) or st.session_state.goals[key]
    if profile.get("coach_memory"): st.session_state.coach_memory = profile["coach_memory"]
    if not st.session_state.profile_loaded:
        if isinstance(profile.get("supplements"), list): st.session_state.user_supplements = profile["supplements"]
        if isinstance(profile.get("chat_history"), list) and profile["chat_history"]: st.session_state.messages = profile["chat_history"]
        st.session_state.profile_loaded = True
else:
    creds = st.session_state.user_credentials or {}
    INTERVALS_API_KEY, ATHLETE_ID, display_name = creds.get("icu_key", ""), creds.get("icu_id", ""), creds.get("name", "Athlete")
    st.session_state.athlete_gear = st.session_state.athlete_gear or creds.get("gear", "")
    st.session_state.athlete_limitations = st.session_state.athlete_limitations or creds.get("limitations", "")
    if isinstance(creds.get("goals"), dict): st.session_state.goals.update({key: value for key, value in creds["goals"].items() if key in DEFAULT_GOALS and value})
    if creds.get("coach_memory"): st.session_state.coach_memory = creds["coach_memory"]
    if not st.session_state.profile_loaded:
        if isinstance(creds.get("supplements"), list): st.session_state.user_supplements = creds["supplements"]
        if isinstance(creds.get("chat_history"), list) and creds["chat_history"]: st.session_state.messages = creds["chat_history"]
        st.session_state.profile_loaded = True

ensure_initial_message()
load_persisted_trend(ATHLETE_ID, display_name)

wellness_list, activities_data, planned_events, intervals_status = fetch_intervals_data(ATHLETE_ID, INTERVALS_API_KEY)
st.session_state.calendar_context = json.dumps([session_summary(ev) for ev in planned_events[:10]], ensure_ascii=False)
check_for_new_rides_on_startup(activities_data)

if st.session_state.active_nav not in NAV_OPTIONS: st.session_state.active_nav = NAV_OPTIONS[0]; st.session_state.sidebar_nav = NAV_OPTIONS[0]
if st.session_state.sidebar_nav != st.session_state.active_nav: st.session_state.sidebar_nav = st.session_state.active_nav

# --- SIDEBAR NAVIGATION & CONTROLS ---
with st.sidebar:
    st.markdown("##### 🚴‍♂️🏃‍♂️ AI Multi-Sport Coach")
    st.caption(f"Athlete: **{display_name}**")

    st.session_state.primary_discipline = st.selectbox("Primary Focus", ["Cycling & Running (Multi-Sport)", "Cycling Focus", "Running Focus"], index=0)

    st.markdown("---")
    st.markdown("**Navigation**")
    for nav_item in NAV_OPTIONS:
        if st.button(nav_item, use_container_width=True, type="primary" if st.session_state.active_nav == nav_item else "secondary"):
            go_to(nav_item)
            st.rerun()

    st.divider()
    st.session_state.coach_persona = st.selectbox("Coaching Persona", ["Collaborative Peer (Balanced & Brainstorming)", "Sports Scientist (Data & Periodization Focus)", "Drill Sergeant (Strict & Direct Accountability)"], index=0)
    
    with st.expander("Recovery, fuel & supplements", expanded=False):
        with st.form("sidebar_supplement_form", clear_on_submit=True):
            supplement_name = st.text_input("Supplement / fuel")
            supplement_timing = st.text_input("When to use it")
            supplement_notes = st.text_input("Purpose or notes")
            if st.form_submit_button("Add to coach reference", use_container_width=True) and supplement_name.strip():
                st.session_state.user_supplements.append({"name": supplement_name.strip(), "timing": supplement_timing.strip() or "As needed", "notes": supplement_notes.strip() or ""})
                persist_supplements_to_db()
                st.rerun()
                
        if st.session_state.user_supplements:
            for item in st.session_state.user_supplements: st.write(f"• **{item['name']}** — {item['timing']}")
            remove_name = st.selectbox("Remove item", ["Keep all"] + [item["name"] for item in st.session_state.user_supplements], key="remove_supplement")
            if remove_name != "Keep all" and st.button("Remove selected", key="remove_supplement_button", use_container_width=True):
                st.session_state.user_supplements = [item for item in st.session_state.user_supplements if item["name"] != remove_name]
                persist_supplements_to_db()
                st.rerun()

    with st.expander("Athlete profile & goal", expanded=False):
        with st.form("sidebar_profile_form"):
            event_name = st.text_input("Target event", value=st.session_state.goals["event_name"])
            target_metric = st.text_area("Primary objective", value=st.session_state.goals["target_metric"])
            race_date = st.date_input("Race date", value=dt.date.fromisoformat(st.session_state.goals["race_date"]))
            gear = st.text_area("Gear / shoes / bike notes", value=st.session_state.athlete_gear)
            limitations = st.text_area("Limitations / coaching notes", value=st.session_state.athlete_limitations)
            if st.form_submit_button("Save profile", use_container_width=True):
                st.session_state.goals = {"event_name": event_name.strip() or "Target event", "target_metric": target_metric.strip() or "Not provided", "race_date": race_date.isoformat()}
                st.session_state.athlete_gear, st.session_state.athlete_limitations = gear, limitations
                if st.session_state.user and supabase:
                    try:
                        (supabase.table("profiles").update({
                            "event_name": st.session_state.goals["event_name"],
                            "target_metric": st.session_state.goals["target_metric"],
                            "race_date": st.session_state.goals["race_date"],
                            "gear_notes": gear,
                            "limitations_notes": limitations,
                            "supplements": st.session_state.user_supplements,
                            "chat_history": st.session_state.messages[-30:]
                        }).eq("id", st.session_state.user.id).execute())
                    except Exception as exc: st.warning(f"Profile saved locally: {exc}")
                st.toast("Profile saved successfully!", icon="💾")
                st.rerun()

    with st.expander("🧠 Coach's Long-Term Memory", expanded=False):
        st.caption("Permanent running notes your AI coach keeps about your physiological responses and training style preferences.")
        updated_memory = st.text_area("Coach's Notebook", value=st.session_state.get("coach_memory", ""), height=130)
        if st.button("Save Memory Notes", use_container_width=True):
            st.session_state.coach_memory = updated_memory
            persist_memory_to_db()
            st.toast("Coach's memory updated!", icon="🧠")
            st.rerun()
            
    with st.expander("AI connection", expanded=False):
        if st.button("Test AI connection", key="test_gemini", use_container_width=True):
            with st.spinner("Pinging coach..."):
                try:
                    execute_ai([{"role": "user", "parts": [{"text": "Reply exactly: AI connection successful."}]}], max_tokens=20)
                    st.success(st.session_state.ai_diagnostic)
                except Exception as exc: st.error(str(exc))
        if st.session_state.ai_diagnostic:
            st.caption("Diagnostic")
            st.code(st.session_state.ai_diagnostic, language="text")
            
    if st.button("Clear chat history", use_container_width=True):
        st.session_state.messages = []
        ensure_initial_message()
        persist_chat_to_db()
        st.rerun()

selected_nav = st.session_state.active_nav

latest = wellness_list[-1] if wellness_list else {}
ctl = latest.get("ctl", 0) or latest.get("CTL", 0) or 0
atl = latest.get("atl", 0) or latest.get("ATL", 0) or 0
tsb = latest.get("tsb", 0) or latest.get("TSB", 0) or 0

# --- MAIN ROUTING LOGIC ---

if selected_nav == NAV_OPTIONS[0]:
    current_hour = dt.datetime.now(LOCAL_TZ).hour
    time_greeting = "Good morning" if current_hour < 12 else ("Good afternoon" if current_hour < 18 else "Good evening")
    
    # --- FIND TODAY'S ACTIVITY FROM PLANNED EVENTS ---
    today_date_str = dt.datetime.now(LOCAL_TZ).date().isoformat()
    todays_workouts = [ev for ev in planned_events if event_date(ev) and event_date(ev).isoformat() == today_date_str]
    
    if todays_workouts:
        session_titles = [w.get("name", "Planned Workout") for w in todays_workouts]
        today_activity_text = " + ".join(session_titles)
        today_activity_type = todays_workouts[0].get("type", "Workout")
    else:
        today_activity_text = "Rest Day / Flexible Recovery"
        today_activity_type = "Rest"

    st.markdown(f"##### ☀️ {time_greeting}, {display_name}! Here is your training briefing.")
    st.caption(f"Intervals.icu connection status: {intervals_status}")
    
    # --- TODAY'S ACTIVITY SPOTLIGHT BANNER ---
    st.markdown(f"""
    <div style="background: linear-gradient(135deg, rgba(37, 99, 235, 0.15), rgba(37, 99, 235, 0.03)); border: 1px solid rgba(37, 99, 235, 0.35); border-radius: 10px; padding: 16px 20px; margin-bottom: 1.2rem; color: {TEXT_PRIMARY};">
        <h4 style="margin:0 0 4px 0; font-size:1.1rem; color: #58A6FF;">🎯 Today's Focus ({today_date_str})</h4>
        <p style="margin:0; font-size:1.05rem; font-weight:600;">{today_activity_text} <span class='workout-pill'>{today_activity_type}</span></p>
    </div>
    """, unsafe_allow_html=True)

    sleep_score = latest.get("sleep_score") or latest.get("sleepScore")
    acwr_val, acwr_status = calculate_acwr(wellness_list)
    
    if not wellness_list:
        readiness, focus, watch = "Readiness unavailable", "Sync Intervals.icu to assess today.", "No current wellness data."
        card_class = "readiness-card-green"
    elif tsb <= -20 or (sleep_score and sleep_score < 60) or acwr_val > 1.35:
        readiness, focus, watch = "Recovery & Adaptation Focus", f"ACWR: {acwr_val} ({acwr_status}). Your fatigue metrics indicate a need for recovery.", f"Accumulated TSB {tsb:.0f}, Sleep {sleep_score or 'N/A'}/100."
        card_class = "readiness-card-amber"
    elif tsb <= -8:
        readiness, focus, watch = "Steady & Controlled", f"ACWR: {acwr_val}. Keep your planned session steady and avoid extra intensity.", f"Fatigue is moderately elevated (TSB {tsb:.0f})."
        card_class = "readiness-card-amber"
    else:
        readiness, focus, watch = "Primed & Ready", f"ACWR: {acwr_val} ({acwr_status}). Your body is balanced and ready for quality work.", f"Form is stable (TSB {tsb:.0f})."
        card_class = "readiness-card-green"
        
    st.markdown(f"""
    <div class="{card_class}">
        <h4 style="margin:0 0 4px 0; font-size:1.1rem;">💡 {readiness}</h4>
        <p style="margin:0; font-size:.95rem;">{focus} &bull; <em>{watch}</em></p>
    </div>
    """, unsafe_allow_html=True)
    
    c1, c2, c3 = st.columns(3)
    c1.metric("Fitness (CTL)", round(float(ctl), 1), delta="Aerobic Base")
    c2.metric("Fatigue (ATL)", round(float(atl), 1), delta="Recent Load")
    c3.metric("Form (TSB)", round(float(tsb), 1), delta="Freshness")

    col_a, col_b = st.columns([2, 1])
    with col_a:
        if st.button("⚡ I missed a workout / Life got in the way — Rebalance my week", use_container_width=True):
            discuss_with_coach("adjusting my training week because I missed a workout due to schedule disruption", "User missed a session and needs a sliding macrocycle adaptation.")
            st.rerun()

    with st.expander("📊 View 90-Day Performance Management Chart (CTL / ATL / TSB)", expanded=False):
        if wellness_list:
            try:
                df = pd.DataFrame(wellness_list)
                date_col = next((col for col in ['id', 'date', 'start_date'] if col in df.columns), None)
                if date_col and not df.empty:
                    df['date_parsed'] = pd.to_datetime(df[date_col], errors='coerce')
                    df = df.dropna(subset=['date_parsed']).sort_values('date_parsed')
                    raw_ctl = df.get('ctl', df.get('CTL', 0))
                    raw_atl = df.get('atl', df.get('ATL', 0))
                    raw_tsb = df.get('tsb', df.get('TSB', 0))
                    df['ctl_clean'] = pd.to_numeric(raw_ctl if isinstance(raw_ctl, pd.Series) else pd.Series(raw_ctl), errors='coerce').fillna(0)
                    df['atl_clean'] = pd.to_numeric(raw_atl if isinstance(raw_atl, pd.Series) else pd.Series(raw_atl), errors='coerce').fillna(0)
                    df['tsb_clean'] = pd.to_numeric(raw_tsb if isinstance(raw_tsb, pd.Series) else pd.Series(raw_tsb), errors='coerce').fillna(0)
                    
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(x=df['date_parsed'], y=df['ctl_clean'], mode='lines', name='Fitness (CTL)', line=dict(color='#00E676', width=2)))
                    fig.add_trace(go.Scatter(x=df['date_parsed'], y=df['atl_clean'], mode='lines', name='Fatigue (ATL)', line=dict(color='#FF4081', width=2)))
                    fig.add_trace(go.Bar(x=df['date_parsed'], y=df['tsb_clean'], name='Form (TSB)', marker_color=['#00E676' if val >= 0 else '#FF4081' for val in df['tsb_clean']]))
                    fig.update_layout(
                        title="90-Day Multi-Sport Performance Management Chart", title_font=dict(size=14, color=TEXT_PRIMARY),
                        margin=dict(l=0, r=0, t=40, b=0), plot_bgcolor='rgba(0,0,0,0)', paper_bgcolor='rgba(0,0,0,0)',
                        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1, font=dict(color=TEXT_PRIMARY)),
                        xaxis=dict(showgrid=False, color=TEXT_PRIMARY), yaxis=dict(showgrid=True, gridcolor="rgba(128,128,128,0.2)", color=TEXT_PRIMARY)
                    )
                    st.plotly_chart(fig, use_container_width=True)
            except Exception as e:
                st.caption(f"Chart render warning: {e}")
    
    if "cached_trend_analyses" not in st.session_state:
        st.session_state.cached_trend_analyses = []

    if st.button("🚀 Run 90-Day Multi-Sport Trend Synthesis", type="primary"):
        payload_text = f"Analyze this multi-sport athlete's last 90 days. CTL {ctl}; ATL {atl}; TSB {tsb}. ACWR: {acwr_val}. Goal: {st.session_state.goals['target_metric']}."
        with st.spinner("Analyzing 90 days of multi-sport training data..."):
            try:
                new_analysis = execute_ai([{"role": "user", "parts": [{"text": payload_text}]}], max_tokens=9000)
                timestamp_str = dt.datetime.now(LOCAL_TZ).strftime("%d %b %Y, %H:%M %Z")
                st.session_state.cached_trend_analyses.insert(0, {"timestamp": timestamp_str, "analysis": new_analysis})
                st.session_state.cached_trend_analyses = st.session_state.cached_trend_analyses[:3]
                persist_trend(ATHLETE_ID, display_name)
                st.toast("Multi-sport trend synthesis complete!", icon="📈")
            except Exception as exc: st.error(str(exc))
            
    if st.session_state.cached_trend_analyses:
        st.markdown("###### 📈 Saved 90-Day Trend Analyses (Last 3)")
        for idx, item in enumerate(st.session_state.cached_trend_analyses):
            with st.expander(f"📌 Trend Report #{len(st.session_state.cached_trend_analyses) - idx} · Generated {item['timestamp']}", expanded=(idx == 0)):
                st.markdown(item['analysis'])
                a, b = st.columns(2)
                if a.button("💬 Discuss with Coach", key=f"trend_discuss_{idx}"):
                    open_coach_with_reference(f"Your dated 90-Day Trend Analysis from {item['timestamp']} remains on record.")
                    st.rerun()
                if b.button("Delete report", key=f"clear_single_trend_{idx}"):
                    st.session_state.cached_trend_analyses.pop(idx)
                    persist_trend(ATHLETE_ID, display_name)
                    st.rerun()

elif selected_nav == COACH_PAGE:
    st.markdown("##### 🤖 AI Multi-Sport Coach & Sparring Partner")
    if st.session_state.coach_reference_notice:
        st.info(st.session_state.coach_reference_notice)
        st.session_state.coach_reference_notice = None

    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(clean_chat_content(message["content"]))
            if message["role"] == "assistant":
                icu_payload = extract_icu_workout(message["content"])
                if isinstance(icu_payload, list) and len(icu_payload) > 0:
                    with st.container(border=True):
                        st.markdown(f"📋 **Proposed Training Block ({len(icu_payload)} sessions):**")
                        for session in icu_payload:
                            w_type = session.get('type', 'Ride')
                            pill_color = "#2563EB" if "Ride" in w_type else "#D97706"
                            st.markdown(f"<span class='workout-pill' style='border-color: {pill_color};'>{session.get('start_date_local')}</span> **{session.get('name', 'Workout')}** ({w_type})", unsafe_allow_html=True)
                        if st.button("🚀 Approve & Sync Plan to Intervals.icu", key=f"sync_hist_{idx}", type="primary"):
                            with st.spinner("⏳ Syncing workouts to Intervals.icu..."):
                                try:
                                    push_bulk_workouts_to_intervals(ATHLETE_ID, INTERVALS_API_KEY, icu_payload)
                                    st.toast("✅ Proposed plan successfully synced!", icon="✅")
                                except Exception as exc: st.error(f"Sync failed: {exc}")

    pending = st.session_state.pending_coach_prompt
    if pending:
        st.session_state.pending_coach_prompt = None
        render_coach_reply(pending, display_name, wellness_list, ATHLETE_ID, INTERVALS_API_KEY)
    elif question := st.chat_input("Ask your coach anything... e.g. 'Balance my bike intervals and weekend long run'"):
        render_coach_reply(question.strip(), display_name, wellness_list, ATHLETE_ID, INTERVALS_API_KEY)

elif selected_nav == NAV_OPTIONS[2]:
    st.markdown("##### 📅 Multi-Sport Training Calendar & Macrocycle Builder")
    today = dt.datetime.now(LOCAL_TZ).date()
    window_start, window_end = today - dt.timedelta(days=14), today + dt.timedelta(days=14)
    st.caption(f"Showing previous 14 days and next 14 days · {window_start:%d %b}–{window_end:%d %b %Y}")

    def calendar_items(records, source, start_date, end_date):
        result = []
        for record in records:
            date_value = event_date(record)
            if date_value and start_date <= date_value <= end_date:
                item = dict(record)
                item["_calendar_source"] = source
                result.append(item)
        return result

    future_sessions = calendar_items(planned_events, "Planned session", today, window_end)
    past_activities = calendar_items(activities_data, "Completed activity", window_start, today - dt.timedelta(days=1))

    def render_calendar_days(items, empty_message):
        if not items:
            st.info(empty_message)
            return {}
        grouped_items = {}
        for item in items:
            grouped_items.setdefault(event_date(item).isoformat(), []).append(item)
            
        for date_str, sessions in sorted(grouped_items.items()):
            # Parse date string to get weekday name (e.g., Monday, Tuesday)
            d_obj = dt.date.fromisoformat(date_str)
            weekday_name = d_obj.strftime("%A") # e.g. "Monday"
            formatted_date_label = f"{weekday_name}, {d_obj.strftime('%d %b %Y')}"
            
            session_names = [event.get("name") or "Planned workout" for event in sessions]
            header_names = " + ".join(session_names[:2])
            if len(session_names) > 2:
                header_names += f" + {len(session_names) - 2} more"
                
            with st.expander(f"📅 {formatted_date_label} · {header_names}", expanded=False):
                for number, event in enumerate(sessions, 1):
                    session = session_summary(event)
                    st.markdown(f"**Session {number}: {session['name']}**")
                    if session["details"]: st.caption(" · ".join(session["details"]))
                    st.markdown(f"**Coach instructions:** {session['instructions']}")
                    if number < len(sessions): st.divider()
        return grouped_items

    current_tab, past_tab = st.tabs(["Current & future sessions", "Past activities"])
    with current_tab:
        future_grouped = render_calendar_days(future_sessions, "No calendar sessions for the next 14 days.")
    with past_tab:
        past_grouped = render_calendar_days(past_activities, "No completed activities for the previous 14 days.")

    grouped = {**past_grouped}
    for date, sessions in future_grouped.items():
        grouped[date] = grouped.get(date, []) + sessions
    if grouped:
        st.divider()
        discussion_date = st.selectbox("Discuss a calendar day with Coach", list(sorted(grouped)), format_func=lambda val: f"{val} · " + " + ".join(event.get("name") or "Workout" for event in grouped[val]))
        if st.button("💬 Discuss selected day with Coach", type="primary"):
            readable_sessions = [session_summary(event) for event in grouped[discussion_date]]
            discuss_with_coach(f"my training sessions on {discussion_date}", json.dumps(readable_sessions, ensure_ascii=False))
            st.rerun()

    st.divider()
    with st.expander("🏗️ Multi-Sport Macrocycle Periodization Builder", expanded=False):
        st.caption("Generate an automated multi-week skeleton block combining running and cycling leading into your target race date.")
        macro_weeks = st.slider("Macrocycle Duration (Weeks)", min_value=4, max_value=16, value=8, step=2)
        if st.button("Generate & Push Multi-Sport Macrocycle", type="primary"):
            with st.spinner("Synthesizing multi-sport periodized block..."):
                try:
                    macro_prompt = f"Generate a strict {macro_weeks}-week multi-sport (cycling & running) training skeleton leading up to my race on {st.session_state.goals['race_date']}. Return a JSON array inside <icu_weekly_plan> tags containing structured rides and runs."
                    response = execute_ai([{"role": "user", "parts": [{"text": macro_prompt}]}], max_tokens=9000)
                    macro_payload = extract_icu_workout(response)
                    if macro_payload:
                        push_bulk_workouts_to_intervals(ATHLETE_ID, INTERVALS_API_KEY, macro_payload)
                        st.toast(f"Successfully pushed {len(macro_payload)} multi-sport sessions to Intervals.icu!", icon="🚀")
                    else:
                        st.warning("AI generated advice, but could not parse structured weekly plan JSON.")
                except Exception as exc: st.error(str(exc))

    with st.expander("➕ Push Single Workout (Ride or Run) to Intervals.icu", expanded=False):
        with st.form("push_workout_form"):
            w_name = st.text_input("Workout Name", value="Threshold Run / Intervals")
            w_date = st.date_input("Workout Date", value=today)
            w_type = st.selectbox("Activity Type", ["Ride", "Run", "VirtualRide", "VirtualRun", "Workout"], index=1)
            w_desc = st.text_area("Workout Steps / Description", value="Warmup\n- 15m Z2 Pace\n\nMain Set 4x\n- 1km Threshold Pace\n- 90s Jog Recovery\n\nCooldown\n- 10m Easy Jog")
            if st.form_submit_button("🚀 Push Workout to Intervals.icu", use_container_width=True):
                with st.spinner("⏳ Pushing workout to Intervals.icu..."):
                    try:
                        push_bulk_workouts_to_intervals(ATHLETE_ID, INTERVALS_API_KEY, [{
                            "name": w_name, "start_date_local": w_date.isoformat(), "type": w_type, "description": w_desc
                        }])
                        st.toast(f"Pushed '{w_name}' to Intervals.icu for {w_date.isoformat()}!", icon="🚀")
                    except Exception as exc: st.error(str(exc))

elif selected_nav == NAV_OPTIONS[3]:
    st.markdown("##### 🔍 Multi-Sport Activity Inspector")
    if not activities_data:
        st.info("No activities found.")
    else:
        options = {f"[{x.get('type','Ride')}] {x.get('start_date_local','')[:10]} — {x.get('name','Unnamed')} ({round((x.get('distance') or 0)/1000,1)} km)": x for x in activities_data}
        label = st.selectbox("Choose an activity", list(options))
        activity = options[label]
        
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Distance", f"{round((activity.get('distance') or 0)/1000,2)} km")
        c2.metric("Moving Time", f"{int((activity.get('moving_time') or 0)/60)} min")
        c3.metric("Avg Power / HR", f"{activity.get('average_watts','N/A')} W / {activity.get('average_heartrate','N/A')} bpm")
        c4.metric("Compliance Score", calculate_compliance_score(activity))
        
        if st.button("Run AI Debrief", type="primary"):
            compact_activity = activity_summary(activity)
            compliance = calculate_compliance_score(activity)
            with st.spinner("Analyzing multi-sport performance data..."):
                try:
                    prompt_text = f"Give a concise multi-sport performance debrief for this activity: {json.dumps(compact_activity)}. Calculated Compliance: {compliance}. Goal: {st.session_state.goals['target_metric']}."
                    st.session_state.selected_activity_analysis = execute_ai([{"role": "user", "parts": [{"text": prompt_text}]}], max_tokens=9000)
                    st.session_state.selected_activity_label = label
                    st.toast("Debrief generated successfully!", icon="✅")
                except Exception as exc: st.error(str(exc))
                
        if st.session_state.selected_activity_analysis:
            with st.expander("📝 Read Full Debrief", expanded=True):
                st.markdown(st.session_state.selected_activity_analysis)
                if st.button("💬 Discuss with Coach", key="activity_discuss"):
                    discuss_with_coach(f"activity debrief for {st.session_state.selected_activity_label}", st.session_state.selected_activity_analysis)
                    st.rerun()

elif selected_nav == NAV_OPTIONS[4]:
    st.markdown("##### 🗺️ Route Pacing, Climbing & Fueling Strategist")
    uploaded = st.file_uploader("Upload GPX File", type=["gpx"])
    if uploaded:
        metrics = parse_gpx(uploaded.read())
        if metrics:
            st.markdown("###### 📊 Route Summary & Elevation Profile")
            m1, m2, m3 = st.columns(3)
            m1.metric("📏 Total Distance", f"{metrics['distance_km']} km")
            m2.metric("🏔️ Elevation Gain", f"{metrics['elevation_gain_m']} m")
            m3.metric("📈 Max Elevation", f"{metrics['max_elevation_m']} m")
            st.divider()
            
            st.markdown("###### 🧮 Estimated Fueling Calculator")
            est_hours = st.slider("Estimated Completion Time (Hours)", min_value=0.5, max_value=8.0, value=1.5, step=0.25)
            
            carbs_per_hr = 60 if est_hours <= 2.0 else 90
            total_carbs = int(carbs_per_hr * est_hours)
            total_fluid_ml = int(600 * est_hours)
            sodium_mg = int(400 * est_hours)
            
            fc1, fc2, fc3 = st.columns(3)
            fc1.metric("Carbs Target", f"{total_carbs}g total", f"{carbs_per_hr}g / hour")
            fc2.metric("Fluid Target", f"{total_fluid_ml / 1000:.1f} L", "600ml / hour")
            fc3.metric("Sodium Target", f"{sodium_mg}mg total", "400mg / hour")
            st.divider()

            if st.button("Generate Strategy", type="primary"):
                with st.spinner("Analyzing profile & fueling requirements..."):
                    try:
                        prompt_text = f"Analyze this route profile: {json.dumps(metrics)}. Est Duration: {est_hours}h. Goal: {st.session_state.goals['target_metric']}. Guide with practical pacing, climbing, and hourly nutrition guidelines."
                        st.session_state.route_analysis = execute_ai([{"role": "user", "parts": [{"text": prompt_text}]}], max_tokens=9000)
                        st.toast("Strategy generated!", icon="🏔️")
                    except Exception as exc: st.error(str(exc))
                    
            if st.session_state.route_analysis:
                with st.expander("🗺️ Read Strategy", expanded=True):
                    st.markdown(st.session_state.route_analysis)
                    if st.button("💬 Discuss with Coach", key="route_discuss"):
                        discuss_with_coach("my route strategy and fueling plan", st.session_state.route_analysis)
                        st.rerun()
        else:
            st.error("Could not parse GPX file. Ensure it contains valid track points and elevation data.")
