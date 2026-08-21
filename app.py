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

# --- CREDENTIALS & INITIALIZATION ---
SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase credentials missing! Add SUPABASE_URL and SUPABASE_KEY to Secrets.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Google Keys Only (Removed OpenAI/Anthropic entirely)
P_KEY = st.secrets.get("google_keys", {}).get("primary_key") or os.getenv("PRIMARY_KEY") or st.secrets.get("GEMINI_API_KEY")
S_KEY = st.secrets.get("google_keys", {}).get("secondary_key") or os.getenv("SECONDARY_KEY")
T_KEY = st.secrets.get("google_keys", {}).get("tertiary_key") or os.getenv("TERTIARY_KEY")

g_clients = {
    "Primary": genai.Client(api_key=P_KEY) if P_KEY else None,
    "Secondary": genai.Client(api_key=S_KEY) if S_KEY else None,
    "Tertiary": genai.Client(api_key=T_KEY) if T_KEY else None
}

# --- PURE GEMINI AI ROUTER WITH SAFETY NET ---
def execute_multiprovider_generation(prompt, preferred_provider="Google Gemini"):
    errors = []
    
    # Modern model strings with fallbacks
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash", "gemini-1.5-pro"]
    
    for name, client in g_clients.items():
        if not client: continue
        for m in models:
            try:
                res = client.models.generate_content(model=m, contents=prompt)
                if res and hasattr(res, "text") and res.text:
                    return res.text, f"Google {m} ({name})"
                else:
                    errors.append(f"{name} ({m}): Empty response (Safety Block / Filtered)")
            except Exception as e:
                errors.append(f"{name} ({m}): {str(e)}")
                
    raise Exception(f"Google Engine Failed. Diagnostics: {' | '.join(errors[:4])}")

localS = LocalStorage()

# --- URL TOKEN HANDLER ---
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
    except:
        pass

if "user_credentials" not in st.session_state:
    st.session_state.user_credentials = None

if "user" not in st.session_state:
    st.session_state.user = None

stored_guest = localS.getItem("athlete_profile_config")
if not st.session_state.user and stored_guest and not st.session_state.user_credentials:
    st.session_state.user_credentials = stored_guest

# --- AUTHENTICATION PORTAL ---
if not st.session_state.user and not st.session_state.user_credentials:
    st.markdown("### 🔐 Elite Athlete Portal • Authentication")
    owner_tab, guest_tab = st.tabs(["👑 Owner Login (Supabase)", "⚙️ Friend / Guest Setup (BYOK)"])
    
    with owner_tab:
        st.markdown("Log in using your registered Supabase account credentials.")
        with st.form("supabase_login_form"):
            email = st.text_input("Email")
            password = st.text_input("Password", type="password")
            if st.form_submit_button("Log In with Supabase", use_container_width=True):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    st.session_state.user = res.user
                    st.success("Supabase login successful!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Login failed: {e}")
                    
    with guest_tab:
        st.markdown("Friends can connect using their own Intervals.icu and Google AI Studio keys.")
        with st.form("guest_setup_form"):
            col_name = st.text_input("Your Name / Identifier")
            icu_key = st.text_input("Intervals.icu API Key")
            icu_id = st.text_input("Intervals.icu Athlete ID")
            gemini_key = st.text_input("Google AI Studio (Gemini) API Key", type="password")
            
            if st.form_submit_button("Save & Launch Guest Session", use_container_width=True):
                if icu_key and icu_id and gemini_key:
                    config_data = {
                        "name": col_name.strip() if col_name else "Guest Athlete",
                        "icu_key": icu_key.strip(),
                        "icu_id": icu_id.strip(),
                        "gemini_key": gemini_key.strip(),
                        "gear": "",
                        "limitations": "",
                        "onboarding_done": False
                    }
                    localS.setItem("athlete_profile_config", config_data)
                    st.session_state.user_credentials = config_data
                    st.success("Configuration saved! Launching dashboard...")
                    st.rerun()
                else:
                    st.warning("Please fill in all required fields.")
    st.stop()

# --- RESOLVE ACTIVE VARIABLES ---
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

