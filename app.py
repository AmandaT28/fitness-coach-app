"""AI Performance Coach — Streamlit single-file app.

Secrets required: GEMINI_API_KEY, SECONDARY_GEMINI_KEY, TERTIARY_GEMINI_KEY.
OpenAI and Anthropic are intentionally not used.
"""
import base64
import datetime as dt
import json
import math
import os
import re
import xml.etree.ElementTree as ET

import pandas as pd
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
GEMINI_MODEL = secret("GEMINI_MODEL", "gemini-3.6-flash")
AI_TIMEOUT = 25
INTERVALS_TIMEOUT = 8
NAV_OPTIONS = ["📊 Command Center", "🤖 AI Coach & Sparring", "📅 Training Calendar", "🔍 Activity Inspector", "🗺️ Route Strategist"]
COACH_PAGE = "🤖 AI Coach & Sparring"
DEFAULT_GOALS = {"event_name": "Bintan Round Island", "target_metric": "Survive steep climbs on group rides & improve threshold power", "race_date": "2026-10-24"}

supabase = None
if SUPABASE_URL and SUPABASE_KEY and create_client:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        pass
localS = LocalStorage() if LocalStorage else None

st.markdown("""
<style>
/* Theme-aware polish: all surfaces inherit the active Streamlit light/dark palette. */
.block-container { max-width: 1480px; padding-top: 1.4rem; padding-bottom: 3rem; }
.top-nav-spacer { height: 2.5rem; }
section[data-testid="stSidebar"] { border-right: 1px solid rgba(128,128,128,.18); }
div[data-testid="stMetric"] { background: var(--secondary-background-color); border: 1px solid rgba(128,128,128,.20); border-radius: 14px; padding: 14px 16px; box-shadow: 0 4px 18px rgba(0,0,0,.05); }
div[data-testid="stExpander"] { border: 1px solid rgba(128,128,128,.22); border-radius: 12px; overflow: hidden; }
div[data-testid="stExpander"] details summary { font-weight: 600; }
.stButton > button { border-radius: 10px; font-weight: 600; transition: transform .15s ease, box-shadow .15s ease; }
.stButton > button:hover { transform: translateY(-1px); box-shadow: 0 5px 14px rgba(0,0,0,.10); }
div[data-testid="stChatMessage"] { border-radius: 14px; }
div[data-testid="stChatMessage"] div[data-testid="stMarkdownContainer"],
div[data-testid="stMarkdownContainer"] { font-size: .92rem; line-height: 1.5; }
div[data-testid="stChatMessage"] div[data-testid="stMarkdownContainer"] p,
div[data-testid="stMarkdownContainer"] li { font-size: .92rem; line-height: 1.5; }
div[data-testid="stRadio"] [role="radiogroup"] { flex-wrap: wrap; gap: .25rem 1rem; }
div[data-testid="stRadio"] label { font-size: .86rem; white-space: nowrap; }
</style>
""", unsafe_allow_html=True)

