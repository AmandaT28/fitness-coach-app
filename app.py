import datetime
import os
import concurrent.futures
import xml.etree.ElementTree as ET
import math
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

# Load environment variables safely
try:
    load_dotenv()
except ImportError:
    pass

# Grab keys from Streamlit Secrets or environment
SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase credentials are missing! Add SUPABASE_URL and SUPABASE_KEY to Secrets.")
    st.stop()

# Initialize Database & Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
google_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None
openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None

# App UI Configuration & Mobile-Responsive Custom CSS Styling
st.set_page_config(page_title="AI Sports Science Coach • Elite Suite", page_icon="🚴‍♂️", layout="wide")

st.markdown("""
<style>
    /* Global Card & Container Styling */
    .stCard {
        background-color: var(--background-secondary-color, #ffffff);
        border: 1px solid rgba(128, 128, 128, 0.15);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
    }
    
    /* Metric Card Polish */
    div[data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.03);
        border: 1px solid rgba(128, 128, 128, 0.1);
        padding: 14px 18px;
        border-radius: 10px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.01);
    }

    /* Button Polish */
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    
    /* Tab Container Spacing */
    .stTabs [data-baseweb="tab-list"] {
        gap: 8px;
    }
    .stTabs [data-baseweb="tab"] {
        border-radius: 8px 8px 0px 0px;
        padding: 10px 16px;
        font-weight: 500;
    }

    /* Mobile Responsive Adjustments */
    @media (max-width: 768px) {
        .main .block-container {
            padding: 1rem 0.75rem;
        }
        h1 {
            font-size: 1.75rem !important;
        }
    }
</style>
""", unsafe_allow_html=True)

st.title("🚴‍♂️🏃‍♂️ AI Sports Science Coach")
st.caption("Multi-Sport Elite Command Center • Intervals.icu & Multi-LLM Integrated")

# --- MULTI-PROVIDER CROSS-PROVIDER FALLBACK ROUTER (Gemini 3.5+ & Fallbacks) ---
def execute_multiprovider_generation(prompt, preferred_provider="⚡ Auto-Fallback Chain", is_stream=False):
    def call_openai(stream=False):
        if not openai_client: raise Exception("OpenAI API key missing")
        if stream:
            return openai_client.chat.completions.create(
                model="gpt-4o", messages=[{"role": "user", "content": prompt}], stream=True
            ), "OpenAI GPT-4o"
        else:
            res = openai_client.chat.completions.create(
                model="gpt-4o", messages=[{"role": "user", "content": prompt}]
            )
            return res.choices[0].message.content, "OpenAI GPT-4o"

    def call_anthropic(stream=False):
        if not anthropic_client: raise Exception("Anthropic API key missing")
        if stream:
            return anthropic_client.messages.stream(
                model="claude-3-5-sonnet-20241022", max_tokens=2048, messages=[{"role": "user", "content": prompt}]
            ), "Anthropic Claude"
        else:
            res = anthropic_client.messages.create(
                model="claude-3-5-sonnet-20241022", max_tokens=2048, messages=[{"role": "user", "content": prompt}]
            )
            return res.content[0].text, "Anthropic Claude"

    def call_google(stream=False):
        if not google_client: raise Exception("Google API key missing")
        # Modern Gemini 3 & 3.5/3.7 models with safe fallbacks
        models = ["gemini-3.7-flash", "gemini-3.5-flash", "gemini-2.5-flash"]
        last_err = None
        for m in models:
            try:
                if stream:
                    return google_client.models.generate_content_stream(model=m, contents=prompt), f"Google {m}"
                else:
                    return google_client.models.generate_content(model=m, contents=prompt).text, f"Google {m}"
            except Exception as e:
                last_err = e
                continue
        raise last_err

    active_stack = []
    if openai_client: active_stack.append(("OpenAI", lambda: call_openai(is_stream)))
    if anthropic_client: active_stack.append(("Anthropic", lambda: call_anthropic(is_stream)))
    if google_client: active_stack.append(("Google", lambda: call_google(is_stream)))

    if not active_stack:
        raise Exception("No AI provider API keys are configured in Streamlit Secrets!")

    if preferred_provider == "OpenAI GPT" and openai_client:
        active_stack.insert(0, active_stack.pop([i for i, p in enumerate(active_stack) if p[0] == "OpenAI"][0]))
    elif preferred_provider == "Anthropic Claude" and anthropic_client:
        active_stack.insert(0, active_stack.pop([i for i, p in enumerate(active_stack) if p[0] == "Anthropic"][0]))
    elif preferred_provider == "Google Gemini" and google_client:
        active_stack.insert(0, active_stack.pop([i for i, p in enumerate(active_stack) if p[0] == "Google"][0]))

    last_error = ""
    for name, action in active_stack:
        try:
            return action()
        except Exception as e:
            last_error += f"[{name} Error: {str(e)}] "
            continue

    raise Exception(f"All active AI providers failed. Details: {last_error}")


