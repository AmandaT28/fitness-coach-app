import datetime
import os
import concurrent.futures
import xml.etree.ElementTree as ET
import math
import re
import base64
import json
from dotenv import load_dotenv
from google import genai
from openai import OpenAI
import anthropic
import requests
import streamlit as st
from supabase import create_client, Client
import pandas as pd
from streamlit_local_storage import LocalStorage

# Load environment variables safely
try:
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase credentials missing! Add SUPABASE_URL and SUPABASE_KEY to Secrets.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None

# App UI Configuration
st.set_page_config(page_title="AI Performance Coach • Elite Suite", page_icon="🚴‍♂️", layout="wide")

st.markdown("""
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
""", unsafe_allow_html=True)

# --- GOOGLE API KEYS & MULTI-PROVIDER AI ROUTER ---
PRIMARY_GEMINI_KEY = st.secrets.get("google_keys", {}).get("primary_key") or st.secrets.get("GEMINI_API_KEY") or os.getenv("PRIMARY_KEY") or os.getenv("GEMINI_API_KEY")
SECONDARY_GEMINI_KEY = st.secrets.get("google_keys", {}).get("secondary_key") or os.getenv("SECONDARY_GEMINI_KEY") or os.getenv("SECONDARY_KEY")
TERTIARY_GEMINI_KEY = st.secrets.get("google_keys", {}).get("tertiary_key") or os.getenv("TERTIARY_GEMINI_KEY") or os.getenv("TERTIARY_KEY")

primary_google_client = genai.Client(api_key=PRIMARY_GEMINI_KEY) if PRIMARY_GEMINI_KEY else None
secondary_google_client = genai.Client(api_key=SECONDARY_GEMINI_KEY) if SECONDARY_GEMINI_KEY else None
tertiary_google_client = genai.Client(api_key=TERTIARY_GEMINI_KEY) if TERTIARY_GEMINI_KEY else None

def execute_multiprovider_generation(prompt, preferred_provider="⚡ Auto-Fallback Chain"):
    errors = []

    def call_google(client, name):
        if not client: raise ValueError(f"{name} client not initialized.")
        models = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash"]
        for m in models:
            try:
                res = client.models.generate_content(model=m, contents=prompt)
                if res and res.text: return res.text, f"Google {m} ({name})"
            except Exception as e:
                errors.append(f"{name} ({m}): {str(e)}")
                continue
        raise Exception(f"All Gemini models failed for {name}.")

    def action_primary_google(): return call_google(primary_google_client, "Primary Key")
    def action_secondary_google(): return call_google(secondary_google_client, "Secondary Key")
    def action_tertiary_google(): return call_google(tertiary_google_client, "Tertiary Key")

    def action_openai():
        if not openai_client: raise ValueError("OpenAI client missing.")
        res = openai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content, "OpenAI GPT-4o-mini"

    def action_anthropic():
        if not anthropic_client: raise ValueError("Anthropic client missing.")
        res = anthropic_client.messages.create(model="claude-3-5-sonnet-20241022", max_tokens=1500, messages=[{"role": "user", "content": prompt}])
        return res.content[0].text, "Anthropic Claude"

    all_actions = [action_primary_google, action_secondary_google, action_tertiary_google, action_openai, action_anthropic]
    for action in all_actions:
        try:
            result = action()
            if isinstance(result, tuple) and len(result) == 2: return result
        except Exception as e:
            errors.append(str(e))
            continue
    raise Exception(f"All AI providers failed. Diagnostics: {' | '.join(errors[:3])}")

localS = LocalStorage()

# --- AUTH & SESSION STATE ---
query_params = st.query_params
url_token = query_params.get("token")

if url_token and "user_credentials" not in st.session_state:
    try:
        decoded = base64.urlsafe_b64decode(url_token.encode("utf-8"))
        guest_config = json.loads(decoded.decode("utf-8"))
        if guest_config and "icu_key" in guest_config:
            localS.setItem("athlete_profile_config", guest_config)
            st.session_state.user_credentials = guest_config
            st.rerun()
    except: pass

if "user_credentials" not in st.session_state: st.session_state.user_credentials = None
if "user" not in st.session_state: st.session_state.user = None

stored_guest = localS.getItem("athlete_profile_config")
if not st.session_state.user and stored_guest and not st.session_state.user_credentials:
    st.session_state.user_credentials = stored_guest