def init_state():
    defaults = {
        "user": None, "user_credentials": None, "messages": [],
        "active_nav": NAV_OPTIONS[0], "sidebar_nav": NAV_OPTIONS[0],
        "coach_persona": "Collaborative Peer (Balanced & Brainstorming)",
        "athlete_gear": "", "athlete_limitations": "", "goals": DEFAULT_GOALS.copy(),
        "user_supplements": [], "cached_trend_analysis": None,
        "trend_analysis_timestamp": None, "selected_activity_analysis": None,
        "selected_activity_label": None, "route_analysis": None,
        "pending_coach_prompt": None, "ai_test_result": None,
        "ai_diagnostic": None, "coach_reference_notice": None,
        "trend_loaded": False, "calendar_context": "", "profile_loaded": False
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def ensure_initial_message():
    if not st.session_state.messages:
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I am your AI Performance Coach. Ask me to draft next week's training block based on your goals, or discuss any adjustments before pushing them to Intervals.icu & MyWhoosh."}]

def go_to(page):
    st.session_state.active_nav = page

def sidebar_changed():
    st.session_state.active_nav = st.session_state.sidebar_nav

def top_nav_changed():
    st.session_state.active_nav = st.session_state.top_nav

def discuss_with_coach(topic, context):
    context = str(context)
    if len(context) > 6000:
        context = context[:6000] + "\n[Context truncated for a fast coach response.]"
    st.session_state.pending_coach_prompt = f"Let's discuss {topic}.\n\nContext from the app:\n{context}\n\nPlease explain what matters and give my next best action."
    go_to(COACH_PAGE)

def open_coach_with_reference(notice):
    st.session_state.coach_reference_notice = notice
    go_to(COACH_PAGE)

def extract_icu_workout(text):
    """Parses single <icu_workout> or array <icu_weekly_plan> XML tags from AI responses."""
    text_content = text or ""
    
    # Try array / weekly plan format first
    plan_match = re.search(r"<icu_weekly_plan>(.*?)</icu_weekly_plan>", text_content, re.DOTALL | re.IGNORECASE)
    if plan_match:
        try:
            parsed = json.loads(plan_match.group(1).strip())
            if isinstance(parsed, list):
                return parsed
        except Exception:
            pass

    # Single workout format
    single_match = re.search(r"<icu_workout>(.*?)</icu_workout>", text_content, re.DOTALL | re.IGNORECASE)
    if single_match:
        try:
            parsed = json.loads(single_match.group(1).strip())
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

def gemini_generate(prompt, api_key, max_tokens=9000):
    if not api_key:
        raise RuntimeError("Gemini API key is not configured.")
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        json={
            "contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": {
                "maxOutputTokens": max_tokens,
                "thinkingConfig": {"thinkingLevel": "low"},
            },
        },
        timeout=AI_TIMEOUT,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:500]}")
    parts = (response.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    text = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
    if not text:
        raise RuntimeError("Gemini returned no usable text.")
    return text

def execute_ai(prompt, max_tokens=9000):
    errors, seen = [], set()
    for _, key in GEMINI_KEYS:
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            return gemini_generate(prompt, key, max_tokens=max_tokens)
        except Exception as exc:
            errors.append(str(exc))
    st.session_state.ai_diagnostic = "\n\n".join(errors)[:2000] or "No Gemini API keys were found in Streamlit secrets."
    raise RuntimeError("The coach is temporarily unavailable. Please try again shortly.")

def push_bulk_workouts_to_intervals(athlete_id, api_key, workout_list):
    """Pushes a list of structured workouts directly to Intervals.icu calendar (syncs to MyWhoosh)."""
    if not athlete_id or not api_key:
        raise RuntimeError("Intervals.icu credentials are required to push workouts.")
    if not workout_list:
        raise RuntimeError("No workout items to sync.")
        
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events/bulk?upsert=true"
    payload = []
    
    for item in workout_list:
        date_str = item.get("start_date_local", dt.date.today().isoformat())
        payload.append({
            "category": "WORKOUT",
            "start_date_local": f"{date_str}T08:00:00" if "T" not in date_str else date_str,
            "name": item.get("name", "Planned Session"),
            "description": item.get("description", ""),
            "type": item.get("type", "Ride"),
        })
        
    response = requests.post(url, auth=("API_KEY", api_key), json=payload, timeout=INTERVALS_TIMEOUT)
    if response.status_code not in (200, 201):
        raise RuntimeError(f"Failed to push workouts to Intervals.icu (HTTP {response.status_code}): {response.text[:300]}")
    return True

def persist_supplements_to_db():
    if st.session_state.user and supabase:
        try:
            (supabase.table("profiles")
             .update({"supplements": st.session_state.user_supplements})
             .eq("id", st.session_state.user.id)
             .execute())
        except Exception:
            pass
    elif localS and st.session_state.user_credentials:
        try:
            st.session_state.user_credentials["supplements"] = st.session_state.user_supplements
            localS.setItem("athlete_profile_config", st.session_state.user_credentials)
        except Exception:
            pass

def persist_chat_to_db():
    if st.session_state.user and supabase:
        try:
            (supabase.table("profiles")
             .update({"chat_history": st.session_state.messages[-50:]})
             .eq("id", st.session_state.user.id)
             .execute())
        except Exception:
            pass
    elif localS and st.session_state.user_credentials:
        try:
            st.session_state.user_credentials["chat_history"] = st.session_state.messages[-50:]
            localS.setItem("athlete_profile_config", st.session_state.user_credentials)
        except Exception:
            pass

def trend_storage_key():
    return f"coach_trend_analysis:{ATHLETE_ID or display_name}"

def load_persisted_trend():
    if st.session_state.trend_loaded:
        return
    st.session_state.trend_loaded = True
    saved = None
    if st.session_state.user and supabase:
        try:
            result = (supabase.table("profiles").select("trend_analysis, trend_analysis_timestamp")
                      .eq("id", st.session_state.user.id).execute())
            row = result.data[0] if result.data else {}
            if row.get("trend_analysis"):
                saved = {"analysis": row["trend_analysis"], "timestamp": row.get("trend_analysis_timestamp")}
        except Exception:
            pass
    if not saved and localS:
        try:
            value = localS.getItem(trend_storage_key())
            saved = json.loads(value) if isinstance(value, str) else value
        except Exception:
            pass
    if isinstance(saved, dict) and saved.get("analysis"):
        st.session_state.cached_trend_analysis = saved["analysis"]
        st.session_state.trend_analysis_timestamp = saved.get("timestamp") or "Saved previously"

def persist_trend():
    payload = {"analysis": st.session_state.cached_trend_analysis, "timestamp": st.session_state.trend_analysis_timestamp}
    if st.session_state.user and supabase:
        try:
            (supabase.table("profiles").update({"trend_analysis": payload["analysis"], "trend_analysis_timestamp": payload["timestamp"]})
             .eq("id", st.session_state.user.id).execute())
        except Exception:
            pass
    if localS:
        try:
            localS.setItem(trend_storage_key(), json.dumps(payload))
        except Exception:
            pass

def clear_persisted_trend():
    st.session_state.cached_trend_analysis = None
    st.session_state.trend_analysis_timestamp = None
    if st.session_state.user and supabase:
        try:
            (supabase.table("profiles").update({"trend_analysis": None, "trend_analysis_timestamp": None})
             .eq("id", st.session_state.user.id).execute())
        except Exception:
            pass
    if localS:
        try:
            localS.deleteItem(trend_storage_key())
        except Exception:
            pass

@st.cache_data(ttl=300, show_spinner=False)
def fetch_intervals_data(athlete_id, api_key):
    if not athlete_id or not api_key:
        return [], [], [], "Intervals.icu credentials are missing."
    try:
        today = dt.date.today()
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
    try:
        return dt.date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None

def session_summary(event):
    duration_seconds = event.get("moving_time") or event.get("duration") or 0
    distance_m = event.get("distance") or 0
    details = []
    if duration_seconds:
        details.append(f"Duration: {round(float(duration_seconds) / 60)} min")
    if distance_m:
        details.append(f"Distance: {float(distance_m) / 1000:.1f} km")
    if event.get("icu_training_load") is not None:
        details.append(f"Training load: {round(float(event['icu_training_load']))}")
    if event.get("type"):
        details.append(f"Type: {event['type']}")
    if event.get("_calendar_source"):
        details.append(event["_calendar_source"])
    instructions = event.get("description") or event.get("notes") or event.get("workout_description") or event.get("workout_doc") or "No coach instructions were supplied for this session."
    if isinstance(instructions, dict):
        instructions = instructions.get("description") or instructions.get("notes") or instructions.get("name") or "No coach instructions were supplied for this session."
    elif isinstance(instructions, list):
        instructions = " ".join(str(item) for item in instructions if item)
    return {"name": event.get("name") or "Planned workout", "date": str(event.get("start_date_local", ""))[:10], "details": details, "instructions": instructions}

def activity_summary(activity):
    fields = {
        "date": str(activity.get("start_date_local", ""))[:10], "name": activity.get("name", "Unnamed"),
        "type": activity.get("type"), "distance_km": round(float(activity.get("distance") or 0) / 1000, 1),
        "moving_minutes": round(float(activity.get("moving_time") or 0) / 60),
        "average_power_w": activity.get("average_watts"), "normalized_power_w": activity.get("icu_weighted_avg_watts") or activity.get("weighted_average_watts"),
        "training_load": activity.get("icu_training_load"), "elevation_gain_m": activity.get("total_elevation_gain"),
    }
    return {key: value for key, value in fields.items() if value not in (None, "", 0)}

def coach_prompt(question, display_name):
    recent_messages = st.session_state.messages[-4:]
    history = "\n".join(
        f"{m['role'].upper()}: {str(m['content'])[-1200:]}"
        for m in recent_messages
    )
    question = str(question)[-4000:]
    cal_ctx = st.session_state.get("calendar_context", "Not loaded")
    
    # Calculate upcoming Monday date for explicit prompt guidance
    today = dt.date.today()
    next_monday = today + dt.timedelta(days=(0 - today.weekday()) % 7)
    if next_monday == today:
        next_monday += dt.timedelta(days=7)
        
    return f"""You are an elite cycling performance coach with full read/write capability to the athlete's training calendar on Intervals.icu (which automatically syncs to MyWhoosh).
Persona: {st.session_state.coach_persona}
Athlete: {display_name}
Today's Date: {today.isoformat()}
Next Week Starts On (Monday): {next_monday.isoformat()}
Goal: {st.session_state.goals['target_metric']}
Target event: {st.session_state.goals['event_name']} on {st.session_state.goals['race_date']}
Gear: {st.session_state.athlete_gear or 'Not provided'}
Limitations: {st.session_state.athlete_limitations or 'Not provided'}
Available supplements / fuel: {json.dumps(st.session_state.user_supplements, ensure_ascii=False) or 'Not provided'}
Athlete's Recent/Upcoming Calendar Context:\n{cal_ctx}
Recent conversation:\n{history}
Current question:\n{question}

CRITICAL WORKOUT & WEEKLY PLAN GENERATION INSTRUCTIONS:
1. Explain the rationale for the plan directly to the athlete.
2. IF YOU ARE PRESCRBING OR UPDATING A MULTI-DAY OR FULL WEEKLY SCHEDULE, YOU MUST append a JSON array enclosed inside `<icu_weekly_plan>` tags at the very end of your message.
Format example for weekly schedule:
<icu_weekly_plan>
[
  {{
    "name": "VO2 Max 5x3min",
    "type": "Ride",
    "start_date_local": "{next_monday.isoformat()}",
    "description": "- Warmup\\n  - 10m 50-65%\\n\\n- Main Set 5x\\n  - 3m 110-120% 95rpm\\n  - 3m 50% 85rpm\\n\\n- Cooldown\\n  - 10m 50-40%"
  }},
  {{
    "name": "Sweet Spot 3x12min",
    "type": "Ride",
    "start_date_local": "{(next_monday + dt.timedelta(days=2)).isoformat()}",
    "description": "- Warmup\\n  - 10m 50-65%\\n\\n- Main Set 3x\\n  - 12m 88-94% 90rpm\\n  - 4m 50% 85rpm\\n\\n- Cooldown\\n  - 10m 50-40%"
  }}
]
</icu_weekly_plan>

3. IF PRESCRBING A SINGLE WORKOUT ONLY, enclose a JSON object in `<icu_workout>` tags instead.
Always supply valid Intervals.icu plain-text syntax in the `description` field for each workout so MyWhoosh renders ERG mode targets properly."""

def render_coach_reply(question, display_name):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("🤔 **Coach is thinking...**")
        try:
            response = execute_ai(coach_prompt(question, display_name), max_tokens=9000)
        except Exception:
            response = "⚠️ **Coach could not respond right now.** Please try again in a moment."
        placeholder.markdown(clean_chat_content(response))
        
        icu_payload = extract_icu_workout(response)
        if isinstance(icu_payload, list) and len(icu_payload) > 0:
            st.divider()
            st.markdown(f"📋 **Proposed Schedule ({len(icu_payload)} sessions):**")
            for session in icu_payload:
                st.write(f"• **{session.get('start_date_local')}**: `{session.get('name', 'Workout')}` ({session.get('type', 'Ride')})")
                
            if st.button("🚀 Approve & Sync Weekly Plan to Intervals.icu & MyWhoosh", key=f"sync_chat_{len(st.session_state.messages)}", type="primary"):
                try:
                    push_bulk_workouts_to_intervals(ATHLETE_ID, INTERVALS_API_KEY, icu_payload)
                    st.success("✅ All proposed workouts successfully synced to your Intervals.icu calendar! Open MyWhoosh to train.")
                except Exception as exc:
                    st.error(f"Sync failed: {exc}")
                    
        st.session_state.messages.append({"role": "assistant", "content": response})
        persist_chat_to_db()

def parse_gpx(raw):
    root = ET.fromstring(raw.decode("utf-8", errors="ignore")); points, elevations = [], []
    for elem in root.iter():
        if elem.tag.split("}")[-1].lower() not in ("trkpt", "rtept") or not elem.attrib.get("lat") or not elem.attrib.get("lon"):
            continue
        points.append((float(elem.attrib["lat"]), float(elem.attrib["lon"])))
        elevations.append(next((float(c.text) for c in elem if c.tag.split("}")[-1].lower() in ("ele", "elevation", "alt") and c.text), 0.0))
    if not points: return None
    distance = sum(6371 * 2 * math.asin(math.sqrt(math.sin(math.radians(points[i][0]-points[i-1][0])/2)**2 + math.cos(math.radians(points[i-1][0]))*math.cos(math.radians(points[i][0]))*math.sin(math.radians(points[i][1]-points[i-1][1])/2)**2)) for i in range(1, len(points)))
    return {"distance_km": round(distance, 2), "elevation_gain_m": round(sum(max(0, elevations[i]-elevations[i-1]) for i in range(1, len(elevations))), 1), "max_elevation_m": round(max(elevations), 1)}

init_state()
try:
    token = st.query_params.get("token")
    if token and not st.session_state.user_credentials:
        config = json.loads(base64.urlsafe_b64decode(token.encode()).decode())
        if config.get("icu_key") and config.get("icu_id"): st.session_state.user_credentials = config
except Exception:
    pass
if not st.session_state.user and not st.session_state.user_credentials and localS:
    try: st.session_state.user_credentials = localS.getItem("athlete_profile_config")
    except Exception: pass

if not st.session_state.user and not st.session_state.user_credentials:
    st.markdown("##### 🔐 Elite Athlete Portal")
    owner_tab, guest_tab = st.tabs(["Owner Login", "Friend / Guest Setup"])
    with owner_tab:
        if not supabase:
            st.info("Owner login is unavailable until SUPABASE_URL and SUPABASE_KEY are configured.")
        else:
            with st.form("owner_login"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")
                if st.form_submit_button("Log In", use_container_width=True):
                    try:
                        st.session_state.user = supabase.auth.sign_in_with_password({"email": email, "password": password}).user
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Login failed: {exc}")
    with guest_tab:
        with st.form("guest_setup"):
            name = st.text_input("Your Name / Identifier")
            icu_key = st.text_input("Intervals.icu API Key", type="password")
            icu_id = st.text_input("Intervals.icu Athlete ID")
            if st.form_submit_button("Save & Launch Guest Session", use_container_width=True):
                if not icu_key or not icu_id: st.error("Intervals.icu API key and Athlete ID are required.")
                else:
                    st.session_state.user_credentials = {"name": name.strip() or "Guest Athlete", "icu_key": icu_key.strip(), "icu_id": icu_id.strip()}
                    if localS: localS.setItem("athlete_profile_config", st.session_state.user_credentials)
                    st.rerun()
    st.stop()

if st.session_state.user:
    try:
        profile_result = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute() if supabase else None
        profile = profile_result.data[0] if profile_result and profile_result.data else {}
    except Exception:
        profile = {}
    INTERVALS_API_KEY = profile.get("intervals_api_key", "")
    ATHLETE_ID = profile.get("intervals_athlete_id", "")
    display_name = profile.get("name") or "Athlete"
    st.session_state.athlete_gear = st.session_state.athlete_gear or profile.get("gear_notes", "")
    st.session_state.athlete_limitations = st.session_state.athlete_limitations or profile.get("limitations_notes", "")
    for key in DEFAULT_GOALS:
        st.session_state.goals[key] = profile.get(key) or st.session_state.goals[key]
    
    if not st.session_state.profile_loaded:
        if isinstance(profile.get("supplements"), list):
            st.session_state.user_supplements = profile["supplements"]
        if isinstance(profile.get("chat_history"), list) and profile["chat_history"]:
            st.session_state.messages = profile["chat_history"]
        st.session_state.profile_loaded = True
else:
    creds = st.session_state.user_credentials or {}
    INTERVALS_API_KEY, ATHLETE_ID, display_name = creds.get("icu_key", ""), creds.get("icu_id", ""), creds.get("name", "Athlete")
    st.session_state.athlete_gear = st.session_state.athlete_gear or creds.get("gear", "")
    st.session_state.athlete_limitations = st.session_state.athlete_limitations or creds.get("limitations", "")
    if isinstance(creds.get("goals"), dict):
        st.session_state.goals.update({key: value for key, value in creds["goals"].items() if key in DEFAULT_GOALS and value})
    if not st.session_state.profile_loaded:
        if isinstance(creds.get("supplements"), list):
            st.session_state.user_supplements = creds["supplements"]
        if isinstance(creds.get("chat_history"), list) and creds["chat_history"]:
            st.session_state.messages = creds["chat_history"]
        st.session_state.profile_loaded = True

ensure_initial_message()
load_persisted_trend()

wellness_list, activities_data, planned_events, intervals_status = fetch_intervals_data(ATHLETE_ID, INTERVALS_API_KEY)
st.session_state.calendar_context = json.dumps([session_summary(ev) for ev in planned_events[:15]], ensure_ascii=False)

if st.session_state.active_nav not in NAV_OPTIONS:
    st.session_state.active_nav = NAV_OPTIONS[0]
    st.session_state.sidebar_nav = NAV_OPTIONS[0]
if st.session_state.sidebar_nav != st.session_state.active_nav:
    st.session_state.sidebar_nav = st.session_state.active_nav
with st.sidebar:
    st.markdown("##### AI Performance Coach")
    st.radio("Navigate", NAV_OPTIONS, key="sidebar_nav", on_change=sidebar_changed)
    st.divider()
    st.session_state.coach_persona = st.selectbox("Coaching Persona", ["Collaborative Peer (Balanced & Brainstorming)", "Sports Scientist (Data & Periodization Focus)", "Drill Sergeant (Strict & Direct Accountability)"], index=["Collaborative Peer (Balanced & Brainstorming)", "Sports Scientist (Data & Periodization Focus)", "Drill Sergeant (Strict & Direct Accountability)"].index(st.session_state.coach_persona))
    
    with st.expander("Recovery, fuel & supplements", expanded=False):
        st.caption("For your coach's reference when discussing recovery and ride fueling.")
        with st.form("sidebar_supplement_form", clear_on_submit=True):
            supplement_name = st.text_input("Supplement / fuel")
            supplement_timing = st.text_input("When to use it")
            supplement_notes = st.text_input("Purpose or notes")
            if st.form_submit_button("Add to coach reference", use_container_width=True) and supplement_name.strip():
                st.session_state.user_supplements.append({
                    "name": supplement_name.strip(),
                    "timing": supplement_timing.strip() or "As needed",
                    "notes": supplement_notes.strip() or ""
                })
                persist_supplements_to_db()
                st.rerun()
                
        if st.session_state.user_supplements:
            for item in st.session_state.user_supplements:
                st.write(f"• **{item['name']}** — {item['timing']}{(': ' + item['notes']) if item['notes'] else ''}")
            remove_name = st.selectbox("Remove from coach reference", ["Keep all"] + [item["name"] for item in st.session_state.user_supplements], key="remove_supplement")
            if remove_name != "Keep all" and st.button("Remove selected", key="remove_supplement_button", use_container_width=True):
                st.session_state.user_supplements = [item for item in st.session_state.user_supplements if item["name"] != remove_name]
                persist_supplements_to_db()
                st.rerun()

    with st.expander("Athlete profile & goal", expanded=False):
        with st.form("sidebar_profile_form"):
            event_name = st.text_input("Target event", value=st.session_state.goals["event_name"])
            target_metric = st.text_area("Primary objective", value=st.session_state.goals["target_metric"])
            race_date = st.date_input("Race date", value=dt.date.fromisoformat(st.session_state.goals["race_date"]))
            gear = st.text_area("Bike / gear notes", value=st.session_state.athlete_gear)
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
                            "chat_history": st.session_state.messages[-50:]
                        }).eq("id", st.session_state.user.id).execute())
                    except Exception as exc:
                        st.warning(f"Profile saved for session, but Supabase could not be updated: {exc}")
                elif localS:
                    try:
                        st.session_state.user_credentials.update({"gear": gear, "limitations": limitations, "goals": st.session_state.goals, "supplements": st.session_state.user_supplements, "chat_history": st.session_state.messages[-50:]})
                        localS.setItem("athlete_profile_config", st.session_state.user_credentials)
                    except Exception:
                        pass
                st.success("Profile saved.")
                
    with st.expander("AI connection", expanded=False):
        configured = sum(bool(key) for _, key in GEMINI_KEYS)
        st.write(f"Gemini keys configured: {configured}/3")
        st.caption(f"Model: {GEMINI_MODEL}")
        if st.button("Test AI connection", key="test_gemini", use_container_width=True):
            try:
                execute_ai("Reply exactly: AI connection successful.")
                st.session_state.ai_diagnostic = None
                st.success("AI connection successful.")
            except Exception:
                st.error("AI connection failed. Details are shown below.")
        if st.session_state.ai_diagnostic:
            st.caption("Diagnostic (does not include API keys)")
            st.code(st.session_state.ai_diagnostic, language="text")
            
    if st.button("Clear chat history", use_container_width=True):
        st.session_state.messages = []
        ensure_initial_message()
        persist_chat_to_db()
        st.rerun()
    if st.button("Log out / switch account", use_container_width=True):
        if st.session_state.user and supabase:
            try: supabase.auth.sign_out()
            except Exception: pass
        st.session_state.user, st.session_state.user_credentials = None, None
        st.session_state.profile_loaded = False
        if localS:
            try: localS.deleteItem("athlete_profile_config")
            except Exception: pass
        st.rerun()

