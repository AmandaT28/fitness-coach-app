import datetime
import os
import time
import concurrent.futures
from dotenv import load_dotenv
from google import genai
import requests
import streamlit as st
from supabase import create_client, Client

# Load environment variables safely
try:
  load_dotenv()
except ImportError:
  pass

# Grab keys from Streamlit Secrets or environment
GEMINI_API_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
INTERVALS_API_KEY = st.secrets.get("INTERVALS_API_KEY") or os.getenv("INTERVALS_API_KEY")
ATHLETE_ID = st.secrets.get("INTERVALS_ATHLETE_ID") or os.getenv("INTERVALS_ATHLETE_ID")
SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")

if not GEMINI_API_KEY:
  st.error("❌ GEMINI_API_KEY is missing! Configure it in Streamlit Cloud Secrets.")
  st.stop()

if not SUPABASE_URL or not SUPABASE_KEY:
  st.error("❌ Supabase credentials are missing! Add SUPABASE_URL and SUPABASE_KEY to Secrets.")
  st.stop()

# Initialize Clients
client = genai.Client(api_key=GEMINI_API_KEY)
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
USER_ID = "primary_athlete"

# App UI Configuration
st.set_page_config(page_title="AI Sports Science Coach", page_icon="🚴‍♂️", layout="wide")

st.title("🚴‍♂️ AI Sports Science Coach • Pro Command Center")
st.caption("High-Performance Endurance Engine • Powered by Garmin, Intervals.icu & Supabase")

# --- 1. DATA FETCHING FUNCTIONS ---
@st.cache_data(ttl=300, show_spinner=False) 
def fetch_intervals_wellness():
  try:
    end_date = (datetime.date.today() + datetime.timedelta(days=1)).isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/wellness?oldest={start_date}&newest={end_date}"
    res = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=8)
    if res.status_code == 200 and res.json():
        return res.json()
    return []
  except Exception:
    return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_recent_activities():
  try:
    end_date = datetime.date.today().isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/activities?oldest={start_date}&newest={end_date}"
    res = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=8)
    return res.json() if res.status_code == 200 else []
  except Exception:
    return []

@st.cache_data(ttl=300, show_spinner=False)
def fetch_athlete_stats():
  try:
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}"
    res = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=8)
    return res.json() if res.status_code == 200 else {}
  except Exception:
    return {}

@st.cache_data(ttl=300, show_spinner=False)
def fetch_planned_workouts():
  try:
    end_date = (datetime.date.today() + datetime.timedelta(days=7)).isoformat()
    start_date = (datetime.date.today() - datetime.timedelta(days=14)).isoformat()
    url = f"https://intervals.icu/api/v1/athlete/{ATHLETE_ID}/events?oldest={start_date}&newest={end_date}"
    res = requests.get(url, auth=("API_KEY", INTERVALS_API_KEY), timeout=8)
    return res.json() if res.status_code == 200 else []
  except Exception:
    return []

# --- PARALLEL DATA FETCHING FOR INSTANT LOAD ---
with st.spinner("Syncing live metrics from Intervals.icu..."):
    with concurrent.futures.ThreadPoolExecutor() as executor:
        future_wellness = executor.submit(fetch_intervals_wellness)
        future_activities = executor.submit(fetch_recent_activities)
        future_stats = executor.submit(fetch_athlete_stats)
        future_planned = executor.submit(fetch_planned_workouts)

        wellness_list = future_wellness.result()
        activities_data = future_activities.result()
        athlete_stats = future_stats.result()
        planned_data = future_planned.result()

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
    "ftp": athlete_stats.get("ftp", athlete_stats.get("icu_ftp", "Unknown")),
    "max_hr": athlete_stats.get("max_hr", "Unknown")
}

# --- 2. SESSION STATE & SUPABASE CLOUD SYNC ---
if "performance_goals" not in st.session_state:
  st.session_state.performance_goals = "Maintain aerobic base, peak for upcoming events, and balance fatigue."

if "event_date" not in st.session_state:
  st.session_state.event_date = datetime.date.today() + datetime.timedelta(days=60)

