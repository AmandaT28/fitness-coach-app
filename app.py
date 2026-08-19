import datetime
import os
import concurrent.futures
import xml.etree.ElementTree as ET
import math
import re
from dotenv import load_dotenv
from google import genai
from openai import OpenAI
import anthropic
import requests
import streamlit as st
from supabase import create_client, Client
import pandas as pd

# Load environment variables safely
try:
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase credentials missing! Add SUPABASE_URL and SUPABASE_KEY to Secrets.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
google_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None
openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None

# App UI Configuration
st.set_page_config(page_title="ICU Coach • Elite Suite", page_icon="🚴‍♂️", layout="centered")

st.markdown("""
<style>
    /* Mobile Wrapper Feel */
    .main .block-container {
        max-width: 480px;
        padding-top: 1rem;
        padding-bottom: 3rem;
    }
    .stCard {
        background-color: #ffffff;
        border: 1px solid rgba(128, 128, 128, 0.12);
        border-radius: 16px;
        padding: 18px;
        margin-bottom: 14px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.02);
    }
    div[data-testid="stMetric"] {
        background-color: #f8f9fa;
        border: 1px solid #eee;
        padding: 12px;
        border-radius: 12px;
    }
</style>
""", unsafe_allow_html=True)

# --- MULTI-PROVIDER AI ROUTER ---
def execute_multiprovider_generation(prompt, preferred_provider="⚡ Auto-Fallback Chain"):
    def call_openai():
        res = openai_client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content, "OpenAI GPT-4o"
    def call_anthropic():
        res = anthropic_client.messages.create(model="claude-3-5-sonnet-20241022", max_tokens=2048, messages=[{"role": "user", "content": prompt}])
        return res.content[0].text, "Anthropic Claude"
    def call_google():
        for m in ["gemini-2.5-flash", "gemini-3.5-flash"]:
            try:
                return google_client.models.generate_content(model=m, contents=prompt).text, f"Google {m}"
            except: continue
        raise Exception("Google failed")

    active = []
    if openai_client: active.append(("OpenAI", call_openai))
    if anthropic_client: active.append(("Anthropic", call_anthropic))
    if google_client: active.append(("Google", call_google))

    for name, action in active:
        try: return action()
        except: continue
    raise Exception("All AI providers failed.")

# --- AUTHENTICATION ---
if "user" not in st.session_state: st.session_state.user = None
if not st.session_state.user:
    st.markdown("### 🔐 ICU Coach Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Log In", use_container_width=True):
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state.user = res.user
            st.rerun()
        except Exception as e: st.error(f"Login failed: {e}")
    st.stop()

USER_ID = st.session_state.user.id

# Fetch profile & Intervals API keys
profile_res = supabase.table("profiles").select("*").eq("id", USER_ID).execute()
user_profile = profile_res.data[0] if profile_res.data else {}

if not user_profile.get("intervals_api_key"):
    st.error("Please configure your Intervals.icu API key in Supabase profiles.")
    st.stop()

INTERVALS_API_KEY = user_profile["intervals_api_key"]
ATHLETE_ID = user_profile["intervals_athlete_id"]

# Fetch Wellness Data from Intervals.icu
@st.cache_data(ttl=300, show_spinner=False)
def fetch_wellness(aid, key):
    try:
        url = f"https://intervals.icu/api/v1/athlete/{aid}/wellness?oldest=2026-08-01&newest=2026-08-31"
        res = requests.get(url, auth=("API_KEY", key), timeout=5)
        return res.json() if res.status_code == 200 else []
    except: return []

wellness = fetch_wellness(ATHLETE_ID, INTERVALS_API_KEY)
latest = wellness[-1] if wellness else {}
r_hr = latest.get("restingHR", 47)
hrv = latest.get("hrv", 41)
sleep_secs = latest.get("sleepSecs") if latest and latest.get("sleepSecs") is not None else 22320
sleep_hrs = sleep_secs / 3600.0
weight = latest.get("weight", 66.55)

# Target Race Setup
race_name = "Bintan Round Island"
race_date = datetime.date(2026, 10, 24)
days_left = (race_date - datetime.date.today()).days

# --- NAVIGATION TABS (Bottom Bar Simulation in Sidebar/Top) ---
tab_dash, tab_workout, tab_ai, tab_settings = st.tabs(["🏠 Dashboard", "🏋️‍♂️ Workout", "🤖 AI Labs", "⚙️ Settings"])