st.markdown("<div class='top-nav-spacer'></div>", unsafe_allow_html=True)
if st.session_state.get("top_nav") != st.session_state.active_nav:
    st.session_state.top_nav = st.session_state.active_nav
st.radio(
    "Navigate pages",
    NAV_OPTIONS,
    horizontal=True,
    label_visibility="collapsed",
    key="top_nav",
    on_change=top_nav_changed,
)
selected_nav = st.session_state.active_nav

latest = wellness_list[-1] if wellness_list else {}
ctl, atl, tsb = latest.get("ctl", 0) or 0, latest.get("atl", 0) or 0, latest.get("tsb", 0) or 0

if selected_nav == NAV_OPTIONS[0]:
    st.markdown("##### ☀️ Command Center")
    st.caption(f"Intervals.icu: {intervals_status}")
    sleep_score = latest.get("sleep_score") or latest.get("sleepScore")
    if not wellness_list:
        readiness, focus, watch = "Readiness unavailable", "Sync Intervals.icu to assess today.", "No current wellness data."
    elif tsb <= -20:
        readiness, focus, watch = "Recovery first", "Keep today easy or rest.", f"High accumulated fatigue (TSB {tsb:.0f})."
    elif tsb <= -8:
        readiness, focus, watch = "Manage the load", "Train, but avoid adding unplanned intensity.", f"Fatigue is elevated (TSB {tsb:.0f})."
    elif tsb <= 12:
        readiness, focus, watch = "Ready to train", "Your planned session is appropriate.", f"Form is balanced (TSB {tsb:.0f})."
    else:
        readiness, focus, watch = "Fresh", "A quality session can fit if it is on the plan.", f"You are carrying low fatigue (TSB {tsb:.0f})."
    sleep_note = f" Sleep score: {sleep_score}/100." if sleep_score else ""
    st.markdown("###### Today at a glance")
    st.info(f"**{readiness}.** {focus} **Note:** {watch}{sleep_note}")
    c1,c2,c3 = st.columns(3); c1.metric("Fitness (CTL)", round(ctl,1)); c2.metric("Fatigue (ATL)", round(atl,1)); c3.metric("Form (TSB)", round(tsb,1))
    if st.button("🚀 Run 90-Day Trend Synthesis", type="primary"):
        payload = f"Analyze this cycling athlete's last 90 days. CTL {ctl}; ATL {atl}; TSB {tsb}. Recent activities: {json.dumps(activities_data[:15], default=str)}. Goal: {st.session_state.goals['target_metric']}. Give trajectory, consistency, fatigue, climbing readiness, and practical next steps."
        with st.spinner("Analyzing 90 days of training..."):
            try:
                st.session_state.cached_trend_analysis = execute_ai(payload, max_tokens=9000)
                st.session_state.trend_analysis_timestamp = dt.datetime.now().astimezone().strftime("%d %b %Y, %H:%M %Z")
                persist_trend()
            except Exception as exc: st.error(str(exc))
    if st.session_state.cached_trend_analysis:
        st.markdown("###### 90-Day Trend Analysis")
        st.caption(f"Generated {st.session_state.trend_analysis_timestamp} · remains visible until cleared or re-run.")
        st.markdown(st.session_state.cached_trend_analysis)
        a,b = st.columns(2)
        if a.button("💬 Discuss with Coach", key="trend_discuss"):
            open_coach_with_reference("Your dated 90-Day Trend Analysis remains on the Command Center. Ask the coach a question about it here; the full report is not copied into chat.")
            st.rerun()
        if b.button("Clear trend analysis", key="clear_trend"): clear_persisted_trend(); st.rerun()