if "weekly_report" not in st.session_state:
  st.session_state.weekly_report = None

# Pull persistent chat history from Supabase cloud database
if "messages" not in st.session_state:
    try:
        response = supabase.table("chat_messages").select("*").eq("user_id", USER_ID).order("created_at").execute()
        db_messages = response.data
        if db_messages:
            st.session_state.messages = [{"role": msg["role"], "content": msg["content"]} for msg in db_messages]
        else:
            st.session_state.messages = [{
                "role": "model",
                "content": f"Hello! Irading telemetry synced. Your chat history is now linked to Supabase cloud across all your devices."
            }]
    except Exception:
        st.session_state.messages = [{"role": "model", "content": "Hello! Running in local fallback mode."}]

with st.sidebar:
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
    with st.spinner("Analyzing performance trends & compliance..."):
      report_prompt = (
          "Generate a formal Weekly Progress Report. Review past 14 days of "
          f"completed activities ({activities_data}) against planned calendar events ({planned_data}). "
          f"Analyze overall metrics ({athlete_stats}), and recovery trends (Sleep: {sleep_score}, HRV: {hrv}) against goals: "
          f"'{st.session_state.performance_goals}' and event date ({st.session_state.event_date}). "
          "Critique pacing compliance and suggest adjustments."
      )
      
      report_response = None
      for attempt in range(3):
          try:
            res = client.models.generate_content(
                model="gemini-3.6-flash", contents=report_prompt
            )
            report_response = res.text
            break
          except Exception as e:
            if "503" in str(e) and attempt < 2:
                time.sleep(2 ** attempt) 
                continue
            st.error(f"Could not generate report: {e}")
            break
      
      if report_response:
          st.session_state.weekly_report = report_response
          st.rerun()

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


