import datetime
import os
import time
import concurrent.futures
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

# Initialize Database & Clients conditionally based on available keys
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

google_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None
openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None

# App UI Configuration
st.set_page_config(page_title="AI Sports Science Coach • Pro Suite", page_icon="🚴‍♂️", layout="wide")

st.title("🚴‍♂️ AI Sports Science Coach • Ultimate Endurance Command Center")
st.caption("Powered by Intervals.icu, Supabase, Multi-LLM Fallbacks, and Advanced Performance Tools")

# --- MULTI-PROVIDER CROSS-PROVIDER FALLBACK ROUTER ---
def execute_multiprovider_generation(prompt, preferred_provider="⚡ Auto-Fallback Chain", is_stream=False):
    """
    Tries the preferred provider first, then cascades across OpenAI, Anthropic, 
    and Google Gemini to completely bypass service interruptions and 503 spikes.
    """
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
        models = ["gemini-3.7-flash", "gemini-3.6-flash"]
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

    last_error = None
    for name, action in active_stack:
        try:
            return action()
        except Exception as e:
            last_error = e
            continue

    raise Exception(f"All active AI providers failed. Last error: {str(last_error)}")


# --- AUTHENTICATION FLOW (SUPABASE AUTH) ---
if "user" not in st.session_state:
    st.session_state.user = None

if not st.session_state.user:
    st.markdown("### 🔐 Secure Athlete Portal Login")
    st.caption("Log in or create an account to access your personal, isolated training command center.")
    
    auth_tab1, auth_tab2 = st.tabs(["Log In", "Sign Up"])
    
    with auth_tab1:
        login_email = st.text_input("Email", key="login_email")
        login_pass = st.text_input("Password", type="password", key="login_pass")
        if st.button("Log In", type="primary"):
            try:
                res = supabase.auth.sign_in_with_password({"email": login_email, "password": login_pass})
                st.session_state.user = res.user
                st.success("Login successful! Loading command center...")
                st.rerun()
            except Exception as e:
                st.error(f"Login failed: {e}")
                
    with auth_tab2:
        signup_email = st.text_input("Email", key="signup_email")
        signup_pass = st.text_input("Password", type="password", key="signup_pass")
        if st.button("Create Account", type="primary"):
            try:
                res = supabase.auth.sign_up({"email": signup_email, "password": signup_pass})
                st.session_state.user = res.user
                st.success("Account created successfully! Welcome aboard.")
                st.rerun()
            except Exception as e:
                st.error(f"Sign up failed: {e}")
    st.stop()

USER_ID = st.session_state.user.id

# --- CHECK IF USER HAS CONFIGURED INTERVALS.ICU CREDENTIALS ---
user_profile = None
try:
    profile_res = supabase.table("profiles").select("*").eq("id", USER_ID).execute()
    if profile_res.data:
        user_profile = profile_res.data[0]
except Exception:
    pass

if not user_profile or not user_profile.get("intervals_api_key") or not user_profile.get("intervals_athlete_id"):
    st.markdown("---")
    st.subheader("⚙️ Intervals.icu Account Setup")
    st.write("To pull your personal Garmin and training data, please enter your Intervals.icu API Key and Athlete ID.")
    st.markdown("[Find your Intervals.icu API Key here (scroll to bottom of Settings)](https://intervals.icu/settings)")
    
    with st.form("setup_form"):
        input_api_key = st.text_input("Intervals.icu API Key", type="password")
        input_athlete_id = st.text_input("Intervals.icu Athlete ID (e.g., i12345 or your username)")
        submitted = st.form_submit_button("Save & Launch Command Center")
        
        if submitted:
            if input_api_key and input_athlete_id:
                try:
                    supabase.table("profiles").upsert({
                        "id": USER_ID,
                        "intervals_api_key": input_api_key.strip(),
                        "intervals_athlete_id": input_athlete_id.strip()
                    }).execute()
                    st.success("Configuration saved! Refreshing...")
                    st.rerun()
                except Exception as e:
                    st.error(f"Failed to save profile: {e}")
            else:
                st.warning("Please provide both your API Key and Athlete ID.")
    st.stop()

INTERVALS_API_KEY = user_profile["intervals_api_key"]
ATHLETE_ID = user_profile["intervals_athlete_id"]