# --- AUTHENTICATION FLOW (SUPABASE AUTH) ---
if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    st.markdown("### 🔐 Secure Athlete Portal Login")
    auth_tab1, auth_tab2 = st.tabs(["Log In", "Sign Up"])
    with auth_tab1:
        login_email = st.text_input("Email", key="login_email")
        login_pass = st.text_input("Password", type="password", key="login_pass")
        if st.button("Log In", type="primary", use_container_width=True):
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
        if st.button("Create Account", type="primary", use_container_width=True):
            try:
                res = supabase.auth.sign_up({"email": signup_email, "password": signup_pass})
                st.session_state.user = res.user
                st.success("Account created successfully!")
                st.rerun()
            except Exception as e:
                st.error(f"Sign up failed: {e}")
    st.stop()

USER_ID = st.session_state.user.id

# --- FETCH USER PROFILE FROM SUPABASE ---
user_profile = None
try:
    profile_res = supabase.table("profiles").select("*").eq("id", USER_ID).execute()
    if profile_res.data: user_profile = profile_res.data[0]
except Exception: pass

if not user_profile or not user_profile.get("intervals_api_key") or not user_profile.get("intervals_athlete_id"):
    st.markdown("---")
    st.subheader("⚙️ Intervals.icu Account Setup")
    with st.form("setup_form"):
        input_api_key = st.text_input("Intervals.icu API Key", type="password")
        input_athlete_id = st.text_input("Intervals.icu Athlete ID")
        submitted = st.form_submit_button("Save & Launch", use_container_width=True)
        if submitted and input_api_key and input_athlete_id:
            supabase.table("profiles").upsert({
                "id": USER_ID, 
                "intervals_api_key": input_api_key.strip(), 
                "intervals_athlete_id": input_athlete_id.strip()
            }).execute()
            st.rerun()
    st.stop()

INTERVALS_API_KEY = user_profile["intervals_api_key"]
ATHLETE_ID = user_profile["intervals_athlete_id"]

# --- SAFE GOALS & TARGET EVENT INITIALIZATION ---
if "goals" not in st.session_state or not isinstance(st.session_state.goals, dict):
    st.session_state.goals = {}

st.session_state.goals.setdefault("primary_sport", "Cycling (Road)")
st.session_state.goals.setdefault("event_name", "Target Gran Fondo / Race")
st.session_state.goals.setdefault("event_date", datetime.date.today() + datetime.timedelta(days=60))
st.session_state.goals.setdefault("target_metric", "Maintain 4.2 W/kg or build aerobic base")

