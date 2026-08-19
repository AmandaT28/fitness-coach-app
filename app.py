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

# --- SPEED-OPTIMIZED MULTI-PROVIDER AI ROUTER ---
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

    # Prioritize Google Flash first for speed if Auto is selected
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

import streamlit as st
from streamlit_local_storage import LocalStorage

# --- BROWSER LOCAL STORAGE AUTHENTICATION (MASTER AUTO-FILL & REMEMBER ME) ---
localS = LocalStorage()

# Check if keys are already saved in the user's browser local storage
stored_user = localS.getItem("athlete_profile_config")

if "user_credentials" not in st.session_state:
    if stored_user:
        st.session_state.user_credentials = stored_user
    else:
        st.session_state.user_credentials = None

# If no credentials found in browser storage, show setup screen
if not st.session_state.user_credentials:
    st.markdown("### 🚴‍♂️ Welcome to the AI Performance Coach")
    st.markdown("Enter your personal keys once. Your browser will securely remember them for future visits!")
    
    # MASTER CONFIG FOR YOU: Change these to your actual keys so you can click one button to log in!
    MY_MASTER_NAME = "Owner"
    MY_MASTER_ICU_KEY = "YOUR_ACTUAL_INTERVALS_API_KEY"
    MY_MASTER_ICU_ID = "YOUR_ACTUAL_ATHLETE_ID"
    MY_MASTER_GEMINI_KEY = "YOUR_ACTUAL_GEMINI_API_KEY"

    if st.button("👑 One-Click Login (Owner Auto-Fill)", type="primary", use_container_width=True):
        master_config = {
            "name": MY_MASTER_NAME,
            "icu_key": MY_MASTER_ICU_KEY,
            "icu_id": MY_MASTER_ICU_ID,
            "gemini_key": MY_MASTER_GEMINI_KEY
        }
        localS.setItem("athlete_profile_config", master_config)
        st.session_state.user_credentials = master_config
        st.success("Owner profile loaded!")
        st.rerun()

    st.markdown("---")
    st.markdown("#### ⚙️ Or Register / Connect New Profile (For Friends)")

    with st.form("browser_setup_form"):
        col_name = st.text_input("Your Name / Identifier")
        icu_key = st.text_input("Intervals.icu API Key", help="Found in Intervals.icu Settings -> Developer")
        icu_id = st.text_input("Intervals.icu Athlete ID", help="e.g., i608928")
        gemini_key = st.text_input("Google AI Studio (Gemini) API Key", type="password", help="Free from aistudio.google.com")
        
        if st.form_submit_button("Save & Launch Dashboard", use_container_width=True):
            if icu_key and icu_id and gemini_key:
                config_data = {
                    "name": col_name.strip() if col_name else "Athlete",
                    "icu_key": icu_key.strip(),
                    "icu_id": icu_id.strip(),
                    "gemini_key": gemini_key.strip()
                }
                localS.setItem("athlete_profile_config", config_data)
                st.session_state.user_credentials = config_data
                st.success("Configuration saved! Launching dashboard...")
                st.rerun()
            else:
                st.warning("Please fill in all required keys.")
    st.stop()

# Once loaded, extract keys:
current_creds = st.session_state.user_credentials
INTERVALS_API_KEY = current_creds["icu_key"]
ATHLETE_ID = current_creds["icu_id"]
GEMINI_KEY = current_creds["gemini_key"]

google_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None
USER_ID = current_creds["name"]

# --- INITIALIZE GEAR & LIMITATIONS IN SESSION STATE ---
if "athlete_gear" not in st.session_state:
    st.session_state.athlete_gear = "Cervélo Soloist (48), 160mm crankset, dual power meter, Wahoo Speedplay titanium pedals, GP5000 28mm tires."

if "athlete_limitations" not in st.session_state:
    st.session_state.athlete_limitations = "None reported. Focus on climbing efficiency and cadence consistency."
    
