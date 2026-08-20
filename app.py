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
GEMINI_MODEL = secret("GEMINI_MODEL", "gemini-2.5-
")
AI_TIMEOUT = 25
INTERVALS_TIMEOUT = 6
NAV_OPTIONS = ["📊 Command Center", "🤖 AI Coach & Sparring", "📅 Training Calendar", "🔍 Activity Inspector", "💊 Recovery & Supplements", "🗺️ Route Strategist"]
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
/* Use Streamlit's active theme variables; no hard-coded white surfaces. */
.stCard { background: var(--secondary-background-color); border: 1px solid rgba(128,128,128,.24); border-radius: 12px; padding: 20px; margin-bottom: 16px; }
div[data-testid="stMetric"] { background: color-mix(in srgb, var(--secondary-background-color) 92%, transparent); border: 1px solid rgba(128,128,128,.20); border-radius: 10px; padding: 12px 16px; }
div[data-testid="stExpander"] { border-color: rgba(128,128,128,.28); }
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
        "ai_diagnostic": None,
        "trend_loaded": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

def ensure_initial_message():
    if not st.session_state.messages:
        st.session_state.messages = [{"role": "assistant", "content": "Hello! I am your AI Performance Coach. Ask about training, recovery, climbing, threshold work, or your upcoming event."}]

def go_to(page):
    """Change the route without mutating an already-created radio widget."""
    st.session_state.active_nav = page

def sidebar_changed():
    st.session_state.active_nav = st.session_state.sidebar_nav

def discuss_with_coach(topic, context):
    """Carry a view's context into the coach page and generate the reply there."""
    st.session_state.pending_coach_prompt = f"Let's discuss {topic}.\n\nContext from the app:\n{context}\n\nPlease explain what matters and give my next best action."
    go_to(COACH_PAGE)

def clean_chat_content(text):
    text = text or ""
    text = re.sub(r"```xml\s*<\?xml.*?</workout_file>\s*```", "", text, flags=re.S | re.I)
    return re.sub(r"<icu_workout>.*?</icu_workout>", "", text, flags=re.S | re.I).strip()

def gemini_generate(prompt, api_key):
    if not api_key:
        raise RuntimeError("Gemini API key is not configured.")
    response = requests.post(
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
        json={"contents": [{"role": "user", "parts": [{"text": prompt}]}]}, timeout=AI_TIMEOUT,
    )
    if response.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:500]}")
    parts = (response.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    text = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
    if not text:
        raise RuntimeError("Gemini returned no usable text.")
    return text

def execute_ai(prompt):
    """Gemini-only server-side failover. Provider/key identity is never displayed."""
    errors, seen = [], set()
    for _, key in GEMINI_KEYS:
        if not key or key in seen:
            continue
        seen.add(key)
        try:
            return gemini_generate(prompt, key)
        except Exception as exc:
            errors.append(str(exc))
    st.session_state.ai_diagnostic = "\n\n".join(errors)[:2000] or "No Gemini API keys were found in Streamlit secrets."
    raise RuntimeError("The coach is temporarily unavailable. Please try again shortly.")

def trend_storage_key():
    """Names guest-browser storage by athlete, rather than by the current page."""
    return f"coach_trend_analysis:{ATHLETE_ID or display_name}"

def load_persisted_trend():
    """Restore the latest trend once per session, preferring the signed-in profile."""
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
            # The browser copy remains a safe fallback when the migration is not deployed yet.
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
    """Save to the authenticated profile where available and always keep a browser copy."""
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
            f"{base}/events?oldest={(today-dt.timedelta(days=7)).isoformat()}&newest={(today+dt.timedelta(days=14)).isoformat()}",
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

def coach_prompt(question, display_name):
    history = "\n".join(f"{m['role'].upper()}: {m['content']}" for m in st.session_state.messages[-7:])
    return f"""You are an elite cycling performance coach.
Persona: {st.session_state.coach_persona}
Athlete: {display_name}
Goal: {st.session_state.goals['target_metric']}
Target event: {st.session_state.goals['event_name']} on {st.session_state.goals['race_date']}
Gear: {st.session_state.athlete_gear or 'Not provided'}
Limitations: {st.session_state.athlete_limitations or 'Not provided'}
Recent conversation:\n{history}
Current question:\n{question}
Give a direct, practical coaching answer. Do not invent telemetry or claim to alter Intervals.icu."""

def render_coach_reply(question, display_name):
    st.session_state.messages.append({"role": "user", "content": question})
    with st.chat_message("user"):
        st.markdown(question)
    with st.chat_message("assistant"):
        placeholder = st.empty()
        placeholder.markdown("🤔 **Coach is thinking...**")
        try:
            response = execute_ai(coach_prompt(question, display_name))
        except Exception:
            response = "⚠️ **Coach could not respond right now.** Please try again in a moment."
        placeholder.markdown(response)
        st.session_state.messages.append({"role": "assistant", "content": response})

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
    st.markdown("## 🔐 Elite Athlete Portal")
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
else:
    creds = st.session_state.user_credentials or {}
    INTERVALS_API_KEY, ATHLETE_ID, display_name = creds.get("icu_key", ""), creds.get("icu_id", ""), creds.get("name", "Athlete")
    st.session_state.athlete_gear = st.session_state.athlete_gear or creds.get("gear", "")
    st.session_state.athlete_limitations = st.session_state.athlete_limitations or creds.get("limitations", "")
    if isinstance(creds.get("goals"), dict):
        st.session_state.goals.update({key: value for key, value in creds["goals"].items() if key in DEFAULT_GOALS and value})
ensure_initial_message()
load_persisted_trend()

# A single source of truth fixes the former two-click navigation bug.
if st.session_state.sidebar_nav != st.session_state.active_nav:
    st.session_state.sidebar_nav = st.session_state.active_nav
with st.sidebar:
    st.header("AI Performance Coach")
    st.radio("Navigate", NAV_OPTIONS, key="sidebar_nav", on_change=sidebar_changed)
    st.divider()
    st.session_state.coach_persona = st.selectbox("Coaching Persona", ["Collaborative Peer (Balanced & Brainstorming)", "Sports Scientist (Data & Periodization Focus)", "Drill Sergeant (Strict & Direct Accountability)"], index=["Collaborative Peer (Balanced & Brainstorming)", "Sports Scientist (Data & Periodization Focus)", "Drill Sergeant (Strict & Direct Accountability)"].index(st.session_state.coach_persona))
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
                        (supabase.table("profiles").update({"event_name": st.session_state.goals["event_name"], "target_metric": st.session_state.goals["target_metric"], "race_date": st.session_state.goals["race_date"], "gear_notes": gear, "limitations_notes": limitations}).eq("id", st.session_state.user.id).execute())
                    except Exception as exc:
                        st.warning(f"Profile is saved for this session, but Supabase could not be updated: {exc}")
                elif localS:
                    try:
                        st.session_state.user_credentials.update({"gear": gear, "limitations": limitations, "goals": st.session_state.goals})
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
        st.rerun()
    if st.button("Log out / switch account", use_container_width=True):
        if st.session_state.user and supabase:
            try: supabase.auth.sign_out()
            except Exception: pass
        st.session_state.user, st.session_state.user_credentials = None, None
        if localS:
            try: localS.deleteItem("athlete_profile_config")
            except Exception: pass
        st.rerun()

top = st.columns(len(NAV_OPTIONS))
for column, page in zip(top, NAV_OPTIONS):
    if column.button(page, key=f"top_{page}", use_container_width=True):
        go_to(page); st.rerun()
selected_nav = st.session_state.active_nav

if selected_nav == COACH_PAGE:
    wellness_list, activities_data, planned_events, intervals_status = [], [], [], "Skipped on coach page for responsiveness."
else:
    wellness_list, activities_data, planned_events, intervals_status = fetch_intervals_data(ATHLETE_ID, INTERVALS_API_KEY)
latest = wellness_list[-1] if wellness_list else {}
ctl, atl, tsb = latest.get("ctl", 0) or 0, latest.get("atl", 0) or 0, latest.get("tsb", 0) or 0

if selected_nav == NAV_OPTIONS[0]:
    st.markdown("### ☀️ Command Center")
    st.caption(f"Intervals.icu: {intervals_status}")
    c1,c2,c3 = st.columns(3); c1.metric("Fitness (CTL)", round(ctl,1)); c2.metric("Fatigue (ATL)", round(atl,1)); c3.metric("Form (TSB)", round(tsb,1))
    if st.button("🚀 Run 90-Day Trend Synthesis", type="primary"):
        payload = f"Analyze this cycling athlete's last 90 days. CTL {ctl}; ATL {atl}; TSB {tsb}. Recent activities: {json.dumps(activities_data[:15], default=str)}. Goal: {st.session_state.goals['target_metric']}. Give trajectory, consistency, fatigue, climbing readiness, and practical next steps."
        with st.spinner("Analyzing 90 days of training..."):
            try:
                st.session_state.cached_trend_analysis = execute_ai(payload)
                st.session_state.trend_analysis_timestamp = dt.datetime.now().astimezone().strftime("%d %b %Y, %H:%M %Z")
                persist_trend()
            except Exception as exc: st.error(str(exc))
    if st.session_state.cached_trend_analysis:
        st.markdown("#### 90-Day Trend Analysis")
        st.caption(f"Generated {st.session_state.trend_analysis_timestamp} · remains visible until cleared or re-run.")
        st.markdown(st.session_state.cached_trend_analysis)
        a,b = st.columns(2)
        if a.button("💬 Discuss with Coach", key="trend_discuss"): discuss_with_coach("my 90-day trend analysis", st.session_state.cached_trend_analysis); st.rerun()
        if b.button("Clear trend analysis", key="clear_trend"): clear_persisted_trend(); st.rerun()

elif selected_nav == COACH_PAGE:
    st.markdown("### 🤖 AI Coach & Collaborative Sparring Partner")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]): st.markdown(clean_chat_content(message["content"]))
    pending = st.session_state.pending_coach_prompt
    if pending:
        st.session_state.pending_coach_prompt = None
        render_coach_reply(pending, display_name)
    elif question := st.chat_input("Ask your coach anything..."):
        render_coach_reply(question.strip(), display_name)

