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
import plotly.graph_objects as go
import io
from streamlit_local_storage import LocalStorage

# Load environment variables safely
try:
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase credentials missing! Add SUPABASE_URL and SUPABASE_KEY to Secrets.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None

# App UI Configuration
st.set_page_config(page_title="AI Performance Coach • Elite Suite", page_icon="🚴‍♂️", layout="wide")

PRIMARY_GEMINI_KEY = st.secrets.get("google_keys", {}).get("primary_key") or st.secrets.get("GEMINI_API_KEY") or os.getenv("PRIMARY_KEY") or os.getenv("GEMINI_API_KEY")
SECONDARY_GEMINI_KEY = st.secrets.get("google_keys", {}).get("secondary_key") or st.secrets.get("SECONDARY_GEMINI_KEY") or os.getenv("SECONDARY_KEY")

primary_google_client = genai.Client(api_key=PRIMARY_GEMINI_KEY) if PRIMARY_GEMINI_KEY else None
secondary_google_client = genai.Client(api_key=SECONDARY_GEMINI_KEY) if SECONDARY_GEMINI_KEY else None

st.title("🚴‍♂️🏃‍♂️ AI Sports Science Coach")
st.caption("Multi-Sport Elite Command Center • Intervals.icu & Multi-LLM Integrated")

# --- AUTHENTICATION & SESSION STATE ---
if "user" not in st.session_state:
    st.session_state.user = None

localS = LocalStorage()

if not st.session_state.user:
    st.markdown("### 🔐 Secure Athlete Portal Login")
    auth_tab1, auth_tab2 = st.tabs(["Log In", "Sign Up"])
    with auth_tab1:
        login_email = st.text_input("Email", key="login_email")
        login_pass = st.text_input("Password", type="password", key="login_pass")
        if st.button("Log In", type="primary"):
            try:
                res = supabase.auth.sign_in_with_password({"email": login_email, "password": login_pass})
                st.session_state.user = res.user
                st.success("Login successful!")
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")
    with auth_tab2:
        signup_email = st.text_input("Email", key="signup_email")
        signup_pass = st.text_input("Password", type="password", key="signup_pass")
        if st.button("Create Account", type="primary"):
            try:
                res = supabase.auth.sign_up({"email": signup_email, "password": signup_pass})
                st.session_state.user = res.user
                st.success("Account created!")
                st.rerun()
            except Exception as e:
                st.error(f"Sign up failed: {e}")
    st.stop()

USER_ID = st.session_state.user.id

# Fetch user profile data from Supabase
try:
    profile_res = supabase.table("profiles").select("*").eq("id", USER_ID).execute()
    user_profile = profile_res.data[0] if profile_res.data else {}
except Exception:
    user_profile = {}

INTERVALS_API_KEY = user_profile.get("intervals_api_key")
ATHLETE_ID = user_profile.get("intervals_athlete_id")
display_name = user_profile.get("name") or "Athlete"

if "goals" not in st.session_state:
    st.session_state.goals = {
        "primary_sport": user_profile.get("primary_sport", "Cycling (Road)"),
        "secondary_sport": user_profile.get("secondary_sport", "Running"),
        "strength_sessions_per_week": user_profile.get("strength_sessions_per_week", 2),
        "event_name": user_profile.get("event_name", "Target Race"),
        "target_metric": user_profile.get("target_metric", "Build aerobic base"),
        "race_date": user_profile.get("event_date", str(datetime.date.today() + datetime.timedelta(days=60)))
    }

if "athlete_gear" not in st.session_state:
    st.session_state.athlete_gear = user_profile.get("gear_notes", "")
if "athlete_limitations" not in st.session_state:
    st.session_state.athlete_limitations = user_profile.get("limitations_notes", "")
if "messages" not in st.session_state:
    st.session_state.messages = user_profile.get("chat_history", [{"role": "assistant", "content": "Hello! I am your AI Multi-Sport Coach. Ask me to balance your training blocks or review your progress."}])
if "debrief_logs" not in st.session_state:
    st.session_state.debrief_logs = []
if "periodization_review" not in st.session_state:
    st.session_state.periodization_review = None