elif selected_nav == COACH_PAGE:
    st.markdown("##### 🤖 AI Coach & Collaborative Sparring Partner")
    if st.session_state.coach_reference_notice:
        st.info(st.session_state.coach_reference_notice)
        st.session_state.coach_reference_notice = None
        
    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            st.markdown(clean_chat_content(message["content"]))
            if message["role"] == "assistant":
                icu_payload = extract_icu_workout(message["content"])
                if isinstance(icu_payload, list) and len(icu_payload) > 0:
                    st.divider()
                    st.markdown(f"📋 **Proposed Plan ({len(icu_payload)} sessions):**")
                    for session in icu_payload:
                        st.write(f"• **{session.get('start_date_local')}**: `{session.get('name', 'Workout')}` ({session.get('type', 'Ride')})")
                        
                    if st.button("🚀 Sync Plan to Intervals.icu & MyWhoosh", key=f"sync_hist_{idx}", type="primary"):
                        try:
                            push_bulk_workouts_to_intervals(ATHLETE_ID, INTERVALS_API_KEY, icu_payload)
                            st.success("✅ Workouts successfully synced to Intervals.icu calendar!")
                        except Exception as exc:
                            st.error(f"Sync failed: {exc}")

    pending = st.session_state.pending_coach_prompt
    if pending:
        st.session_state.pending_coach_prompt = None
        render_coach_reply(pending, display_name)
    elif question := st.chat_input("Ask your coach anything... e.g. 'Plan my next week of training'"):
        render_coach_reply(question.strip(), display_name)

