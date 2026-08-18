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

# Initialize Database & Clients
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
google_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None
openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None

# App UI Configuration
st.set_page_config(page_title="AI Sports Science Coach • Multi-Sport Elite Suite", page_icon="🚴‍♂️", layout="wide")

st.title("🚴‍♂️🏃‍♂️ AI Sports Science Coach • Multi-Sport, Strength & Automated Safety Suite")
st.caption("Powered by Intervals.icu, Supabase, Multi-LLM Fallbacks, and Automated Overtraining Protection")

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
    auth_tab1, auth_tab2 = st.tabs(["Log In", "Sign Up"])
    with auth_tab1:
        login_email = st.text_input("Email", key="login_email")
        login_pass = st.text_input("Password", type="password", key="login_pass")
        if st.button("Log In", type="primary"):
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
        if st.button("Create Account", type="primary"):
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
        submitted = st.form_submit_button("Save & Launch")
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
  except Exception: return {}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_planned_workouts(athlete_id, api_key):
  try:
    end_date = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
    url = f"https://intervals.icu/api/v1/athlete/{athlete_id}/events?oldest={start_date}&newest={end_date}"
    res = requests.get(url, auth=("API_KEY", api_key), timeout=8)
    return res.json() if res.status_code == 200 else []
  except Exception: return []

def fetch_weather_intelligence():
  try:
    url = "https://api.open-meteo.com/v1/forecast?latitude=1.3521&longitude=103.8198&current=temperature_2m,relative_humidity_2m,wind_speed_10m"
    res = requests.get(url, timeout=5)
    return res.json().get("current", {})
  except Exception: return {}

with st.spinner("Syncing multi-sport telemetry & safety metrics..."):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_wellness = executor.submit(fetch_intervals_wellness, ATHLETE_ID, INTERVALS_API_KEY)
        future_activities = executor.submit(fetch_recent_activities, ATHLETE_ID, INTERVALS_API_KEY)
        future_stats = executor.submit(fetch_athlete_stats, ATHLETE_ID, INTERVALS_API_KEY)
        future_planned = executor.submit(fetch_planned_workouts, ATHLETE_ID, INTERVALS_API_KEY)
        future_weather = executor.submit(fetch_weather_intelligence)

        wellness_list = future_wellness.result()
        activities_data = future_activities.result()
        athlete_stats = future_stats.result()
        planned_data = future_planned.result()
        weather_data = future_weather.result()

ctl, atl, tsb, sleep_score, hrv = 0, 0, 0, 0, 0
if wellness_list:
    latest = wellness_list[-1]
    ctl, atl, tsb = latest.get("ctl", 0), latest.get("atl", 0), latest.get("tsb", 0)
    for r in reversed(wellness_list):
        if sleep_score == 0 and r.get("sleepScore"): sleep_score = r.get("sleepScore")
        if hrv == 0 and r.get("hrv"): hrv = r.get("hrv")

# --- MULTI-SPORT GOALS CONFIG ---
if "goals" not in st.session_state:
    st.session_state.goals = {
        "primary_sport": "Cycling (Road)",
        "secondary_sport": "Running",
        "strength_sessions_per_week": 2,
        "event_name": "Target Gran Fondo & Half Marathon",
        "event_date": datetime.date.today() + datetime.timedelta(days=60),
        "kpi_target": "Maintain 4.2 W/kg cycling while building running aerobic base"
    }

if "webhook_url" not in st.session_state:
    st.session_state.webhook_url = ""

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "model", "content": "Hello! Multi-sport engine & automated safety sentinel active. Cycling + Running + S&C monitored."}]

if "debrief_logs" not in st.session_state: st.session_state.debrief_logs = []
if "periodization_review" not in st.session_state: st.session_state.periodization_review = None

with st.sidebar:
    st.write(f"👤 **{st.session_state.user.email}**")
    selected_provider = st.selectbox("AI Engine", ["⚡ Auto-Fallback Chain", "OpenAI GPT", "Anthropic Claude", "Google Gemini"])
    
    st.markdown("---")
    st.header("🚨 Safety & Push Notifications")
    st.session_state.webhook_url = st.text_input("Discord/Telegram Webhook URL", value=st.session_state.webhook_url, type="password", help="Enter a webhook URL to receive automated push alerts when TSB drops too low.")
    
    st.markdown("---")
    st.header("🎯 Multi-Sport & Strength Goals")
    with st.form("goal_form"):
        st.session_state.goals["primary_sport"] = st.selectbox("Primary Sport", ["Cycling (Road)", "Cycling (Time Trial)", "Gravel"], index=0)
        st.session_state.goals["secondary_sport"] = st.selectbox("Secondary Sport", ["Running", "Trail Running", "Swimming", "None"], index=0)
        st.session_state.goals["strength_sessions_per_week"] = st.slider("Strength Sessions / Week", 0, 4, 2)
        st.session_state.goals["event_name"] = st.text_input("Event / Objective", value=st.session_state.goals["event_name"])
        st.session_state.goals["kpi_target"] = st.text_input("KPI Target", value=st.session_state.goals["kpi_target"])
        st.session_state.goals["event_date"] = st.date_input("Target Date", value=st.session_state.goals["event_date"])
        if st.form_submit_button("Update Strategy"): st.success("Strategy updated.")

    st.markdown("---")
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.rerun()

    if st.button("Log Out"):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