# --- INITIALIZE SESSION STATES ---
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

if "messages" not in st.session_state:
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
    
    auto_prompt = f"""
    [Autonomous Post-Workout Auto-Debrief]
    A new activity has synced via Garmin / Intervals.icu: {latest_act}
    Athlete Gear/Setup: {st.session_state.athlete_gear}
    Goal: {st.session_state.goals['event_name']} ({st.session_state.goals['target_metric']})
    Provide a concise, high-level autonomous performance debrief.
    """
    try:
        auto_res, _ = execute_multiprovider_generation(auto_prompt)
        st.session_state.messages.append({"role": "model", "content": f"🚨 **Autonomous Post-Ride Debrief ({act_name}):**\n\n{auto_res}"})
    except: pass

# --- SIDEBAR (Customizable Profile & Gear Settings) ---
with st.sidebar:
    st.markdown(f"👤 **{USER_ID}**")
    
    st.subheader("⚙️ Athlete & Equipment Profile")
    with st.form("gear_profile_form"):
        custom_gear = st.text_area("Bike Build & Gear Notes", value=st.session_state.athlete_gear, height=100)
        custom_limits = st.text_area("Physical Limitations / Notes", value=st.session_state.athlete_limitations, height=70)
        if st.form_submit_button("Update Profile", use_container_width=True):
            st.session_state.athlete_gear = custom_gear
            st.session_state.athlete_limitations = custom_limits
            st.success("Gear & profile updated!")

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
            supabase.table("profiles").update({"event_name": ev_name, "target_metric": t_metric}).eq("id", USER_ID).execute()
            st.success("Goals updated!")

    st.markdown("---")
    selected_provider = st.selectbox("⚡ AI Engine Model", ["⚡ Auto-Fallback Chain", "Google Gemini (Flash)", "OpenAI GPT-4o-mini", "Anthropic Claude"])

    st.markdown("---")
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = [{"role": "model", "content": "Chat history cleared. What topic or idea would you like to discuss next?"}]
        st.rerun()

    if st.button("Log Out", use_container_width=True):
        supabase.auth.sign_out()
        st.session_state.user = None
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
        trend_payload = f"""
        Perform a rigorous, detailed 90-day sports science trend analysis based on my wellness and training data:
        CTL (Fitness): {ctl}, ATL (Fatigue): {atl}, TSB (Form): {tsb}
        Athlete Gear/Setup: {st.session_state.athlete_gear}
        Physical Notes: {st.session_state.athlete_limitations}
        Recent Activities Summary: {activities_data[:25] if activities_data else 'None'}
        Target Event: {st.session_state.goals['event_name']} in {days_left} days.
        Objective: {st.session_state.goals['target_metric']}
        
        Provide a structured analysis covering fitness trajectory, consistency, climbing readiness, and next steps.
        """
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
        # 1. Immediately append user prompt to session state
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        # 2. Force Streamlit to rerun instantly so the user message appears on screen right away
        st.rerun()

# --- BACKGROUND AI PROCESSOR (Runs immediately after user message is rendered) ---
if st.session_state.messages and st.session_state.messages[-1]["role"] == "user":
    last_user_prompt = st.session_state.messages[-1]["content"]
    
    stack_summary = ", ".join([f"{s['name']} ({s['timing']})" for s in st.session_state.user_supplements])
    payload = f"""
    You are an elite cycling sports science coach acting with the persona: '{coach_persona}'.
    ATHLETE GEAR & SETUP: {st.session_state.athlete_gear}
    PHYSICAL LIMITATIONS / NOTES: {st.session_state.athlete_limitations}
    ACTIVE SUPPLEMENT STACK: {stack_summary}
    GOAL: {st.session_state.goals['event_name']} ({st.session_state.goals['target_metric']})
    METRICS: CTL={ctl}, ATL={atl}, TSB={tsb}.
    ACTIVITIES HISTORY: {activities_data[:15] if activities_data else 'None'}
    UPCOMING SCHEDULE: {planned_events[:15] if planned_events else 'None'}
    
    Provide concise, lightning-fast, and rigorous coaching insights matching your assigned persona.
    CRITICAL WORKOUT INSTRUCTION: If an indoor workout is requested, include a valid .zwo XML workout block enclosed inside a ```xml ... ``` code block.
    """ + last_user_prompt
    
    with st.spinner("Coach is thinking..."):
        try:
            resp, engine = execute_multiprovider_generation(payload, preferred_provider=selected_provider)
            full_resp = f"{resp}\n\n*(Engine: {engine})*"
            st.session_state.messages.append({"role": "model", "content": full_resp})
            st.rerun()
        except Exception as e:
            st.error(f"AI Generation Failed: {str(e)}")