# --- 1. DATA FETCHING FUNCTIONS ---
@st.cache_data(ttl=300, show_spinner=False) 
def fetch_intervals_wellness(athlete_id, api_key):
  try:
    end_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/wellness?oldest={start_date}&newest={end_date}"
    res = requests.get(url, auth=("API_KEY", api_key), timeout=8)
    return res.json() if res.status_code == 200 and res.json() else []
  except Exception:
    return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_recent_activities(athlete_id, api_key):
  try:
    end_date = datetime.date.today().isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/activities?oldest={start_date}&newest={end_date}"
    res = requests.get(url, auth=("API_KEY", api_key), timeout=8)
    return res.json() if res.status_code == 200 else []
  except Exception:
    return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_athlete_stats(athlete_id, api_key):
  try:
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}"
    res = requests.get(url, auth=("API_KEY", api_key), timeout=8)
    return res.json() if res.status_code == 200 else {}
  except Exception:
    return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_planned_workouts(athlete_id, api_key):
  try:
    end_date = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events?oldest={start_date}&newest={end_date}"
    res = requests.get(url, auth=("API_KEY", api_key), timeout=8)
    return res.json() if res.status_code == 200 else []
  except Exception:
    return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_power_curve(athlete_id, api_key):
  try:
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/power-curves?curves=42d&type=Ride"
    res = requests.get(url, auth=("API_KEY", api_key), timeout=8)
    return res.json() if res.status_code == 200 else {}
  except Exception:
    return []

# --- PARALLEL DATA FETCHING ---
with st.spinner("Syncing live metrics & power duration curve from Intervals.icu..."):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_wellness = executor.submit(fetch_intervals_wellness, ATHLETE_ID, INTERVALS_API_KEY)
        future_activities = executor.submit(fetch_recent_activities, ATHLETE_ID, INTERVALS_API_KEY)
        future_stats = executor.submit(fetch_athlete_stats, ATHLETE_ID, INTERVALS_API_KEY)
        future_planned = executor.submit(fetch_planned_workouts, ATHLETE_ID, INTERVALS_API_KEY)
        future_power = executor.submit(fetch_power_curve, ATHLETE_ID, INTERVALS_API_KEY)

        wellness_list = future_wellness.result()
        activities_data = future_activities.result()
        athlete_stats = future_stats.result()
        planned_data = future_planned.result()
        power_curve_data = future_power.result()

# Extract Metrics Safely
ctl, atl, tsb, sleep_score, hrv = 0, 0, 0, 0, 0
if wellness_list:
    latest_record = wellness_list[-1]
    ctl = latest_record.get("ctl", 0)
    atl = latest_record.get("atl", 0)
    tsb = latest_record.get("tsb", 0)
    for record in reversed(wellness_list):
        if sleep_score == 0 and record.get("sleepScore"):
            sleep_score = record.get("sleepScore")
        if hrv == 0 and record.get("hrv"):
            hrv = record.get("hrv")

athlete_zones = {
    "ftp": athlete_stats.get("ftp", athlete_stats.get("icu_ftp", 250)),
    "max_hr": athlete_stats.get("max_hr", 190)
}

# --- 2. SESSION STATE & CONFIG ---
if "performance_goals" not in st.session_state:
  st.session_state.performance_goals = "Maintain aerobic base, peak for upcoming events, and balance fatigue."

if "event_date" not in st.session_state:
  st.session_state.event_date = datetime.date.today() + datetime.timedelta(days=60)

if "weekly_report" not in st.session_state:
  st.session_state.weekly_report = None

if "gear_items" not in st.session_state:
    st.session_state.gear_items = [
        {"name": "Continental GP5000 Tires (28mm)", "distance_km": 1450, "max_km": 4000},
        {"name": "Shimano Dura-Ace Chain", "distance_km": 2100, "max_km": 3500},
        {"name": "Shimano Dura-Ace Cassette (11-34)", "distance_km": 4200, "max_km": 10000},
        {"name": "BBInfinite T47a Ceramic Bottom Bracket", "distance_km": 4200, "max_km": 15000}
    ]

