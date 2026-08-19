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

# App UI Configuration
st.set_page_config(page_title="AI Cycling Performance Coach", page_icon="🚴‍♂️", layout="wide")

st.markdown("""
<style>
    div[data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.02);
        border: 1px solid rgba(128, 128, 128, 0.08);
        padding: 10px 14px;
        border-radius: 8px;
        box-shadow: none;
    }
    div[data-testid="stMetric"] label {
        font-size: 0.85rem !important;
        font-weight: 500;
        color: #666666;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: 1.35rem !important;
        font-weight: 600;
    }
    @media (max-width: 768px) {
        .main .block-container {
            padding: 1rem 0.75rem;
        }
    }
</style>
""", unsafe_allow_html=True)

st.title("🚴‍♂️ AI Cycling Performance Coach")
st.caption("Performance Analytics • Intervals.icu Trend Interpretation • MyWhoosh Integration")

# --- MULTI-PROVIDER CROSS-PROVIDER FALLBACK ROUTER ---
def execute_multiprovider_generation(prompt, preferred_provider="⚡ Auto-Fallback Chain", is_stream=False):
    def call_openai(stream=False):
        if not openai_client: raise Exception("OpenAI API key missing")
        res = openai_client.chat.completions.create(
            model="gpt-4o", messages=[{"role": "user", "content": prompt}]
        )
        return res.choices[0].message.content, "OpenAI GPT-4o"

    def call_anthropic(stream=False):
        if not anthropic_client: raise Exception("Anthropic API key missing")
        res = anthropic_client.messages.create(
            model="claude-3-5-sonnet-20241022", max_tokens=2048, messages=[{"role": "user", "content": prompt}]
        )
        return res.content[0].text, "Anthropic Claude"

    def call_google(stream=False):
        if not google_client: raise Exception("Google API key missing")
        models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.5-flash", "gemini-3.1-pro-preview"]
        last_err = None
        for m in models:
            try:
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
        raise Exception("No AI provider API keys configured in Streamlit Secrets!")

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


# --- AUTHENTICATION FLOW (SUPABASE) ---
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

if "goals" not in st.session_state or not isinstance(st.session_state.goals, dict):
    st.session_state.goals = {}

st.session_state.goals["event_name"] = user_profile.get("event_name") or "Weekend Group Rides (Climbing Efficiency)"
st.session_state.goals["target_metric"] = user_profile.get("target_metric") or "Improve threshold power and climbing resilience to stay with the lead group"

# --- DATA FETCHING (90-Day Range for Trend Analysis) ---
@st.cache_data(ttl=300, show_spinner=False) 
def fetch_intervals_wellness(athlete_id, api_key):
    try:
        end_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        start_date = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
        url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness?oldest={start_date}&newest={end_date}"
        res = requests.get(url, auth=("API_KEY", api_key), timeout=5)
        return res.json() if res.status_code == 200 and res.json() else []
    except Exception: return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_recent_activities(athlete_id, api_key):
    try:
        end_date = datetime.date.today().isoformat()
        start_date = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
        url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/activities?oldest={start_date}&newest={end_date}"
        res = requests.get(url, auth=("API_KEY", api_key), timeout=5)
        return res.json() if res.status_code == 200 else []
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

with st.spinner("Syncing 90-day performance telemetry..."):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_wellness = executor.submit(fetch_intervals_wellness, ATHLETE_ID, INTERVALS_API_KEY)
        future_activities = executor.submit(fetch_recent_activities, ATHLETE_ID, INTERVALS_API_KEY)
        future_planned = executor.submit(fetch_planned_workouts, ATHLETE_ID, INTERVALS_API_KEY)

        wellness_list = future_wellness.result()
        activities_data = future_activities.result()
        planned_data = future_planned.result()

ctl, atl, tsb, sleep_score = 0, 0, 0, 0
if wellness_list:
    latest = wellness_list[-1]
    ctl, atl, tsb = latest.get("ctl", 0), latest.get("atl", 0), latest.get("tsb", 0)
    for r in reversed(wellness_list):
        if sleep_score == 0 and r.get("sleepScore"): sleep_score = r.get("sleepScore")

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "model", "content": "Hello! Your performance coach is online. Ask me to analyze your 90-day Intervals.icu trends, review recent rides, or build a MyWhoosh workout."}]

if "debrief_logs" not in st.session_state: st.session_state.debrief_logs = []

# --- SIDEBAR ---
with st.sidebar:
    st.markdown(f"👤 **{st.session_state.user.email}**")
    st.subheader("🎯 Training Objectives")
    with st.form("goal_feedback_form"):
        ev_name = st.text_input("Focus Area", value=st.session_state.goals["event_name"])
        t_metric = st.text_input("Key Objective", value=st.session_state.goals["target_metric"])
        
        if st.form_submit_button("Update Goals", use_container_width=True):
            st.session_state.goals["event_name"] = ev_name
            st.session_state.goals["target_metric"] = t_metric
            supabase.table("profiles").update({"event_name": ev_name, "target_metric": t_metric}).eq("id", USER_ID).execute()
            st.success("Goals updated!")

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

# --- NAVIGATION SUITE ---
tab_cmd, tab_coach, tab_strat = st.tabs(["📊 Performance Command Center", "🤖 AI Coach & Trends", "🗺️ Route Strategist"])

