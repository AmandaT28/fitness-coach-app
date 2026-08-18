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
INTERVALS_API_KEY = st.secrets.get("INTERVALS_API_KEY") or os.getenv(
    "INTERVALS_API_KEY"
)
ATHLETE_ID = st.secrets.get("INTERVALS_ATHLETE_ID") or os.getenv(
    "INTERVALS_ATHLETE_ID"
)

if not GEMINI_API_KEY:
  st.error(
      "❌ GEMINI_API_KEY is missing! Configure it in Streamlit Cloud Secrets."
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


# Fetch functions with short 5-second timeouts to avoid hanging
@st.cache_data(ttl=3600, show_spinner=False)
def fetch_intervals_wellness():
  try:
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness.json"
    res = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=5)
    return res.json()[-1] if res.status_code == 200 and res.json() else {}
  except Exception:
    return {}


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_recent_activities():
  try:
    end_date = datetime.date.today()
    start_date = end_date - datetime.timedelta(days=14)
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities.json?oldest={start_date}&newest={end_date}"
    res = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=5)
    return res.json() if res.status_code == 200 else []
  except Exception:
    return []


@st.cache_data(ttl=3600, show_spinner=False)
def fetch_athlete_stats():
  try:
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
    res = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=5)
    return res.json() if res.status_code == 200 else {}
  except Exception:
    return {}


# Quick initial load
wellness_data = fetch_intervals_wellness()
activities_data = fetch_recent_activities()
athlete_stats = fetch_athlete_stats()

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
    with st.spinner("Analyzing performance trends..."):
      report_prompt = (
          "Generate a formal Weekly Progress Report. Review past 14 days of"
          f" activities ({activities_data}), overall metrics ({athlete_stats}),"
          f" and recovery trends ({wellness_data}) against goals:"
          f" '{st.session_state.performance_goals}' and event date"
          f" ({st.session_state.event_date})."
      )
      try:
        res = client.models.generate_content(
            model="gemini-2.5-flash", contents=report_prompt
        )
        st.session_state.weekly_report = res.text
      except Exception as e:
        st.error(f"Could not generate report: {e}")

# Calculate Readiness Badge & Event Countdown
ctl = athlete_stats.get("icu_ctl", 0) or 0
atl = athlete_stats.get("icu_atl", 0) or 0
tsb = ctl - atl
sleep_score = wellness_data.get("sleepScore", 80) or 80

if tsb < -25 or sleep_score < 60:
  readiness_status = "🔴 RED - RECOVERY REQUIRED"
  readiness_advice = "High fatigue detected. Pivot to active recovery or rest."
elif -25 <= tsb <= 5 and sleep_score >= 70:
  readiness_status = "🟢 GREEN - PRIMED FOR HARD SESSION"
  readiness_advice = "Body is well-adapted and ready for high intensity."
else:
  readiness_status = "🟡 YELLOW - AEROBIC / ZONE 2"
  readiness_advice = "Keep workouts structured in Zone 2 or light endurance."

days_to_event = (st.session_state.event_date - datetime.date.today()).days

# Top Dashboard Metrics & Readiness
st.markdown("---")
col_r1, col_r2 = st.columns([2, 1])
with col_r1:
  st.subheader(f"Daily Readiness: {readiness_status}")
  st.info(readiness_advice)
with col_r2:
  st.subheader("🏁 Event Countdown")
  st.metric("Days to Target Peak", f"{days_to_event} Days")

# Training Load Metrics Row
st.subheader("📈 Fitness, Fatigue & Form Metrics")
m1, m2, m3, m4 = st.columns(4)
m1.metric("Fitness (CTL)", round(ctl, 1))
m2.metric("Fatigue (ATL)", round(atl, 1))
m3.metric("Form (TSB)", round(tsb, 1))
m4.metric("Sleep Score", f"{sleep_score}/100")

# Lazy load Plotly chart only when data exists
if activities_data:
  try:
    import pandas as pd
    import plotly.graph_objects as go

    df_act = pd.DataFrame(activities_data)
    if (
        "start_date_local" in df_act.columns
        and "icu_training_load" in df_act.columns
    ):
      df_act["Date"] = pd.to_datetime(df_act["start_date_local"]).dt.date
      chart_data = (
          df_act.groupby("Date")["icu_training_load"].sum().reset_index()
      )

      fig = go.Figure()
      fig.add_trace(
          go.Bar(
              x=chart_data["Date"],
              y=chart_data["icu_training_load"],
              name="Daily TSS",
              marker_color="#1f77b4",
          )
      )
      fig.update_layout(
          title="14-Day Training Load (TSS) Distribution",
          xaxis_title="Date",
          yaxis_title="TSS",
          height=250,
          margin=dict(l=20, r=20, t=30, b=20),
      )
      st.plotly_chart(fig, use_container_width=True)
  except Exception:
    pass

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
          f"Hello! I'm your AI Sports Scientist. Based on your Form ({round(tsb, 1)} TSB) and Readiness ({readiness_status}), I'm ready to review your training."
      ),
  }]

for message in st.session_state.messages:
  with st.chat_message(message["role"]):
    st.markdown(message["content"])

if prompt := st.chat_input(
    "Ask your coach about workouts, fueling, or pacing..."
):
  st.session_state.messages.append({"role": "user", "content": prompt})
  with st.chat_message("user"):
    st.markdown(prompt)

  with st.chat_message("model"):
    with st.spinner("Analyzing metrics..."):
      context_payload = f"""
            You are an elite endurance sports science coach.
            ATHLETE PROFILE: Cervélo Soloist (Size 48), 160mm crankset, power meter. Flexible flat feet, hypermobility.
            GOALS: {st.session_state.performance_goals} (Target Event in {days_to_event} days)
            READINESS: {readiness_status} | CTL: {ctl} | ATL: {atl} | TSB: {tsb} | Sleep: {sleep_score}
            RECENT ACTIVITIES: {activities_data}
            """
      for msg in st.session_state.messages:
        context_payload += f"\n{msg['role'].upper()}: {msg['content']}\n"

      try:
        response = client.models.generate_content(
            model="gemini-2.5-flash", contents=context_payload
        )
        st.markdown(response.text)
        st.session_state.messages.append(
            {"role": "model", "content": response.text}
        )
      except Exception:
        st.warning("⚠️ High traffic. Please retry in a few seconds.")