if "messages" not in st.session_state:
    try:
        response = supabase.table("chat_messages").select("*").eq("user_id", USER_ID).order("created_at").execute()
        db_messages = response.data
        if db_messages:
            st.session_state.messages = [{"role": msg["role"], "content": msg["content"]} for msg in db_messages]
        else:
            st.session_state.messages = [{
                "role": "model",
                "content": f"Hello! Telemetry & Power Curve loaded securely. Ask me to review target feasibility, build a workout, or push workouts to your calendar!"
            }]
    except Exception:
        st.session_state.messages = [{"role": "model", "content": "Hello! Running in local fallback mode."}]

with st.sidebar:
  st.write(f"👤 Logged in as: **{st.session_state.user.email}**")
  
  st.markdown("---")
  st.header("🧠 AI Provider Settings")
  selected_provider = st.selectbox(
      "Preferred AI Engine",
      ["⚡ Auto-Fallback Chain", "OpenAI GPT", "Anthropic Claude", "Google Gemini"],
      help="Select your primary LLM engine with automatic multi-provider cross-fallback."
  )

  if st.button("Log Out"):
      supabase.auth.sign_out()
      st.session_state.user = None
      st.rerun()

  st.markdown("---")
  st.header("🎯 Target Event & Goals")
  new_goal = st.text_area("Update your current goals:", value=st.session_state.performance_goals)
  target_event = st.date_input("Target Event Date:", value=st.session_state.event_date)

  if st.button("Save Configuration"):
    st.session_state.performance_goals = new_goal
    st.session_state.event_date = target_event
    st.success("Configuration updated!")
    st.rerun()

  st.markdown("---")
  st.header("📊 Weekly Check-In")
  if st.button("Run Weekly Progress Report"):
    with st.spinner("Analyzing performance trends across multi-LLM router..."):
      report_prompt = (
          "Generate a formal Weekly Progress Report. Review past 14 days of "
          f"completed activities ({activities_data}) against planned calendar events ({planned_data}). "
          f"Analyze overall metrics ({athlete_stats}), Power Duration Curve profile ({power_curve_data}), "
          f"and recovery trends (Sleep: {sleep_score}, HRV: {hrv}) against goals: "
          f"'{st.session_state.performance_goals}' and event date ({st.session_state.event_date}). "
          "Critique pacing compliance and suggest adjustments."
      )
      
      try:
          report_text, model_used = execute_multiprovider_generation(report_prompt, preferred_provider=selected_provider, is_stream=False)
          st.session_state.weekly_report = f"{report_text}\n\n*(Generated via: {model_used})*"
          st.rerun()
      except Exception as e:
          st.error(f"Could not generate report: {e}")

# Calculate Readiness & Days
if tsb < -25 or (sleep_score > 0 and sleep_score < 60):
  readiness_status = "🔴 RED - RECOVERY REQUIRED"
  readiness_advice = "High fatigue detected. Pivot to active recovery or rest."
elif -25 <= tsb <= 5 and sleep_score >= 70:
  readiness_status = "🟢 GREEN - PRIMED FOR HARD SESSION"
  readiness_advice = "Body is well-adapted and ready for high intensity."
else:
  readiness_status = "🟡 YELLOW - AEROBIC / ZONE 2"
  readiness_advice = "Keep workouts structured in Zone 2 or light endurance."

days_to_event = (st.session_state.event_date - datetime.date.today()).days


# --- 3. TABBED NAVIGATION SUITE ---
tab_dash, tab_coach, tab_gear, tab_fuel, tab_fit, tab_cal = st.tabs([
    "📊 Command Center", 
    "🤖 AI Coach & Builder", 
    "🛠️ Gear Tracker",
    "⚡ Fueling Calculator",
    "📈 FIT Analyzer",
    "📅 Calendar & Compliance"
])