# --- MESSAGES & STATE INIT ---
if "messages" not in st.session_state: st.session_state.messages = []
if "selected_activity_analysis" not in st.session_state: st.session_state.selected_activity_analysis = None
if "auto_debriefed_id" not in st.session_state: st.session_state.auto_debriefed_id = None
if "user_supplements" not in st.session_state:
    st.session_state.user_supplements = [
        {"name": "Creatine", "timing": "Post-Workout", "notes": "Cellular ATP replenishment & sprint power"},
        {"name": "Protein", "timing": "Post-Workout (<45m)", "notes": "Muscle repair & glycogen resynthesis"},
        {"name": "Turmeric", "timing": "Morning with Fats", "notes": "Systemic inflammation control"},
        {"name": "Fish Oil", "timing": "Morning & Evening", "notes": "Cardiovascular & nocturnal recovery"},
        {"name": "NMN", "timing": "Morning (Fasted)", "notes": "Cellular NAD+ & mitochondrial support"}
    ]

# --- ONBOARDING ---
is_onboarded = user_profile.get("onboarding_done", False) if st.session_state.user else current_creds.get("onboarding_done", False)

if not is_onboarded:
    st.markdown("### 🚴‍♂️ Coach's Initial Intake & Onboarding")
    st.markdown("Welcome! Before we dive into your telemetry, let's have a quick introductory chat.")
    
    if len(st.session_state.messages) == 0:
        st.session_state.messages = [{"role": "model", "content": f"Hey {display_name}! I'm your autonomous performance coach. Tell me a bit about your current routine, limitations, and focus."}]
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    if intake_reply := st.chat_input("Tell your coach about yourself..."):
        st.session_state.messages.append({"role": "user", "content": intake_reply})
        intake_prompt = f"[Coach Onboarding Intake] The athlete shared: '{intake_reply}'. Acknowledge them professionally."

        with st.spinner("Coach is reviewing your intake..."):
            try:
                resp, _ = execute_multiprovider_generation(intake_prompt)
                st.session_state.messages.append({"role": "model", "content": resp})
            except Exception:
                st.session_state.messages.append({"role": "model", "content": "Welcome! We're ready to start training."})
            
            if st.session_state.user: supabase.table("profiles").update({"onboarding_done": True}).eq("id", USER_ID).execute()
            else:
                current_creds["onboarding_done"] = True
                localS.setItem("athlete_profile_config", current_creds)
            st.rerun()
    st.stop()  
    
if not st.session_state.messages:
    st.session_state.messages = [{"role": "model", "content": "Hello! I am your autonomous AI Performance Coach. I'm actively monitoring your Intervals.icu & Garmin sync pipeline and training calendar. How can I help you train today?"}]

# --- FETCH DATA ---
@st.cache_data(ttl=300, show_spinner=False)
def fetch_intervals_data(aid, key):
    try:
        today = datetime.date.today()
        start_90 = (today - datetime.timedelta(days=90)).isoformat()
        start_7 = (today - datetime.timedelta(days=7)).isoformat()
        end_14 = (today + datetime.timedelta(days=14)).isoformat()
        
        w_res = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/wellness?oldest={start_90}&newest={end_14}", auth=("API_KEY", key), timeout=5)
        a_res = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/activities?oldest={start_90}&newest={end_14}", auth=("API_KEY", key), timeout=5)
        e_res = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/events?oldest={start_7}&newest={end_14}", auth=("API_KEY", key), timeout=5)
        
        return (
            w_res.json() if w_res.status_code == 200 else [], 
            a_res.json() if a_res.status_code == 200 else [],
            e_res.json() if e_res.status_code == 200 else []
        )
    except: return [], [], []

wellness_list, activities_data, planned_events = fetch_intervals_data(ATHLETE_ID, INTERVALS_API_KEY)

ctl, atl, tsb, sleep_score = 0, 0, 0, 0
if wellness_list:
    latest = wellness_list[-1]
    ctl, atl, tsb = latest.get("ctl", 0), latest.get("atl", 0), latest.get("tsb", 0)
    for r in reversed(wellness_list):
        if sleep_score == 0 and r.get("sleepScore"): sleep_score = r.get("sleepScore")

try:
    race_date_obj = datetime.datetime.strptime(st.session_state.goals["race_date"], "%Y-%m-%d").date()
except:
    race_date_obj = datetime.date(2026, 10, 24)
days_left = (race_date_obj - datetime.date.today()).days

