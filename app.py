import base64
import datetime as dt
import json
import math
import os
import re
import time
import xml.etree.ElementTree as ET
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd
import requests
import streamlit as st

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None

try:
    from google import genai
    from google.genai import types as genai_types
except ImportError:
    genai = None
    genai_types = None

from supabase import Client, create_client

try:
    from streamlit_local_storage import LocalStorage
except ImportError:
    LocalStorage = None


# -----------------------------------------------------------------------------
# APP CONFIG
# -----------------------------------------------------------------------------
st.set_page_config(
    page_title="AI Performance Coach • Elite Suite",
    page_icon="🚴‍♂️",
    layout="wide",
)

if load_dotenv:
    load_dotenv()


# -----------------------------------------------------------------------------
# SECRETS / ENV HELPERS
# -----------------------------------------------------------------------------
def secret_or_env(name: str, default: Optional[str] = None) -> Optional[str]:
    try:
        value = st.secrets.get(name)
        if value:
            return str(value)
    except Exception:
        pass
    return os.getenv(name, default)


SUPABASE_URL = secret_or_env("SUPABASE_URL")
SUPABASE_KEY = secret_or_env("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase credentials missing. Add SUPABASE_URL and SUPABASE_KEY to Streamlit Secrets.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)


# -----------------------------------------------------------------------------
# UI STYLE
# -----------------------------------------------------------------------------
st.markdown(
    """
    <style>
        [data-testid="stStatusWidget"],
        .viewerBadge_container__1QSob,
        div[class*="viewerBadge"] {
            visibility: hidden !important;
            display: none !important;
        }
        .stCard {
            background-color: #ffffff;
            border: 1px solid rgba(128, 128, 128, 0.15);
            border-radius: 12px;
            padding: 20px;
            margin-bottom: 16px;
            box-shadow: 0 4px 12px rgba(0,0,0,0.03);
        }
        div[data-testid="stMetric"] {
            background-color: rgba(128, 128, 128, 0.02);
            border: 1px solid rgba(128, 128, 128, 0.08);
            padding: 12px 16px;
            border-radius: 10px;
        }
        div[data-testid="stMetric"] label {
            font-size: 0.85rem !important;
            font-weight: 500;
            color: #555555;
        }
        div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
            font-size: 1.3rem !important;
            font-weight: 600;
        }
    </style>
    """,
    unsafe_allow_html=True,
)


# -----------------------------------------------------------------------------
# LOCAL STORAGE
# -----------------------------------------------------------------------------
class SessionStorage:
    """Small abstraction so the app still works if streamlit-local-storage is absent."""

    def __init__(self):
        self._backend = LocalStorage() if LocalStorage else None
        self._fallback = {}

    def getItem(self, key: str):
        if self._backend:
            try:
                return self._backend.getItem(key)
            except Exception:
                pass
        return self._fallback.get(key)

    def setItem(self, key: str, value: Any):
        if self._backend:
            try:
                self._backend.setItem(key, value)
                return
            except Exception:
                pass
        self._fallback[key] = value

    def deleteItem(self, key: str):
        if self._backend:
            try:
                self._backend.deleteItem(key)
                return
            except Exception:
                pass
        self._fallback.pop(key, None)


localS = SessionStorage()


# -----------------------------------------------------------------------------
# AI KEY INITIALIZATION (GEMINI MULTI-KEY FAILOVER)
# -----------------------------------------------------------------------------
def get_nested_secret(section: str, key: str) -> Optional[str]:
    try:
        group = st.secrets.get(section, {})
        if isinstance(group, dict):
            value = group.get(key)
            return str(value) if value else None
    except Exception:
        pass
    return None


PRIMARY_GEMINI_KEY = (
    get_nested_secret("google_keys", "primary_key")
    or secret_or_env("GEMINI_API_KEY")
    or secret_or_env("PRIMARY_KEY")
)
SECONDARY_GEMINI_KEY = (
    get_nested_secret("google_keys", "secondary_key")
    or secret_or_env("SECONDARY_GEMINI_API_KEY")
    or secret_or_env("SECONDARY_KEY")
)
TERTIARY_GEMINI_KEY = (
    get_nested_secret("google_keys", "tertiary_key")
    or secret_or_env("TERTIARY_GEMINI_API_KEY")
    or secret_or_env("TERTIARY_KEY")
)


# -----------------------------------------------------------------------------
# SESSION STATE
# -----------------------------------------------------------------------------
def init_state() -> None:
    defaults = {
        "user_credentials": None,
        "user": None,
        "messages": [],
        "selected_activity_analysis": None,
        "auto_debriefed_id": None,
        "cached_trend_analysis": None,
        "trend_analysis_timestamp": None,
        "athlete_gear": "",
        "athlete_limitations": "",
        "goals": {
            "event_name": "Bintan Round Island",
            "target_metric": "Survive steep climbs on group rides & improve threshold power",
            "race_date": "2026-10-24",
        },
        "user_supplements": [
            {"name": "Creatine", "timing": "Post-Workout", "notes": "Cellular ATP replenishment & sprint power"},
            {"name": "Protein", "timing": "Post-Workout (<45m)", "notes": "Muscle repair & glycogen resynthesis"},
            {"name": "Turmeric", "timing": "Morning with Fats", "notes": "Systemic inflammation control"},
            {"name": "Fish Oil", "timing": "Morning & Evening", "notes": "Cardiovascular & nocturnal recovery"},
            {"name": "NMN", "timing": "Morning (Fasted)", "notes": "Cellular NAD+ & mitochondrial support"},
        ],
        "active_nav": "📊 Command Center",
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


init_state()


# -----------------------------------------------------------------------------
# URL TOKEN HANDLER
# -----------------------------------------------------------------------------
url_token = st.query_params.get("token")
if url_token and not st.session_state.user_credentials:
    try:
        decoded = base64.urlsafe_b64decode(url_token.encode("utf-8"))
        guest_config = json.loads(decoded.decode("utf-8"))
        if isinstance(guest_config, dict) and guest_config.get("icu_key") and guest_config.get("icu_id"):
            localS.setItem("athlete_profile_config", guest_config)
            st.session_state.user_credentials = guest_config
            st.rerun()
    except Exception:
        pass


# -----------------------------------------------------------------------------
# AUTH / PROFILE
# -----------------------------------------------------------------------------
stored_guest = localS.getItem("athlete_profile_config")
if not st.session_state.user and stored_guest and not st.session_state.user_credentials:
    st.session_state.user_credentials = stored_guest


if not st.session_state.user and not st.session_state.user_credentials:
    st.markdown("### 🔐 Elite Athlete Portal • Authentication")
    owner_tab, guest_tab = st.tabs(["👑 Owner Login (Supabase)", "⚙️ Friend / Guest Setup (BYOK)"])

    with owner_tab:
        st.markdown("Log in using your registered Supabase account credentials.")
        with st.form("supabase_login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            submitted = st.form_submit_button("Log In with Supabase", use_container_width=True)
            if submitted:
                try:
                    result = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user = result.user
                    st.success("Supabase login successful!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Login failed: {exc}")

    with guest_tab:
        st.markdown("Friends can connect using their own Intervals.icu and Google AI Studio key.")
        with st.form("guest_setup_form"):
            col_name = st.text_input("Your Name / Identifier")
            icu_key = st.text_input("Intervals.icu API Key", type="password")
            icu_id = st.text_input("Intervals.icu Athlete ID")
            gemini_key = st.text_input("Google AI Studio (Gemini) API Key", type="password")
            submitted = st.form_submit_button("Save & Launch Guest Session", use_container_width=True)
            if submitted:
                if icu_key.strip() and icu_id.strip() and gemini_key.strip():
                    config_data = {
                        "name": col_name.strip() if col_name else "Guest Athlete",
                        "icu_key": icu_key.strip(),
                        "icu_id": icu_id.strip(),
                        "gemini_key": gemini_key.strip(),
                        "gear": "",
                        "limitations": "",
                        "onboarding_done": False,
                    }
                    localS.setItem("athlete_profile_config", config_data)
                    st.session_state.user_credentials = config_data
                    st.success("Configuration saved! Launching dashboard...")
                    st.rerun()
                else:
                    st.warning("Please fill in all required fields.")
    st.stop()


# Resolve user/guest profile.
if st.session_state.user:
    USER_ID = st.session_state.user.id
    try:
        profile_res = supabase.table("profiles").select("*").eq("id", USER_ID).execute()
        user_profile = profile_res.data[0] if profile_res.data else {}
    except Exception:
        user_profile = {}

    INTERVALS_API_KEY = user_profile.get("intervals_api_key")
    ATHLETE_ID = user_profile.get("intervals_athlete_id")
    display_name = user_profile.get("name") or "Athlete"
    guest_gemini_key = None

    st.session_state.athlete_gear = st.session_state.athlete_gear or user_profile.get("gear_notes") or ""
    st.session_state.athlete_limitations = st.session_state.athlete_limitations or user_profile.get("limitations_notes") or ""
    st.session_state.goals["event_name"] = user_profile.get("event_name") or st.session_state.goals["event_name"]
    st.session_state.goals["target_metric"] = user_profile.get("target_metric") or st.session_state.goals["target_metric"]
    st.session_state.goals["race_date"] = user_profile.get("race_date") or st.session_state.goals["race_date"]
else:
    current_creds = st.session_state.user_credentials or {}
    INTERVALS_API_KEY = current_creds.get("icu_key")
    ATHLETE_ID = current_creds.get("icu_id")
    display_name = current_creds.get("name") or "Guest Athlete"
    guest_gemini_key = current_creds.get("gemini_key")
    st.session_state.athlete_gear = st.session_state.athlete_gear or current_creds.get("gear", "")
    st.session_state.athlete_limitations = st.session_state.athlete_limitations or current_creds.get("limitations", "")


# -----------------------------------------------------------------------------
# AI PROVIDER ROUTER (Gemini 3.x Flash Suite)
# -----------------------------------------------------------------------------
def get_model_id_from_selection(selection: str) -> str:
    if "3.7" in selection:
        return "gemini-3.7-flash"
    elif "3.6" in selection:
        return "gemini-3.6-flash"
    elif "3.5" in selection:
        return "gemini-3.5-flash"
    return "gemini-3.7-flash"


def make_gemini_client(api_key: Optional[str]):
    if not api_key or not genai:
        return None
    try:
        http_options = genai_types.HttpOptions(timeout=45000) if genai_types else None
        return genai.Client(api_key=api_key, http_options=http_options)
    except Exception:
        return None


def append_error(errors: List[str], label: str, exc: Exception) -> None:
    message = str(exc).replace("\n", " ")
    if len(message) > 400:
        message = message[:400] + "…"
    errors.append(f"{label}: {message}")


def call_gemini(prompt: str, api_key: Optional[str], label: str, model_name: str) -> Tuple[str, str]:
    client = make_gemini_client(api_key)
    if not client:
        raise RuntimeError(f"{label} Gemini client is not configured.")

    result = client.models.generate_content(
        model=model_name,
        contents=prompt,
        config={"max_output_tokens": 1800, "temperature": 0.7},
    )
    text = getattr(result, "text", None)
    if not text:
        raise RuntimeError(f"{label} Gemini returned an empty response.")
    return text.strip(), f"Google {model_name} ({label})"


def execute_multiprovider_generation(prompt: str, preferred_provider: str = "Gemini 3.7 Flash") -> Tuple[str, str]:
    """Graceful multi-key & multi-model fallback chain."""
    errors: List[str] = []
    target_model = get_model_id_from_selection(preferred_provider)

    guest_action = lambda: call_gemini(prompt, guest_gemini_key, "Guest Key", target_model)
    primary_action = lambda: call_gemini(prompt, PRIMARY_GEMINI_KEY, "Primary Key", target_model)
    secondary_action = lambda: call_gemini(prompt, SECONDARY_GEMINI_KEY, "Secondary Key", target_model)
    tertiary_action = lambda: call_gemini(prompt, TERTIARY_GEMINI_KEY, "Tertiary Key", target_model)

    actions = []
    if guest_gemini_key:
        actions.append(guest_action)
    actions.extend([primary_action, secondary_action, tertiary_action])

    for action in actions:
        try:
            return action()
        except Exception as exc:
            append_error(errors, getattr(action, "__name__", "provider"), exc)
            continue

    diagnostic = " | ".join(errors) if errors else "No Gemini API keys were configured."
    raise RuntimeError(f"All Gemini fallback keys failed for {target_model}. {diagnostic}")


# -----------------------------------------------------------------------------
# ONBOARDING
# -----------------------------------------------------------------------------
def profile_is_onboarded() -> bool:
    if st.session_state.user:
        return bool(user_profile.get("onboarding_done", False))
    return bool((st.session_state.user_credentials or {}).get("onboarding_done", False))


if not st.session_state.messages:
    st.session_state.messages = [
        {
            "role": "assistant",
            "content": f"Hey {display_name}! I'm your autonomous performance coach. Tell me a bit about your current routine, limitations, and focus.",
        }
    ]


if not profile_is_onboarded():
    st.markdown("### 🚴‍♂️ Coach's Initial Intake & Onboarding")
    st.markdown("Welcome! Before we dive into your telemetry, let's have a quick introductory chat.")

    for msg in st.session_state.messages:
        role = "user" if msg.get("role") == "user" else "assistant"
        with st.chat_message(role):
            st.markdown(msg.get("content", ""))

    intake_reply = st.chat_input("Tell your coach about yourself...", key="onboarding_chat_input")
    selected_provider = "Gemini 3.7 Flash"
    if intake_reply and intake_reply.strip():
        text = intake_reply.strip()
        st.session_state.messages.append({"role": "user", "content": text})
        try:
            response, _ = execute_multiprovider_generation(
                f"You are an elite cycling performance coach. The athlete shared: {text}\nAcknowledge them professionally and ask one useful follow-up question.",
                selected_provider
            )
        except Exception:
            response = "Thanks — I have enough context to get started. We can refine your profile as we go."

        st.session_state.messages.append({"role": "assistant", "content": response})
        if st.session_state.user:
            try:
                supabase.table("profiles").update({"onboarding_done": True}).eq("id", USER_ID).execute()
            except Exception:
                pass
        else:
            creds = st.session_state.user_credentials or {}
            creds["onboarding_done"] = True
            localS.setItem("athlete_profile_config", creds)
            st.session_state.user_credentials = creds
        st.rerun()
    st.stop()


# -----------------------------------------------------------------------------
# INTERVALS.ICU DATA
# -----------------------------------------------------------------------------
@st.cache_data(ttl=300, show_spinner=False)
def fetch_intervals_data(aid: str, key: str):
    if not aid or not key:
        return [], [], []

    today = dt.date.today()
    start_90 = (today - dt.timedelta(days=90)).isoformat()
    start_7 = (today - dt.timedelta(days=7)).isoformat()
    end_14 = (today + dt.timedelta(days=14)).isoformat()

    urls = {
        "wellness": f"https://intervals.icu/api/v1/athlete/{aid}/wellness?oldest={start_90}&newest={end_14}",
        "activities": f"https://intervals.icu/api/v1/athlete/{aid}/activities?oldest={start_90}&newest={end_14}",
        "events": f"https://intervals.icu/api/v1/athlete/{aid}/events?oldest={start_7}&newest={end_14}",
    }

    headers = {"Accept": "application/json"}

    def get_json(url: str):
        response = requests.get(url, auth=("API_KEY", key), headers=headers, timeout=(5, 20))
        response.raise_for_status()
        data = response.json()
        return data if isinstance(data, list) else []

    try:
        wellness = get_json(urls["wellness"])
    except Exception:
        wellness = []
    try:
        activities = get_json(urls["activities"])
    except Exception:
        activities = []
    try:
        events = get_json(urls["events"])
    except Exception:
        events = []

    return wellness, activities, events


wellness_list, activities_data, planned_events = fetch_intervals_data(ATHLETE_ID, INTERVALS_API_KEY)

ctl = atl = tsb = sleep_score = 0.0
if wellness_list:
    latest = wellness_list[-1] if isinstance(wellness_list[-1], dict) else {}
    ctl = float(latest.get("ctl") or 0)
    atl = float(latest.get("atl") or 0)
    tsb = float(latest.get("tsb") or 0)
    for row in reversed(wellness_list):
        candidate = row.get("sleepScore") if isinstance(row, dict) else None
        if candidate not in (None, "", 0):
            try:
                sleep_score = float(candidate)
            except Exception:
                pass
            break

try:
    race_date_obj = dt.datetime.strptime(st.session_state.goals["race_date"], "%Y-%m-%d").date()
except Exception:
    race_date_obj = dt.date(2026, 10, 24)

days_left = (race_date_obj - dt.date.today()).days


# -----------------------------------------------------------------------------
# NAVIGATION
# -----------------------------------------------------------------------------
NAV_OPTIONS = [
    "📊 Command Center",
    "🤖 AI Coach & Sparring",
    "📅 Training Calendar",
    "🔍 Activity Inspector",
    "💊 Recovery & Supplements",
    "🗺️ Route Strategist",
]


def set_nav(value: str):
    st.session_state.active_nav = value


top_nav = st.radio(
    "Navigation Suite Top",
    NAV_OPTIONS,
    index=NAV_OPTIONS.index(st.session_state.active_nav),
    horizontal=True,
    label_visibility="collapsed",
    key="top_nav_widget",
)
if top_nav != st.session_state.active_nav:
    set_nav(top_nav)
    st.rerun()

st.markdown("---")


# -----------------------------------------------------------------------------
# SIDEBAR
# -----------------------------------------------------------------------------
with st.sidebar:
    st.markdown(f"👤 **{display_name}**")
    st.markdown("---")

    st.subheader("⚡ Quick Navigation Links")
    sidebar_nav = st.radio(
        "Secondary Navigation",
        NAV_OPTIONS,
        index=NAV_OPTIONS.index(st.session_state.active_nav),
        key="sidebar_nav_selector",
        label_visibility="collapsed",
    )
    if sidebar_nav != st.session_state.active_nav:
        set_nav(sidebar_nav)
        st.rerun()

    st.markdown("---")
    st.subheader("⚙️ Athlete & Equipment Profile")
    with st.form("gear_profile_form"):
        custom_gear = st.text_area("Bike Build & Gear Notes", value=st.session_state.athlete_gear, height=100)
        custom_limits = st.text_area("Physical Limitations / Notes", value=st.session_state.athlete_limitations, height=70)
        if st.form_submit_button("Save Profile", use_container_width=True):
            st.session_state.athlete_gear = custom_gear.strip()
            st.session_state.athlete_limitations = custom_limits.strip()
            if st.session_state.user:
                try:
                    supabase.table("profiles").update(
                        {"gear_notes": custom_gear, "limitations_notes": custom_limits}
                    ).eq("id", USER_ID).execute()
                    st.success("Synced to Supabase cloud!")
                except Exception as exc:
                    st.error(f"Sync failed: {exc}")
            else:
                creds = st.session_state.user_credentials or {}
                creds["gear"] = custom_gear
                creds["limitations"] = custom_limits
                st.session_state.user_credentials = creds
                localS.setItem("athlete_profile_config", creds)
                st.success("Saved to browser memory!")

    st.markdown("---")
    st.subheader("🎭 Coaching Persona")
    coach_persona = st.selectbox(
        "Select AI Style",
        [
            "Collaborative Peer (Balanced & Brainstorming)",
            "Sports Scientist (Data & Periodization Focus)",
            "Drill Sergeant (Strict & Direct Accountability)",
        ],
    )

    st.markdown("---")
    st.subheader("🎯 Target Race & Goals")
    with st.form("goal_feedback_form"):
        ev_name = st.text_input("Target Race", value=st.session_state.goals["event_name"])
        t_metric = st.text_input("Key Objective", value=st.session_state.goals["target_metric"])
        try:
            default_date = dt.datetime.strptime(st.session_state.goals["race_date"], "%Y-%m-%d").date()
        except Exception:
            default_date = dt.date(2026, 10, 24)
        r_date = st.date_input("Target Race Date", value=default_date)
        if st.form_submit_button("Update Goals", use_container_width=True):
            st.session_state.goals.update(
                {"event_name": ev_name.strip(), "target_metric": t_metric.strip(), "race_date": str(r_date)}
            )
            if st.session_state.user:
                try:
                    supabase.table("profiles").update(
                        {"event_name": ev_name, "target_metric": t_metric, "race_date": str(r_date)}
                    ).eq("id", USER_ID).execute()
                except Exception as exc:
                    st.error(f"Goal sync failed: {exc}")
            st.success("Goals updated!")

    st.markdown("---")
    selected_provider = st.selectbox(
        "⚡ AI Engine Model",
        [
            "Gemini 3.7 Flash (Latest Reasoning & Agentic)",
            "Gemini 3.6 Flash (Workhorse)",
            "Gemini 3.5 Flash (Base)",
        ],
    )

    st.markdown("---")
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = [
            {"role": "assistant", "content": "Chat history cleared. What topic or idea would you like to discuss next?"}
        ]
        st.rerun()

    if st.button("Log Out / Switch Account", use_container_width=True):
        try:
            if st.session_state.user:
                supabase.auth.sign_out()
        except Exception:
            pass
        st.session_state.user = None
        st.session_state.user_credentials = None
        localS.deleteItem("athlete_profile_config")
        st.query_params.clear()
        st.rerun()


selected_nav = st.session_state.active_nav


# -----------------------------------------------------------------------------
# CHAT HELPERS
# -----------------------------------------------------------------------------
WORKOUT_BLOCK_RE = re.compile(
    r"```(?:xml)?\s*(<workout_file>.*?</workout_file>)\s*```|(<workout_file>.*?</workout_file>)",
    re.IGNORECASE | re.DOTALL,
)
ICU_BLOCK_RE = re.compile(r"<icu_workout>\s*(.*?)\s*</icu_workout>", re.IGNORECASE | re.DOTALL)


def sanitize_chat_text(text: str) -> str:
    clean = WORKOUT_BLOCK_RE.sub("", text or "")
    clean = re.sub(r"<icu_workout>.*?</icu_workout>", "", clean, flags=re.IGNORECASE | re.DOTALL)
    return clean.strip()


def build_chat_prompt(prompt: str) -> str:
    stack_summary = ", ".join(
        f"{item['name']} ({item['timing']})" for item in st.session_state.user_supplements
    )
    recent_acts = activities_data[:5] if activities_data else []
    upcoming_events = planned_events[:7] if planned_events else []

    recent_history = []
    for item in st.session_state.messages[-8:]:
        role = "USER" if item.get("role") == "user" else "COACH"
        content = str(item.get("content", ""))
        if len(content) > 2500:
            content = content[:2500] + "…"
        recent_history.append(f"{role}: {content}")

    return "\n".join(
        [
            "You are an elite cycling sports science performance coach.",
            f"Coaching persona: {coach_persona}.",
            f"Primary goal: {st.session_state.goals['event_name']} — {st.session_state.goals['target_metric']}.",
            f"Target date: {st.session_state.goals['race_date']} ({days_left} days from today).",
            f"Current metrics: CTL={ctl:.1f}, ATL={atl:.1f}, TSB={tsb:.1f}, sleep score={sleep_score:.0f}.",
            f"Supplements: {stack_summary or 'None listed'}.",
            f"Bike/gear notes: {st.session_state.athlete_gear or 'None provided'}.",
            f"Limitations/notes: {st.session_state.athlete_limitations or 'None provided'}.",
            f"Recent activities: {json.dumps(recent_acts, ensure_ascii=False, default=str)}",
            f"Upcoming events: {json.dumps(upcoming_events, ensure_ascii=False, default=str)}",
            "Recent conversation:",
            "\n".join(recent_history) if recent_history else "None yet.",
            "",
            "Important: propose plans before syncing them. Only emit an <icu_workout> JSON block when the athlete clearly asks to sync/add workouts.",
            f"USER'S CURRENT QUESTION: {prompt.strip()}",
        ]
    )


def sync_icu_workouts(response_text: str) -> int:
    """Only sync when AI explicitly emits the structured <icu_workout> block."""
    if not ATHLETE_ID or not INTERVALS_API_KEY:
        return 0

    matches = ICU_BLOCK_RE.findall(response_text or "")
    synced = 0
    endpoint = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events"

    for match in matches:
        block = match[0].strip() if isinstance(match, tuple) else str(match).strip()
        try:
            cleaned = re.sub(r"```json|```", "", block, flags=re.IGNORECASE).strip()
            payload = json.loads(cleaned)
            workouts = payload if isinstance(payload, list) else [payload]
            for workout in workouts:
                if not isinstance(workout, dict):
                    continue
                workout = dict(workout)
                workout["category"] = "WORKOUT"
                start = workout.get("start_date_local")
                if isinstance(start, str) and len(start) == 10:
                    workout["start_date_local"] = start + "T00:00:00"

                response = requests.post(
                    endpoint,
                    json=workout,
                    auth=("API_KEY", INTERVALS_API_KEY),
                    headers={"Accept": "application/json"},
                    timeout=(5, 20),
                )
                if response.ok:
                    synced += 1
        except Exception:
            continue

    return synced


# -----------------------------------------------------------------------------
# VIEW 1: COMMAND CENTER
# -----------------------------------------------------------------------------
# -----------------------------------------------------------------------------
# VIEW 1: COMMAND CENTER
# -----------------------------------------------------------------------------
if selected_nav == "📊 Command Center":
    st.markdown("### ☀️ Autonomous AI Performance Coach • Command Center")
    st.markdown(
        f"""
        <div style="background-color:#fef9e7;border:1px solid #f9e79f;padding:16px;border-radius:14px;margin-bottom:16px;">
            <span style="font-size:.75rem;font-weight:bold;color:#d68910;background:#fcf3cf;padding:2px 6px;border-radius:4px;">📊 INTERVALS.ICU & GARMIN SYNC ACTIVE</span>
            <div style="font-weight:bold;font-size:1.1rem;margin-top:4px;">Target Race: {st.session_state.goals['event_name']} ({days_left} days left — {race_date_obj.strftime('%B %d, %Y')})</div>
            <div style="color:#666;font-size:.85rem;margin-top:4px;">Objective: {st.session_state.goals['target_metric']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fitness (CTL)", round(ctl, 1))
    c2.metric("Fatigue (ATL)", round(atl, 1))
    c3.metric("Form (TSB)", round(tsb, 1))
    c4.metric("Sleep Score", f"{sleep_score:.0f}/100" if sleep_score > 0 else "N/A")

    st.markdown("---")
    st.markdown("#### 📈 Deep 90-Day Training Load & Progression Trend Analysis")

    # Use a form or callback-driven execution to safely handle the generation trigger
    with st.form("trend_analysis_form"):
        submitted = st.form_submit_button("🚀 Run 90-Day Trend Synthesis", use_container_width=True, type="primary")
        if submitted:
            trend_payload = "\n".join(
                [
                    "Perform a rigorous 90-day cycling sports-science trend analysis.",
                    f"CTL={ctl}, ATL={atl}, TSB={tsb}.",
                    f"Recent activities: {json.dumps(activities_data[:25], ensure_ascii=False, default=str)}",
                    f"Target event: {st.session_state.goals['event_name']} in {days_left} days.",
                    f"Objective: {st.session_state.goals['target_metric']}.",
                    "Cover fitness trajectory, consistency, fatigue management, climbing readiness, and next steps.",
                ]
            )
            with st.spinner("Synthesizing 90-day performance trends…"):
                try:
                    result, _ = execute_multiprovider_generation(trend_payload, selected_provider)
                    st.session_state.cached_trend_analysis = result
                    st.session_state.trend_analysis_timestamp = dt.datetime.now().strftime("%B %d, %Y at %H:%M")
                except Exception as exc:
                    st.error(f"Trend synthesis failed: {exc}")

    # Render cached analysis independently of the button state
    if st.session_state.cached_trend_analysis:
        st.markdown("---")
        st.caption(f"🕒 Analysis generated on: **{st.session_state.trend_analysis_timestamp}**")
        st.markdown(st.session_state.cached_trend_analysis)
        
        a, b = st.columns(2)
        with a:
            if st.button("💬 Discuss These Trends With Coach", use_container_width=True):
                st.session_state.messages.append(
                    {
                        "role": "user",
                        "content": f"Review my 90-day trend analysis and tell me whether I'm progressing toward '{st.session_state.goals['target_metric']}'.",
                    }
                )
                st.session_state.active_nav = "🤖 AI Coach & Sparring"
                st.rerun()
        with b:
            if st.button("🗑️ Clear Trend Analysis", use_container_width=True):
                st.session_state.cached_trend_analysis = None
                st.session_state.trend_analysis_timestamp = None
                st.rerun()


# -----------------------------------------------------------------------------
# VIEW 2: AI COACH CHAT (Fixed Streamlit Chat Pattern)
# -----------------------------------------------------------------------------
elif selected_nav == "🤖 AI Coach & Sparring":
    st.markdown("### 🤖 AI Coach & Collaborative Sparring Partner")
    st.caption(
        f"Active Persona: **{coach_persona}** | The coach proposes plans first; Intervals.icu sync only occurs when a structured workout block is explicitly emitted."
    )

    for message in st.session_state.messages:
        if message.get("role") not in ("user", "assistant"):
            message["role"] = "assistant"

    for idx, message in enumerate(st.session_state.messages):
        with st.chat_message(message["role"]):
            clean = sanitize_chat_text(message["content"])
            if clean:
                st.markdown(clean)

            if message["role"] == "assistant":
                matches = WORKOUT_BLOCK_RE.findall(message["content"] or "")
                for xml_index, match in enumerate(matches):
                    zwo_data = (match[0] or match[1]).strip()
                    if zwo_data:
                        st.download_button(
                            label="📥 Download MyWhoosh File (.zwo)",
                            data=zwo_data,
                            file_name=f"Coach_Workout_{idx}_{xml_index}.zwo",
                            mime="application/xml",
                            key=f"zwo_{idx}_{xml_index}",
                        )

    if prompt := st.chat_input("Ask your coach to plan training or bounce an idea…"):
        st.session_state.messages.append({"role": "user", "content": prompt.strip()})
        with st.chat_message("user"):
            st.markdown(prompt.strip())

        with st.chat_message("assistant"):
            with st.spinner("🤖 Coach is analyzing and drafting…"):
                try:
                    payload = build_chat_prompt(prompt.strip())
                    response, engine = execute_multiprovider_generation(payload, selected_provider)
                    synced = sync_icu_workouts(response)

                    final_response = response.rstrip()
                    final_response += f"\n\n*Engine: {engine}*"
                    if synced:
                        final_response += f"\n\n✅ **Success:** {synced} workout(s) synchronized with Intervals.icu."
                        fetch_intervals_data.clear()

                    st.markdown(sanitize_chat_text(final_response))
                    st.session_state.messages.append({"role": "assistant", "content": final_response})
                except Exception as exc:
                    error_text = str(exc)
                    error_msg = (
                        "⚠️ I couldn't complete that request. Your message is still in the chat, "
                        "so you can retry without losing it.\n\n"
                        f"**Technical detail:** `{error_text}`"
                    )
                    st.markdown(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})


# -----------------------------------------------------------------------------
# VIEW 3: TRAINING CALENDAR
# -----------------------------------------------------------------------------
elif selected_nav == "📅 Training Calendar":
    st.markdown("### 📅 Training Calendar & 2-Week Block Planner")
    st.caption("Review your schedule, view full session details, or inspect recent double-session days.")

    combined = []
    cutoff = (dt.date.today() - dt.timedelta(days=7)).isoformat()
    today_str = dt.date.today().isoformat()

    for event in planned_events or []:
        date_text = str(event.get("start_date_local", ""))[:10]
        if date_text >= cutoff:
            combined.append(
                {
                    "id": event.get("id"),
                    "date": date_text,
                    "name": event.get("name", "Planned Workout"),
                    "type": event.get("type", "Ride"),
                    "desc": event.get("description", "No description provided."),
                    "status": "Planned",
                }
            )

    for activity in activities_data or []:
        date_text = str(activity.get("start_date_local", ""))[:10]
        if date_text >= cutoff:
            dist_km = round((activity.get("distance") or 0) / 1000, 1)
            duration = int((activity.get("moving_time") or 0) / 60)
            combined.append(
                {
                    "id": activity.get("id"),
                    "date": date_text,
                    "name": activity.get("name", "Recorded Activity"),
                    "type": activity.get("type", "Ride"),
                    "desc": f"Distance: {dist_km} km | Time: {duration} mins | Avg Power: {activity.get('average_watts', 'N/A')}W",
                    "status": "Completed",
                }
            )

    for item in combined:
        try:
            item["formatted_date"] = dt.datetime.strptime(item["date"], "%Y-%m-%d").strftime("%A, %b %d")
        except Exception:
            item["formatted_date"] = item["date"]

    upcoming = sorted([x for x in combined if x["date"] >= today_str], key=lambda x: x["date"])
    past = sorted([x for x in combined if x["date"] < today_str], key=lambda x: x["date"], reverse=True)

    tab_up, tab_past = st.tabs(["📅 Upcoming", "✅ Past"])
    with tab_up:
        if upcoming:
            for item in upcoming:
                with st.expander(f"{item['formatted_date']} — {item['name']} ({item['status']})"):
                    st.markdown(f"**Type:** {item['type']}\n\n**Details:**\n{item['desc']}")
        else:
            st.info("No upcoming workouts scheduled.")
    with tab_past:
        if past:
            for item in past:
                with st.expander(f"{item['formatted_date']} — {item['name']} ({item['status']})"):
                    st.markdown(f"**Type:** {item['type']}\n\n**Summary:**\n{item['desc']}")
        else:
            st.info("No recent activities recorded.")

    st.markdown("---")
    st.markdown("#### 🤖 AI 2-Week Block Planner & Rescheduler")
    plan_focus = st.selectbox(
        "Select 2-Week Block Focus:",
        [
            "Threshold Power & Sweet Spot Progression",
            "Climbing Endurance & Resistance Blocks",
            "Recovery & Taper Structure",
            "Custom Indoor/Outdoor Balance",
        ],
    )

    left, right = st.columns(2)
    with left:
        if st.button("🚀 Propose 2-Week Block Plan", type="primary", use_container_width=True):
            prompt_text = f"Please propose a complete 2-week training block focused on '{plan_focus}'. I want to review it before syncing."
            st.session_state.messages.append({"role": "user", "content": prompt_text})
            st.session_state.active_nav = "🤖 AI Coach & Sparring"
            st.rerun()
    with right:
        if st.button("🔄 Propose Shift Forward 1 Day", use_container_width=True):
            prompt_text = "Please propose shifting all upcoming workouts forward by 1 day so I can review the changes before syncing."
            st.session_state.messages.append({"role": "user", "content": prompt_text})
            st.session_state.active_nav = "🤖 AI Coach & Sparring"
            st.rerun()


# -----------------------------------------------------------------------------
# VIEW 4: ACTIVITY INSPECTOR
# -----------------------------------------------------------------------------
elif selected_nav == "🔍 Activity Inspector":
    st.markdown("### 🔍 Past Activity Inspector & Deep Debrief")
    if activities_data:
        options = {}
        for activity in activities_data:
            name = activity.get("name", "Unnamed Activity")
            date_text = str(activity.get("start_date_local", ""))[:10]
            dist = round((activity.get("distance") or 0) / 1000, 1)
            duration = int((activity.get("moving_time") or 0) / 60)
            options[f"{date_text} — {name} ({dist} km, {duration} mins)"] = activity

        selected_label = st.selectbox("Choose a past activity to analyze:", list(options.keys()))
        selected_activity = options[selected_label]
        name = selected_activity.get("name", "Workout")
        date_text = str(selected_activity.get("start_date_local", ""))[:10]

        st.markdown(
            f"""
            <div style="background-color:#eaf2f8;border:1px solid #a9cce3;padding:12px 16px;border-radius:10px;margin-bottom:16px;">
                <div style="font-size:.8rem;font-weight:bold;color:#2471a3;">Selected Activity Inspection</div>
                <div style="font-size:1.2rem;font-weight:bold;color:#1b4f72;">{name}</div>
                <div style="font-size:.9rem;color:#515a5a;">📅 Date: {date_text}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

        x1, x2, x3 = st.columns(3)
        x1.metric("Distance", f"{round((selected_activity.get('distance') or 0) / 1000, 2)} km")
        x2.metric("Moving Time", f"{int((selected_activity.get('moving_time') or 0) / 60)} mins")
        x3.metric("Average Power", f"{selected_activity.get('average_watts', 'N/A')} W")

        if st.button("🤖 Run Deep AI Activity Debrief", type="primary", use_container_width=True):
            with st.spinner("Analyzing activity metrics…"):
                prompt = (
                    f"Perform a deep performance debrief for this cycling activity: {name} on {date_text}. "
                    f"Details: {json.dumps(selected_activity, ensure_ascii=False, default=str)}. "
                    f"Goal: {st.session_state.goals['target_metric']}."
                )
                try:
                    result, engine = execute_multiprovider_generation(prompt, selected_provider)
                    st.session_state.selected_activity_analysis = (
                        f"### 🚴‍♂️ Performance Debrief: {name}\n"
                        f"📅 **Date:** {date_text}\n\n{result}\n\n*Engine: {engine}*"
                    )
                except Exception as exc:
                    st.error(f"Analysis failed: {exc}")

        if st.session_state.selected_activity_analysis:
            st.markdown("---")
            st.markdown(st.session_state.selected_activity_analysis)
            if st.button("💬 Clarify This Debrief with Coach"):
                text = f"I want clarifications regarding my activity '{name}' on {date_text}."
                st.session_state.messages.append({"role": "user", "content": text})
                st.session_state.active_nav = "🤖 AI Coach & Sparring"
                st.rerun()
    else:
        st.info("No activities found in your Intervals.icu sync history.")


# -----------------------------------------------------------------------------
# VIEW 5: RECOVERY & SUPPLEMENTS
# -----------------------------------------------------------------------------
elif selected_nav == "💊 Recovery & Supplements":
    st.markdown("### 💊 Dynamic Recovery & Supplement Protocol")
    with st.form("add_supplement_form", clear_on_submit=True):
        a, b, c = st.columns([1, 1, 2])
        new_name = a.text_input("Name")
        new_timing = b.text_input("Timing")
        new_notes = c.text_input("Notes")
        if st.form_submit_button("➕ Add to Stack", use_container_width=True) and new_name.strip():
            st.session_state.user_supplements.append(
                {
                    "name": new_name.strip(),
                    "timing": new_timing.strip() or "As needed",
                    "notes": new_notes.strip() or "Custom",
                }
            )
            st.rerun()

    st.markdown("---")
    if st.session_state.user_supplements:
        st.dataframe(pd.DataFrame(st.session_state.user_supplements), use_container_width=True, hide_index=True)
        names = [item["name"] for item in st.session_state.user_supplements]
        to_remove = st.selectbox("Select a supplement to remove:", ["-- Select --"] + names)
        if to_remove != "-- Select --" and st.button("🗑️ Remove Selected Supplement"):
            st.session_state.user_supplements = [x for x in st.session_state.user_supplements if x["name"] != to_remove]
            st.rerun()

    st.markdown("---")
    if st.button("💬 Discuss Updated Supplement Stack With Coach"):
        stack_desc = ", ".join(f"{s['name']} ({s['timing']})" for s in st.session_state.user_supplements)
        text = f"Let's review my active supplement stack: {stack_desc}."
        st.session_state.messages.append({"role": "user", "content": text})
        st.session_state.active_nav = "🤖 AI Coach & Sparring"
        st.rerun()


# -----------------------------------------------------------------------------
# VIEW 6: ROUTE STRATEGIST
# -----------------------------------------------------------------------------
elif selected_nav == "🗺️ Route Strategist":
    st.markdown("### 🗺️ Route Pacing & Climbing Strategist")
    uploaded_gpx = st.file_uploader("Upload GPX Route File (.gpx)", type=["gpx"])

    def parse_gpx(file_bytes: bytes):
        try:
            root = ET.fromstring(file_bytes.decode("utf-8", errors="ignore"))
            latlons: List[Tuple[float, float]] = []
            elevations: List[float] = []
            for elem in root.iter():
                tag = elem.tag.split("}")[-1].lower()
                if tag not in {"trkpt", "rtept"}:
                    continue

                lat = elem.attrib.get("lat") or elem.attrib.get("latitude")
                lon = elem.attrib.get("lon") or elem.attrib.get("longitude")
                if lat is None or lon is None:
                    continue

                latlons.append((float(lat), float(lon)))
                ele_value = elevations[-1] if elevations else 0.0
                for child in elem:
                    child_tag = child.tag.split("}")[-1].lower()
                    if child_tag in {"ele", "elevation", "alt"}:
                        try:
                            ele_value = float(child.text)
                        except Exception:
                            pass
                        break
                elevations.append(ele_value)

            if len(latlons) < 2:
                return None

            total_gain = sum(
                max(0.0, elevations[i] - elevations[i - 1]) for i in range(1, len(elevations))
            )

            def haversine_km(a, b):
                lat1, lon1 = map(math.radians, a)
                lat2, lon2 = map(math.radians, b)
                dlat = lat2 - lat1
                dlon = lon2 - lon1
                h = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
                return 6371.0 * (2 * math.asin(min(1.0, math.sqrt(h))))

            distance = sum(haversine_km(latlons[i - 1], latlons[i]) for i in range(1, len(latlons)))
            return {
                "distance_km": round(max(distance, 0.1), 2),
                "elevation_gain_m": round(total_gain, 1),
                "max_elevation": round(max(elevations), 1) if elevations else 0,
            }
        except Exception:
            return None

    if uploaded_gpx:
        metrics = parse_gpx(uploaded_gpx.getvalue())
        if metrics:
            a, b, c = st.columns(3)
            a.metric("Distance", f"{metrics['distance_km']} km")
            b.metric("Elevation Gain", f"{metrics['elevation_gain_m']} m")
            c.metric("Max Elevation", f"{metrics['max_elevation']} m")

            if st.button("🤖 Generate Climbing Strategy", type="primary"):
                prompt = (
                    f"Analyze this cycling route profile: Distance {metrics['distance_km']} km, "
                    f"Elevation gain {metrics['elevation_gain_m']} m, max elevation {metrics['max_elevation']} m. "
                    f"Objective: {st.session_state.goals['target_metric']}. "
                    "Provide pacing, climbing, fueling, and effort-control strategy."
                )
                with st.spinner("Analyzing route profile…"):
                    try:
                        result, engine = execute_multiprovider_generation(prompt, selected_provider)
                        st.markdown("---")
                        st.markdown(result)
                        st.caption(f"Generated via: {engine}")
                    except Exception as exc:
                        st.error(f"Strategy generation failed: {exc}")
        else:
            st.error("Could not parse that GPX file. Please upload a standard GPX track/route file.")