# --- DATA FETCHING (Optimized Timeouts) ---
@st.cache_data(ttl=300, show_spinner=False) 
def fetch_intervals_wellness(athlete_id, api_key):
    try:
        end_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        start_date = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness?oldest={start_date}&newest={end_date}"
        res = requests.get(url, auth=("API_KEY", api_key), timeout=5)
        return res.json() if res.status_code == 200 and res.json() else []
    except Exception: return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_recent_activities(athlete_id, api_key):
    try:
        end_date = datetime.date.today().isoformat()
        start_date = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
        url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/activities?oldest={start_date}&newest={end_date}"
        res = requests.get(url, auth=("API_KEY", api_key), timeout=5)
        return res.json() if res.status_code == 200 else []
    except Exception: return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_athlete_stats(athlete_id, api_key):
    try:
        url = f"https://intervals.icu/api/v1/athlete/{athlete_id}"
        res = requests.get(url, auth=("API_KEY", api_key), timeout=5)
        return res.json() if res.status_code == 200 else {}
    except Exception: return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_planned_workouts(athlete_id, api_key):
    try:
        end_date = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
        start_date = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
        url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events?oldest={start_date}&newest={end_date}"
        res = requests.get(url, auth=("API_KEY", api_key), timeout=5)
        return res.json() if res.status_code == 200 else []
    except Exception: return []

@st.cache_data(ttl=600, show_spinner=False)
def fetch_rain_intelligence():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=1.3521&longitude=103.8198&current=precipitation,weather_code"
        res = requests.get(url, timeout=3)
        data = res.json().get("current", {})
        precip = data.get("precipitation", 0.0)
        w_code = data.get("weather_code", 0)
        return precip > 0.1 or w_code in [51, 53, 55, 56, 57, 61, 63, 65, 66, 67, 80, 81, 82, 95, 96, 99]
    except Exception:
        return False

def parse_gpx(file_bytes):
    try:
        try:
            xml_content = file_bytes.decode('utf-8')
        except UnicodeDecodeError:
            try:
                xml_content = file_bytes.decode('latin-1')
            except:
                xml_content = file_bytes.decode('utf-16', errors='ignore')
                
        root = ET.fromstring(xml_content)
        
        latlons = []
        elevations = []
        
        for elem in root.iter():
            tag = elem.tag.split('}')[-1].lower()
            if tag in ['trkpt', 'rtept']:
                lat_str = elem.attrib.get('lat') or elem.attrib.get('latitude')
                lon_str = elem.attrib.get('lon') or elem.attrib.get('longitude')
                
                if lat_str and lon_str:
                    try:
                        lat = float(lat_str)
                        lon = float(lon_str)
                        latlons.append((lat, lon))
                        
                        ele_val = elevations[-1] if elevations else 0.0
                        for child in elem:
                            if child.tag.split('}')[-1].lower() in ['ele', 'elevation', 'alt']:
                                try:
                                    ele_val = float(child.text)
                                except (TypeError, ValueError):
                                    pass
                                break
                        elevations.append(ele_val)
                    except ValueError:
                        pass
                        
        if not latlons:
            return None

        total_ele_gain = 0
        for i in range(1, len(elevations)):
            diff = elevations[i] - elevations[i-1]
            if diff > 0: 
                total_ele_gain += diff
                
        total_dist_km = 0
        for i in range(1, len(latlons)):
            lat1, lon1 = latlons[i-1]
            lat2, lon2 = latlons[i]
            R = 6371.0 
            dlat = math.radians(lat2 - lat1)
            dlon = math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            c = 2 * math.asin(math.sqrt(a))
            total_dist_km += R * c

        return {
            "distance_km": round(max(total_dist_km, 0.1), 2),
            "elevation_gain_m": round(total_ele_gain, 1),
            "max_elevation": round(max(elevations), 1) if elevations else 0,
            "min_elevation": round(min(elevations), 1) if elevations else 0
        }
        
    except Exception as e:
        st.error(f"XML Parsing Error: {str(e)}")
        return None

with st.spinner("Syncing multi-sport telemetry & weather intelligence..."):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_wellness = executor.submit(fetch_intervals_wellness, ATHLETE_ID, INTERVALS_API_KEY)
        future_activities = executor.submit(fetch_recent_activities, ATHLETE_ID, INTERVALS_API_KEY)
        future_stats = executor.submit(fetch_athlete_stats, ATHLETE_ID, INTERVALS_API_KEY)
        future_planned = executor.submit(fetch_planned_workouts, ATHLETE_ID, INTERVALS_API_KEY)
        future_rain = executor.submit(fetch_rain_intelligence)

        wellness_list = future_wellness.result()
        activities_data = future_activities.result()
        athlete_stats = future_stats.result()
        planned_data = future_planned.result()
        is_raining = future_rain.result()