# --- FULL NAVIGATION SUITE ---
NAV_OPTIONS = ["📊 Command Center", "🤖 AI Coach & Sparring", "📅 Training Calendar", "🔍 Activity Inspector", "💊 Recovery & Supplements", "🗺️ Route Strategist"]
if "active_nav" not in st.session_state: st.session_state.active_nav = "📊 Command Center"

top_nav = st.radio("Navigation Suite Top", NAV_OPTIONS, index=NAV_OPTIONS.index(st.session_state.active_nav), horizontal=True, label_visibility="collapsed", key="top_nav_widget")
if top_nav != st.session_state.active_nav:
    st.session_state.active_nav = top_nav
    st.rerun()

st.markdown("---")

# --- SIDEBAR ---
with st.sidebar:
    st.markdown(f"👤 **{display_name}**")
    st.markdown("---")
    st.subheader("⚡ Quick Navigation Links")
    sidebar_nav = st.radio("Secondary Navigation", NAV_OPTIONS, index=NAV_OPTIONS.index(st.session_state.active_nav), key="sidebar_nav_selector", label_visibility="collapsed")
    if sidebar_nav != st.session_state.active_nav:
        st.session_state.active_nav = sidebar_nav
        st.rerun()

    st.markdown("---")
    st.subheader("⚙️ Athlete & Equipment Profile")
    with st.form("gear_profile_form"):
        custom_gear = st.text_area("Bike Build & Gear Notes", value=st.session_state.athlete_gear, height=100)
        custom_limits = st.text_area("Physical Limitations / Notes", value=st.session_state.athlete_limitations, height=70)
        if st.form_submit_button("Save Profile", use_container_width=True):
            st.session_state.athlete_gear = custom_gear
            st.session_state.athlete_limitations = custom_limits
            if st.session_state.user:
                try:
                    supabase.table("profiles").update({"gear_notes": custom_gear, "limitations_notes": custom_limits}).eq("id", USER_ID).execute()
                    st.success("Synced to Supabase cloud!")
                except Exception as e: st.error(f"Sync failed: {e}")
            else:
                current_creds["gear"] = custom_gear
                current_creds["limitations"] = custom_limits
                localS.setItem("athlete_profile_config", current_creds)
                st.success("Saved to browser memory!")

    st.markdown("---")
    st.subheader("🎭 Coaching Persona")
    coach_persona = st.selectbox("Select AI Style", ["Collaborative Peer (Balanced & Brainstorming)", "Sports Scientist (Data & Periodization Focus)", "Drill Sergeant (Strict & Direct Accountability)"])

    st.markdown("---")
    st.subheader("🎯 Target Race & Goals")
    with st.form("goal_feedback_form"):
        ev_name = st.text_input("Target Race", value=st.session_state.goals["event_name"])
        t_metric = st.text_input("Key Objective", value=st.session_state.goals["target_metric"])
        try: default_date = datetime.datetime.strptime(st.session_state.goals["race_date"], "%Y-%m-%d").date()
        except: default_date = datetime.date(2026, 10, 24)
        r_date = st.date_input("Target Race Date", value=default_date)
        
        if st.form_submit_button("Update Goals", use_container_width=True):
            st.session_state.goals["event_name"] = ev_name
            st.session_state.goals["target_metric"] = t_metric
            st.session_state.goals["race_date"] = str(r_date)
            if st.session_state.user:
                supabase.table("profiles").update({"event_name": ev_name, "target_metric": t_metric, "race_date": str(r_date)}).eq("id", USER_ID).execute()
            st.success("Goals updated!")

    st.markdown("---")
    # Pure Gemini Architecture Only
    selected_provider = st.selectbox("⚡ AI Engine Model", ["Google Gemini (Flash Cascade)"])

    st.markdown("---")
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = [{"role": "model", "content": "Chat history cleared. What topic or idea would you like to discuss next?"}]
        st.rerun()

    if st.button("Log Out / Switch Account", use_container_width=True):
        if st.session_state.user:
            supabase.auth.sign_out()
            st.session_state.user = None
        if st.session_state.user_credentials:
            localS.deleteItem("athlete_profile_config")
            st.session_state.user_credentials = None
        st.query_params.clear()
        st.rerun()

selected_nav = st.session_state.active_nav