elif selected_nav == NAV_OPTIONS[2]:
    st.markdown("##### 📅 Training Calendar & Intervals.icu Sync")
    today = dt.date.today()
    window_start, window_end = today - dt.timedelta(days=14), today + dt.timedelta(days=14)
    st.caption(f"Showing the previous 14 days and the next 14 days · {window_start:%d %b}–{window_end:%d %b %Y}")
    
    with st.expander("➕ Push New Workout to Intervals.icu Calendar (Syncs to MyWhoosh)", expanded=False):
        with st.form("push_workout_form"):
            w_name = st.text_input("Workout Name", value="VO2Max Intervals")
            w_date = st.date_input("Workout Date", value=today)
            w_type = st.selectbox("Activity Type", ["Ride", "VirtualRide", "Workout"], index=0)
            w_desc = st.text_area("Workout Steps (Intervals.icu Text Syntax)", value="- 10m 50%\n- 5x [3m 115%, 3m 50%]\n- 10m 50%")
            if st.form_submit_button("🚀 Push Workout to Intervals.icu", use_container_width=True):
                try:
                    push_bulk_workouts_to_intervals(ATHLETE_ID, INTERVALS_API_KEY, [{
                        "name": w_name,
                        "start_date_local": w_date.isoformat(),
                        "type": w_type,
                        "description": w_desc
                    }])
                    st.success(f"Successfully pushed '{w_name}' to Intervals.icu for {w_date.isoformat()}! It will sync to MyWhoosh.")
                except Exception as exc:
                    st.error(str(exc))

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
    past_activities = calendar_items(activities_data, "Completed ride", window_start, today - dt.timedelta(days=1))

    def render_calendar_days(items, empty_message):
        if not items:
            st.info(empty_message)
            return {}
        grouped_items = {}
        for item in items:
            grouped_items.setdefault(event_date(item).isoformat(), []).append(item)
        for date, sessions in sorted(grouped_items.items()):
            session_names = [event.get("name") or "Planned workout" for event in sessions]
            header_names = " + ".join(session_names[:2])
            if len(session_names) > 2:
                header_names += f" + {len(session_names) - 2} more"
            with st.expander(f"{date} · {header_names}", expanded=False):
                for number, event in enumerate(sessions, 1):
                    session = session_summary(event)
                    st.markdown(f"**Session {number}: {session['name']}**")
                    if session["details"]:
                        st.caption(" · ".join(session["details"]))
                    st.markdown(f"**Coach instructions:** {session['instructions']}")
                    if number < len(sessions):
                        st.divider()
        return grouped_items

    current_tab, past_tab = st.tabs(["Current & future sessions", "Past activities"])
    with current_tab:
        future_grouped = render_calendar_days(future_sessions, "No calendar sessions were returned for the next 14 days.")
    with past_tab:
        past_grouped = render_calendar_days(past_activities, "No completed activities were returned for the previous 14 days.")

    grouped = {**past_grouped}
    for date, sessions in future_grouped.items():
        grouped[date] = grouped.get(date, []) + sessions
    if grouped:
        st.divider()
        discussion_date = st.selectbox("Discuss a calendar day with Coach", list(sorted(grouped)), format_func=lambda value: f"{value} · " + " + ".join(event.get("name") or "Planned workout" for event in grouped[value]))
        if st.button("💬 Discuss selected day with Coach", type="primary"):
            readable_sessions = [session_summary(event) for event in grouped[discussion_date]]
            discuss_with_coach(f"my training sessions on {discussion_date}", json.dumps(readable_sessions, ensure_ascii=False))
            st.rerun()