# ================= TAB 3: TRAINING CALENDAR =================
with tab_calendar:
    st.markdown("### 📅 3-Week Training Calendar & 2-Week Planner")
    st.caption("Review completed past activities and scheduled upcoming workouts. Use the AI Planner to schedule new sessions for the next 2 weeks.")

    c_cal1, c_cal2 = st.columns([2, 1])
    with c_cal1:
        st.markdown("#### 🗓️ Your 21-Day Training Timeline")
        
        today_str = datetime.date.today().isoformat()
        
        if planned_events or activities_data:
            combined_timeline = []
            for ev in planned_events:
                dt = ev.get('start_date_local', '')[:10]
                combined_timeline.append({
                    "date": dt,
                    "name": ev.get('name', 'Planned Workout'),
                    "type": ev.get('type', 'Ride'),
                    "desc": ev.get('description', ''),
                    "status": "📅 Planned" if dt >= today_str else "✅ Completed / Past"
                })
            
            for act in activities_data:
                dt = act.get('start_date_local', '')[:10]
                dist_km = round((act.get('distance') or 0) / 1000, 1)
                dur_min = int((act.get('moving_time') or 0) / 60)
                combined_timeline.append({
                    "date": dt,
                    "name": act.get('name', 'Recorded Activity'),
                    "type": act.get('type', 'Ride'),
                    "desc": f"Distance: {dist_km} km | Time: {dur_min} mins | Avg Power: {act.get('average_watts', 'N/A')}W",
                    "status": "🏆 Recorded Activity"
                })
            
            seen = set()
            unique_timeline = []
            for item in sorted(combined_timeline, key=lambda x: x['date'], reverse=True):
                identifier = (item['date'], item['name'])
                if identifier not in seen:
                    seen.add(identifier)
                    unique_timeline.append(item)

            for item in unique_timeline[:15]:
                card_style = "calendarCard" if "Planned" in item['status'] else "calendarCardPast"
                st.markdown(f"""
                <div class="{card_style}">
                    <div style="display: flex; justify-content: space-between; font-weight: bold; font-size: 0.95rem;">
                        <span>{item['date']} — {item['name']}</span>
                        <span style="font-size: 0.8rem; color: #555;">{item['status']}</span>
                    </div>
                    <div style="font-size: 0.85rem; color: #444; margin-top: 4px;">{item['desc']}</div>
                </div>
                """, unsafe_allow_html=True)
        else:
            st.info("No timeline events found.")

        st.markdown("---")
        st.markdown("#### 🤖 AI 2-Week Planner & Calendar Integrator")
        
        plan_focus = st.selectbox("Planning Focus for Next 2 Weeks:", [
            "Threshold Power & Sweet Spot Progression", 
            "Climbing Endurance & Resistance Blocks", 
            "Recovery & Taper Structure", 
            "Custom Indoor/Outdoor Balance"
        ])
        
        if st.button("🤖 Generate 2-Week Training Plan & Push to Coach", type="primary"):
            st.session_state.messages.append({
                "role": "user", 
                "content": f"Please design and plan my training schedule for the next 2 weeks with a focus on '{plan_focus}'. Give me specific workout names, durations, and power targets so I can add them to my Intervals.icu calendar."
            })
            st.session_state.messages.append({
                "role": "model", 
                "content": f"I've generated your 2-week training block focused on '{plan_focus}'. Let's review the schedule!"
            })
            st.success("Plan generated! Head to the **AI Coach & Sparring** tab.")
            st.rerun()

    with c_cal2:
        st.markdown("#### 🚨 Missed Workout Protocol")
        st.info(
            "**Human Coach Rulebook for Missed Sessions:**\n\n"
            "1. **Never double up** high-intensity days to 'make up' for lost time.\n"
            "2. If you missed an **easy/recovery ride**, drop it and move on.\n"
            "3. If you missed a **key interval/climbing session**, evaluate your Form (TSB). If TSB > -10, shift it to today. If TSB < -20, skip it entirely to prevent overtraining."
        )
        if st.button("🤖 Ask Coach About a Missed Workout", use_container_width=True):
            st.session_state.messages.append({
                "role": "user", 
                "content": "I missed my scheduled workout yesterday. Given my current TSB and upcoming weekend group ride, what should I do?"
            })
            st.session_state.messages.append({
                "role": "model", 
                "content": "Let's figure out the best move for your missed session. Check your current TSB—is it holding steady or deeply negative?"
            })
            st.success("Context loaded! Head to the **AI Coach & Sparring** tab.")
            st.rerun()