if not st.session_state.user and not st.session_state.user_credentials:
    st.markdown("### 🔐 Elite Athlete Portal • Authentication")
    owner_tab, guest_tab = st.tabs(["👑 Owner Login (Supabase)", "⚙️ Friend / Guest Setup (BYOK)"])
    with owner_tab:
        with st.form("supabase_login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log In with Supabase", use_container_width=True):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user = res.user
                    st.rerun()
                except Exception as e: st.error(f"Login failed: {e}")
    with guest_tab:
        with st.form("guest_setup_form"):
            col_name = st.text_input("Your Name")
            icu_key = st.text_input("Intervals.icu API Key")
            icu_id = st.text_input("Intervals.icu Athlete ID")
            gemini_key = st.text_input("Google AI Studio API Key", type="password")
            if st.form_submit_button("Save & Launch Guest Session", use_container_width=True):
                if icu_key and icu_id and gemini_key:
                    config_data = {"name": col_name.strip() or "Guest", "icu_key": icu_key.strip(), "icu_id": icu_id.strip(), "gemini_key": gemini_key.strip(), "gear": "", "limitations": "", "onboarding_done": False}
                    localS.setItem("athlete_profile_config", config_data)
                    st.session_state.user_credentials = config_data
                    st.rerun()
    st.stop()

if st.session_state.user:
    USER_ID = st.session_state.user.id
    profile_res = supabase.table("profiles").select("*").eq("id", USER_ID).execute()
    user_profile = profile_res.data[0] if profile_res.data else {}
    INTERVALS_API_KEY = user_profile.get("intervals_api_key")
    ATHLETE_ID = user_profile.get("intervals_athlete_id")
    display_name = "Amanda"
    if "athlete_gear" not in st.session_state: st.session_state.athlete_gear = user_profile.get("gear_notes") or ""
    if "athlete_limitations" not in st.session_state: st.session_state.athlete_limitations = user_profile.get("limitations_notes") or ""
    if "goals" not in st.session_state or not isinstance(st.session_state.goals, dict): st.session_state.goals = {}
    st.session_state.goals["event_name"] = user_profile.get("event_name") or "Bintan Round Island"
    st.session_state.goals["target_metric"] = user_profile.get("target_metric") or "Survive steep climbs on group rides & improve threshold power"
    st.session_state.goals["race_date"] = user_profile.get("race_date") or str(datetime.date(2026, 10, 24))
else:
    current_creds = st.session_state.user_credentials
    INTERVALS_API_KEY = current_creds["icu_key"]
    ATHLETE_ID = current_creds["icu_id"]
    display_name = current_creds["name"]
    if "athlete_gear" not in st.session_state: st.session_state.athlete_gear = current_creds.get("gear", "")
    if "athlete_limitations" not in st.session_state: st.session_state.athlete_limitations = current_creds.get("limitations", "")
    if "goals" not in st.session_state or not isinstance(st.session_state.goals, dict): st.session_state.goals = {}
    if "event_name" not in st.session_state.goals: st.session_state.goals["event_name"] = "Bintan Round Island"
    if "target_metric" not in st.session_state.goals: st.session_state.goals["target_metric"] = "Survive steep climbs on group rides & improve threshold power"
    if "race_date" not in st.session_state.goals: st.session_state.goals["race_date"] = str(datetime.date(2026, 10, 24))

if "messages" not in st.session_state: st.session_state.messages = []

# --- DATA FETCHING ---
@st.cache_data(ttl=300, show_spinner=False)
def fetch_intervals_data(aid, key):
    try:
        today = datetime.date.today()
        start_90 = (today - datetime.timedelta(days=90)).isoformat()
        start_7 = (today - datetime.timedelta(days=7)).isoformat()
        end_14 = (today + datetime.timedelta(days=14)).isoformat()
        w_res = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/wellness?oldest={start_90}&newest={end_14}", auth=("API_KEY", key), timeout=6)
        a_res = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/activities?oldest={start_90}&newest={end_14}", auth=("API_KEY", key), timeout=6)
        e_res = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/events?oldest={start_7}&newest={end_14}", auth=("API_KEY", key), timeout=6)
        return w_res.json() if w_res.status_code == 200 else [], a_res.json() if a_res.status_code == 200 else [], e_res.json() if e_res.status_code == 200 else []
    except: return [], [], []

wellness_list, activities_data, planned_events = fetch_intervals_data(ATHLETE_ID, INTERVALS_API_KEY)

# FIX 1: Robust Wellness Extraction scanning backward across last 7 days for Sleep, HRV, and Resting HR
ctl, atl, tsb = 0, 0, 0
sleep_score, hrv, resting_hr = 0, 0, 0
if wellness_list:
    latest = wellness_list[-1]
    ctl, atl, tsb = latest.get("ctl", 0), latest.get("atl", 0), latest.get("tsb", 0)
    for record in reversed(wellness_list):
        if sleep_score == 0: sleep_score = record.get("sleepScore") or record.get("sleep_score") or 0
        if hrv == 0: hrv = record.get("hrv") or record.get("HRV") or 0
        if resting_hr == 0: resting_hr = record.get("restingHR") or record.get("resting_hr") or record.get("rhr") or 0

