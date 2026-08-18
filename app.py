import datetime
import os
import time
from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError, ServerError
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
    page_title="Fitness Coach App", page_icon="🚴‍♂️", layout="centered"
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


with st.spinner("Syncing complete Garmin & Intervals.icu data..."):
  wellness_data = fetch_intervals_wellness()
  activities_data = fetch_recent_activities()
  athlete_stats = fetch_athlete_stats()

# Initialize session state for performance goals if it doesn't exist
if "performance_goals" not in st.session_state:
  st.session_state.performance_goals = (
      "Maintain aerobic base, peak for upcoming events, and balance fatigue"
      " (TSB)."
  )

# Sidebar UI for tracking and updating goals
with st.sidebar:
  st.header("🎯 Performance Goals")
  new_goal = st.text_area(
      "Update your current goals:", value=st.session_state.performance_goals
  )
  if st.button("Save Goals"):
    st.session_state.performance_goals = new_goal
    st.success("Goals updated! Your coach will adapt.")

# Enhanced System Instruction with Memory & Feedback Loop framework
system_instruction = f"""
    You are an elite endurance sports science coach specializing in cycling and running. You evaluate the athlete's performance, track improvements, and manage a continuous feedback loop.

    CURRENT PERFORMANCE GOALS:
    {st.session_state.performance_goals}

    OVERALL FITNESS & TRAINING LOAD (CTL / ATL / TSB Form):
    {athlete_stats}

    TODAY'S RECOVERY & WELLNESS DATA (Sleep, HRV, RHR):
    {wellness_data}

    RECENT ACTIVITIES (Past 7 Days - rides, runs, power, distance):
    {activities_data}

    FEEDBACK LOOP INSTRUCTIONS:
    1. Act as an expert sports scientist. Evaluate their training status based on their Form (TSB), Fitness (CTL), Fatigue (ATL), sleep, and HRV.
    2. Answer questions about training, pacing, fueling, recovery, and workout adjustments for running and cycling.
    3. Reference their actual numbers when giving advice on whether they should train hard, keep it easy, or rest.
    4. Formulate training plans utilising MyWhoosh indoor training, outdoor rides, runs, strength or gym work to work towards performance targets.
    5. Monitor, critique, and evaluate progress against their goals.
    """

# Initialize or re-create chat session if it doesn't exist (Prioritizing stable gemini-2.5-flash)
if "chat_session" not in st.session_state:
  models_to_try = ["gemini-2.5-flash", "gemini-3.7-flash", "gemini-3.6-flash"]
  chat_session = None

  for model_name in models_to_try:
    try:
      chat_session = client.chats.create(
          model=model_name,
          config=genai.types.GenerateContentConfig(
              system_instruction=system_instruction,
          ),
      )
      break
    except Exception:
      continue

  if not chat_session:
    st.error(
        "❌ All AI model endpoints are currently experiencing high traffic. Please"
        " try again in a moment."
    )
    st.stop()

  st.session_state.chat_session = chat_session

if "messages" not in st.session_state:
  st.session_state.messages = [{
      "role": "model",
      "content": (
          "Hello! I'm your Fitness Coach App. I've synced your complete Garmin"
          " fitness load, recent workouts, and recovery stats. Ask me anything"
          " about your training status or whether you should train today!"
      ),
  }]

# Display chat history
for message in st.session_state.messages:
  with st.chat_message(message["role"]):
    st.markdown(message["content"])

# Single clean chat input loop with 503 Auto-Retry logic
if prompt := st.chat_input("Ask your coach anything..."):
  st.session_state.messages.append({"role": "user", "content": prompt})
  with st.chat_message("user"):
    st.markdown(prompt)

  with st.chat_message("model"):
    with st.spinner("Coach is analyzing your training status..."):
      response_text = None
      max_retries = 3
      retry_delay = 2

      for attempt in range(max_retries):
        try:
          response = st.session_state.chat_session.send_message(prompt)
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
            "⚠️ Google's servers are experiencing temporary high traffic (503"
            " Unavailable). Please wait a moment and try sending your message"
            " again."
        )
