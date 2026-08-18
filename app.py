import datetime
import os
import time
from dotenv import load_dotenv
from google import genai
import requests
import streamlit as st

# Load environment variables safely
try:
  load_dotenv()
except ImportError:
  pass

# Grab keys from Streamlit Secrets or environment
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
INTERVALS_API_KEY = st.secrets.get("INTERVALS_API_KEY") or os.getenv("INTERVALS_API_KEY")
ATHLETE_ID = st.secrets.get("INTERVALS_ATHLETE_ID") or os.getenv("INTERVALS_ATHLETE_ID")

if not GEMINI_API_KEY:
  st.error("❌ GEMINI_API_KEY is missing! Configure it in Streamlit Cloud Secrets.")
  st.stop()

client = genai.Client(api_key=GEMINI_API_KEY)

# App UI Configuration
st.set_page_config(page_title="AI Sports Science Coach", page_icon="🚴‍♂️", layout="wide")
st.title("🚴‍♂️ AI Sports Science Coach")
st.caption("Live Endurance Performance Engine • Powered by Garmin & Intervals.icu")

# --- 1. DATA FETCHING FUNCTIONS ---
# We use shorter TTLs and explicitly format the dates so Intervals API accepts them
@st.cache_data(ttl=300, show_spinner=False) 
def fetch_intervals_wellness():
  try:
    end_date = datetime.date.today().isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness?oldest={start_date}&newest={end_date}"
    res = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
    if res.status_code == 200 and res.json():
        return res.json()[-1] # Return the most recent day's wellness/load data
    return {}
  except Exception:
    return {}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_recent_activities():
  try:
    end_date = datetime.date.today().isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities?oldest={start_date}&newest={end_date}"
    res = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
    return res.json() if res.status_code == 200 else []
  except Exception:
    return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_athlete_stats():
  try:
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
    res = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
    return res.json() if res.status_code == 200 else {}
  except Exception:
    return {}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_planned_workouts():
  try:
    end_date = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events?oldest={start_date}&newest={end_date}"
    res = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
    return res.json() if res.status_code == 200 else []
  except Exception:
    return []

# Fetch Data
wellness_data = fetch_intervals_wellness()
activities_data = fetch_recent_activities()
athlete_stats = fetch_athlete_stats()
planned_data = fetch_planned_workouts()

# --- 2. EXTRACT METRICS PROPERLY ---
# Intervals API stores CTL/ATL/TSB in the wellness payload, and FTP in the athlete stats payload
ctl = wellness_data.get("ctl", 0)
atl = wellness_data.get("atl", 0)
tsb = wellness_data.get("tsb", 0)
sleep_score = wellness_data.get("sleepScore", 0)
hrv = wellness_data.get("hrv", 0)

athlete_zones = {
    "ftp": athlete_stats.get("ftp", athlete_stats.get("icu_ftp", "Unknown")),
    "max_hr": athlete_stats.get("max_hr", "Unknown")
}