days_to_event = (st.session_state.goals["event_date"] - datetime.date.today()).days

# --- AUTOMATED SAFETY EVALUATION ENGINE ---
def evaluate_safety_risk(tsb, strength_freq, secondary_sport):
    risk = "NORMAL"
    msg = "Training load is balanced across your sports and recovery."
    if tsb < -25 and strength_freq >= 2 and secondary_sport != "None":
        risk = "HIGH"
        msg = f"CRITICAL OVERREACHING RISK: TSB is deeply negative ({tsb:.1f}) while maintaining {secondary_sport} and {strength_freq}x weekly strength sessions. High risk of neuromuscular breakdown or overuse injury. Immediate recovery or strength tapering required."
    elif tsb < -15:
        risk = "MODERATE"
        msg = f"ELEVATED FATIGUE: Form TSB is {tsb:.1f}. Monitor running impact loads and leg strength volume closely this week."
    return risk, msg

def send_push_alert(webhook_url, message):
    if not webhook_url: return False
    try:
        payload = {"content": f"🚨 **AI Coach Safety Alert**: {message}"} if "discord" in webhook_url else {"text": f"🚨 AI Coach Safety Alert: {message}"}
        res = requests.post(webhook_url, json=payload, timeout=5)
        return res.status_code in [200, 204]
    except:
        return False

safety_risk, safety_msg = evaluate_safety_risk(tsb, st.session_state.goals["strength_sessions_per_week"], st.session_state.goals["secondary_sport"])

# --- NAVIGATION SUITE ---
tab_dash, tab_coach, tab_strength, tab_fuel, tab_fit, tab_debrief, tab_cal = st.tabs([
    "📊 Dashboard", "🤖 AI Coach", "🏋️‍♂️ Strength & S&C", "⚡ Fueling", "📈 Multi-Sport Fit", "📝 Debrief", "📅 Calendar"
])

# ================= TAB 1: DASHBOARD =================
with tab_dash:
    st.markdown("### Multi-Sport Readiness & Automated Safety Sentinel")
    
    # --- AUTOMATED FATIGUE & OVERTRAINING ALERT BANNER ---
    if safety_risk == "HIGH":
        st.error(f"🚨 **HIGH OOVERTRAINING RISK DETECTED**\n\n{safety_msg}")
        if st.session_state.webhook_url:
            if st.button("📤 Send Immediate Push Alert via Webhook"):
                if send_push_alert(st.session_state.webhook_url, safety_msg):
                    st.success("Push notification sent successfully!")
                else:
                    st.error("Failed to deliver webhook alert.")
    elif safety_risk == "MODERATE":
        st.warning(f"⚠️ **Moderate Fatigue Warning**: {safety_msg}")
    else:
        st.success(f"🟢 **Status Normal**: {safety_msg}")

    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fitness (CTL)", round(ctl, 1))
    m2.metric("Fatigue (ATL)", round(atl, 1))
    m3.metric("Form (TSB)", round(tsb, 1))
    m4.metric("Sleep Score", f"{sleep_score}/100" if sleep_score > 0 else "N/A")

    if weather_data:
        st.markdown("---")
        st.subheader("🌤️ Environmental Conditions")
        c1, c2, c3 = st.columns(3)
        c1.metric("Temperature", f"{weather_data.get('temperature_2m')} °C")
        c2.metric("Humidity", f"{weather_data.get('relative_humidity_2m')}%")
        c3.metric("Wind Speed", f"{weather_data.get('wind_speed_10m')} km/h")

    st.markdown("---")
    st.subheader("🔄 Proactive Multi-Sport Periodization")
    if st.button("Run Periodization Audit", type="primary"):
        with st.spinner("Analyzing cycling, running, and strength balance..."):
            prompt = f"Audit my multi-sport plan. Primary: {st.session_state.goals['primary_sport']}, Secondary: {st.session_state.goals['secondary_sport']}, Strength: {st.session_state.goals['strength_sessions_per_week']}x/wk. CTL: {ctl}, TSB: {tsb}. Safety Risk Level: {safety_risk}. Event in {days_to_event} days."
            res, model = execute_multiprovider_generation(prompt, preferred_provider=selected_provider)
            st.session_state.periodization_review = f"{res}\n\n*(Engine: {model})*"
            st.rerun()

    if st.session_state.periodization_review:
        with st.expander("📋 Periodization Audit Results", expanded=True):
            st.markdown(st.session_state.periodization_review)
            if st.button("Clear Review"): st.session_state.periodization_review = None; st.rerun()

