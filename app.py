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
    .stCard {
        background-color: #ffffff;
        border: 1px solid rgba(128, 128, 128, 0.15);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    .calendarCard {
        background-color: #f8f9fa;
        border-left: 4px solid #2e86c1;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 10px;
    }
    .calendarCardPast {
        background-color: #f1f2f6;
        border-left: 4px solid #7f8c8d;
        padding: 12px 16px;
        border-radius: 8px;
        margin-bottom: 10px;
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

# --- SPEED-OPTIMIZED MULTI-PROVIDER AI ROUTER (Exact Models Preserved) ---
def execute_multiprovider_generation(prompt, preferred_provider="⚡ Auto-Fallback Chain"):
    def call_google():
        models = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-3.7-pro-preview"]
        for m in models:
            try:
                return google_client.models.generate_content(model=m, contents=prompt).text, f"Google {m}"
            except: 
                continue
        raise Exception("Google failed")
        
    def call_openai():
        res = openai_client.chat.completions.create(model="gpt-4o-mini", messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content, "OpenAI GPT-4o-mini"

    def call_anthropic():
        res = anthropic_client.messages.create(model="claude-3-5-sonnet-20241022", max_tokens=1500, messages=[{"role": "user", "content": prompt}])
        return res.content[0].text, "Anthropic Claude"

    if preferred_provider == "⚡ Auto-Fallback Chain":
        active_chain = [call_google, call_openai, call_anthropic]
    elif "Google" in preferred_provider:
        active_chain = [call_google, call_openai]
    elif "OpenAI" in preferred_provider:
        active_chain = [call_openai, call_google]
    else:
        active_chain = [call_anthropic, call_google]

    for action in active_chain:
        try: return action()
        except: continue
    raise Exception("All AI providers failed.")

localS = LocalStorage()

# --- URL TOKEN HANDLER FOR MOBILE / CROSS-DEVICE GUESTS ---
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

# Initialize session state flags
if "user_credentials" not in st.session_state:
    st.session_state.user_credentials = None

if "user" not in st.session_state:
    st.session_state.user = None

# Check browser local storage for guest credentials
stored_guest = localS.getItem("athlete_profile_config")
if not st.session_state.user and stored_guest and not st.session_state.user_credentials:
    st.session_state.user_credentials = stored_guest

# Show Dual-Pathway Login Portal if neither owner nor guest is logged in
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
            icu_key = st.text_input("Intervals.icu API Key", help="Found in Intervals.icu Settings -> Developer")
            icu_id = st.text_input("Intervals.icu Athlete ID", help="e.g., i123456")
            gemini_key = st.text_input("Google AI Studio (Gemini) API Key", type="password", help="Free from aistudio.google.com")
            
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

# --- RESOLVE ACTIVE VARIABLES & CLOUD SYNCED NOTES ---
if st.session_state.user:
    USER_ID = st.session_state.user.id
    profile_res = supabase.table("profiles").select("*").eq("id", USER_ID).execute()
    user_profile = profile_res.data[0] if profile_res.data else {}
    
    INTERVALS_API_KEY = user_profile.get("intervals_api_key")
    ATHLETE_ID = user_profile.get("intervals_athlete_id")
    GEMINI_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
    display_name = st.session_state.user.email

    if "athlete_gear" not in st.session_state:
        st.session_state.athlete_gear = user_profile.get("gear_notes") or ""
    if "athlete_limitations" not in st.session_state:
        st.session_state.athlete_limitations = user_profile.get("limitations_notes") or ""
        
    if "goals" not in st.session_state or not isinstance(st.session_state.goals, dict):
        st.session_state.goals = {}
    st.session_state.goals["event_name"] = user_profile.get("event_name") or "Bintan Round Island"
    st.session_state.goals["target_metric"] = user_profile.get("target_metric") or "Survive steep climbs on group rides & improve threshold power"

else:
    current_creds = st.session_state.user_credentials
    INTERVALS_API_KEY = current_creds["icu_key"]
    ATHLETE_ID = current_creds["icu_id"]
    GEMINI_KEY = current_creds["gemini_key"]
    display_name = current_creds["name"]

    if "athlete_gear" not in st.session_state:
        st.session_state.athlete_gear = current_creds.get("gear", "")
    if "athlete_limitations" not in st.session_state:
        st.session_state.athlete_limitations = current_creds.get("limitations", "")

    if "goals" not in st.session_state or not isinstance(st.session_state.goals, dict):
        st.session_state.goals = {}
    if "event_name" not in st.session_state.goals:
        st.session_state.goals["event_name"] = "Bintan Round Island"
    if "target_metric" not in st.session_state.goals:
        st.session_state.goals["target_metric"] = "Survive steep climbs on group rides & improve threshold power"

google_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None

# --- INITIALIZE MESSAGES STATE EARLY ---
if "messages" not in st.session_state:
    st.session_state.messages = []
    
# --- ONE-TIME INITIAL ONBOARDING CHECK ---
if st.session_state.user:
    is_onboarded = user_profile.get("onboarding_done", False)
else:
    is_onboarded = current_creds.get("onboarding_done", False)

if not is_onboarded:
    st.markdown("### 🚴‍♂️ Coach's Initial Intake & Onboarding")
    st.markdown("Welcome! Before we dive into your Intervals.icu telemetry and training logs, let's have a quick introductory chat so your AI coach truly understands your background, constraints, and current goals.")
    
    if len(st.session_state.messages) == 0:
        st.session_state.messages = [{
            "role": "model", 
            "content": f"Hey {display_name}! Welcome to your Elite Coaching Suite. I'm your autonomous performance coach. To kick things off, tell me a bit about your current riding routine, any specific physical limitations or past injuries I should keep in mind, and what your main focus is over the next few months."
        }]
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    if intake_reply := st.chat_input("Tell your coach about yourself..."):
        st.session_state.messages.append({"role": "user", "content": intake_reply})
        
        intake_prompt = f"""
        [Coach Onboarding Intake]
        The athlete just shared their background and goals: '{intake_reply}'
        Acknowledge their background professionally as an elite cycling coach, summarize what you noted, and welcome them into the Elite Coaching Suite.
        """
        with st.spinner("Coach is reviewing your intake..."):
            try:
                global google_client
                if not google_client and GEMINI_KEY:
                    google_client = genai.Client(api_key=GEMINI_KEY)
                
                resp, _ = execute_multiprovider_generation(intake_prompt)
                st.session_state.messages.append({"role": "model", "content": resp})
            except Exception as e:
                st.session_state.messages.append({
                    "role": "model", 
                    "content": "Welcome aboard! I've noted down your details and we're ready to start training."
                })
            
            if st.session_state.user:
                supabase.table("profiles").update({"onboarding_done": True}).eq("id", USER_ID).execute()
            else:
                current_creds["onboarding_done"] = True
                localS.setItem("athlete_profile_config", current_creds)
            
            st.rerun()
    st.stop()  # Halts the rest of the app until they finish this one-time intro!
    
# --- INITIALIZE REMAINING SESSION STATES ---
if "user_supplements" not in st.session_state:
    st.session_state.user_supplements = [
        {"name": "Creatine", "timing": "Post-Workout", "notes": "Cellular ATP replenishment & sprint power"},
        {"name": "Protein", "timing": "Post-Workout (<45m)", "notes": "Muscle repair & glycogen resynthesis"},
        {"name": "Turmeric", "timing": "Morning with Fats", "notes": "Systemic inflammation control"},
        {"name": "Fish Oil", "timing": "Morning & Evening", "notes": "Cardiovascular & nocturnal recovery"},
        {"name": "NMN", "timing": "Morning (Fasted)", "notes": "Cellular NAD+ & mitochondrial support"},
        {"name": "Collagen", "timing": "30m pre-loading", "notes": "Tendon/ligament fortification with Vitamin C"},
        {"name": "Magnesium", "timing": "30m before bed", "notes": "Nervous system relaxation & slow-wave sleep"}
    ]

if not st.session_state.messages:
    st.session_state.messages = [{"role": "model", "content": "Hello! I am your autonomous AI Performance Coach. I'm actively monitoring your Intervals.icu & Garmin sync pipeline, gear profile, and training calendar. How can I help you train today?"}]

if "selected_activity_analysis" not in st.session_state:
    st.session_state.selected_activity_analysis = None

if "auto_debriefed_id" not in st.session_state:
    st.session_state.auto_debriefed_id = None

# --- FETCH DATA (3-Week Window) ---
@st.cache_data(ttl=300, show_spinner=False)
def fetch_intervals_data(aid, key):
    try:
        today = datetime.date.today()
        start_90 = (today - datetime.timedelta(days=90)).isoformat()
        end_14 = (today + datetime.timedelta(days=14)).isoformat()
        start_7 = (today - datetime.timedelta(days=7)).isoformat()
        
        w_res = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/wellness?oldest={start_90}&newest={end_14}", auth=("API_KEY", key), timeout=5)
        a_res = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/activities?oldest={start_7}&newest={end_14}", auth=("API_KEY", key), timeout=5)
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

race_date = datetime.date(2026, 10, 24)
days_left = (race_date - datetime.date.today()).days

# --- AUTOMATED POST-WORKOUT CHECKER ---
if activities_data and st.session_state.auto_debriefed_id != activities_data[0].get('id'):
    latest_act = activities_data[0]
    act_id = latest_act.get('id')
    act_name = latest_act.get('name', 'Latest Ride')
    st.session_state.auto_debriefed_id = act_id
    
    auto_prompt = (
        "[Autonomous Post-Workout Auto-Debrief]\n"
        f"A new activity has synced via Garmin / Intervals.icu: {latest_act}\n"
        f"Athlete Gear/Setup: {st.session_state.athlete_gear}\n"
        f"Goal: {st.session_state.goals['event_name']} ({st.session_state.goals['target_metric']})\n"
        "Provide a concise, high-level autonomous performance debrief."
    )
    try:
        auto_res, _ = execute_multiprovider_generation(auto_prompt)
        st.session_state.messages.append({"role": "model", "content": f"🚨 **Autonomous Post-Ride Debrief ({act_name}):**\n\n{auto_res}"})
    except: pass

# --- SIDEBAR (Customizable Profile, Gear & Mobile Link Exporter) ---
with st.sidebar:
    st.markdown(f"👤 **{display_name}**")
            
    st.subheader("⚙️ Athlete & Equipment Profile")
    with st.form("gear_profile_form"):
        custom_gear = st.text_area("Bike Build & Gear Notes", value=st.session_state.athlete_gear, height=100)
        custom_limits = st.text_area("Physical Limitations / Notes", value=st.session_state.athlete_limitations, height=70)
        
        if st.form_submit_button("Save Profile", use_container_width=True):
            st.session_state.athlete_gear = custom_gear
            st.session_state.athlete_limitations = custom_limits
            
            if st.session_state.user:
                try:
                    supabase.table("profiles").update({
                        "gear_notes": custom_gear,
                        "limitations_notes": custom_limits
                    }).eq("id", USER_ID).execute()
                    st.success("Synced to Supabase cloud!")
                except Exception as e:
                    st.error(f"Sync failed: {e}")
            else:
                current_creds["gear"] = custom_gear
                current_creds["limitations"] = custom_limits
                localS.setItem("athlete_profile_config", current_creds)
                st.success("Saved to browser memory!")

    # --- MOBILE LINK EXPORTER FOR FRIENDS ---
    if not st.session_state.user:
        st.markdown("---")
        with st.expander("📱 Transfer to Mobile / New Device"):
            st.caption("Copy this private link and open it on your phone to log in instantly without re-typing your keys:")
            token_str = base64.urlsafe_b64encode(json.dumps(current_creds).encode("utf-8")).decode("utf-8")
            base_url = st.context.headers.get("Host", "your-app.streamlit.app")
            mobile_link = f"https://{base_url}/?token={token_str}"
            st.code(mobile_link, language="text")

    st.markdown("---")
    st.subheader("🎭 Coaching Persona")
    coach_persona = st.selectbox("Select AI Style", ["Collaborative Peer (Balanced & Brainstorming)", "Sports Scientist (Data & Periodization Focus)", "Drill Sergeant (Strict & Direct Accountability)"])

    st.markdown("---")
    st.subheader("🎯 Target Race & Goals")
    with st.form("goal_feedback_form"):
        ev_name = st.text_input("Target Race", value=st.session_state.goals["event_name"])
        t_metric = st.text_input("Key Objective", value=st.session_state.goals["target_metric"])
        if st.form_submit_button("Update Goals", use_container_width=True):
            st.session_state.goals["event_name"] = ev_name
            st.session_state.goals["target_metric"] = t_metric
            if st.session_state.user:
                supabase.table("profiles").update({"event_name": ev_name, "target_metric": t_metric}).eq("id", USER_ID).execute()
            st.success("Goals updated!")

    st.markdown("---")
    selected_provider = st.selectbox("⚡ AI Engine Model", ["⚡ Auto-Fallback Chain", "Google Gemini (Flash)", "OpenAI GPT-4o-mini", "Anthropic Claude"])

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

# --- NAVIGATION SUITE ---
tab_dash, tab_coach, tab_calendar, tab_history, tab_recovery, tab_strat = st.tabs([
    "📊 Command Center", "🤖 AI Coach & Sparring", "📅 Training Calendar", "🔍 Activity Inspector", "💊 Recovery & Supplements", "🗺️ Route Strategist"
])

# ================= TAB 1: COMMAND CENTER =================
with tab_dash:
    st.markdown(f"### ☀️ Autonomous AI Performance Coach • Command Center")
    
    st.markdown(f"""
    <div style="background-color: #fef9e7; border: 1px solid #f9e79f; padding: 16px; border-radius: 14px; margin-bottom: 16px;">
        <span style="font-size: 0.75rem; font-weight: bold; color: #d68910; background: #fcf3cf; padding: 2px 6px; border-radius: 4px;">📊 INTERVALS.ICU & GARMIN SYNC ACTIVE</span>
        <div style="font-weight: bold; font-size: 1.1rem; margin-top: 4px;">Target Race: {st.session_state.goals['event_name']} ({days_left} days left)</div>
        <div style="color: #666; font-size: 0.85rem; margin-top: 4px;">Objective: {st.session_state.goals['target_metric']}</div>
        <hr style="margin: 10px 0; border-top: 1px solid #fce881;">
        <div style="font-size: 0.9rem; font-weight: 500; color: #333;">
            {'🟢 <strong>Readiness High:</strong> Telemetry verified via Garmin/Intervals.icu. Form (TSB) is optimal for hard efforts.' if tsb >= -15 else '🟡 <strong>Fatigue Warning:</strong> Telemetry shows elevated stress. Prioritize sleep and recovery pacing.'}
        </div>
    </div>
    """, unsafe_allow_html=True)

    c_met1, c_met2, c_met3, c_met4 = st.columns(4)
    with c_met1: st.metric("Fitness (CTL)", round(ctl, 1))
    with c_met2: st.metric("Fatigue (ATL)", round(atl, 1))
    with c_met3: st.metric("Form (TSB)", round(tsb, 1))
    with c_met4: st.metric("Sleep Score", f"{sleep_score}/100" if sleep_score > 0 else "N/A")

    st.markdown("---")
    st.markdown("#### 📈 Deep 90-Day Training Load & Progression Trend Analysis")
    st.caption("Click below to synthesize your 90-day performance trends on demand.")

    if "cached_trend_analysis" not in st.session_state:
        st.session_state.cached_trend_analysis = None

    if st.button("🚀 Run 90-Day Trend Synthesis", type="primary"):
        trend_payload = (
            "Perform a rigorous, detailed 90-day sports science trend analysis based on my wellness and training data:\n"
            f"CTL (Fitness): {ctl}, ATL (Fatigue): {atl}, TSB (Form): {tsb}\n"
            f"Athlete Gear/Setup: {st.session_state.athlete_gear}\n"
            f"Physical Notes: {st.session_state.athlete_limitations}\n"
            f"Recent Activities Summary: {activities_data[:25] if activities_data else 'None'}\n"
            f"Target Event: {st.session_state.goals['event_name']} in {days_left} days.\n"
            f"Objective: {st.session_state.goals['target_metric']}\n\n"
            "Provide a structured analysis covering fitness trajectory, consistency, climbing readiness, and next steps."
        )
        with st.spinner("Synthesizing 90-day performance trends..."):
            try:
                trend_res, _ = execute_multiprovider_generation(trend_payload, preferred_provider=selected_provider)
                st.session_state.cached_trend_analysis = trend_res
            except Exception as e:
                st.error(f"Trend synthesis failed: {e}")

    if st.session_state.cached_trend_analysis:
        st.markdown(st.session_state.cached_trend_analysis)
        if st.button("💬 Discuss These Trends With Coach", key="discuss_trends_btn"):
            st.session_state.messages.append({
                "role": "user", 
                "content": f"Let's review my recent 90-day training trends (Fitness CTL: {round(ctl, 1)}, Fatigue ATL: {round(atl, 1)}, Form TSB: {round(tsb, 1)}). Based on my goal of '{st.session_state.goals['target_metric']}', am I progressing correctly?"
            })
            st.session_state.messages.append({
                "role": "model", 
                "content": "I've pulled up your 90-day trends. What specific part of your progression would you like to tweak?"
            })
            st.success("Context loaded! Head to the **AI Coach & Sparring** tab.")
            st.rerun()
            
# ================= TAB 2: AI COACH & SPARRING CHAT =================
with tab_coach:
    st.markdown("### 🤖 AI Coach & Collaborative Sparring Partner")
    st.caption(f"Active Persona: **{coach_persona}** | Plan your next 2 weeks, add workouts, or request MyWhoosh workouts.")

    chat_container = st.container()
    with chat_container:
        for idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg["role"]):
                clean_content = re.sub(r"```xml\s*<\?xml.*?>.*?</\s*workout_file\s*>\s*```", "", msg["content"], flags=re.DOTALL)
                clean_content = re.sub(r"```\s*<workout_file>.*?</\s*workout_file>\s*```", "", clean_content, flags=re.DOTALL)
                st.markdown(clean_content.strip())
                
                if msg["role"] == "model":
                    match = re.search(r"```xml\s*(<\?xml.*?>.*?<\s*/\s*workout_file\s*>|<workout_file>.*?</\s*workout_file>)\s*```", msg["content"], re.DOTALL)
                    if not match:
                        match = re.search(r"```\s*(<workout_file>.*?</\s*workout_file>)\s*```", msg["content"], re.DOTALL)
                    
                    if match:
                        zwo_data = match.group(1).strip()
                        st.download_button(
                            label="📥 Download MyWhoosh Workout File (.zwo)",
                            data=zwo_data,
                            file_name=f"AI_Coach_Workout_{idx}.zwo",
                            mime="application/xml",
                            key=f"download_zwo_{idx}"
                        )

    if prompt := st.chat_input("Ask your coach to plan training or bounce an idea..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.rerun()

# --- BACKGROUND AI PROCESSOR ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last_user_prompt = st.session_state.messages[-1]["content"]
    
    stack_summary = ", ".join([f"{s['name']} ({s['timing']})" for s in st.session_state.user_supplements])
    payload = (
        f"You are an elite cycling sports science coach acting with the persona: '{coach_persona}'.\n"
        f"ATHLETE GEAR & SETUP: {st.session_state.athlete_gear}\n"
        f"PHYSICAL LIMITATIONS / NOTES: {st.session_state.athlete_limitations}\n"
        f"ACTIVE SUPPLEMENT STACK: {stack_summary}\n"
        f"GOAL: {st.session_state.goals['event_name']} ({st.session_state.goals['target_metric']})\n"
        f"METRICS: CTL={ctl}, ATL={atl}, TSB={tsb}.\n"
        f"ACTIVITIES HISTORY: {activities_data[:15] if activities_data else 'None'}\n"
        f"UPCOMING SCHEDULE: {planned_events[:15] if planned_events else 'None'}\n\n"
        "Provide concise, lightning-fast, and rigorous coaching insights matching your assigned persona.\n"
        "CRITICAL WORKOUT INSTRUCTION: If an indoor workout is requested, include a valid .zwo XML workout block enclosed inside a ```xml ...