ctl, atl, tsb, sleep_score, hrv = 0, 0, 0, 0, 0
if wellness_list:
    latest = wellness_list[-1]
    ctl, atl, tsb = latest.get("ctl", 0), latest.get("atl", 0), latest.get("tsb", 0)
    for r in reversed(wellness_list):
        if sleep_score == 0 and r.get("sleepScore"): sleep_score = r.get("sleepScore")
        if hrv == 0 and r.get("hrv"): hrv = r.get("hrv")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "model", "content": "Hello! Elite Coaching engine active with Gemini 3.5/3.7 reasoning core. Your target goals and live readiness loop are synced."}]

if "debrief_logs" not in st.session_state: st.session_state.debrief_logs = []
if "periodization_review" not in st.session_state: st.session_state.periodization_review = None

# Hardware Integration Context for AI Payload
equipment_context = """
Athlete Equipment Profile:
- Bike: Cervélo Soloist (Size 48)
- Gearing: Magene 50-34T chainrings, Dura-Ace 11-34T cassette
- Crank: Magene TEO P515 Carbon (160mm) with P515 Spider power meter
- Cockpit: THE ONE PRO Aero Carbon handlebars
- Pedals: Wahoo Speedplay (Titanium Spindles)
- Computer: Garmin Edge 530
Note: Factor the 160mm crank length and 1:1 lowest gear ratio (34-34) into biomechanics, cadence, and climbing strategies.
"""

# --- SIDEBAR (Goals & Targets Feedback Loop Input) ---
with st.sidebar:
    st.markdown(f"👤 **{st.session_state.user.email}**")
    
    st.subheader("🎯 Target Event & Goals")
    with st.form("goal_feedback_form"):
        p_sport = st.selectbox("Primary Discipline", ["Cycling (Road)", "Cycling (Time Trial)", "Gravel", "Triathlon"], index=0)
        ev_name = st.text_input("Target Event Name", value=st.session_state.goals["event_name"])
        ev_date = st.date_input("Target Event Date", value=st.session_state.goals["event_date"])
        t_metric = st.text_input("Target Objective / KPI", value=st.session_state.goals["target_metric"])
        
        if st.form_submit_button("Update Feedback Loop", use_container_width=True):
            st.session_state.goals = {
                "primary_sport": p_sport,
                "event_name": ev_name,
                "event_date": ev_date,
                "target_metric": t_metric
            }
            st.success("Goals updated in feedback loop!")

    st.markdown("---")
    selected_provider = st.selectbox("⚡ AI Engine Model", ["⚡ Auto-Fallback Chain", "OpenAI GPT", "Anthropic Claude", "Google Gemini"])

    st.markdown("---")
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = []
        st.rerun()

    if st.button("Log Out", use_container_width=True):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

days_to_event = (st.session_state.goals["event_date"] - datetime.date.today()).days

# --- NAVIGATION SUITE (Consolidated) ---
tab_cmd, tab_coach, tab_strat, tab_strength = st.tabs([
    "📊 Command Center", "🤖 AI Coach & Logs", "🗺️ Event Strategist", "🏋️‍♂️ Strength"
])

