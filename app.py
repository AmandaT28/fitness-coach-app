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
    page_title="AI Sports Science Coach", page_icon="🚴‍♂️", layout="wide"
)

st.title("🚴‍♂️ AI Sports Science Coach")
st.caption(
    "Live Endurance Performance Engine • Powered by Garmin & Intervals.icu"
)


# Fetch latest wellness data (Sleep, HRV, RHR)
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_intervals_wellness():
  url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness.json"
  response = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
  if response.status_code != 200:
    return None
  data = response.json()
  return data[-1] if data else None


# Fetch recent activities (Last 14 days for trend visualization and execution analysis)
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_recent_activities():
  end_date = datetime.date.today()
  start_date = end_date - datetime.timedelta(days=14)
  url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities.json?oldest={start_date}&newest={end_date}"
  response = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
  if response.status_code != 200:
    return []
  return response.json()


# Fetch overall Fitness/Load summary (CTL/Fitness, ATL/Fatigue, TSB/Form)
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_athlete_stats():
  url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
  response = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
  if response.status_code != 200:
    return {}
  return response.json()


# Fetch Power and Heart Rate Zones
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_athlete_zones():
  url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/folders"
  response = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=10)
  if response.status_code != 200:
    return {}
  return response.json()


with st.spinner("Syncing live Garmin & Intervals.icu metrics..."):
  wellness_data = fetch_intervals_wellness() or {}
  activities_data = fetch_recent_activities()
  athlete_stats = fetch_athlete_stats()
  athlete_zones = fetch_athlete_zones()

# Initialize session state variables
if "performance_goals" not in st.session_state:
  st.session_state.performance_goals = (
      "Maintain aerobic base, peak for upcoming events, and balance fatigue"
      " (TSB)."
  )

if "event_date" not in st.session_state:
  st.session_state.event_date = datetime.date.today() + datetime.timedelta(
      days=60
  )

if "weekly_report" not in st.session_state:
  st.session_state.weekly_report = None

# Sidebar UI Configuration
with st.sidebar:
  st.header("🎯 Target Event & Goals")
  new_goal = st.text_area(
      "Update your current goals:", value=st.session_state.performance_goals
  )
  target_event = st.date_input(
      "Target Event Date:", value=st.session_state.event_date
  )

  if st.button("Save Configuration"):
    st.session_state.performance_goals = new_goal
    st.session_state.event_date = target_event
    st.success("Configuration updated!")
    st.rerun()

  st.markdown("---")
  st.header("📊 Weekly Check-In")
  if st.button("Run Weekly Progress Report"):
    with st.spinner("Analyzing performance trends and execution..."):
      report_prompt = (
          "Generate a formal Weekly Progress Report. Review the past 14 days"
          f" of activities ({activities_data}), overall fitness metrics (CTL,"
          f" ATL, TSB: {athlete_stats}), and recovery trends"
          f" ({wellness_data}) against my stated goals:"
          f" '{st.session_state.performance_goals}' and target event date"
          f" ({st.session_state.event_date}). Include compliance critique,"
          " fatigue warnings, and specific intra-workout fueling guidelines"
          " for the coming week."
      )

      try:
        report_response = client.models.generate_content(
            model="gemini-2.5-flash", contents=report_prompt
        )
        st.session_state.weekly_report = report_response.text
      except Exception as e:
        st.error(f"Could not generate report: {e}")

# Calculate Readiness Badge & Event Countdown
ctl = athlete_stats.get("icu_ctl", 0) or 0
atl = athlete_stats.get("icu_atl", 0) or 0
tsb = ctl - atl

sleep_score = wellness_data.get("sleepScore", 80) or 80
hrv = wellness_data.get("hrv", 50) or 50

# Logic for Readiness
if tsb < -25 or sleep_score < 60:
  readiness_status = "🔴 RED - RECOVERY REQUIRED"
  readiness_advice = (
      "High fatigue or suppressed sleep detected. Pivot to active recovery or"
      " rest today."
  )
elif -25 <= tsb <= 5 and sleep_score >= 70:
  readiness_status = "🟢 GREEN - PRIMED FOR HARD SESSION"
  readiness_advice = (
      "Body is well-adapted and ready for high-intensity intervals or threshold"
      " work."
  )
else:
  readiness_status = "🟡 YELLOW - AEROBIC / ZONE 2"
  readiness_advice = (
      "Moderate load balance. Keep workouts structured in Zone 2 or light"
      " endurance."
  )

days_to_event = (st.session_state.event_date - datetime.date.today()).days