# ================= TAB 1: COMMAND CENTER =================
with tab_dash:
    st.markdown("### Daily Readiness & Training Load")
    col_r1, col_r2 = st.columns([2, 1])
    with col_r1:
      st.subheader(f"Status: {readiness_status}")
      st.info(readiness_advice)
    with col_r2:
      st.subheader("🏁 Event Countdown")
      st.metric("Days to Target Peak", f"{days_to_event} Days")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fitness (CTL)", round(ctl, 1))
    m2.metric("Fatigue (ATL)", round(atl, 1))
    m3.metric("Form (TSB)", round(tsb, 1))
    m4.metric("Sleep Score", f"{sleep_score}/100" if sleep_score > 0 else "N/A")

    # --- FEATURE 5: MORNING AUDIO BRIEFING (TTS) ---
    st.markdown("---")
    st.subheader("🎙️ AI Morning Audio Briefing")
    st.caption("Generate an synthesized 60-second audio briefing summarizing your recovery, sleep score, and daily focus.")
    
    if st.button("🔊 Generate Morning Briefing Audio", type="primary"):
        if not openai_client:
            st.error("OpenAI API key is required to generate audio briefings using TTS.")
        else:
            with st.spinner("Synthesizing coaching voice brief..."):
                brief_script = (
                    f"Good morning! Here is your daily coaching brief. "
                    f"Your current readiness status is {readiness_status}. "
                    f"Fitness CTL is {round(ctl, 1)}, Fatigue ATL is {round(atl, 1)}, and Form TSB is {round(tsb, 1)}. "
                    f"Your last recorded sleep score is {sleep_score} out of 100. "
                    f"Recommendation for today: {readiness_advice}. Train smart and stay aero!"
                )
                try:
                    speech_response = openai_client.audio.speech.create(
                        model="tts-1",
                        voice="alloy",
                        input=brief_script
                    )
                    audio_bytes = speech_response.content
                    st.audio(audio_bytes, format="audio/mp3")
                    st.success("Audio briefing generated successfully!")
                except Exception as e:
                    st.error(f"Failed to generate audio: {e}")

    try:
        fig_gauge = go.Figure(go.Indicator(
            mode = "gauge+number",
            value = tsb,
            domain = {'x': [0, 1], 'y': [0, 1]},
            title = {'text': "Form (TSB) Spectrum"},
            gauge = {
                'axis': {'range': [-50, 30]},
                'bar': {'color': "black"},
                'steps' : [
                    {'range': [-50, -25], 'color': "rgba(255, 0, 0, 0.4)"}, 
                    {'range': [-25, -10], 'color': "rgba(0, 128, 0, 0.5)"}, 
                    {'range': [-10, 5], 'color': "rgba(255, 255, 0, 0.5)"},  
                    {'range': [5, 30], 'color': "rgba(0, 0, 255, 0.4)"}     
                ]
            }
        ))
        fig_gauge.update_layout(height=250, margin=dict(l=20, r=20, t=30, b=10))
        st.plotly_chart(fig_gauge, use_container_width=True)
    except Exception:
        pass

    if activities_data:
      try:
        df_act = pd.DataFrame(activities_data)
        if "start_date_local" in df_act.columns and "icu_training_load" in df_act.columns:
          df_act["Date"] = pd.to_datetime(df_act["start_date_local"]).dt.date
          chart_data = df_act.groupby("Date")["icu_training_load"].sum().reset_index()

          fig = go.Figure()
          fig.add_trace(go.Bar(
              x=chart_data["Date"], y=chart_data["icu_training_load"],
              name="Daily TSS", marker_color="#1f77b4"
          ))
          fig.update_layout(
              title="14-Day Training Load (TSS) Distribution",
              xaxis_title="Date", yaxis_title="TSS", height=250,
              margin=dict(l=20, r=20, t=30, b=20),
          )
          st.plotly_chart(fig, use_container_width=True)
      except Exception:
        pass

    if st.session_state.weekly_report:
      with st.expander("📅 Latest Weekly Progress Report", expanded=True):
        st.markdown(st.session_state.weekly_report)
        if st.button("Clear Report"):
          st.session_state.weekly_report = None
          st.rerun()


# ================= TAB 2: AI COACH & WORKOUT BUILDER =================
with tab_coach:
    st.markdown("### Interactive AI Sports Scientist")
    st.caption("Ask for target reviews, structured workouts, or MyWhoosh `.zwo` exports. Push workouts directly to your Intervals.icu calendar.")

    for i, message in enumerate(st.session_state.messages):
      display_text = message["content"]
      has_workout = "<workout_file>" in display_text
      if has_workout:
          display_text = display_text.split("<workout_file>")[0].strip()

      with st.chat_message(message["role"]):
        st.markdown(display_text)
        
        if has_workout and message["role"] == "model":
            try:
                workout_xml = message["content"].split("<workout_file>")[1].split("</workout_file>")[0].strip()
                workout_xml = workout_xml.replace("```xml", "").replace("