# ================= TAB 1: PERFORMANCE COMMAND CENTER =================
with tab_cmd:
    st.markdown("### 📈 90-Day Performance & Load Metrics")
    
    c_brief, c_metrics = st.columns([2, 1])
    with c_brief:
        st.info(
            f"**Primary Objective:** *{st.session_state.goals['target_metric']}*.\n\n"
            f"**Readiness Status:** Form (TSB) is `{tsb:.1f}` | Fitness (CTL): `{ctl:.1f}` | Fatigue (ATL): `{atl:.1f}`.\n"
            f"{'🟢 Form is optimal for hard efforts & climbing blocks.' if tsb >= -15 else '🟡 Accumulated fatigue is high; prioritize structured recovery.'}"
        )
    with c_metrics:
        m1, m2 = st.columns(2)
        with m1:
            st.metric("Fitness (CTL)", round(ctl, 1))
            st.metric("Fatigue (ATL)", round(atl, 1))
        with m2:
            st.metric("Form (TSB)", round(tsb, 1))
            st.metric("Sleep", f"{sleep_score}" if sleep_score > 0 else "N/A")

    st.markdown("---")
    
    col_act, col_cal = st.columns(2)
    with col_act:
        st.markdown("#### 🚴 Recent Activities (Intervals.icu)")
        if activities_data:
            df_act = pd.DataFrame(activities_data)
            cols_to_show = [c for c in ['start_date_local', 'name', 'distance', 'moving_time'] if c in df_act.columns]
            if cols_to_show:
                df_display = df_act[cols_to_show].head(6).copy()
                if 'distance' in df_display.columns:
                    df_display['distance'] = (df_display['distance'] / 1000).round(2).astype(str) + " km"
                st.dataframe(df_display, use_container_width=True, hide_index=True)
            else:
                st.dataframe(df_act.head(6), use_container_width=True, hide_index=True)
        else:
            st.info("No recent activities found.")
            
    with col_cal:
        st.markdown("#### 📅 Planned Schedule")
        if planned_data:
            df_cal = pd.DataFrame(planned_data)
            display_cols = [c for c in ['start_date_local', 'name', 'type'] if c in df_cal.columns]
            st.dataframe(df_cal[display_cols] if display_cols else df_cal, use_container_width=True, hide_index=True)
        else:
            st.info("No upcoming calendar events synced.")

# ================= TAB 2: AI COACH & TREND INTERPRETATION =================
with tab_coach:
    st.markdown("### 🤖 Performance Coaching & Trend Interpretation")
    
    chat_container = st.container()
    with chat_container:
        for idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg["role"]): 
                st.markdown(msg["content"])
                
                # Render download button cleanly if workout XML is present in the message
                if msg["role"] == "model":
                    match = re.search(r"```xml\s*(<\?xml.*?>.*?<\s*/\s*workout_file\s*>|<workout_file>.*?</\s*workout_file>)\s*```", msg["content"], re.DOTALL)
                    if not match:
                        match = re.search(r"```\s*(<workout_file>.*?</\s*workout_file>)\s*```", msg["content"], re.DOTALL)
                    
                    if match:
                        zwo_data = match.group(1).strip()
                        st.download_button(
                            label="📥 Download MyWhoosh Workout File (.zwo)",
                            data=zwo_data,
                            file_name=f"MyWhoosh_Workout_{idx}.zwo",
                            mime="application/xml",
                            key=f"download_zwo_{idx}"
                        )

    if prompt := st.chat_input("Ask for a 90-day trend analysis, ride critique, or MyWhoosh workout..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        payload = f"""
        You are an elite cycling sports science coach. Your job is to interpret the athlete's Intervals.icu data and trends.
        GOAL: {st.session_state.goals['event_name']} ({st.session_state.goals['target_metric']})
        METRICS (90-day baseline): CTL={ctl}, ATL={atl}, TSB={tsb}.
        RECENT ACTIVITIES DATA: {activities_data[:15] if activities_data else 'None'}
        
        Provide direct, analytical coaching insights. Analyze trends in their training load, consistency, power progression, or recovery patterns.
        
        CRITICAL INSTRUCTION FOR WORKOUTS: If the user requests an indoor workout, you MUST include a complete valid MyWhoosh workout block in valid XML format (.zwo) enclosed inside a ```xml ... ``` code block (starting with <workout_file> and ending with </workout_file>). Do NOT explain the raw code; just provide it cleanly so the download button handles it.
        """ + prompt
        
        try:
            resp, engine = execute_multiprovider_generation(payload, preferred_provider=selected_provider)
            full_resp = f"{resp}\n\n*(Engine: {engine})*"
            st.session_state.messages.append({"role": "model", "content": full_resp})
            st.rerun()
        except Exception as e:
            st.error(f"AI Generation Failed: {str(e)}")

# ================= TAB 3: ROUTE STRATEGIST =================
with tab_strat:
    st.markdown("### 🗺️ Route Pacing & Power Strategist")
    uploaded_gpx = st.file_uploader("Upload GPX Route File", type=["gpx"])
    
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
            
            if st.button("🤖 Generate Pacing Strategy", type="primary"):
                with st.spinner("Analyzing profile..."):
                    strat_prompt = f"""
                    Analyze this route profile for climbing performance: Distance {route_metrics['distance_km']} km, Elevation Gain {route_metrics['elevation_gain_m']} m.
                    Objective: {st.session_state.goals['target_metric']}
                    Provide precise power pacing targets and climbing strategies to maintain group ride cohesion.
                    """
                    try:
                        strat_res, strat_model = execute_multiprovider_generation(strat_prompt, preferred_provider=selected_provider)
                        st.markdown("---")
                        st.markdown(strat_res)
                        st.caption(f"Generated via: {strat_model}")
                    except Exception as e:
                        st.error(f"Strategy generation failed: {e}")
