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
st.set_page_config(page_title="AI Cycling Performance Coach", page_icon="🚴‍♂️", layout="wide")

st.markdown("""
<style>
    .stCard {
        background-color: var(--background-secondary-color, #ffffff);
        border: 1px solid rgba(128, 128, 128, 0.15);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 4px 12px rgba(0, 0, 0, 0.03);
    }
    div[data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.03);
        border: 1px solid rgba(128, 128, 128, 0.1);
        padding: 14px 18px;
        border-radius: 10px;
        box-shadow: 0 2px 6px rgba(0,0,0,0.01);
    }
    .stButton > button {
        border-radius: 8px;
        font-weight: 600;
        transition: all 0.2s ease-in-out;
    }
    @media (max-width: 768px) {
        .main .block-container {
            padding: 1rem 0.75rem;
        }
    }
</style>
""", unsafe_allow_html=True)

st.title("🚴‍♂️ AI Cycling Performance Coach")
st.caption("Indoor MyWhoosh & Outdoor Group Ride Intelligence • Intervals.icu Integrated")

# --- MULTI-PROVIDER CROSS-PROVIDER FALLBACK ROUTER ---
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
        models = ["gemini-2.5-flash", "gemini-2.5-pro", "gemini-3.5-flash", "gemini-3.1-pro-preview"]
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

# --- PERSISTENT GOALS & TARGET EVENT INITIALIZATION FROM SUPABASE ---
if "goals" not in st.session_state or not isinstance(st.session_state.goals, dict):
    st.session_state.goals = {}

st.session_state.goals["primary_sport"] = user_profile.get("primary_sport") or "Cycling (Road & Climbing)"
st.session_state.goals["event_name"] = user_profile.get("event_name") or "Weekend Group Rides (No More Getting Dropped)"

db_date = user_profile.get("event_date")
if db_date:
    try:
        if isinstance(db_date, str):
            st.session_state.goals["event_date"] = datetime.date.fromisoformat(db_date)
        else:
            st.session_state.goals["event_date"] = db_date
    except Exception:
        st.session_state.goals["event_date"] = datetime.date.today() + datetime.timedelta(days=60)
else:
    st.session_state.goals["event_date"] = datetime.date.today() + datetime.timedelta(days=60)

st.session_state.goals["target_metric"] = user_profile.get("target_metric") or "Survive steep climbs on Saturday club rides and improve threshold power"

# --- DATA FETCHING ---
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
        elevation_list = []
        
        for elem in root.iter():
            tag = elem.tag.split('}')[-1].lower()
            if tag in ['trkpt', 'rtept']:
                lat_str = elem.attrib.get('lat') or elem.attrib.get('latitude')
                lon_str = elem.attrib.get('lon') or elem.attrib.get('longitude')
                if lat_str and lon_str:
                    try:
                        lat, lon = float(lat_str), float(lon_str)
                        latlons.append((lat, lon))
                        ele_val = elevation_list[-1] if elevation_list else 0.0
                        for child in elem:
                            if child.tag.split('}')[-1].lower() in ['ele', 'elevation', 'alt']:
                                try: ele_val = float(child.text)
                                except: pass
                                break
                        elevation_list.append(ele_val)
                    except ValueError: pass
                        
        if not latlons: return None

        total_ele_gain = sum(max(0, elevation_list[i] - elevation_list[i-1]) for i in range(1, len(elevation_list)))
        total_dist_km = 0
        for i in range(1, len(latlons)):
            lat1, lon1 = latlons[i-1]
            lat2, lon2 = latlons[i]
            R = 6371.0 
            dlat, dlon = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
            a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
            total_dist_km += R * (2 * math.asin(math.sqrt(a)))

        return {
            "distance_km": round(max(total_dist_km, 0.1), 2),
            "elevation_gain_m": round(total_ele_gain, 1),
            "max_elevation": round(max(elevation_list), 1) if elevation_list else 0
        }
    except Exception as e:
        st.error(f"XML Parsing Error: {str(e)}")
        return None