# ================= TAB 4: ACTIVITY INSPECTOR =================
with tab_history:
    st.markdown("### 🔍 Past Activity Inspector & Deep Debrief")
    st.caption("Select any past activity from your history to run an AI-powered performance debrief with clear activity and date identification.")

    if activities_data:
        act_options = {}
        for act in activities_data:
            name = act.get("name", "Unnamed Activity")
            date = act.get("start_date_local", "")[:10]
            raw_dist = act.get("distance")
            dist = round(((raw_dist if raw_dist is not None else 0) / 1000), 1)
            raw_time = act.get("moving_time")
            dur_min = int((raw_time if raw_time is not None else 0) / 60)
            label = f"{date} — {name} ({dist} km, {dur_min} mins)"
            act_options[label] = act

        selected_label = st.selectbox("Choose a past activity to analyze:", list(act_options.keys()))
        selected_act = act_options[selected_label]

        act_display_name = selected_act.get('name', 'Workout')
        act_display_date = selected_act.get('start_date_local', '')[:10]
        st.markdown(f"""
        <div style="background-color: #eaf2f8; border: 1px solid #a9cce3; padding: 12px 16px; border-radius: 10px; margin-bottom: 16px;">
            <div style="font-size: 0.8rem; font-weight: bold; color: #2471a3; text-transform: uppercase;">Selected Activity Inspection</div>
            <div style="font-size: 1.2rem; font-weight: bold; color: #1b4f72; margin-top: 2px;">{act_display_name}</div>
            <div style="font-size: 0.9rem; color: #515a5a; margin-top: 2px;">📅 Date: {act_display_date}</div>
        </div>
        """, unsafe_allow_html=True)

        col_info1, col_info2, col_info3 = st.columns(3)
        sel_dist = selected_act.get("distance")
        safe_dist = round(((sel_dist if sel_dist is not None else 0) / 1000), 2)
        col_info1.metric("Distance", f"{safe_dist} km")
        
        sel_time = selected_act.get("moving_time")
        safe_time = int((sel_time if sel_time is not None else 0) / 60)
        col_info2.metric("Moving Time", f"{safe_time} mins")
        
        avg_watts = selected_act.get("average_watts")
        safe_watts = f"{avg_watts} W" if avg_watts is not None else "N/A"
        col_info3.metric("Average Power", safe_watts)

        if st.button("🤖 Run Deep AI Activity Debrief", type="primary", use_container_width=True):
            with st.spinner("Analyzing activity metrics, power output, and pacing..."):
                debrief_prompt = f"""
                You are an elite cycling coach. Perform a deep performance debrief for this specific activity:
                Activity Name: {act_display_name}
                Activity Date: {act_display_date}
                Activity Details: {selected_act}
                Athlete Gear/Setup: {st.session_state.athlete_gear}
                Target Event Goal: {st.session_state.goals['event_name']} ({st.session_state.goals['target_metric']})
                
                Evaluate: 1) Intensity distribution, 2) Pacing efficiency, 3) Strengths, and 4) Areas for improvement.
                """
                try:
                    debrief_res, debrief_engine = execute_multiprovider_generation(debrief_prompt, preferred_provider=selected_provider)
                    st.session_state.selected_activity_analysis = f"### 🚴‍♂️ Performance Debrief: {act_display_name}\n📅 **Date:** {act_display_date}\n\n{debrief_res}\n\n*(Engine: {debrief_engine})*"
                except Exception as e:
                    st.error(f"Analysis failed: {e}")

        if st.session_state.selected_activity_analysis:
            st.markdown("---")
            st.markdown(st.session_state.selected_activity_analysis)
            
            if st.button("💬 Clarify This Debrief with Coach", key="discuss_debrief_btn"):
                act_dist = round((selected_act.get('distance') or 0) / 1000, 2)
                act_time = int((selected_act.get('moving_time') or 0) / 60)
                act_watts = selected_act.get('average_watts', 'N/A')
                
                st.session_state.messages.append({
                    "role": "user", 
                    "content": f"I want clarifications regarding my activity '{act_display_name}' on {act_display_date} ({act_dist} km, {act_time} mins, {act_watts}W avg power)."
                })
                st.session_state.messages.append({
                    "role": "model", 
                    "content": f"I have the details for '{act_display_name}' ({act_display_date}) right here. What specific section would you like to unpack?"
                })
                st.success("Context loaded! Head to the **AI Coach & Sparring** tab.")
                st.rerun()
    else:
        st.info("No activities found in your Intervals.icu sync history.")