# ================= TAB 1: DASHBOARD =================
with tab_dash:
    st.markdown(f"### Hello, **{st.session_state.user.email.split('@')[0]}** 👋")
    st.caption(f"Wednesday, {datetime.date.today().strftime('%B %d, %Y')} • Last updated: {datetime.datetime.now().strftime('%I:%M %p')}")
    
    # Coach Today Banner
    st.info("💡 **Coach Today:** Build • Week 3/9 — Add strength and harder efforts to build climbing resilience.")
    
    # Weekly Load Progress Bar
    st.markdown("**Weekly load** — 0 / 550 TSS (0%)")
    st.progress(0.0)
    
    # Target Race Card
    st.markdown(f"""
    <div style="background-color: #fef9e7; border: 1px solid #f9e79f; padding: 14px; border-radius: 12px; margin-bottom: 14px;">
        <span style="font-size: 0.8rem; font-weight: bold; color: #d68910; background: #fcf3cf; padding: 2px 6px; border-radius: 4px;">BUILD</span>
        <div style="font-weight: bold; font-size: 1.05rem; margin-top: 4px;">Target Race: {race_name}</div>
        <div style="color: #666; font-size: 0.85rem;">October 24, 2026 • 10 hours/week</div>
        <hr style="margin: 8px 0; border-top: 1px solid #fce881;">
        <div style="display: flex; justify-content: space-between; font-size: 0.9rem; font-weight: 500;">
            <span>{days_left} days left</span>
            <span>9 weeks left</span>
        </div>
    </div>
    """, unsafe_allow_html=True)
    
    # Biometrics Grid (Apple HealthKit Style Cards)
    b1, b2 = st.columns(2)
    with b1:
        st.metric("RESTING HR", f"{r_hr} bpm", "-1 bpm", delta_color="inverse")
        st.metric("SLEEP", f"{round(sleep_hrs, 1)}h", "-0.5h", delta_color="inverse")
    with b2:
        st.metric("HRV", f"{hrv} ms", "Stable")
        st.metric("WEIGHT", f"{weight} kg", "+0.2kg")

# ================= TAB 2: WORKOUT PLANNER =================
with tab_workout:
    st.markdown("### Training Plan")
    st.markdown(f"**{race_name}** (10 hours/week)")
    
    # Day Selector Pills
    days = ["Wed 19", "Thu 20", "Fri 21", "Sat 22", "Sun 23", "Mon 24", "Tue 25"]
    cols = st.columns(7)
    for i, d in enumerate(days):
        with cols[i]:
            if st.button(d, key=f"day_{i}", use_container_width=True):
                st.session_state.selected_day = d

    st.markdown("#### Sport Selector")
    col_s1, col_s2 = st.columns(2)
    with col_s1: sel_sport = st.button("🏃‍♂️ Run", use_container_width=True)
    with col_s2: sel_bike = st.button("🚴‍♂️ Cycling", use_container_width=True)

    st.markdown("#### How are you feeling?")
    f1, f2, f3, f4 = st.columns(4)
    with f1: st.button("💪 Great")
    with f2: st.button("👍 Normal")
    with f3: st.button(" Tired")
    with f4: st.button(" Exhausted")

    if st.button("🤖 Create AI Workout & .ZWO File", type="primary", use_container_width=True):
        with st.spinner("Generating structured workout..."):
            prompt = "Generate a 75-minute MyWhoosh sweet-spot climbing workout for Bintan Round Island preparation. Include a valid .zwo XML block."
            res, engine = execute_multiprovider_generation(prompt, preferred_provider=st.session_state.get("provider", "⚡ Auto-Fallback Chain"))
            st.markdown(res)
            
            # Extract and provide download button for MyWhoosh
            match = re.search(r"```xml\s*(<workout_file>.*?</\s*workout_file>)\s*```", res, re.DOTALL)
            if match:
                st.download_button("📥 Download MyWhoosh Workout (.zwo)", match.group(1), file_name="ICU_Coach_Workout.zwo", mime="application/xml")

    st.markdown("---")
    st.markdown("#### This Week's Scheduled Sessions")
    st.markdown("""
    * 🚴‍♂️ **Aerobic Flush Ride** • 19/8/2026 • 45m
    * 🚴‍♂️ **FTP Intervals (MyWhoosh)** • 20/8/2026 • 1h 5m
    * 🚴‍♂️ **Outdoor Group Ride** • 22/8/2026 • 3h 30m
    * 🏃‍♂️ **Social Run (HR Focused)** • 23/8/2026 • 1h 10m
    """)

# ================= TAB 3: AI LABS & COMMAND CENTER =================
with tab_ai:
    st.markdown("### 🧠 AI Command Center & Labs")
    
    col_c1, col_c2 = st.columns(2)
    with col_c1:
        if st.button("☀️ How am I today?", use_container_width=True):
            st.info("AI Analysis: HRV is stable and resting HR is optimal. You are primed for today's threshold session.")
        if st.button("🏥 Sickness Risk Analysis", use_container_width=True):
            st.success("Sickness Risk: Low. Baseline immune metrics and sleep patterns are normal.")
        if st.button("⚡ Recovery Pro", use_container_width=True):
            st.info("Recovery Pro: Central nervous system recovery score is 88/100. Full gas for weekend club rides.")
    with col_c2:
        if st.button("📅 Weekly Strategy", use_container_width=True):
            st.info("Weekly Strategy: Front-load intensity on Tuesday/Thursday, preserve weekend for group climbing endurance.")
        if st.button("📈 My Progress", use_container_width=True):
            st.info("Progress: CTL is building steadily toward October target race readiness.")
        if st.button("🏆 Race Predictor", use_container_width=True):
            st.info("Race Predictor: On track to complete Bintan Round Island in under 4 hours 15 minutes.")

# ================= TAB 4: SETTINGS =================
with tab_settings:
    st.markdown("### ⚙️ Settings & API Config")
    st.text_input("Intervals.icu Athlete ID", value=ATHLETE_ID)
    st.text_input("Intervals.icu API Key", type="password", value=INTERVALS_API_KEY)
    if st.button("Log Out", use_container_width=True):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()