# --- 3. PRO TABBED NAVIGATION LAYOUT ---
tab_dash, tab_coach, tab_cal = st.tabs([
    "📊 Command Center & Metrics", 
    "🤖 AI Coach & MyWhoosh Builder", 
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

    try:
        import plotly.graph_objects as go
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
        import pandas as pd
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
    st.caption("Ask for structured workouts, pacing review, or MyWhoosh `.zwo` file generation. Chat history syncs via Supabase.")

    # Render chat message history safely inside the tab layout
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
                workout_xml = workout_xml.replace("```xml", "").replace("```", "").strip()
                
                st.download_button(
                    label="⬇️ Download Workout for MyWhoosh (.zwo)",
                    data=workout_xml,
                    file_name=f"Coach_Workout_{datetime.date.today()}.zwo",
                    mime="application/xml",
                    type="primary",
                    key=f"download_{i}"
                )
            except Exception:
                pass

    # Chat input placed cleanly at the bottom of Tab 2
    if prompt := st.chat_input("Ask your coach to build a MyWhoosh workout, check your pacing, or plan your week...", key="coach_chat_input"):
      st.session_state.messages.append({"role": "user", "content": prompt})
      
      # Save user prompt to Supabase cloud database
      try:
          supabase.table("chat_messages").insert({"user_id": USER_ID, "role": "user", "content": prompt}).execute()
      except Exception:
          pass

      with st.chat_message("user"):
        st.markdown(prompt)

      with st.chat_message("model"):
        with st.spinner("Synthesizing telemetry and writing prescription..."):
          
          context_payload = f"""
                You are an elite endurance sports science coach.
                ATHLETE PROFILE & EQUIPMENT: 
                - Setup: Cervélo Soloist (Size 48), custom cockpit, S-Works Power Pro Mirror saddle, Magene TEO P515 power meter / 160mm crankset.
                - Bio-mechanics: Flexible flat feet, some hypermobility.
                GOALS: {st.session_state.performance_goals} (Target Event in {days_to_event} days)
                READINESS: {readiness_status} | CTL: {ctl} | ATL: {atl} | TSB: {tsb} | Sleep: {sleep_score} | HRV: {hrv}
                POWER & HR ZONES: {athlete_zones}
                PLANNED WORKOUTS (Calendar): {planned_data}
                RECENT ACTIVITIES (Completed): {activities_data}

                COACHING INSTRUCTIONS:
                1. FEEDBACK LOOP: Compare 'Planned Workouts' vs 'Recent Activities'. Critique pacing discipline and compliance.
                2. PLAN FORMULATION: If asked for a workout, prescribe exact watts based on the athlete's FTP and zones. Structure as Warmup -> Main Set -> Cool Down. Factor in 160mm cranks and joint health by managing cadence requests.
                3. INDOOR EXPORT (MYWHOOSH): If the athlete asks for a MyWhoosh or Zwift workout, generate the exact XML structure for a `.zwo` file. 
                   - YOU MUST wrap the raw XML code strictly inside `<workout_file>` and `</workout_file>` tags at the very end of your response. 
                   - Do not put markdown around the XML tags.
                """
          for msg in st.session_state.messages[:-1]:
            context_payload += f"\n{msg['role'].upper()}: {msg['content']}\n"
          context_payload += f"\nUSER: {prompt}\n"

          message_placeholder = st.empty()
          full_response = ""
          
          try:
            response_stream = client.models.generate_content_stream(
                model="gemini-3.6-flash", contents=context_payload
            )
            for chunk in response_stream:
                if chunk.text:
                    full_response += chunk.text
                    message_placeholder.markdown(full_response + "▌")
            
            message_placeholder.markdown(full_response)
            st.session_state.messages.append({"role": "model", "content": full_response})
            
            # Save AI response to Supabase cloud database
            try:
                supabase.table("chat_messages").insert({"user_id": USER_ID, "role": "model", "content": full_response}).execute()
            except Exception:
                pass

            st.rerun()

          except Exception as e:
            st.error(f"⚠️ API Error: {str(e)}")


# ================= TAB 3: CALENDAR & COMPLIANCE =================
with tab_cal:
    st.markdown("### Planned vs. Actual Training Compliance")
    st.caption("Review your scheduled calendar blocks against executed Garmin activities.")
    
    import pandas as pd
    
    col_c1, col_c2 = st.columns(2)
    
    with col_c1:
        st.subheader("📅 Scheduled Calendar Events")
        if planned_data:
            try:
                df_planned = pd.DataFrame(planned_data)
                if "start_date_local" in df_planned.columns:
                    df_planned["Date"] = pd.to_datetime(df_planned["start_date_local"]).dt.strftime("%Y-%m-%d")
                
                if "name" not in df_planned.columns and "summary" in df_planned.columns:
                    df_planned["name"] = df_planned["summary"]
                    
                display_cols = [c for c in ["Date", "name", "type", "category", "load"] if c in df_planned.columns or c == "Date"]
                st.dataframe(df_planned[[c for c in display_cols if c in df_planned.columns]], use_container_width=True, hide_index=True)
            except Exception:
                st.write("Could not parse planned events table.")
        else:
            st.info("No planned events found for this window.")
            
    with col_c2:
        st.subheader("🚴‍♂️ Completed Activities")
        if activities_data:
            try:
                df_act = pd.DataFrame(activities_data)
                if "start_date_local" in df_act.columns:
                    df_act["Date"] = pd.to_datetime(df_act["start_date_local"]).dt.strftime("%Y-%m-%d")
                if "moving_time" in df_act.columns:
                    df_act["Duration (min)"] = (df_act["moving_time"] / 60).round(1)
                if "distance" in df_act.columns:
                    df_act["Distance (km)"] = (df_act["distance"] / 1000).round(2)
                if "icu_training_load" in df_act.columns:
                    df_act["TSS"] = df_act["icu_training_load"].round(0)

                columns_to_show = ["Date", "name", "type", "TSS", "Duration (min)", "Distance (km)"]
                available_cols = [c for c in columns_to_show if c in df_act.columns]
                
                st.dataframe(df_act[available_cols], use_container_width=True, hide_index=True)
            except Exception:
                st.write("Could not parse activities table.")
        else:
            st.info("No completed activities found for this window.")
