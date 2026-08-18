import datetime
import os
from dotenv import load_dotenv
from google import genai
from google.genai.errors import APIError, ServerError
import requests
import streamlit as st

# Load environment variables safely for local or cloud deployment
try:
  from dotenv import load_dotenv

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

# Initialize Gemini Chat Session once with complete context
if "chat_session" not in st.session_state:
  system_instruction = f"""
    You are the Fitness Coach App, an elite endurance and sports science coach specializing in cycling and running. 
    You have direct access to the athlete's comprehensive training data synced from Garmin via Intervals.icu.
    
    OVERALL FITNESS & TRAINING LOAD (CTL / ATL / TSB Form):
    {athlete_stats}

    TODAY'S RECOVERY & WELLNESS DATA (Sleep, HRV, RHR):
    {wellness_data}

    RECENT ACTIVITIES (Past 7 Days - rides, runs, power, distance):
    {activities_data}

    Your job is to:
    1. Act as an expert sports scientist. Evaluate their training status based on their Form (TSB), Fitness (CTL), Fatigue (ATL), sleep, and HRV.
    2. Answer questions about training, pacing, fueling, recovery, and workout adjustments for running and cycling.
    3. Reference their actual numbers when giving advice on whether they should train hard, keep it easy, or rest.
    """

  st.session_state.chat_session = client.chats.create(
      model="gemini-3.6-flash",
      config=genai.types.GenerateContentConfig(
          system_instruction=system_instruction,
      ),
  )

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

# Accept user input
if prompt := st.chat_input("Ask your coach anything..."):
  st.session_state.messages.append({"role": "user", "content": prompt})
  with st.chat_message("user"):
    st.markdown(prompt)

  with st.chat_message("model"):
    with st.spinner("Coach is analyzing your training status..."):
      try:
        response = st.session_state.chat_session.send_message(prompt)
        st.markdown(response.text)
        st.session_state.messages.append(
            {"role": "model", "content": response.text}
        )
      except (ServerError, APIError) as e:
        st.warning(
            f"⚠️ The AI service encountered a temporary issue: {e}. Please wait"
            " a moment and try sending your message again."
        )
      except Exception as e:
        st.error(f"An unexpected error occurred: {e}")