# ================= TAB 2: AI COACH =================
with tab_coach:
    st.markdown("### Multi-Sport & Strength AI Coach")
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]): st.markdown(msg["content"])
            
    if prompt := st.chat_input("Ask your coach about balancing cycling, running, and strength..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        
        with st.chat_message("model"):
            with st.spinner("Consulting multi-sport coaching core..."):
                payload = f"""
                You are an elite endurance coach specializing in multi-sport athletes where {st.session_state.goals['primary_sport']} is primary and {st.session_state.goals['secondary_sport']} is secondary, supported by {st.session_state.goals['strength_sessions_per_week']} weekly gym sessions.
                GOALS: {st.session_state.goals}
                METRICS: CTL={ctl}, ATL={atl}, TSB={tsb} (Safety Risk: {safety_risk}).
                RECENT ACTIVITIES: {activities_data}
                
                Provide precise coaching advice, balancing aerobic load with injury prevention and strength work. If prescribing a workout, include exact wattage or pace zones and structural sets.
                """ + prompt
                resp, engine = execute_multiprovider_generation(payload, preferred_provider=selected_provider)
                full_resp = f"{resp}\n\n*(Engine: {engine})*"
                st.markdown(full_resp)
                st.session_state.messages.append({"role": "model", "content": full_resp})

# ================= TAB 3: STRENGTH & S&C WORKOUT BUILDER =================
with tab_strength:
    st.markdown("### 🏋️‍♂️ Strength & Conditioning for Endurance Athletes")
    st.caption("Custom strength sessions designed to bulletproof your joints, enhance force production on the bike, and support running durability.")
    
    st_focus = st.selectbox("Select Focus Area", [
        "Cycling Force & Posterior Chain (Deadlifts, Bulgarian Split Squats)", 
        "Running Durability & Core Stability (Single-leg stability, Plyometrics)", 
        "Full Body Injury Prevention & Mobility"
    ])
    
    if st.button("Generate Custom S&C Workout", type="primary"):
        with st.spinner("Designing strength session..."):
            sc_prompt = f"Design a 45-minute gym strength workout for a cyclist ({st.session_state.goals['primary_sport']}) and runner ({st.session_state.goals['secondary_sport']}) focusing on: {st_focus}. Include exercise name, sets, reps, and specific endurance carryover notes."
            sc_res, sc_model = execute_multiprovider_generation(sc_prompt, preferred_provider=selected_provider)
            st.markdown(sc_res)

# ================= TAB 4: FUELING =================
with tab_fuel:
    st.markdown("### ⚡ Fueling Calculator")
    col1, col2 = st.columns(2)
    with col1:
        dur = st.slider("Duration (Hours)", 1.0, 6.0, 3.0, 0.5)
        sport_type = st.selectbox("Activity Sport", ["Cycling", "Running"])
        wt = st.number_input("Weight (kg)", 45.0, 100.0, 58.0)
    with col2:
        carbs = 90 if sport_type == "Cycling" else 60
        st.metric("Recommended Carbs", f"{carbs} g/hr", f"Total: {int(carbs * dur)}g")
        st.metric("Fluid Target", f"{int(wt * 8)} ml/hr")

# ================= TAB 5: MULTI-SPORT FIT ANALYZER =================
with tab_fit:
    st.markdown("### 📈 Multi-Sport Activity & Load Breakdown")
    if activities_data:
        df_act = pd.DataFrame(activities_data)
        if "type" in df_act.columns:
            st.bar_chart(df_act.groupby("type")["icu_training_load"].sum())
        
        act_opts = {f"{a.get('start_date_local', '')[:10]} - {a.get('name', 'Workout')} ({a.get('type', 'Ride')})": a for a in activities_data}
        chosen_lbl = st.selectbox("Select Activity to Inspect:", list(act_opts.keys()))
        chosen = act_opts[chosen_lbl]
        st.json(chosen)
    else:
        st.info("No activities found.")

# ================= TAB 6: DEBRIEF =================
with tab_debrief:
    st.markdown("### 📝 Post-Workout Qualitative Debrief")
    with st.form("debrief"):
        d_date = st.date_input("Date")
        d_sport = st.selectbox("Sport", ["Cycling", "Running", "Strength"])
        d_rpe = st.slider("RPE (1-10)", 1, 10, 5)
        d_notes = st.text_area("Notes")
        if st.form_submit_button("Save Debrief"):
            st.session_state.debrief_logs.append({"date": str(d_date), "sport": d_sport, "rpe": d_rpe, "notes": d_notes})
            st.success("Debrief saved to AI context memory!")

# ================= TAB 7: CALENDAR =================
with tab_cal:
    st.markdown("### 📅 Planned vs Actual Calendar")
    if planned_data:
        st.dataframe(pd.DataFrame(planned_data), use_container_width=True)
    else:
        st.info("No upcoming calendar events found.")