elif selected_nav == NAV_OPTIONS[3]:
    st.markdown("##### 🔍 Activity Inspector")
    if not activities_data: st.info("No activities found.")
    else:
        options = {f"{x.get('start_date_local','')[:10]} — {x.get('name','Unnamed')} ({round((x.get('distance') or 0)/1000,1)} km)": x for x in activities_data}
        label = st.selectbox("Choose an activity", list(options)); activity = options[label]
        c1,c2,c3=st.columns(3); c1.metric("Distance", f"{round((activity.get('distance') or 0)/1000,2)} km"); c2.metric("Moving Time", f"{int((activity.get('moving_time') or 0)/60)} min"); c3.metric("Average Power", f"{activity.get('average_watts','N/A')} W")
        if st.button("Run AI Debrief", type="primary"):
            compact_activity = activity_summary(activity)
            try: st.session_state.selected_activity_analysis = execute_ai(f"Give a concise cycling performance debrief based only on this summary: {json.dumps(compact_activity)}. Goal: {st.session_state.goals['target_metric']}. Use six short sections: execution, intensity, stimulus, strengths, recovery, and next session."); st.session_state.selected_activity_label = label
            except Exception as exc: st.error(str(exc))
        if st.session_state.selected_activity_analysis:
            st.markdown(st.session_state.selected_activity_analysis)
            if st.button("💬 Discuss with Coach", key="activity_discuss"): discuss_with_coach(f"activity debrief for {st.session_state.selected_activity_label}", st.session_state.selected_activity_analysis); st.rerun()

elif selected_nav == "🗺️ Route Strategist":
    st.markdown("##### 🗺️ Route Pacing & Climbing Strategist")
    uploaded = st.file_uploader("Upload GPX", type=["gpx"])
    if uploaded:
        try:
            metrics = parse_gpx(uploaded.read())
            if metrics:
                st.json(metrics)
                if st.button("Generate Climbing Strategy", type="primary"): st.session_state.route_analysis = execute_ai(f"Analyze this cycling route: {json.dumps(metrics)}. Goal: {st.session_state.goals['target_metric']}. Give a practical pacing and climbing strategy.")
                if st.session_state.route_analysis:
                    st.markdown(st.session_state.route_analysis)
                    if st.button("💬 Discuss with Coach", key="route_discuss"): discuss_with_coach("my route strategy", st.session_state.route_analysis); st.rerun()
        except Exception as exc: st.error(f"Could not parse GPX: {exc}")
