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
        models = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-2.5-flash", "gemini-1.5-flash"]
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

# --- INTERVALS.ICU CONFIG CHECK ---
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
            supabase.table("profiles").upsert({"id": USER_ID, "intervals_api_key": input_api_key.strip(), "intervals_athlete_id": input_athlete_id.strip()}).execute()
            st.rerun()
    st.stop()

INTERVALS_API_KEY = user_profile["intervals_api_key"]
ATHLETE_ID = user_profile["intervals_athlete_id"]

# --- DATA FETCHING ---
@st.cache_data(ttl=300, show_spinner=False) 
def fetch_intervals_wellness(athlete_id, api_key):
    try:
        end_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
        start_date = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness?oldest={start_date}&newest={end_date}"
        res = requests.get(url, auth=("API_KEY", api_key), timeout=8)
        return res.json() if res.status_code == 200 and res.json() else []
    except Exception: return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_recent_activities(athlete_id, api_key):
    try:
        end_date = datetime.date.today().isoformat()
        start_date = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
        url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/activities?oldest={start_date}&newest={end_date}"
        res = requests.get(url, auth=("API_KEY", api_key), timeout=8)
        return res.json() if res.status_code == 200 else []
    except Exception: return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_athlete_stats(athlete_id, api_key):
    try:
        url = f"https://intervals.icu/api/v1/athlete/{athlete_id}"
        res = requests.get(url, auth=("API_KEY", api_key), timeout=8)
        return res.json() if res.status_code == 200 else {}
    except Exception: return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_planned_workouts(athlete_id, api_key):
    try:
        end_date = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
        start_date = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
        url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events?oldest={start_date}&newest={end_date}"
        res = requests.get(url, auth=("API_KEY", api_key), timeout=8)
        return res.json() if res.status_code == 200 else []
    except Exception: return []

def fetch_rain_intelligence():
    try:
        url = "https://api.open-meteo.com/v1/forecast?latitude=1.3521&longitude=103.8198&current=precipitation,weather_code"
        res = requests.get(url, timeout=5)
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