with st.spinner("Syncing telemetry & weather intelligence..."):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_wellness = executor.submit(fetch_intervals_wellness, ATHLETE_ID, INTERVALS_API_KEY)
        future_activities = executor.submit(fetch_recent_activities, ATHLETE_ID, INTERVALS_API_KEY)
        future_planned = executor.submit(fetch_planned_workouts, ATHLETE_ID, INTERVALS_API_KEY)
        future_rain = executor.submit(fetch_rain_intelligence)

        wellness_list = future_wellness.result()
        activities_data = future_activities.result()
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
    st.session_state.messages = [{"role": "model", "content": "Hello! Your custom AI cycling coach is active. Ready to help you crush weekend group rides and conquer climbs without paying S$350/mo!"}]

if "debrief_logs" not in st.session_state: st.session_state.debrief_logs = []
if "group_ride_logs" not in st.session_state: st.session_state.group_ride_logs = []

# Custom Equipment Profile Context for AI Payload
equipment_context = """
Athlete Bike Build & Equipment Context:
- Bike: Cervélo Soloist (Size 48), ~6.9kg
- Gearing: Magene 50-34T Compact Chainrings, Dura-Ace 11-34T 12-speed Cassette & Chain
- Crankset & Power Meter: Magene TEO P515 Carbon (160mm crank arm length) with P515 Spider Dual-sided Power Meter
- Cockpit: THE ONE PRO Aero Carbon handlebars
- Pedals: Wahoo Speedplay (Upgraded with Titanium Spindles)
- Computer: Garmin Edge 530
Note: Account for the 160mm short crank arms and 1:1 climbing gear ratio (34-34) in cadence recommendations and power profiling.
"""

# --- SIDEBAR ---
with st.sidebar:
    st.markdown(f"👤 **{st.session_state.user.email}**")
    st.subheader("🎯 Primary Cycling Goals")
    with st.form("goal_feedback_form"):
        ev_name = st.text_input("Main Focus / Event", value=st.session_state.goals["event_name"])
        t_metric = st.text_input("Key Objective", value=st.session_state.goals["target_metric"])
        
        if st.form_submit_button("Update Goals", use_container_width=True):
            st.session_state.goals["event_name"] = ev_name
            st.session_state.goals["target_metric"] = t_metric
            try:
                supabase.table("profiles").update({
                    "event_name": ev_name,
                    "target_metric": t_metric
                }).eq("id", USER_ID).execute()
                st.success("Goals updated successfully!")
            except Exception as e:
                st.error(f"Cloud update failed: {e}")

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
tab_cmd, tab_coach, tab_strat, tab_strength = st.tabs([
    "📊 Command Center", "🤖 AI Coach & MyWhoosh ZWO", "🗺️ Route Strategist", "🏋️‍♂️ Cross-Training"
])

# ================= TAB 1: COMMAND CENTER =================
with tab_cmd:
    st.markdown(f"### ☀️ Daily Coaching Briefing")
    with st.container():
        brief_col1, brief_col2 = st.columns([3, 1])
        with brief_col1:
            weather_advisory = (
                "🌧️ **Rain Alert:** Outdoor conditions wet. Switch your session to an indoor MyWhoosh workout."
                if is_raining else
                "☀️ **Weather Clear:** Great conditions for outdoor riding or club workouts."
            )
            st.info(
                f"**Current Focus:** *{st.session_state.goals['event_name']}*.\n\n"
                f"{weather_advisory}\n\n"
                f"**Readiness:** Form TSB is `{tsb:.1f}`. Sleep score: `{sleep_score}/100`. "
                f"{'🟢 Ready for high-intensity work.' if tsb >= -15 else '🟡 Fatigue is high; prioritize recovery pacing.'}"
            )
        with brief_col2:
            st.metric("Form (TSB)", round(tsb, 1))

    st.markdown("---")
    col_met, col_cal = st.columns([1, 2])
    with col_met:
        st.markdown("#### Training Load")
        st.metric("Fitness (CTL)", round(ctl, 1))
        st.metric("Fatigue (ATL)", round(atl, 1))
        st.metric("Sleep Score", f"{sleep_score}/100" if sleep_score > 0 else "N/A")
    with col_cal:
        st.markdown("#### 📅 Upcoming Calendar (Intervals.icu)")
        if planned_data:
            df_cal = pd.DataFrame(planned_data)
            display_cols = [c for c in ['start_date_local', 'name', 'type'] if c in df_cal.columns]
            st.dataframe(df_cal[display_cols] if display_cols else df_cal, use_container_width=True, hide_index=True)
        else:
            st.info("No upcoming calendar events synced.")

    st.markdown("---")
    st.markdown("### 🏆 Recent Weekend Group Ride Performance History")
    if st.session_state.group_ride_logs:
        for gr in reversed(st.session_state.group_ride_logs):
            with st.container():
                st.markdown(f"**Date:** {gr['date']} | **Outcome:** {gr['outcome']} | **Max Climb HR/Power RPE:** {gr['rpe']}/10")
                st.markdown(f"> *Notes:* {gr['notes']}")
                st.divider()
    else:
        st.caption("No weekend group rides logged yet. Use the tracker below or in the Coach tab after your Saturday club rides.")