# ================= TAB 5: RECOVERY & SUPPLEMENTS =================
with tab_recovery:
    st.markdown("### 💊 Dynamic Recovery & Supplement Protocol")
    st.caption("Manage your personal supplement stack. The AI coach dynamically tracks these to optimize your recovery and training adaptation.")

    with st.form("add_supplement_form", clear_on_submit=True):
        st.markdown("#### Add New Supplement")
        col_s1, col_s2, col_s3 = st.columns([1, 1, 2])
        new_name = col_s1.text_input("Supplement Name")
        new_timing = col_s2.text_input("Target Timing (e.g., Pre-bed)")
        new_notes = col_s3.text_input("Purpose / Notes")
        
        if st.form_submit_button("➕ Add to Stack", use_container_width=True):
            if new_name:
                st.session_state.user_supplements.append({
                    "name": new_name.strip(), 
                    "timing": new_timing.strip() if new_timing else "As needed", 
                    "notes": new_notes.strip() if new_notes else "Custom supplement"
                })
                st.success(f"Added {new_name} to your stack!")
                st.rerun()
            else:
                st.warning("Please enter a supplement name.")

    st.markdown("---")
    st.markdown("#### 📋 Current Active Supplement Stack")

    if st.session_state.user_supplements:
        df_supps = pd.DataFrame(st.session_state.user_supplements)
        st.dataframe(df_supps, use_container_width=True, hide_index=True)

        supp_names = [s["name"] for s in st.session_state.user_supplements]
        to_remove = st.selectbox("Select a supplement to remove (optional):", ["-- Select --"] + supp_names)
        if to_remove != "-- Select --":
            if st.button("🗑️ Remove Selected Supplement"):
                st.session_state.user_supplements = [s for s in st.session_state.user_supplements if s["name"] != to_remove]
                st.success(f"Removed {to_remove} from your stack.")
                st.rerun()
    else:
        st.info("Your supplement stack is currently empty. Add one above!")

    st.markdown("---")
    
    if st.button("💬 Discuss Updated Supplement Stack With Coach", key="discuss_supplements_btn"):
        stack_desc = ", ".join([f"{s['name']} ({s['timing']})" for s in st.session_state.user_supplements])
        st.session_state.messages.append({
            "role": "user", 
            "content": f"Let's review my active supplement stack: {stack_desc}. How should I coordinate these around my training schedule?"
        })
        st.session_state.messages.append({
            "role": "model", 
            "content": "I've loaded your updated supplement stack into our chat. Let's optimize your recovery!"
        })
        st.success("Context loaded with your live stack! Head to the **AI Coach & Sparring** tab.")
        st.rerun()

