import datetime
import os
import time
from dotenv import load_dotenv
from google import genai
import pandas as pd
import plotly.graph_objects as go
import requests
import streamlit as st

# Load environment variables safely for local or cloud deployment
try:
  load_dotenv()
except ImportError:
  pass

# Grab keys from Streamlit Secrets or environment
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
INTERVALS_API_KEY = st.secrets.get("INTERVALS_API_KEY") or os.getenv(
    "INTERVALS_API_KEY"
)
ATHLETE_ID = st.secrets.get("INTERVALS_ATHLETE_ID") or os.getenv(
    "INTERVALS_ATHLETE_ID"
)

# Validate that the API key exists before initializing the client
if not GEMINI_API_KEY:
  st.error(
      "❌ GEMINI_API_KEY is missing! Please configure it in your Streamlit Cloud"
      " Secrets."
  )
  st.stop()

client = genai.Client(api_key=GEMINI_API_KEY)

# App UI Configuration
st.set_page_config(
    page_title="Fitness Coach App", page_icon="🚴‍♂️", layout="wide"
)

st.title("🚴‍♂️ Fitness Coach App")
st.write(
    "Your personalized AI sports scientist for running, cycling, and recovery."
)


# Fetch latest wellness data (Sleep, HRV, RHR)
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_intervals_wellness():
  url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness.json"
  response = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY))
  if response.status_code != 200:
    return None
  data = response.json()
  return data[-1] if data else None


# Fetch recent activities (Last 7 days of workouts, power, distance)
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_recent_activities():
  end_date = datetime.date.today()
  start_date = end_date - datetime.timedelta(days=7)
  url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities.json?oldest={start_date}&newest={end_date}"
  response = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY))
  if response.status_code != 200:
    return []
  return response.json()


# Fetch overall Fitness/Load summary (CTL/Fitness, ATL/Fatigue, TSB/Form)
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_athlete_stats():
  url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
  response = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY))
  if response.status_code != 200:
    return {}
  return response.json()


# Fetch Power and Heart Rate Zones
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_athlete_zones():
  url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/folders"
  response = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY))
  if response.status_code != 200:
    return {}
  return response.json()


with st.spinner("Syncing complete Garmin & Intervals.icu data..."):
  wellness_data = fetch_intervals_wellness()
  activities_data = fetch_recent_activities()
  athlete_stats = fetch_athlete_stats()
  athlete_zones = fetch_athlete_zones()

# Initialize session state for performance goals and weekly reports
if "performance_goals" not in st.session_state:
  st.session_state.performance_goals = (
      "Maintain aerobic base, peak for upcoming events, and balance fatigue"
      " (TSB)."
  )

if "weekly_report" not in st.session_state:
  st.session_state.weekly_report = None

# Sidebar UI for goals and Weekly Progress Check-In
with st.sidebar:
  st.header("🎯 Performance Goals")
  new_goal = st.text_area(
      "Update your current goals:", value=st.session_state.performance_goals
  )
  if st.button("Save Goals"):
    st.session_state.performance_goals = new_goal
    st.success("Goals updated!")
    st.rerun()

  st.markdown("---")
  st.header("📊 Weekly Check-In")
  if st.button("Run Weekly Progress Report"):
    with st.spinner("Analyzing weekly metrics and trends..."):
      report_prompt = (
          "Generate a formal Weekly Progress Report. Review the past 7 days"
          f" of activities ({activities_data}), overall fitness metrics (CTL,"
          f" ATL, TSB: {athlete_stats}), and recent recovery/wellness trends"
          f" ({wellness_data}) against my stated goals:"
          f" '{st.session_state.performance_goals}'. Highlight what went"
          " well, areas of fatigue accumulation, and actionable adjustments for"
          " the upcoming week."
      )

      try:
        report_response = client.models.generate_content(
            model="gemini-2.5-flash", contents=report_prompt
        )
        st.session_state.weekly_report = report_response.text
      except Exception as e:
        st.error(f"Could not generate report: {e}")

# Display Training Load Chart if data exists
if athlete_stats and "icu_ctl" in athlete_stats:
  st.subheader("📈 Training Load & Form Overview")
  col1, col2, col3 = st.columns(3)
  col1.metric("Fitness (CTL)", round(athlete_stats.get("icu_ctl", 0), 1))
  col2.metric("Fatigue (ATL)", round(athlete_stats.get("icu_atl", 0), 1))
  col3.metric(
      "Form (TSB)",
      round(
          athlete_stats.get("icu_ctl", 0) - athlete_stats.get("icu_atl", 0), 1
      ),
  )

# Display Weekly Report on the main screen if generated
if st.session_state.weekly_report:
  with st.expander("📅 Your Latest Weekly Progress Report", expanded=True):
    st.markdown(st.session_state.weekly_report)
    if st.button("Clear Report"):
      st.session_state.weekly_report = None
      st.rerun()

if "messages" not in st.session_state:
  st.session_state.messages = [{
      "role": "model",
      "content": (
          "Hello! I'm your Fitness Coach App. I've synced your complete Garmin"
          " fitness load, power zones, recent workouts, and recovery stats. Ask"
          " me anything about your training status!"
      ),
  }]

# Display chat history
for message in st.session_state.messages:
  with st.chat_message(message["role"]):
    st.markdown(message["content"])

# Chat Input & Stateless Context Execution (Bypasses 503 Chat Session Bottlenecks)
if prompt := st.chat_input("Ask your coach anything..."):
  st.session_state.messages.append({"role": "user", "content": prompt})
  with st.chat_message("user"):
    st.markdown(prompt)

  with st.chat_message("model"):
    with st.spinner("Coach is analyzing your training status..."):
      # Build full context payload incorporating updated profile & equipment context
      context_payload = f"""
            You are an elite endurance sports science coach specializing in cycling and running. 
            Evaluate the athlete's performance, track improvements, and manage a continuous feedback loop.

            ATHLETE PROFILE & EQUIPMENT CONTEXT:
            - Bike Setup: Cervélo Soloist (Size 48), custom cockpit, S-Works Power Pro Mirror saddle, Magene TEO P515 power meter/ 160mm crankset.
            - Physical Considerations: Flexible flat feet, some hypermobility.

            CURRENT PERFORMANCE GOALS:
            {st.session_state.performance_goals}

            OVERALL FITNESS & TRAINING LOAD (CTL / ATL / TSB Form):
            {athlete_stats}

            POWER & HEART RATE ZONES DATA:
            {athlete_zones}

            TODAY'S RECOVERY & WELLNESS DATA (Sleep, HRV, RHR):
            {wellness_data}

            RECENT ACTIVITIES (Past 7 Days - rides, runs, power, distance):
            {activities_data}

            CONVERSATION HISTORY:
            """
      for msg in st.session_state.messages:
        context_payload += (
            f"\n{msg['role'].upper()}: {msg['content']}\n"
        )

      response_text = None
      max_retries = 3
      retry_delay = 2

      for attempt in range(max_retries):
        try:
          response = client.models.generate_content(
              model="gemini-2.5-flash", contents=context_payload
          )
          response_text = response.text
          break
        except Exception as e:
          if "503" in str(e) or "UNAVAILABLE" in str(e):
            if attempt < max_retries - 1:
              time.sleep(retry_delay)
              retry_delay *= 2
              continue
          break

      if response_text:
        st.markdown(response_text)
        st.session_state.messages.append(
            {"role": "model", "content": response_text}
        )
      else:
        st.warning(
            "⚠️ Google's servers are experiencing high traffic. Please try"
            " sending your message again in a few seconds."
        )