elif selected_nav == NAV_OPTIONS[2]:
    st.markdown("### 📅 Training Calendar")
    if not planned_events: st.info("No upcoming Intervals.icu events were returned.")
    grouped = {}
    for event in planned_events: grouped.setdefault(event.get("start_date_local", "")[:10] or "Unscheduled", []).append(event)
    for date, sessions in grouped.items():
        with st.expander(f"{date} · {len(sessions)} session{'s' if len(sessions) != 1 else ''}", expanded=False):
            for number, event in enumerate(sessions, 1):
                st.markdown(f"**Session {number}: {event.get('name', 'Planned workout')}**")
                st.write(event.get("description") or event.get("notes") or "No coach instructions provided.")
                with st.expander("Session details", expanded=False): st.json(event)
            if st.button("💬 Discuss these sessions with Coach", key=f"calendar_{date}"): discuss_with_coach(f"the {date} training sessions", json.dumps(sessions, default=str)); st.rerun()

elif selected_nav == NAV_OPTIONS[3]:
    st.markdown("### 🔍 Activity Inspector")
    if not activities_data: st.info("No activities found.")
    else:
        options = {f"{x.get('start_date_local','')[:10]} — {x.get('name','Unnamed')} ({round((x.get('distance') or 0)/1000,1)} km)": x for x in activities_data}
        label = st.selectbox("Choose an activity", list(options)); activity = options[label]
        c1,c2,c3=st.columns(3); c1.metric("Distance", f"{round((activity.get('distance') or 0)/1000,2)} km"); c2.metric("Moving Time", f"{int((activity.get('moving_time') or 0)/60)} min"); c3.metric("Average Power", f"{activity.get('average_watts','N/A')} W")
        if st.button("Run AI Debrief", type="primary"):
            try: st.session_state.selected_activity_analysis = execute_ai(f"Perform a cycling performance debrief. Activity: {json.dumps(activity, default=str)}. Goal: {st.session_state.goals['target_metric']}. Cover execution, intensity, stimulus, strengths, weaknesses, recovery, and next recommendation."); st.session_state.selected_activity_label = label
            except Exception as exc: st.error(str(exc))
        if st.session_state.selected_activity_analysis:
            st.markdown(st.session_state.selected_activity_analysis)
            if st.button("💬 Discuss with Coach", key="activity_discuss"): discuss_with_coach(f"activity debrief for {st.session_state.selected_activity_label}", st.session_state.selected_activity_analysis); st.rerun()

elif selected_nav == NAV_OPTIONS[4]:
    st.markdown("### 💊 Recovery & Supplement Protocol")
    with st.form("supplement"):
        a,b,c=st.columns(3); name=a.text_input("Name"); timing=b.text_input("Timing"); notes=c.text_input("Notes")
        if st.form_submit_button("Add") and name.strip(): st.session_state.user_supplements.append({"name":name.strip(),"timing":timing.strip() or "As needed","notes":notes.strip()}); st.rerun()
    if st.session_state.user_supplements: st.dataframe(pd.DataFrame(st.session_state.user_supplements), hide_index=True, use_container_width=True)
    if st.button("💬 Discuss recovery with Coach"): discuss_with_coach("my recovery and supplements", json.dumps(st.session_state.user_supplements)); st.rerun()

elif selected_nav == NAV_OPTIONS[5]:
    st.markdown("### 🗺️ Route Pacing & Climbing Strategist")
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