# Top Dashboard Metrics & Readiness
st.markdown("---")
col_r1, col_r2 = st.columns([2, 1])

with col_r1:
  st.subheader(f"Daily Readiness: {readiness_status}")
  st.info(readiness_advice)

with col_r2:
  st.subheader("🏁 Event Countdown")
  st.metric(
      "Days to Target Peak",
      f"{days_to_event} Days",
      delta="Taper Period Active" if days_to_event <= 10 else "Build Phase",
  )

# Training Load Metrics Row
st.subheader("📈 Fitness, Fatigue & Form Metrics")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Fitness (CTL)", round(ctl, 1))
m2.metric("Fatigue (ATL)", round(atl, 1))
m3.metric(
    "Form (TSB)",
    round(tsb, 1),
    delta="Fresh" if tsb > 0 else "Fatigued",
    delta_color="normal" if tsb > 0 else "inverse",
)
m4.metric("Sleep Score", f"{sleep_score}/100")

# Training Load Plotly Chart
if activities_data:
  df_act = pd.DataFrame(activities_data)
  if "start_date_local" in df_act.columns and "icu_training_load" in df_act.columns:
    df_act["Date"] = pd.to_datetime(df_act["start_date_local"]).dt.date
    chart_data = (
        df_act.groupby("Date")["icu_training_load"].sum().reset_index()
    )

    fig = go.Figure()
    fig.add_trace(
        go.Bar(
            x=chart_data["Date"],
            y=chart_data["icu_training_load"],
            name="Daily TSS / Load",
            marker_color="#1f77b4",
        )
    )
    fig.update_layout(
        title="14-Day Training Load (TSS) Distribution",
        xaxis_title="Date",
        yaxis_title="Training Stress Score (TSS)",
        height=300,
        margin=dict(l=20, r=20, t=40, b=20),
    )
    st.plotly_chart(fig, use_container_width=True)

# Display Weekly Report if active
if st.session_state.weekly_report:
  with st.expander("📅 Latest Weekly Progress Report", expanded=True):
    st.markdown(st.session_state.weekly_report)
    if st.button("Clear Report"):
      st.session_state.weekly_report = None
      st.rerun()

st.markdown("---")
st.subheader("💬 Interactive Sports Science Coach")

if "messages" not in st.session_state:
  st.session_state.messages = [{
      "role": "model",
      "content": (
          f"Hello! I'm your AI Sports Scientist. Based on your current Form"
          f" ({round(tsb, 1)} TSB) and Readiness ({readiness_status}), I'm"
          " ready to review your pacing, prescribe fueling plans, or analyze"
          " recent workouts."
      ),
  }]

# Display chat history
for message in st.session_state.messages:
  with st.chat_message(message["role"]):
    st.markdown(message["content"])

# Stateless Chat Input Loop with Error Handling & Retry Logic
if prompt := st.chat_input("Ask your coach about workouts, fueling, or pacing..."):
  st.session_state.messages.append({"role": "user", "content": prompt})
  with st.chat_message("user"):
    st.markdown(prompt)

  with st.chat_message("model"):
    with st.spinner("Analyzing metrics and formulating prescription..."):
      context_payload = f"""
            You are an elite endurance sports science coach specializing in cycling and running. 
            Evaluate the athlete's performance, track improvements, and manage a continuous feedback loop.

            ATHLETE PROFILE & EQUIPMENT CONTEXT:
            - Bike Setup: Cervélo Soloist (Size 48), custom cockpit, S-Works Power Pro Mirror saddle, Magene TEO P515 power meter/ 160mm crankset.
            - Physical Considerations: Flexible flat feet, some hypermobility.

            CURRENT PERFORMANCE GOALS & EVENT COUNTDOWN:
            - Goals: {st.session_state.performance_goals}
            - Target Event Date: {st.session_state.event_date} ({days_to_event} days remaining)

            TODAY'S READINESS & TRAINING LOAD:
            - Readiness Status: {readiness_status}
            - Fitness (CTL): {ctl} | Fatigue (ATL): {atl} | Form (TSB): {tsb}
            - Sleep Score: {sleep_score} | HRV: {hrv}

            POWER & HEART RATE ZONES DATA:
            {athlete_zones}

            RECENT ACTIVITIES & COMPLIANCE (Past 14 Days):
            {activities_data}

            COACHING INSTRUCTIONS:
            1. Provide precise, zone-based training advice and pacing recommendations.
            2. When prescribing sessions over 60 mins, include a distinct Intra-Workout Fueling Card with specific carb/hr and fluid targets.
            3. Critique post-workout pacing execution against their goals.
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