# ================= TAB 2: AI COACH & MYWHOOSH ZWO BUILDER =================
with tab_coach:
    coach_col1, coach_col2 = st.columns([2, 1])
    
    with coach_col1:
        st.markdown("### 🤖 Cycling AI Coach")
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]): st.markdown(msg["content"])
                
        if prompt := st.chat_input("Ask for a climbing workout, review your last ride, or plan your week..."):
            st.session_state.messages.append({"role": "user", "content": prompt})
            with st.chat_message("user"): st.markdown(prompt)
            
            with st.chat_message("model"):
                with st.spinner("Analyzing performance metrics..."):
                    payload = f"""
                    You are an elite cycling performance coach helping an active cyclist avoid getting dropped on group ride climbs.
                    GOAL: {st.session_state.goals['event_name']} ({st.session_state.goals['target_metric']})
                    METRICS: CTL={ctl}, ATL={atl}, TSB={tsb}.
                    WEATHER: {'Raining (Indoor MyWhoosh required)' if is_raining else 'Clear'}
                    DEBRIEFS: {st.session_state.debrief_logs}
                    GROUP RIDE HISTORY: {st.session_state.group_ride_logs}
                    {equipment_context}
                    
                    Provide precise, actionable cycling coaching feedback. Include exact power zones (% of FTP) and cadence recommendations suited to a 160mm crank setup.
                    """ + prompt
                    try:
                        resp, engine = execute_multiprovider_generation(payload, preferred_provider=selected_provider)
                        full_resp = f"{resp}\n\n*(Engine: {engine})*"
                        st.markdown(full_resp)
                        st.session_state.messages.append({"role": "model", "content": full_resp})
                    except Exception as e:
                        st.error(f"AI Generation Failed: {str(e)}")
                        
    with coach_col2:
        st.markdown("### 🛠️ MyWhoosh `.zwo` Generator")
        st.caption("Select custom interval block templates to build MyWhoosh workout files.")
        
        with st.form("zwo_form"):
            z_name = st.text_input("Workout Name", value="Climbing Threshold Builder")
            z_type = st.selectbox("Interval Block Template", [
                "Sweet Spot Pyramid (3x10min @ 88-93% FTP)",
                "Threshold Over-Unders (Surge simulation for hills)",
                "VO2 Max Punchy Hills (40s/20s micro-bursts)",
                "Long Sustained Climbing Simulation (Sweet Spot + Surges)"
            ])
            ftp_val = st.number_input("Your FTP (Watts)", 100, 450, 240)
            
            if st.form_submit_button("Generate .zwo File", use_container_width=True):
                with st.spinner("Building custom workout XML template..."):
                    zwo_prompt = f"""
                    Generate a structured MyWhoosh workout in valid XML format (.zwo) based on this interval block template:
                    Workout Name: {z_name}
                    Selected Template Structure: {z_type}
                    Athlete FTP: {ftp_val}W
                    {equipment_context}
                    
                    Return ONLY the XML structure wrapped inside a ```xml ... ``` code block, starting with <workout_file> and ending with </workout_file>. Include a proper warm-up, the requested intervals block sequence matching the template chosen, and a cool-down.
                    """
                    try:
                        z_resp, _ = execute_multiprovider_generation(zwo_prompt, preferred_provider=selected_provider)
                        if "```xml" in z_resp:
                            zwo_code = z_resp.split("```xml")[1].split("```")[0].strip()
                        elif "```" in z_resp:
                            zwo_code = z_resp.split("```")[1].split("```")[0].strip()
                        else:
                            zwo_code = z_resp
                            
                        st.session_state.latest_zwo = zwo_code
                        st.session_state.latest_zwo_name = z_name.replace(" ", "_")
                        st.success("Workout generated successfully!")
                    except Exception as e:
                        st.error(f"Failed to generate workout file: {e}")
                        
        if "latest_zwo" in st.session_state:
            st.download_button(
                label="📥 Download MyWhoosh Workout (.zwo)",
                data=st.session_state.latest_zwo,
                file_name=f"{st.session_state.latest_zwo_name}.zwo",
                mime="application/xml",
                use_container_width=True
            )

        st.markdown("---")
        st.markdown("### 🚴‍♂️ Weekend Group Ride Debrief")
        with st.form("group_ride_debrief_form"):
            gr_date = st.date_input("Ride Date (Saturday)")
            gr_outcome = st.selectbox("Group Ride Outcome", [
                "Stuck with lead group on all climbs (Success!)",
                "Got dropped on the steepest climb section",
                "Suffered on punchy hills but hung on",
                "Recovered well / Easy social recovery ride"
            ])
            gr_rpe = st.slider("Climb Intensity RPE", 1, 10, 8)
            gr_notes = st.text_area("Group Ride Notes (Which climb hurt? Where did the gap open?)")
            
            if st.form_submit_button("Log Group Ride Result", use_container_width=True):
                st.session_state.group_ride_logs.append({
                    "date": str(gr_date),
                    "outcome": gr_outcome,
                    "rpe": gr_rpe,
                    "notes": gr_notes
                })
                st.success("Group ride result logged to AI performance memory!")