try:
    race_date_obj = datetime.datetime.strptime(st.session_state.goals["race_date"], "%Y-%m-%d").date()
except:
    race_date_obj = datetime.date(2026, 10, 24)
days_left = (race_date_obj - datetime.date.today()).days

NAV_OPTIONS = ["📊 Command Center", "🤖 AI Coach & Sparring", "📅 Training Calendar", "🔍 Activity Inspector", "💊 Recovery & Supplements", "🗺️ Route Strategist"]
if "active_nav" not in st.session_state: st.session_state.active_nav = "📊 Command Center"

top_nav = st.radio("Navigation Suite Top", NAV_OPTIONS, index=NAV_OPTIONS.index(st.session_state.active_nav), horizontal=True, label_visibility="collapsed")
if top_nav != st.session_state.active_nav:
    st.session_state.active_nav = top_nav
    st.rerun()

st.markdown("---")

with st.sidebar:
    st.markdown(f"👤 **{display_name}**")
    selected_provider = st.selectbox("⚡ AI Engine Model", ["⚡ Auto-Fallback Chain", "Google Gemini", "OpenAI GPT-4o-mini", "Anthropic Claude"])
    coach_persona = st.selectbox("Select AI Style", ["Collaborative Peer", "Sports Scientist", "Drill Sergeant"])
    if st.button("Log Out", use_container_width=True):
        if st.session_state.user: supabase.auth.sign_out()
        localS.deleteItem("athlete_profile_config")
        st.session_state.user = None
        st.session_state.user_credentials = None
        st.rerun()

selected_nav = st.session_state.active_nav

# ================= VIEW 1: COMMAND CENTER =================
if selected_nav == "📊 Command Center":
    st.markdown("### ☀️ Autonomous AI Performance Coach • Command Center")
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("Fitness (CTL)", round(ctl, 1))
    c2.metric("Fatigue (ATL)", round(atl, 1))
    c3.metric("Form (TSB)", round(tsb, 1))
    c4.metric("Sleep Score", f"{sleep_score}/100" if sleep_score > 0 else "N/A")
    c5.metric("Resting HR", f"{resting_hr} bpm" if resting_hr > 0 else "N/A")