# ================= TAB 6: ROUTE STRATEGIST =================
with tab_strat:
    st.markdown("### 🗺️ Route Pacing & Climbing Strategist")
    uploaded_gpx = st.file_uploader("Upload GPX Route File (.gpx)", type=["gpx"])
    
    def parse_gpx(file_bytes):
        try:
            xml_content = file_bytes.decode('utf-8', errors='ignore')
            root = ET.fromstring(xml_content)
            latlons, elevation_list = [], []
            for elem in root.iter():
                tag = elem.tag.split('}')[-1].lower()
                if tag in ['trkpt', 'rtept']:
                    lat_str = elem.attrib.get('lat') or elem.attrib.get('latitude')
                    lon_str = elem.attrib.get('lon') or elem.attrib.get('longitude')
                    if lat_str and lon_str:
                        latlons.append((float(lat_str), float(lon_str)))
                        ele_val = elevation_list[-1] if elevation_list else 0.0
                        for child in elem:
                            if child.tag.split('}')[-1].lower() in ['ele', 'elevation', 'alt']:
                                try: ele_val = float(child.text)
                                except: pass
                                break
                        elevation_list.append(ele_val)
            if not latlons: return None
            total_ele_gain = sum(max(0, elevation_list[i] - elevation_list[i-1]) for i in range(1, len(elevation_list)))
            total_dist_km = sum(6371.0 * (2 * math.asin(math.sqrt(math.sin(math.radians(latlons[i][0]-latlons[i-1][0])/2)**2 + math.cos(math.radians(latlons[i-1][0])) * math.cos(math.radians(latlons[i][0])) * math.sin(math.radians(latlons[i][1]-latlons[i-1][1])/2)**2))) for i in range(1, len(latlons)))
            return {"distance_km": round(max(total_dist_km, 0.1), 2), "elevation_gain_m": round(total_ele_gain, 1), "max_elevation": round(max(elevation_list), 1) if elevation_list else 0}
        except Exception: return None

    if uploaded_gpx:
        route_metrics = parse_gpx(uploaded_gpx.read())
        if route_metrics:
            c1, c2, c3 = st.columns(3)
            c1.metric("Distance", f"{route_metrics['distance_km']} km")
            c2.metric("Elevation Gain", f"{route_metrics['elevation_gain_m']} m")
            c3.metric("Max Elevation", f"{route_metrics['max_elevation']} m")
            
            if st.button("🤖 Generate Climbing Strategy", type="primary"):
                with st.spinner("Analyzing route profile..."):
                    strat_prompt = f"""
                    Analyze this route profile: Distance {route_metrics['distance_km']} km, Elevation Gain {route_metrics['elevation_gain_m']} m.
                    Athlete Gear/Setup: {st.session_state.athlete_gear}
                    Objective: {st.session_state.goals['target_metric']}
                    Provide precise power pacing targets and climbing strategies.
                    """
                    try:
                        strat_res, strat_model = execute_multiprovider_generation(strat_prompt, preferred_provider=selected_provider)
                        st.markdown("---")
                        st.markdown(strat_res)
                        st.caption(f"Generated via: {strat_model}")
                    except Exception as e:
                        st.error(f"Strategy generation failed: {e}")