# --- MULTI-PROVIDER ROUTER ---
def execute_multiprovider_generation(prompt, preferred_provider="⚡ Auto-Fallback Chain"):
    def call_openai():
        if not openai_client: raise Exception("OpenAI missing")
        res = openai_client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content, "OpenAI GPT-4o"

    def call_anthropic():
        if not anthropic_client: raise Exception("Anthropic missing")
        res = anthropic_client.messages.create(model="claude-3-5-sonnet-20241022", max_tokens=2048, messages=[{"role": "user", "content": prompt}])
        return res.content[0].text, "Anthropic Claude"

    def call_google():
        if not primary_google_client: raise Exception("Google missing")
        return primary_google_client.models.generate_content(model="gemini-2.5-flash", contents=prompt).text, "Google Gemini"

    stack = []
    if openai_client: stack.append(("OpenAI", call_openai))
    if anthropic_client: stack.append(("Anthropic", call_anthropic))
    if primary_google_client: stack.append(("Google", call_google))

    if not stack:
        raise Exception("No AI provider keys configured.")

    for name, action in stack:
        try:
            return action()
        except Exception:
            continue
    raise Exception("All AI generation providers failed.")

# --- DATA FETCHING ---
@st.cache_data(ttl=300, show_spinner=False)
def fetch_intervals_wellness(athlete_id, api_key):
    try:
        end = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        start = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        res = requests.get(f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness?oldest={start}&newest={end}", auth=("API_KEY", api_key), timeout=5)
        return res.json() if res.status_code == 200 and res.json() else []
    except Exception: return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_recent_activities(athlete_id, api_key):
    try:
        end = datetime.date.today().isoformat()
        start = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
        res = requests.get(f"https://intervals.icu/api/v1/athlete/{athlete_id}/activities?oldest={start}&newest={end}", auth=("API_KEY", api_key), timeout=5)
        return res.json() if res.status_code == 200 else []
    except Exception: return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_planned_workouts(athlete_id, api_key):
    try:
        end = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
        start = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
        res = requests.get(f"https://intervals.icu/api/v1/athlete/{athlete_id}/events?oldest={start}&newest={end}", auth=("API_KEY", api_key), timeout=5)
        return res.json() if res.status_code == 200 else []
    except Exception: return []

@st.cache_data(ttl=600, show_spinner=False)
def fetch_rain_intelligence():
    try:
        res = requests.get("https://api.open-meteo.com/v1/forecast?latitude=1.3521&longitude=103.8198&current=precipitation,weather_code", timeout=3)
        data = res.json().get("current", {})
        return data.get("precipitation", 0.0) > 0.1 or data.get("weather_code", 0) in [51, 61, 63, 65, 80, 95]
    except Exception:
        return False

def parse_gpx(gpx_bytes):
    try:
        root = ET.fromstring(gpx_bytes)
        ns = {'gpx': root.tag.split('}')[0].strip('{')} if '}' in root.tag else {}
        elevations = [float(e.text) for e in root.iterfind('.//gpx:ele', ns)] if ns else [float(e.text) for e in root.iterfind('.//ele')]
        if not elevations: return None
        gain = sum(max(0, elevations[i] - elevations[i-1]) for i in range(1, len(elevations)))
        return {"distance_km": round(len(elevations) * 0.05, 2), "elevation_gain_m": int(gain), "max_elevation": int(max(elevations))}
    except Exception:
        return None

# Fetch data if credentials are setup
wellness_list = fetch_intervals_wellness(ATHLETE_ID, INTERVALS_API_KEY) if ATHLETE_ID and INTERVALS_API_KEY else []
activities_data = fetch_recent_activities(ATHLETE_ID, INTERVALS_API_KEY) if ATHLETE_ID and INTERVALS_API_KEY else []
planned_data = fetch_planned_workouts(ATHLETE_ID, INTERVALS_API_KEY) if ATHLETE_ID and INTERVALS_API_KEY else []
is_raining = fetch_rain_intelligence()

ctl, atl, tsb, sleep_score = 0, 0, 0, 0
if wellness_list:
    latest = wellness_list[-1]
    ctl, atl, tsb = latest.get("ctl", 0), latest.get("atl", 0), latest.get("tsb", 0)
    for r in reversed(wellness_list):
        if sleep_score == 0 and r.get("sleepScore"): sleep_score = r.get("sleepScore")

days_to_event = (datetime.datetime.strptime(str(st.session_state.goals["race_date"]), "%Y-%m-%d").date() - datetime.date.today()).days if "race_date" in st.session_state.goals else 30
equipment_context = f"Gear: {st.session_state.athlete_gear} | Limits: {st.session_state.athlete_limitations}"

# --- SIDEBAR CONFIGURATION ---
with st.sidebar:
    st.markdown(f"👤 **{display_name}**")
    selected_provider = st.selectbox("⚡ AI Engine Model", ["⚡ Auto-Fallback Chain", "OpenAI GPT", "Anthropic Claude", "Google Gemini"])
    
    st.markdown("---")
    st.subheader("⚙️ Athlete Setup & Gear")
    with st.form("gear_form"):
        p_sport = st.text_input("Primary Sport", value=st.session_state.goals["primary_sport"])
        s_sport = st.text_input("Secondary Sport", value=st.session_state.goals["secondary_sport"])
        strength_count = st.number_input("Gym Sessions/Wk", 0, 5, value=st.session_state.goals["strength_sessions_per_week"])
        gear = st.text_area("Gear Notes", value=st.session_state.athlete_gear)
        limits = st.text_area("Physical Limitations", value=st.session_state.athlete_limitations)
        if st.form_submit_button("Save Profile"):
            st.session_state.goals["primary_sport"] = p_sport
            st.session_state.goals["secondary_sport"] = s_sport
            st.session_state.goals["strength_sessions_per_week"] = strength_count
            st.session_state.athlete_gear = gear
            st.session_state.athlete_limitations = limits
            supabase.table("profiles").update({
                "primary_sport": p_sport, "secondary_sport": s_sport, 
                "strength_sessions_per_week": strength_count, "gear_notes": gear, "limitations_notes": limits
            }).eq("id", USER_ID).execute()
            st.success("Updated!")
            st.rerun()

    if st.button("Log Out"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

# --- NAVIGATION SUITE (4 Core Tabs) ---
tab_cmd, tab_coach, tab_strat, tab_strength = st.tabs([
    "📊 Command Center", "🤖 AI Coach & Logs", "🗺️ Event Strategist", "🏋️‍♂️ Strength"
])

# ================= TAB 1: COMMAND CENTER =================
with tab_cmd:
    st.markdown("### ☀️ Daily Coaching Briefing")
    col_b1, col_b2 = st.columns([3, 1])
    with col_b1:
        weather_advisory = "🌧️ **Wet Weather Alert:** Indoor smart trainer or gym workout advised." if is_raining else "☀️ **Weather Clear:** Outdoor routes fully viable."
        st.info(f"**Focus:** Balancing **{st.session_state.goals['primary_sport']}** with secondary **{st.session_state.goals['secondary_sport']}** & **{st.session_state.goals['strength_sessions_per_week']}x weekly gym work**.\n\n{weather_advisory}\n\n**Readiness:** TSB Form is `{tsb:.1f}` | Sleep: `{sleep_score}/100`.")
    with col_b2:
        st.metric("Event Countdown", f"{days_to_event} Days")

    st.markdown("---")
    col_met, col_cal = st.columns([1, 2])
    with col_met:
        st.markdown("#### Training Load")
        st.metric("Fitness (CTL)", round(ctl, 1))
        st.metric("Fatigue (ATL)", round(atl, 1))
        st.metric("Form (TSB)", round(tsb, 1))
    with col_cal:
        st.markdown("#### 📅 Upcoming Calendar")
        if planned_data:
            df_cal = pd.DataFrame(planned_data)
            display_cols = [c for c in ['start_date_local', 'name', 'type'] if c in df_cal.columns]
            st.dataframe(df_cal[display_cols] if display_cols else df_cal, use_container_width=True, hide_index=True)
        else:
            st.info("No upcoming calendar events found.")

    st.markdown("---")
    if st.button("Run Periodization Audit", type="primary"):
        with st.spinner("Analyzing multi-sport balance..."):
            prompt = f"Audit my multi-sport plan. Primary: {st.session_state.goals['primary_sport']}, Secondary: {st.session_state.goals['secondary_sport']}, Strength: {st.session_state.goals['strength_sessions_per_week']}x/wk. Rain: {is_raining}. CTL: {ctl}, TSB: {tsb}. Event in {days_to_event} days. {equipment_context}"
            try:
                res, model = execute_multiprovider_generation(prompt, preferred_provider=selected_provider)
                st.session_state.periodization_review = f"{res}\n\n*(Engine: {model})*"
                st.rerun()
            except Exception as e:
                st.error(f"Failed: {e}")

    if st.session_state.periodization_review:
        with st.expander("📋 Audit Results", expanded=True):
            st.markdown(st.session_state.periodization_review)
            if st.button("Clear Audit"): st.session_state.periodization_review = None; st.rerun()

# ================= TAB 2: AI COACH & LOGS =================
with tab_coach:
    c_col1, c_col2 = st.columns([2, 1])
    with c_col1:
        st.markdown("### 🤖 Multi-Sport AI Coach")
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
                
        if prompt := st.chat_input("Ask about balancing your training blocks..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            with st.chat_message("model"):
                with st.spinner("Consulting coach..."):
                    payload = f"Elite endurance coach context. Goals: {st.session_state.goals}. CTL={ctl}, TSB={tsb}. Rain: {is_raining}. Debriefs: {st.session_state.debrief_logs}. {equipment_context}\nUser: {prompt}"
                    try:
                        resp, engine = execute_multiprovider_generation(payload, preferred_provider=selected_provider)
                        full_resp = f"{resp}\n\n*(Engine: {engine})*"
                        st.markdown(full_resp)
                        st.session_state.messages.append({"role": "model", "content": full_resp})
                        supabase.table("profiles").update({"chat_history": st.session_state.messages[-30:]}).eq("id", USER_ID).execute()
                    except Exception as e:
                        st.error(f"Failed: {e}")
                        
    with c_col2:
        st.markdown("### 📝 Workout Debrief")
        with st.form("debrief_form"):
            d_date = st.date_input("Date")
            d_sport = st.selectbox("Sport", ["Cycling", "Running", "Strength"])
            d_rpe = st.slider("RPE (1-10)", 1, 10, 5)
            d_notes = st.text_area("Notes")
            if st.form_submit_button("Save Debrief"):
                st.session_state.debrief_logs.append({"date": str(d_date), "sport": d_sport, "rpe": d_rpe, "notes": d_notes})
                st.success("Saved!")

# ================= TAB 3: EVENT STRATEGIST =================
with tab_strat:
    st.markdown("### 🗺️ Route & Fueling Strategist")
    f_col1, f_col2 = st.columns(2)
    with f_col1:
        dur = st.slider("Duration (Hours)", 1.0, 6.0, 3.0, 0.5)
        sport_type = st.selectbox("Activity", ["Cycling", "Running"])
        wt = st.number_input("Weight (kg)", 45.0, 100.0, 65.0)
    with f_col2:
        carbs = 90 if sport_type == "Cycling" else 60
        st.metric("Recommended Carbs", f"{carbs} g/hr", f"Total: {int(carbs * dur)}g")
        st.metric("Fluid Target", f"{int(wt * 8)} ml/hr")
        
    st.markdown("---")
    uploaded_gpx = st.file_uploader("Upload GPX Route File", type=["gpx"])
    if uploaded_gpx:
        metrics = parse_gpx(uploaded_gpx.read())
        if metrics:
            rc1, rc2, rc3 = st.columns(3)
            rc1.metric("Distance", f"{metrics['distance_km']} km")
            rc2.metric("Elevation Gain", f"{metrics['elevation_gain_m']} m")
            rc3.metric("Max Elevation", f"{metrics['max_elevation']} m")
            if st.button("Generate AI Course Strategy"):
                with st.spinner("Analyzing profile..."):
                    p = f"Analyze route for {st.session_state.goals['primary_sport']}: {metrics['distance_km']}km, {metrics['elevation_gain_m']}m gain. Readiness: CTL={ctl}. Carbs: {carbs}g/hr. {equipment_context}"
                    res, model = execute_multiprovider_generation(p, preferred_provider=selected_provider)
                    st.markdown(res)

# ================= TAB 4: STRENGTH =================
with tab_strength:
    st.markdown("### 🏋️‍♂️ Strength & Conditioning")
    focus = st.selectbox("Focus Area", ["Cycling Force & Posterior Chain", "Running Durability & Core Stability", "Full Body Mobility"])
    if st.button("Generate Strength Workout"):
        with st.spinner("Designing session..."):
            p = f"{equipment_context}\nDesign a 45-min gym workout for a cyclist/runner focusing on: {focus}."
            res, model = execute_multiprovider_generation(p, preferred_provider=selected_provider)
            st.markdown(res)