# ================= VIEW 1: COMMAND CENTER =================
if selected_nav == "📊 Command Center":
    st.markdown(f"### ☀️ Autonomous AI Performance Coach • Command Center")
    
    st.markdown(f"""
    <div style="background-color: #fef9e7; border: 1px solid #f9e79f; padding: 16px; border-radius: 14px; margin-bottom: 16px;">
        <span style="font-size: 0.75rem; font-weight: bold; color: #d68910; background: #fcf3cf; padding: 2px 6px; border-radius: 4px;">📊 INTERVALS.ICU & GARMIN SYNC ACTIVE</span>
        <div style="font-weight: bold; font-size: 1.1rem; margin-top: 4px;">Target Race: {st.session_state.goals['event_name']} ({days_left} days left — {race_date_obj.strftime('%B %d, %Y')})</div>
        <div style="color: #666; font-size: 0.85rem; margin-top: 4px;">Objective: {st.session_state.goals['target_metric']}</div>
    </div>
    """, unsafe_allow_html=True)

    c_met1, c_met2, c_met3, c_met4 = st.columns(4)
    with c_met1: st.metric("Fitness (CTL)", round(ctl, 1))
    with c_met2: st.metric("Fatigue (ATL)", round(atl, 1))
    with c_met3: st.metric("Form (TSB)", round(tsb, 1))
    with c_met4: st.metric("Sleep Score", f"{sleep_score}/100" if sleep_score > 0 else "N/A")

    st.markdown("---")
    st.markdown("#### 📈 Deep 90-Day Training Load & Progression Trend Analysis")

    if "cached_trend_analysis" not in st.session_state:
        st.session_state.cached_trend_analysis = None
    if "trend_analysis_timestamp" not in st.session_state:
        st.session_state.trend_analysis_timestamp = None

    if st.button("🚀 Run 90-Day Trend Synthesis", type="primary"):
        trend_payload = "\n".join([
            "Perform a rigorous, detailed 90-day sports science trend analysis based on my wellness and training data:",
            f"CTL (Fitness): {ctl}, ATL (Fatigue): {atl}, TSB (Form): {tsb}",
            f"Recent Activities Summary: {activities_data[:25] if activities_data else 'None'}",
            f"Target Event: {st.session_state.goals['event_name']} in {days_left} days.",
            f"Objective: {st.session_state.goals['target_metric']}",
            "Provide a structured analysis covering fitness trajectory, consistency, climbing readiness, and next steps."
        ])

        with st.spinner("Synthesizing 90-day performance trends..."):
            try:
                trend_res, eng = execute_multiprovider_generation(trend_payload, preferred_provider=selected_provider)
                st.session_state.cached_trend_analysis = f"{trend_res}\n\n*(Generated by: {eng})*"
                st.session_state.trend_analysis_timestamp = datetime.datetime.now().strftime("%B %d, %Y at %H:%M")
            except Exception as e:
                st.error(f"Trend synthesis failed: {e}")

    if st.session_state.cached_trend_analysis:
        st.caption(f"🕒 Analysis generated on: **{st.session_state.trend_analysis_timestamp}**")
        st.markdown(st.session_state.cached_trend_analysis)
        
        c_tr1, c_tr2 = st.columns(2)
        with c_tr1:
            if st.button("💬 Discuss These Trends With Coach", key="discuss_trends_btn", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": f"Here is my recent 90-day training trend analysis that I ran on the Command Center:\n\n{st.session_state.cached_trend_analysis}\n\nBased on my goal of '{st.session_state.goals['target_metric']}', am I progressing correctly?"})
                st.session_state.messages.append({"role": "model", "content": "I have reviewed your 90-day trend report. What specific part of your fitness trajectory or training load would you like to tweak?"})
                st.session_state.active_nav = "🤖 AI Coach & Sparring"
                st.rerun()
        with c_tr2:
            if st.button("🗑️ Clear Trend Analysis", key="clear_trend_btn", use_container_width=True):
                st.session_state.cached_trend_analysis = None
                st.session_state.trend_analysis_timestamp = None
                st.rerun()

# ================= VIEW 2: AI COACH & SPARRING CHAT =================
elif selected_nav == "🤖 AI Coach & Sparring":
    st.markdown("### 🤖 AI Coach & Collaborative Sparring Partner")
    st.caption(f"Active Persona: **{coach_persona}** | Proposes plans first, and only syncs to Intervals.icu when you explicitly agree!")

    chat_container = st.container()

    # Render History safely
    with chat_container:
        for idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg["role"]):
                clean_content = re.sub(r"```xml\s*<\?xml.*?>.*?</\s*workout_file\s*>\s*```", "", msg["content"], flags=re.DOTALL)
                clean_content = re.sub(r"```\s*<workout_file>.*?</\s*workout_file>\s*```", "", clean_content, flags=re.DOTALL)
                clean_content = re.sub(r"<icu_workout>.*?</icu_workout>", "", clean_content, flags=re.DOTALL)
                st.markdown(clean_content.strip())
                
                if msg["role"] == "model":
                    match = re.search(r"```xml\s*(<\?xml.*?>.*?<\s*/\s*workout_file\s*>|<workout_file>.*?</\s*workout_file>)\s*```", msg["content"], re.DOTALL)
                    if not match: match = re.search(r"```\s*(<workout_file>.*?</\s*workout_file>)\s*```", msg["content"], re.DOTALL)
                    if match:
                        zwo_data = match.group(1).strip()
                        st.download_button(label="📥 Download MyWhoosh File (.zwo)", data=zwo_data, file_name=f"Coach_Workout_{idx}.zwo", mime="application/xml", key=f"zwo_{idx}")

    # Guaranteed Safe Chat Input
    if prompt := st.chat_input("Ask your coach to plan training or bounce an idea..."):
        st.session_state.messages.append({"role": "user", "content": prompt.strip()})
        with chat_container.chat_message("user"):
            st.markdown(prompt.strip())

        with chat_container.chat_message("assistant"):
            with st.spinner("🤖 Coach is analyzing and drafting..."):
                try:
                    stack_summary = ", ".join([f"{s['name']} ({s['timing']})" for s in st.session_state.user_supplements])
                    # Intelligent context capping to save tokens and speed up response
                    recent_history = "\n".join([f"{m['role'].upper()}: {m['content']}" for m in st.session_state.messages[-7:-1]])
                    recent_acts = activities_data[:5] if activities_data else 'None'
                    upcoming_evs = planned_events[:7] if planned_events else 'None'
                    
                    payload = "\n".join([
                        f"You are an elite cycling sports science coach. Persona: '{coach_persona}'.",
                        f"SUPPLEMENT STACK: {stack_summary}",
                        f"GOAL: {st.session_state.goals['event_name']} ({st.session_state.goals['target_metric']})",
                        f"METRICS: CTL={ctl}, ATL={atl}, TSB={tsb}.",
                        f"RECENT 5 ACTIVITIES: {recent_acts}",
                        f"NEXT 7 DAYS SCHEDULE: {upcoming_evs}",
                        "RECENT CONVERSATION:",
                        recent_history if recent_history else "None yet.",
                        f"Bike/Gear: {st.session_state.athlete_gear}",
                        f"Limits: {st.session_state.athlete_limitations}",
                        "CRITICAL DIRECTIVE: If the user explicitly asks for a deep ride analysis, you MUST ask them to verify key metrics before blasting a huge response. If they are just chatting or asking for a plan, answer normally.",
                        f"USER: {prompt.strip()}"
                    ])
                    
                    resp, engine = execute_multiprovider_generation(payload, preferred_provider=selected_provider)
                    
                    # Sync to Intervals
                    icu_matches = re.findall(r'<icu_workout>\s*(.*?)\s*</icu_workout>', resp, re.DOTALL)
                    parsed_workouts = 0
                    if icu_matches and ATHLETE_ID and INTERVALS_API_KEY:
                        for match_str in icu_matches:
                            try:
                                clean_json_str = match_str.replace("```json", "").replace("```", "").strip()
                                workouts = json.loads(clean_json_str)
                                if not isinstance(workouts, list): workouts = [workouts]
                                for w in workouts:
                                    w['category'] = 'WORKOUT'
                                    if 'start_date_local' in w and len(w['start_date_local']) == 10: w['start_date_local'] += "T00:00:00"
                                    api_resp = requests.post(f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events", json=w, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
                                    if api_resp.status_code == 200: parsed_workouts += 1
                            except Exception: pass

                    full_resp = f"{resp}\n\n*(Engine: {engine})*"
                    if parsed_workouts > 0:
                        full_resp += f"\n\n✅ **Success:** {parsed_workouts} plan(s) synchronized with Intervals.icu!"
                        fetch_intervals_data.clear()

                    st.markdown(re.sub(r"<icu_workout>.*?</icu_workout>", "", full_resp, flags=re.DOTALL))
                    st.session_state.messages.append({"role": "model", "content": full_resp})
                    
                    st.rerun()

                except Exception as e:
                    st.error(f"⚠️ Connection Failed: {str(e)}")
                    st.session_state.messages.pop() 

# ================= VIEW 3: TRAINING CALENDAR =================
elif selected_nav == "📅 Training Calendar":
    st.markdown("### 📅 Training Calendar & 2-Week Block Planner")
    st.caption("Review your schedule, view full session details, or click into any day to inspect double sessions.")

    c_cal1, c_cal2 = st.columns([2, 1])
    with c_cal1:
        st.markdown("#### 🗓️ Your Timeline")
        today_str = datetime.date.today().isoformat()
        
        combined_timeline = []
        if planned_events:
            for ev in planned_events:
                dt = ev.get('start_date_local', '')[:10]
                if dt >= (datetime.date.today() - datetime.timedelta(days=7)).isoformat():
                    combined_timeline.append({"id": ev.get('id'), "date": dt, "name": ev.get('name', 'Planned Workout'), "type": ev.get('type', 'Ride'), "desc": ev.get('description', 'No description provided.'), "status": "Planned"})
        if activities_data:
            for act in activities_data:
                dt = act.get('start_date_local', '')[:10]
                if dt >= (datetime.date.today() - datetime.timedelta(days=7)).isoformat():
                    dist_km = round((act.get('distance') or 0) / 1000, 1)
                    dur_min = int((act.get('moving_time') or 0) / 60)
                    combined_timeline.append({"id": act.get('id'), "date": dt, "name": act.get('name', 'Recorded Activity'), "type": act.get('type', 'Ride'), "desc": f"Distance: {dist_km} km | Time: {dur_min} mins | Avg Power: {act.get('average_watts', 'N/A')}W", "status": "Completed"})

        upcoming, past = [], []
        for item in combined_timeline:
            try: item['formatted_date'] = datetime.datetime.strptime(item['date'], "%Y-%m-%d").strftime("%A, %b %d")
            except: item['formatted_date'] = item['date']
            if item['date'] >= today_str: upcoming.append(item)
            else: past.append(item)

        upcoming = sorted(upcoming, key=lambda x: x['date'])
        past = sorted(past, key=lambda x: x['date'], reverse=True)

        tab_up, tab_past = st.tabs(["📅 Upcoming (Next 14 Days)", "✅ Past (Last 7 Days)"])
        with tab_up:
            if upcoming:
                for item in upcoming:
                    with st.expander(f"{item['formatted_date']} — {item['name']} ({item['status']})"):
                        st.markdown(f"**Type:** {item['type']}\n\n**Details:**\n{item['desc']}")
            else: st.info("No upcoming workouts scheduled.")
        with tab_past:
            if past:
                for item in past:
                    with st.expander(f"{item['formatted_date']} — {item['name']} ({item['status']})"):
                        st.markdown(f"**Type:** {item['type']}\n\n**Summary:**\n{item['desc']}")
            else: st.info("No activities recorded in the past 7 days.")

        st.markdown("---")
        st.markdown("#### 🤖 AI 2-Week Block Planner & Rescheduler")
        plan_focus = st.selectbox("Select 2-Week Block Focus:", ["Threshold Power & Sweet Spot Progression", "Climbing Endurance & Resistance Blocks", "Recovery & Taper Structure", "Custom Indoor/Outdoor Balance"])
        c_pbtn1, c_pbtn2 = st.columns(2)
        with c_pbtn1:
            if st.button("🚀 Propose 2-Week Block Plan", type="primary", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": f"Please propose a complete 2-week training block focused on '{plan_focus}' for me to review first before syncing."})
                st.session_state.messages.append({"role": "model", "content": f"I'm drafting your 2-week block proposal focused on '{plan_focus}'. Review it in the chat and let me know if you want me to sync it!"})
                st.session_state.active_nav = "🤖 AI Coach & Sparring"
                st.rerun()
        with c_pbtn2:
            if st.button("🔄 Propose Shift Forward 1 Day", use_container_width=True):
                st.session_state.messages.append({"role": "user", "content": "Please propose shifting all my upcoming workouts forward by 1 day so I can review the changes before syncing."})
                st.session_state.messages.append({"role": "model", "content": "Here is how shifting your schedule forward by 1 day looks..."})
                st.session_state.active_nav = "🤖 AI Coach & Sparring"
                st.rerun()

    with c_cal2:
        st.markdown("#### 💬 Custom Rescheduling via Chat")
        st.info("**How it works:**\n1. Ask coach for a plan.\n2. Review the workouts in chat.\n3. Reply **'Looks good, sync it'** to push to Intervals.icu!")

# ================= VIEW 4: ACTIVITY INSPECTOR =================
elif selected_nav == "🔍 Activity Inspector":
    st.markdown("### 🔍 Past Activity Inspector & Deep Debrief")
    if activities_data:
        act_options = {}
        for act in activities_data:
            name, date = act.get("name", "Unnamed Activity"), act.get("start_date_local", "")[:10]
            dist = round(((act.get("distance") or 0) / 1000), 1)
            dur_min = int((act.get("moving_time") or 0) / 60)
            act_options[f"{date} — {name} ({dist} km, {dur_min} mins)"] = act

        selected_label = st.selectbox("Choose a past activity to analyze:", list(act_options.keys()))
        selected_act = act_options[selected_label]
        act_display_name, act_display_date = selected_act.get('name', 'Workout'), selected_act.get('start_date_local', '')[:10]

        st.markdown(f"""
        <div style="background-color: #eaf2f8; border: 1px solid #a9cce3; padding: 12px 16px; border-radius: 10px; margin-bottom: 16px;">
            <div style="font-size: 0.8rem; font-weight: bold; color: #2471a3;">Selected Activity Inspection</div>
            <div style="font-size: 1.2rem; font-weight: bold; color: #1b4f72;">{act_display_name}</div>
            <div style="font-size: 0.9rem; color: #515a5a;">📅 Date: {act_display_date}</div>
        </div>
        """, unsafe_allow_html=True)

        col_info1, col_info2, col_info3 = st.columns(3)
        col_info1.metric("Distance", f"{round(((selected_act.get('distance') or 0) / 1000), 2)} km")
        col_info2.metric("Moving Time", f"{int((selected_act.get('moving_time') or 0) / 60)} mins")
        col_info3.metric("Average Power", f"{selected_act.get('average_watts', 'N/A')} W")

        if st.button("🤖 Run Deep AI Activity Debrief", type="primary", use_container_width=True):
            with st.spinner("Analyzing activity metrics..."):
                debrief_prompt = f"Perform a deep performance debrief for this activity: {act_display_name} on {act_display_date}. Details: {selected_act}. Goal: {st.session_state.goals['target_metric']}."
                try:
                    debrief_res, debrief_engine = execute_multiprovider_generation(debrief_prompt, preferred_provider=selected_provider)
                    st.session_state.selected_activity_analysis = f"### 🚴‍♂️ Performance Debrief: {act_display_name}\n📅 **Date:** {act_display_date}\n\n{debrief_res}\n\n*(Engine: {debrief_engine})*"
                except Exception as e: st.error(f"Analysis failed: {e}")

        if st.session_state.selected_activity_analysis:
            st.markdown("---")
            st.markdown(st.session_state.selected_activity_analysis)
            if st.button("💬 Clarify This Debrief with Coach"):
                st.session_state.messages.append({"role": "user", "content": f"I want clarifications regarding my activity '{act_display_name}' on {act_display_date}."})
                st.session_state.messages.append({"role": "model", "content": f"I have the details for '{act_display_name}' ({act_display_date}) right here. What specific section would you like to unpack?"})
                st.session_state.active_nav = "🤖 AI Coach & Sparring"
                st.rerun()
    else: st.info("No activities found in your Intervals.icu sync history.")

# ================= VIEW 5: RECOVERY & SUPPLEMENTS (RESTORED) =================
elif selected_nav == "💊 Recovery & Supplements":
    st.markdown("### 💊 Dynamic Recovery & Supplement Protocol")
    with st.form("add_supplement_form", clear_on_submit=True):
        col_s1, col_s2, col_s3 = st.columns([1, 1, 2])
        new_name, new_timing, new_notes = col_s1.text_input("Name"), col_s2.text_input("Timing"), col_s3.text_input("Notes")
        if st.form_submit_button("➕ Add to Stack", use_container_width=True):
            if new_name:
                st.session_state.user_supplements.append({"name": new_name.strip(), "timing": new_timing.strip() or "As needed", "notes": new_notes.strip() or "Custom"})
                st.success(f"Added {new_name} to your stack!")
                st.rerun()

    st.markdown("---")
    if st.session_state.user_supplements:
        st.dataframe(pd.DataFrame(st.session_state.user_supplements), use_container_width=True, hide_index=True)
        supp_names = [s["name"] for s in st.session_state.user_supplements]
        to_remove = st.selectbox("Select a supplement to remove:", ["-- Select --"] + supp_names)
        if to_remove != "-- Select --" and st.button("🗑️ Remove Selected Supplement"):
            st.session_state.user_supplements = [s for s in st.session_state.user_supplements if s["name"] != to_remove]
            st.rerun()

    st.markdown("---")
    if st.button("💬 Discuss Updated Supplement Stack With Coach"):
        stack_desc = ", ".join([f"{s['name']} ({s['timing']})" for s in st.session_state.user_supplements])
        st.session_state.messages.append({"role": "user", "content": f"Let's review my active supplement stack: {stack_desc}."})
        st.session_state.messages.append({"role": "model", "content": "I've loaded your updated supplement stack into our chat. Let's optimize your recovery!"})
        st.session_state.active_nav = "🤖 AI Coach & Sparring"
        st.rerun()

# ================= VIEW 6: ROUTE STRATEGIST (RESTORED) =================
elif selected_nav == "🗺️ Route Strategist":
    st.markdown("### 🗺️ Route Pacing & Climbing Strategist")
    uploaded_gpx = st.file_uploader("Upload GPX Route File (.gpx)", type=["gpx"])
    def parse_gpx(file_bytes):
        try:
            root = ET.fromstring(file_bytes.decode('utf-8', errors='ignore'))
            latlons, elevation_list = [], []
            for elem in root.iter():
                tag = elem.tag.split('}')[-1].lower()
                if tag in ['trkpt', 'rtept']:
                    lat, lon = elem.attrib.get('lat') or elem.attrib.get('latitude'), elem.attrib.get('lon') or elem.attrib.get('longitude')
                    if lat and lon:
                        latlons.append((float(lat), float(lon)))
                        ele_val = elevation_list[-1] if elevation_list else 0.0
                        for child in elem:
                            if child.tag.split('}')[-1].lower() in ['ele', 'elevation', 'alt']:
                                try: ele_val = float(child.text); break
                                except: pass
                        elevation_list.append(ele_val)
            if not latlons: return None
            total_ele_gain = sum(max(0, elevation_list[i] - elevation_list[i-1]) for i in range(1, len(elevation_list)))
            total_dist_km = sum(6371.0 * (2 * math.asin(math.sqrt(math.sin(math.radians(latlons[i][0]-latlons[i-1][0])/2)**2 + math.cos(math.radians(latlons[i-1][0])) * math.cos(math.radians(latlons[i][0])) * math.sin(math.radians(latlons[i][1]-latlons[i-1][1])/2)**2))) for i in range(1, len(latlons)))
            return {"distance_km": round(max(total_dist_km, 0.1), 2), "elevation_gain_m": round(total_ele_gain, 1), "max_elevation": round(max(elevation_list), 1) if elevation_list else 0}
        except: return None

    if uploaded_gpx:
        route_metrics = parse_gpx(uploaded_gpx.read())
        if route_metrics:
            c1, c2, c3 = st.columns(3)
            c1.metric("Distance", f"{route_metrics['distance_km']} km")
            c2.metric("Elevation Gain", f"{route_metrics['elevation_gain_m']} m")
            c3.metric("Max Elevation", f"{route_metrics['max_elevation']} m")
            if st.button("🤖 Generate Climbing Strategy", type="primary"):
                with st.spinner("Analyzing route profile..."):
                    strat_prompt = f"Analyze this route profile: Distance {route_metrics['distance_km']} km, Elevation Gain {route_metrics['elevation_gain_m']} m. Objective: {st.session_state.goals['target_metric']}."
                    try:
                        strat_res, strat_model = execute_multiprovider_generation(strat_prompt, preferred_provider=selected_provider)
                        st.markdown("---")
                        st.markdown(strat_res)
                        st.caption(f"Generated via: {strat_model}")
                    except Exception as e: st.error(f"Strategy generation failed: {e}")