# ================= TAB 3: ROUTE STRATEGIST =================
with tab_strat:
    st.markdown("### 🗺️ Route Climbing & Pacing Strategist")
    uploaded_gpx = st.file_uploader("Upload GPX Route File", type=["gpx"])
    
    if uploaded_gpx:
        route_metrics = parse_gpx(uploaded_gpx.read())
        if route_metrics:
            c1, c2, c3 = st.columns(3)
            c1.metric("Distance", f"{route_metrics['distance_km']} km")
            c2.metric("Elevation Gain", f"{route_metrics['elevation_gain_m']} m")
            c3.metric("Max Elevation", f"{route_metrics['max_elevation']} m")
            
            if st.button("🤖 Generate Climbing & Gearing Strategy", type="primary"):
                with st.spinner("Analyzing route profile..."):
                    strat_prompt = f"""
                    Analyze this route profile for climbing performance: Distance {route_metrics['distance_km']} km, Elevation Gain {route_metrics['elevation_gain_m']} m.
                    Objective: {st.session_state.goals['target_metric']}
                    {equipment_context}
                    
                    Provide precise pacing advice, specific power targets for the climbs, and how to manage the 34-34 climbing gear ratio so the athlete doesn't get dropped.
                    """
                    try:
                        strat_res, strat_model = execute_multiprovider_generation(strat_prompt, preferred_provider=selected_provider)
                        st.markdown("---")
                        st.markdown(strat_res)
                        st.caption(f"Generated via: {strat_model}")
                    except Exception as e:
                        st.error(f"Strategy generation failed: {e}")

# ================= TAB 4: CROSS-TRAINING =================
with tab_strength:
    st.markdown("### 🏋️‍♂️ Running & Strength Cross-Training")
    st.caption("Targeted supplementary training designed to improve cycling power and prevent injuries.")
    
    st_focus = st.selectbox("Cross-Training Focus", [
        "Core & Posterior Chain Strength for Cycling Climbs",
        "Low-Impact Running for Aerobic Base Maintenance",
        "Full Body Mobility & Injury Prevention"
    ])
    
    if st.button("Generate Cross-Training Session", type="primary"):
        with st.spinner("Designing session..."):
            xt_prompt = f"{equipment_context}\nDesign a 45-minute cross-training session focusing on: {st_focus} to support cycling climbing performance."
            try:
                xt_res, xt_model = execute_multiprovider_generation(xt_prompt, preferred_provider=selected_provider)
                st.markdown(xt_res)
                st.caption(f"Generated via: {xt_model}")
            except Exception as e:
                st.error(f"Generation failed: {e}")