# ================= TAB 1: COMMAND CENTER (Dash + Calendar) =================
with tab_cmd:
    st.markdown(f"### ☀️ Daily Coaching Briefing • Target: {st.session_state.goals['event_name']}")
    with st.container():
        brief_col1, brief_col2 = st.columns([3, 1])
        with brief_col1:
            weather_advisory = (
                "🌧️ **Rain / Wet Weather Alert:** Outdoor conditions are unfavorable. Switch to indoor smart trainer plans or shift to a gym strength session."
                if is_raining else
                "☀️ **Weather Clear:** Outdoor routes are fully viable for your planned sessions."
            )
            st.info(
                f"**Feedback Loop Check:** Training for **{st.session_state.goals['event_name']}** ({days_to_event} days out). Objective: *{st.session_state.goals['target_metric']}*.\n\n"
                f"{weather_advisory}\n\n"
                f"**Readiness Audit:** Form TSB is currently `{tsb:.1f}`. Sleep score is logged at `{sleep_score}/100`. "
                f"{'🟢 Body is primed for high output.' if tsb >= -15 else '🟡 Fatigue is building; prioritize recovery pacing.'}"
            )
        with brief_col2:
            st.metric("Event Countdown", f"{days_to_event} Days")

    st.markdown("---")
    
    col_met, col_cal = st.columns([1, 2])
    
    with col_met:
        st.markdown("#### Training Load")
        st.metric("Fitness (CTL)", round(ctl, 1))
        st.metric("Fatigue (ATL)", round(atl, 1))
        st.metric("Form (TSB)", round(tsb, 1))
        st.metric("Sleep Score", f"{sleep_score}/100" if sleep_score > 0 else "N/A")
        
    with col_cal:
        st.markdown("#### 📅 Upcoming Calendar")
        if planned_data:
            df_cal = pd.DataFrame(planned_data)
            display_cols = [c for c in ['start_date_local', 'name', 'type'] if c in df_cal.columns]
            if display_cols:
                st.dataframe(df_cal[display_cols], use_container_width=True, hide_index=True)
            else:
                st.dataframe(df_cal, use_container_width=True)
        else:
            st.info("No upcoming calendar events found.")

    st.markdown("---")
    st.subheader("🔄 Proactive Feedback Loop & Periodization Audit")
    if st.button("Run Progress & Target Audit", type="primary"):
        with st.spinner("Analyzing current progress against target event goals..."):
            audit_prompt = f"""
            Perform an elite progress and periodization audit for my target event: {st.session_state.goals['event_name']} in {days_to_event} days.
            TARGET OBJECTIVE: {st.session_state.goals['target_metric']}
            PRIMARY SPORT: {st.session_state.goals['primary_sport']}
            CURRENT METRICS: CTL={ctl}, ATL={atl}, TSB={tsb}, Sleep={sleep_score}.
            WEATHER: {'Raining' if is_raining else 'Clear'}
            RECENT DEBRIEFS: {st.session_state.debrief_logs}
            {equipment_context}
            
            Evaluate if my current training load and form are properly aligned to hit my target objective by event day. Provide concrete adjustments if necessary.
            """
            try:
                res, model = execute_multiprovider_generation(audit_prompt, preferred_provider=selected_provider)
                st.session_state.periodization_review = f"{res}\n\n*(Engine: {model})*"
                st.rerun()
            except Exception as e:
                st.error(f"Generation Failed: {str(e)}")

    if st.session_state.periodization_review:
        with st.expander("📋 Target Progress Audit Results", expanded=True):
            st.markdown(st.session_state.periodization_review)
            if st.button("Clear Review"): st.session_state.periodization_review = None; st.rerun()