# ================= VIEW 2: AI COACH & SPARRING (FIX 2 & 3) =================
elif selected_nav == "🤖 AI Coach & Sparring":
    st.markdown("### 🤖 AI Coach & 1-Click Workout Sync Suite")
    
    if not st.session_state.messages:
        st.session_state.messages = [{"role": "model", "content": "Hello! Coach is ready. Workouts can be synced instantly with 1-click."}]

    for idx, msg in enumerate(st.session_state.messages):
        with st.chat_message(msg["role"]):
            clean_content = re.sub(r"<icu_workout>.*?</icu_workout>", "", msg["content"], flags=re.DOTALL)
            st.markdown(clean_content.strip())
            
            # FIX 2: Render instant 1-click approval & sync button if workout JSON is present
            if msg["role"] == "model" and "<icu_workout>" in msg["content"]:
                try:
                    workout_raw = msg["content"].split("<icu_workout>")[1].split("</icu_workout>")[0].strip()
                    workout_json = json.loads(workout_raw)
                    if st.button("🚀 Approve & Sync to Intervals.icu", key=f"sync_btn_{idx}", type="primary"):
                        if not isinstance(workout_json, list): workout_json = [workout_json]
                        success_count = 0
                        for w in workout_json:
                            w['category'] = 'WORKOUT'
                            if 'start_date_local' in w and len(w['start_date_local']) == 10: w['start_date_local'] += "T00:00:00"
                            res = requests.post(f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events", json=w, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
                            if res.status_code == 200: success_count += 1
                        if success_count > 0:
                            st.success("✅ Workout successfully pushed to Intervals.icu!")
                            fetch_intervals_data.clear()
                except Exception as e: st.error(f"Sync failed: {e}")

    if prompt := st.chat_input("Ask for a workout plan or schedule adjustment..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        
        with st.chat_message("model"):
            with st.spinner("Drafting workout plan..."):
                # FIX 3: Inject full planned events and daily notes/travel limitations into system prompt
                calendar_context = json.dumps([{
                    "date": ev.get("start_date_local", "")[:10],
                    "name": ev.get("name"),
                    "type": ev.get("type"),
                    "notes": ev.get("description") or ev.get("notes")
                } for ev in planned_events], ensure_ascii=False)
                
                payload = f"""
                You are an elite sports science coach acting with persona: '{coach_persona}'.
                METRICS: CTL={ctl}, ATL={atl}, TSB={tsb}, Sleep={sleep_score}, HRV={hrv}, RHR={resting_hr}.
                CALENDAR & TRAVEL CONTEXT: {calendar_context}
                
                STRICT RULE: Check the calendar context for travel, illness, or protected rest days. Never schedule a hard workout over travel or incompatible events without confirmation.
                
                When proposing workouts, output the workout JSON wrapped EXACTLY in <icu_workout> ... </icu_workout> tags with fields: 'start_date_local' (YYYY-MM-DD), 'name', 'description', 'type' ('Ride'), 'indoor' (boolean).
                """ + prompt
                
                try:
                    resp, engine = execute_multiprovider_generation(payload, preferred_provider=selected_provider)
                    full_resp = f"{resp}\n\n*(Engine: {engine})*"
                    st.markdown(full_resp.split("<icu_workout>")[0])
                    st.session_state.messages.append({"role": "model", "content": full_resp})
                    st.rerun()
                except Exception as e: st.error(f"Generation failed: {e}")

# ================= VIEW 3: TRAINING CALENDAR & SICKNESS LOGGING (FIX 4) =================
elif selected_nav == "📅 Training Calendar":
    st.markdown("### 📅 Training Calendar & Status Logging")
    
    # FIX 4: Quick-entry form to log sickness, travel, or unavailability directly to Intervals.icu
    with st.expander("📝 Log Sickness, Travel, or Unavailability", expanded=False):
        with st.form("sickness_travel_form"):
            status_type = st.selectbox("Category", ["Illness / Sickness", "Travel / Away", "Soreness / Fatigue", "Forced Rest Day"])
            start_d = st.date_input("Start Date", value=datetime.date.today())
            end_d = st.date_input("End Date", value=datetime.date.today())
            status_notes = st.text_area("Details / Notes")
            
            if st.form_submit_button("Post Status to Intervals.icu", use_container_width=True):
                payload = {
                    "category": "NOTE",
                    "start_date_local": start_d.isoformat() + "T00:00:00",
                    "end_date_local": end_d.isoformat() + "T00:00:00",
                    "name": f"[{status_type}]",
                    "description": status_notes or status_type
                }
                res = requests.post(f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events", json=payload, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
                if res.status_code == 200:
                    st.success("Successfully posted status/unavailability to Intervals.icu calendar!")
                    fetch_intervals_data.clear()
                    st.rerun()
                else: st.error(f"Failed to post: {res.text}")

    st.markdown("#### 🗓️ Upcoming Schedule")
    if planned_events:
        df_cal = pd.DataFrame(planned_events)
        cols = [c for c in ['start_date_local', 'name', 'type', 'description'] if c in df_cal.columns]
        st.dataframe(df_cal[cols], use_container_width=True, hide_index=True)
    else: st.info("No events scheduled.")

# ================= VIEW 4: ACTIVITY INSPECTOR =================
elif selected_nav == "🔍 Activity Inspector":
    st.markdown("### 🔍 Past Activity Inspector")
    if activities_data:
        act_options = {f"{act.get('start_date_local','')[:10]} — {act.get('name')}": act for act in activities_data}
        selected_label = st.selectbox("Select activity:", list(act_options.keys()))
        selected_act = act_options[selected_label]
        st.json(selected_act)
    else: st.info("No activities found.")

# ================= VIEW 5: RECOVERY & SUPPLEMENTS =================
elif selected_nav == "💊 Recovery & Supplements":
    st.markdown("### 💊 Recovery & Supplement Stack")
    if "user_supplements" not in st.session_state: st.session_state.user_supplements = []
    with st.form("add_supp_form", clear_on_submit=True):
        n = st.text_input("Name")
        t = st.text_input("Timing")
        if st.form_submit_button("Add") and n:
            st.session_state.user_supplements.append({"name": n, "timing": t})
            st.success("Added!")
            st.rerun()
    if st.session_state.user_supplements:
        st.dataframe(pd.DataFrame(st.session_state.user_supplements), use_container_width=True, hide_index=True)

# ================= VIEW 6: ROUTE STRATEGIST =================
elif selected_nav == "🗺️ Route Strategist":
    st.markdown("### 🗺️ Route Strategist (.gpx)")
    uploaded_gpx = st.file_uploader("Upload GPX", type=["gpx"])
    if uploaded_gpx:
        st.success("GPX uploaded successfully!")