# ================= TAB 2: AI COACH & LOGS (Chat + Debrief) =================
with tab_coach:
    coach_col1, coach_col2 = st.columns([2, 1])
    
    with coach_col1:
        st.markdown("### 🤖 Endurance AI Coach (Goal-Synced Feedback Loop)")
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
                
        if prompt := st.chat_input("Ask your coach about how your recent sessions match your event targets..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            
            with st.chat_message("model"):
                with st.spinner("Consulting coaching core..."):
                    payload = f"""
                    You are an elite endurance coach. Your feedback loop is continuously tracking the athlete's target event: {st.session_state.goals['event_name']} ({days_to_event} days away).
                    TARGET OBJECTIVE: {st.session_state.goals['target_metric']}
                    METRICS: CTL={ctl}, ATL={atl}, TSB={tsb}.
                    WEATHER STATUS: {'Raining (Outdoor rides blocked; suggest indoor trainer/MyWhoosh or gym alternatives)' if is_raining else 'Clear'}
                    DEBRIEF LOGS: {st.session_state.debrief_logs}
                    {equipment_context}
                    
                    Provide precise coaching advice, explicitly reviewing how the user's question or recent output aligns with hitting their target objective on event day. If prescribing a workout, include exact wattage or pace zones.
                    """ + prompt
                    
                    try:
                        resp, engine = execute_multiprovider_generation(payload, preferred_provider=selected_provider)
                        full_resp = f"{resp}\n\n*(Engine: {engine})*"
                        st.markdown(full_resp)
                        st.session_state.messages.append({"role": "model", "content": full_resp})
                    except Exception as e:
                        st.error(f"AI Generation Failed: {str(e)}")
                        
    with coach_col2:
        st.markdown("### 📝 Workout Debrief")
        st.caption("Log qualitative feedback. Feeds directly into the AI goal feedback loop.")
        with st.form("debrief"):
            d_date = st.date_input("Date")
            d_sport = st.selectbox("Sport", ["Cycling", "Running", "Strength"])
            d_rpe = st.slider("RPE (1-10)", 1, 10, 5)
            d_notes = st.text_area("Notes & Feel")
            if st.form_submit_button("Save Debrief", use_container_width=True):
                st.session_state.debrief_logs.append({"date": str(d_date), "sport": d_sport, "rpe": d_rpe, "notes": d_notes})
                st.success("Logged into feedback loop!")

# ================= TAB 3: EVENT STRATEGIST (Route + Fueling) =================
with tab_strat:
    st.markdown(f"### 🗺️ Route & Fueling Strategist for {st.session_state.goals['event_name']}")
    
    st.markdown("#### ⚡ Fueling & Hydration Calculator")
    f_col1, f_col2 = st.columns(2)
    with f_col1:
        dur = st.slider("Estimated Duration (Hours)", 1.0, 6.0, 3.0, 0.5)
        sport_type = st.selectbox("Activity Sport", ["Cycling", "Running"])
        wt = st.number_input("Weight (kg)", 45.0, 100.0, 58.0)
    with f_col2:
        carbs = 90 if sport_type == "Cycling" else 60
        st.metric("Recommended Carbs", f"{carbs} g/hr", f"Total Target: {int(carbs * dur)}g")
        st.metric("Fluid Target", f"{int(wt * 8)} ml/hr")
        
    st.markdown("---")
    st.markdown("#### 📍 GPX Pacing Planner")
    st.caption("Upload a `.gpx` route file to get an AI-powered course breakdown aligned with your event targets.")
    
    uploaded_gpx = st.file_uploader("Upload Cycling Route (.gpx)", type=["gpx"])
    
    if uploaded_gpx:
        gpx_bytes = uploaded_gpx.read()
        route_metrics = parse_gpx(gpx_bytes)
        
        if route_metrics:
            col_r1, col_r2, col_r3 = st.columns(3)
            col_r1.metric("Route Distance", f"{route_metrics['distance_km']} km")
            col_r2.metric("Elevation Gain", f"{route_metrics['elevation_gain_m']} m")
            col_r3.metric("Max Elevation", f"{route_metrics['max_elevation']} m")
            
            if st.button("🤖 Generate AI Course Strategy & Target Pacing", type="primary"):
                with st.spinner("Analyzing route profile against target event goals..."):
                    route_prompt = (
                        f"Act as an elite cycling head coach. Analyze this uploaded route for target event '{st.session_state.goals['event_name']}': "
                        f"Distance: {route_metrics['distance_km']} km, Elevation Gain: {route_metrics['elevation_gain_m']} m, Max Elevation: {route_metrics['max_elevation']} m. "
                        f"Target Objective: {st.session_state.goals['target_metric']}. "
                        f"Athlete Readiness: CTL={ctl}, TSB={tsb}. Total Fueling target: {int(carbs * dur)}g carbs over {dur} hours. "
                        f"{equipment_context} "
                        "Provide a comprehensive race/ride strategy: 1) Pacing breakdown across climbs vs flats based on the gearing provided, 2) Power targets relative to FTP, 3) Specific fueling execution strategy."
                    )
                    try:
                        route_res, route_model = execute_multiprovider_generation(route_prompt, preferred_provider=selected_provider)
