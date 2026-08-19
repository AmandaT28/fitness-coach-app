import datetime
import os
import concurrent.futures
import xml.etree.ElementTree as ET
import math
import re
from dotenv import load_dotenv
from google import genai
from openai import OpenAI
import anthropic
import requests
import streamlit as st
from supabase import create_client, Client
import pandas as pd

# Load environment variables safely
try:
    load_dotenv()
except ImportError:
    pass

SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
GEMINI_KEY = st.secrets.get("GEMINI_API_KEY") or os.getenv("GEMINI_API_KEY")
OPENAI_KEY = st.secrets.get("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY")
ANTHROPIC_KEY = st.secrets.get("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_API_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase credentials missing! Add SUPABASE_URL and SUPABASE_KEY to Secrets.")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
google_client = genai.Client(api_key=GEMINI_KEY) if GEMINI_KEY else None
openai_client = OpenAI(api_key=OPENAI_KEY) if OPENAI_KEY else None
anthropic_client = anthropic.Anthropic(api_key=ANTHROPIC_KEY) if ANTHROPIC_KEY else None

# App UI Configuration
st.set_page_config(page_title="AI Performance Coach • Elite Suite", page_icon="🚴‍♂️", layout="wide")

st.markdown("""
<style>
    .stCard {
        background-color: #ffffff;
        border: 1px solid rgba(128, 128, 128, 0.15);
        border-radius: 12px;
        padding: 20px;
        margin-bottom: 16px;
        box-shadow: 0 4px 12px rgba(0,0,0,0.03);
    }
    div[data-testid="stMetric"] {
        background-color: rgba(128, 128, 128, 0.02);
        border: 1px solid rgba(128, 128, 128, 0.08);
        padding: 12px 16px;
        border-radius: 10px;
    }
    div[data-testid="stMetric"] label {
        font-size: 0.85rem !important;
        font-weight: 500;
        color: #555555;
    }
    div[data-testid="stMetric"] div[data-testid="stMetricValue"] {
        font-size: 1.3rem !important;
        font-weight: 600;
    }
</style>
""", unsafe_allow_html=True)

# --- MULTI-PROVIDER AI ROUTER ---
def execute_multiprovider_generation(prompt, preferred_provider="⚡ Auto-Fallback Chain"):
    def call_openai():
        res = openai_client.chat.completions.create(model="gpt-4o", messages=[{"role": "user", "content": prompt}])
        return res.choices[0].message.content, "OpenAI GPT-4o"
    def call_anthropic():
        res = anthropic_client.messages.create(model="claude-3-5-sonnet-20241022", max_tokens=2048, messages=[{"role": "user", "content": prompt}])
        return res.content[0].text, "Anthropic Claude"
    def call_google():
        for m in ["gemini-2.5-flash", "gemini-3.5-flash"]:
            try:
                return google_client.models.generate_content(model=m, contents=prompt).text, f"Google {m}"
            except: continue
        raise Exception("Google failed")

    active = []
    if openai_client: active.append(("OpenAI", call_openai))
    if anthropic_client: active.append(("Anthropic", call_anthropic))
    if google_client: active.append(("Google", call_google))

    for name, action in active:
        try: return action()
        except: continue
    raise Exception("All AI providers failed.")

# --- AUTHENTICATION ---
if "user" not in st.session_state: st.session_state.user = None
if not st.session_state.user:
    st.markdown("### 🔐 Secure Athlete Portal Login")
    email = st.text_input("Email")
    password = st.text_input("Password", type="password")
    if st.button("Log In", use_container_width=True):
        try:
            res = supabase.auth.sign_in_with_password({"email": email, "password": password})
            st.session_state.user = res.user
            st.rerun()
        except Exception as e: st.error(f"Login failed: {e}")
    st.stop()

USER_ID = st.session_state.user.id

profile_res = supabase.table("profiles").select("*").eq("id", USER_ID).execute()
user_profile = profile_res.data[0] if profile_res.data else {}

if not user_profile.get("intervals_api_key"):
    st.error("Please configure your Intervals.icu API key in Supabase profiles.")
    st.stop()

INTERVALS_API_KEY = user_profile["intervals_api_key"]
ATHLETE_ID = user_profile["intervals_athlete_id"]

if "goals" not in st.session_state or not isinstance(st.session_state.goals, dict):
    st.session_state.goals = {}

st.session_state.goals["event_name"] = user_profile.get("event_name") or "Bintan Round Island"
st.session_state.goals["target_metric"] = user_profile.get("target_metric") or "Survive steep climbs on group rides & improve threshold power"

if "user_supplements" not in st.session_state:
    st.session_state.user_supplements = [
        {"name": "Creatine", "timing": "Post-Workout", "notes": "Cellular ATP replenishment & sprint power"},
        {"name": "Protein", "timing": "Post-Workout (<45m)", "notes": "Muscle repair & glycogen resynthesis"},
        {"name": "Turmeric", "timing": "Morning with Fats", "notes": "Systemic inflammation control"},
        {"name": "Fish Oil", "timing": "Morning & Evening", "notes": "Cardiovascular & nocturnal recovery"},
        {"name": "NMN", "timing": "Morning (Fasted)", "notes": "Cellular NAD+ & mitochondrial support"},
        {"name": "Collagen", "timing": "30m pre-loading", "notes": "Tendon/ligament fortification with Vitamin C"},
        {"name": "Magnesium", "timing": "30m before bed", "notes": "Nervous system relaxation & slow-wave sleep"}
    ]
    
# --- FETCH DATA ---
@st.cache_data(ttl=300, show_spinner=False)
def fetch_intervals_data(aid, key):
    try:
        end_date = (datetime.date.today() + datetime.timedelta(days=14)).isoformat()
        start_date = (datetime.date.today() - datetime.timedelta(days=90)).isoformat()
        w_res = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/wellness?oldest={start_date}&newest={end_date}", auth=("API_KEY", key), timeout=5)
        a_res = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/activities?oldest={start_date}&newest={end_date}", auth=("API_KEY", key), timeout=5)
        e_res = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/events?oldest={start_date}&newest={end_date}", auth=("API_KEY", key), timeout=5)
        return (
            w_res.json() if w_res.status_code == 200 else [], 
            a_res.json() if a_res.status_code == 200 else [],
            e_res.json() if e_res.status_code == 200 else []
        )
    except: return [], [], []

wellness_list, activities_data, planned_events = fetch_intervals_data(ATHLETE_ID, INTERVALS_API_KEY)

ctl, atl, tsb, sleep_score = 0, 0, 0, 0
if wellness_list:
    latest = wellness_list[-1]
    ctl, atl, tsb = latest.get("ctl", 0), latest.get("atl", 0), latest.get("tsb", 0)
    for r in reversed(wellness_list):
        if sleep_score == 0 and r.get("sleepScore"): sleep_score = r.get("sleepScore")

race_date = datetime.date(2026, 10, 24)
days_left = (race_date - datetime.date.today()).days

if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "model", "content": "Hello! I am your proactive AI Performance Coach and sparring partner. Bounce ideas off me, ask questions about past activities or trends, and let's optimize your training!"}]

if "selected_activity_analysis" not in st.session_state:
    st.session_state.selected_activity_analysis = None

# --- SIDEBAR ---
with st.sidebar:
    st.markdown(f"👤 **{st.session_state.user.email}**")
    st.subheader("🎯 Target Race & Goals")
    with st.form("goal_feedback_form"):
        ev_name = st.text_input("Target Race", value=st.session_state.goals["event_name"])
        t_metric = st.text_input("Key Objective", value=st.session_state.goals["target_metric"])
        if st.form_submit_button("Update Goals", use_container_width=True):
            st.session_state.goals["event_name"] = ev_name
            st.session_state.goals["target_metric"] = t_metric
            supabase.table("profiles").update({"event_name": ev_name, "target_metric": t_metric}).eq("id", USER_ID).execute()
            st.success("Goals updated!")

    st.markdown("---")
    selected_provider = st.selectbox("⚡ AI Engine Model", ["⚡ Auto-Fallback Chain", "OpenAI GPT", "Anthropic Claude", "Google Gemini"])

    st.markdown("---")
    if st.button("🗑️ Clear Chat History", use_container_width=True):
        st.session_state.messages = [{"role": "model", "content": "Chat history cleared. What topic or idea would you like to discuss next?"}]
        st.rerun()

    if st.button("Log Out", use_container_width=True):
        supabase.auth.sign_out()
        st.session_state.user = None
        st.rerun()

# --- NAVIGATION SUITE ---
tab_dash, tab_coach, tab_calendar, tab_recovery, tab_history, tab_strat = st.tabs([
    "📊 Command Center", "🤖 AI Coach & Sparring", "📅 Training Calendar", "💊 Recovery & Supplements", "🔍 Activity Inspector", "🗺️ Route Strategist"
])

# ================= TAB 1: COMMAND CENTER =================
with tab_dash:
    st.markdown(f"### ☀️ Proactive AI Performance Coach • Command Center")
    
    st.markdown(f"""
    <div style="background-color: #fef9e7; border: 1px solid #f9e79f; padding: 16px; border-radius: 14px; margin-bottom: 16px;">
        <span style="font-size: 0.75rem; font-weight: bold; color: #d68910; background: #fcf3cf; padding: 2px 6px; border-radius: 4px;">PROACTIVE COACHING BRIEFING</span>
        <div style="font-weight: bold; font-size: 1.1rem; margin-top: 4px;">Target Race: {st.session_state.goals['event_name']} ({days_left} days left)</div>
        <div style="color: #666; font-size: 0.85rem; margin-top: 4px;">Objective: {st.session_state.goals['target_metric']}</div>
        <hr style="margin: 10px 0; border-top: 1px solid #fce881;">
        <div style="font-size: 0.9rem; font-weight: 500; color: #333;">
            {'🟢 <strong>Readiness High:</strong> Form (TSB) is optimal. Stack your hard intervals today and take your creatine post-ride.' if tsb >= -15 else '🟡 <strong>Fatigue Warning:</strong> TSB is dropping. Prioritize sleep, magnesium tonight, and consider swapping tomorrow for an aerobic flush.'}
        </div>
    </div>
    """, unsafe_allow_html=True)

    c_met1, c_met2, c_met3, c_met4 = st.columns(4)
    with c_met1: st.metric("Fitness (CTL)", round(ctl, 1))
    with c_met2: st.metric("Fatigue (ATL)", round(atl, 1))
    with c_met3: st.metric("Form (TSB)", round(tsb, 1))
    with c_met4: st.metric("Sleep Score", f"{sleep_score}/100" if sleep_score > 0 else "N/A")

    st.markdown("---")
    st.markdown("#### 📈 Deep 90-Day Training Load & Progression Trend Analysis")
    
    with st.spinner("Synthesizing 90-day performance trends..."):
        trend_payload = f"""
        Perform a rigorous, detailed 90-day sports science trend analysis based on my wellness and training data:
        CTL (Fitness): {ctl}, ATL (Fatigue): {atl}, TSB (Form): {tsb}
        Recent Activities Summary: {activities_data[:25] if activities_data else 'None'}
        Target Event: {st.session_state.goals['event_name']} in {days_left} days.
        Objective: {st.session_state.goals['target_metric']}
        
        Provide a structured analysis covering:
        1. **Fitness Trajectory & Ramp Rate:** Are we building fitness on track for October 24?
        2. **Consistency & Intensity Distribution:** Indoor structured work vs weekend group rides.
        3. **Climbing Readiness Indicator:** Are we successfully closing the gap to prevent getting dropped on climbs?
        4. **Proactive Verdict / Next Steps:** Actionable instruction for the coming week.
        """
        try:
            trend_analysis_text, _ = execute_multiprovider_generation(trend_payload, preferred_provider=selected_provider)
            st.markdown(trend_analysis_text)
            
            # Contextual Action: Jump to chat with this trend analysis context
            if st.button("💬 Discuss These Trends With Coach", key="discuss_trends_btn"):
                st.session_state.messages.append({
                    "role": "user", 
                    "content": f"Let's review my recent 90-day training trends (Fitness CTL: {round(ctl, 1)}, Fatigue ATL: {round(atl, 1)}, Form TSB: {round(tsb, 1)}). Based on my goal of '{st.session_state.goals['target_metric']}', am I progressing correctly?"
                })
                st.success("Context loaded! Go to the **AI Coach & Sparring** tab to start chatting.")
        except Exception as e:
            st.error(f"Could not generate deep trend analysis: {e}")

# ================= TAB 2: AI COACH & SPARRING CHAT =================
with tab_coach:
    st.markdown("### 🤖 AI Coach & Collaborative Sparring Partner")
    st.caption("Bounce training ideas off your coach, debate workout structures, check missed session protocols, or request MyWhoosh workouts.")

    chat_container = st.container()
    with chat_container:
        for idx, msg in enumerate(st.session_state.messages):
            with st.chat_message(msg["role"]):
                clean_content = re.sub(r"```xml\s*<\?xml.*?>.*?</\s*workout_file\s*>\s*```", "", msg["content"], flags=re.DOTALL)
                clean_content = re.sub(r"```\s*<workout_file>.*?</\s*workout_file>\s*```", "", clean_content, flags=re.DOTALL)
                st.markdown(clean_content.strip())
                
                if msg["role"] == "model":
                    match = re.search(r"```xml\s*(<\?xml.*?>.*?<\s*/\s*workout_file\s*>|<workout_file>.*?</\s*workout_file>)\s*```", msg["content"], re.DOTALL)
                    if not match:
                        match = re.search(r"```\s*(<workout_file>.*?</\s*workout_file>)\s*```", msg["content"], re.DOTALL)
                    
                    if match:
                        zwo_data = match.group(1).strip()
                        st.download_button(
                            label="📥 Download MyWhoosh Workout File (.zwo)",
                            data=zwo_data,
                            file_name=f"AI_Coach_Workout_{idx}.zwo",
                            mime="application/xml",
                            key=f"download_zwo_{idx}"
                        )

    if prompt := st.chat_input("Bounce an idea or ask your coach a question..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        
        payload = f"""
        You are an elite, proactive cycling sports science coach and collaborative sparring partner. Your job is not just to dictate, but to actively brainstorm with the athlete, weigh pros and cons of training ideas, discuss race tactics, and offer science-backed alternatives when they bounce ideas off you.
        ATHLETE SUPPLEMENT STACK AVAILABLE: Creatine, Protein, Turmeric, Fish Oil, NMN, Collagen, Magnesium.
        GOAL: {st.session_state.goals['event_name']} ({st.session_state.goals['target_metric']})
        METRICS: CTL={ctl}, ATL={atl}, TSB={tsb}.
        ACTIVITIES HISTORY: {activities_data[:20] if activities_data else 'None'}
        UPCOMING SCHEDULE: {planned_events[:10] if planned_events else 'None'}
        
        Provide rigorous, proactive, and conversational coaching insights. Engage in a true back-and-forth dialogue.
        CRITICAL WORKOUT INSTRUCTION: If an indoor workout is requested, include a valid .zwo XML workout block enclosed inside a ```xml ... ``` code block.
        """ + prompt
        
        with st.spinner("Coach is thinking through your idea..."):
            try:
                resp, engine = execute_multiprovider_generation(payload, preferred_provider=selected_provider)
                full_resp = f"{resp}\n\n*(Engine: {engine})*"
                st.session_state.messages.append({"role": "model", "content": full_resp})
                st.rerun()
            except Exception as e:
                st.error(f"AI Generation Failed: {str(e)}")

# ================= TAB 3: TRAINING CALENDAR =================
with tab_calendar:
    st.markdown("### 📅 Training Calendar & Missed Workout Protocols")
    st.caption("Review your upcoming scheduled sessions synced from Intervals.icu, and get instant guidance if you miss a session.")

    c_cal1, c_cal2 = st.columns([2, 1])
    with c_cal1:
        st.markdown("#### Upcoming Scheduled Training")
        if planned_events:
            df_cal = pd.DataFrame(planned_events)
            display_cols = [c for c in ['start_date_local', 'name', 'type', 'description'] if c in df_cal.columns]
            st.dataframe(df_cal[display_cols] if display_cols else df_cal, use_container_width=True, hide_index=True)
            
            if st.button("💬 Discuss Schedule with Coach", key="discuss_calendar_btn"):
                st.session_state.messages.append({"role": "user", "content": f"Let's review my upcoming training schedule: {planned_events[:5]}. Are there any adjustments we should make?"})
                st.info("Switched context! Go to the **AI Coach & Sparring** tab to talk about your schedule.")
        else:
            st.info("No upcoming calendar events found in Intervals.icu.")

    with c_cal2:
        st.markdown("#### 🚨 Missed Workout Protocol")
        st.info(
            "**Human Coach Rulebook for Missed Sessions:**\n\n"
            "1. **Never double up** high-intensity days to 'make up' for lost time.\n"
            "2. If you missed an **easy/recovery ride**, drop it and move on.\n"
            "3. If you missed a **key interval/climbing session**, evaluate your Form (TSB). If TSB > -10, shift it to today. If TSB < -20, skip it entirely to prevent overtraining."
        )
        if st.button("🤖 Ask Coach About a Missed Workout", use_container_width=True):
            st.session_state.messages.append({"role": "user", "content": "I missed my scheduled workout yesterday. Given my current TSB and upcoming weekend group ride, what should I do?"})
            st.info("Switched context! Go to the **AI Coach & Sparring** tab to discuss your missed session.")

# ================= TAB 4: RECOVERY & SUPPLEMENTS =================
with tab_recovery:
    st.markdown("### 💊 Proactive Recovery & Supplement Protocol")
    st.caption("Optimized timing and protocols based on your personal supplement stack to maximize adaptation and minimize inflammation.")

    st.markdown("""
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
        <div class="stCard">
            <h4 style="color: #d68910; margin-top:0;">🌅 Morning / Pre-Ride Routine</h4>
            <ul>
                <li><strong>NMN:</strong> Take upon waking on an empty stomach to support cellular NAD+ and mitochondrial function.</li>
                <li><strong>Turmeric:</strong> Take with breakfast containing healthy fats and black pepper to manage baseline systemic inflammation from heavy training blocks.</li>
                <li><strong>Fish Oil:</strong> Take with your first meal to support cardiovascular health and joint lubrication.</li>
            </ul>
        </div>
        <div class="stCard">
            <h4 style="color: #2e86c1; margin-top:0;">⚡ Post-Ride / Immediate Recovery</h4>
            <ul>
                <li><strong>Protein:</strong> Consume 25–40g within 45 minutes post-ride combined with carbohydrates to jumpstart muscle glycogen resynthesis and repair.</li>
                <li><strong>Creatine:</strong> Take post-workout (ideally with your protein/carbs shake) to maximize cellular uptake for ATP replenishment and sprint/climbing power.</li>
                <li><strong>Collagen:</strong> Take 15g of collagen peptides combined with Vitamin C approx. 30–60 minutes before strength training or heavy loading to fortify tendons and ligaments.</li>
            </ul>
        </div>
    </div>
    
    <div class="stCard" style="margin-top: 16px;">
        <h4 style="color: #27ae60; margin-top:0;">🌙 Evening / Before Bed</h4>
        <ul>
            <li><strong>Magnesium:</strong> Take 300–400mg (Glycinate form recommended) 30 minutes before sleep. This enhances nervous system recovery, promotes deep slow-wave sleep, and prevents cramping.</li>
            <li><strong>Fish Oil (Optional split dose):</strong> Evening dose assists with nocturnal inflammatory regulation.</li>
        </ul>
    </div>
    """, unsafe_allow_html=True)
    
    if st.button("💬 Discuss Supplement Timing with Coach", key="discuss_supplements_btn"):
        st.session_state.messages.append({
            "role": "user", 
            "content": "Let's review my personal supplement stack (creatine, protein, turmeric, fish oil, NMN, collagen, magnesium). How should I time these around my upcoming high-intensity indoor MyWhoosh sessions and weekend outdoor group rides to maximize recovery and reduce climbing fatigue?"
        })
        st.success("Context loaded! Go to the **AI Coach & Sparring** tab to start chatting.")

# ================= TAB 5: ACTIVITY INSPECTOR =================
with tab_history:
    st.markdown("### 🔍 Past Activity Inspector & Deep Debrief")
    st.caption("Select any past activity from your 90-day history to run an AI-powered performance debrief.")

    if activities_data:
        act_options = {}
        for act in activities_data:
            name = act.get("name", "Unnamed Activity")
            date = act.get("start_date_local", "")[:10]
            raw_dist = act.get("distance")
            dist = round(((raw_dist if raw_dist is not None else 0) / 1000), 1)
            raw_time = act.get("moving_time")
            dur_min = int((raw_time if raw_time is not None else 0) / 60)
            label = f"{date} — {name} ({dist} km, {dur_min} mins)"
            act_options[label] = act

        selected_label = st.selectbox("Choose a past activity to analyze:", list(act_options.keys()))
        selected_act = act_options[selected_label]

        col_info1, col_info2, col_info3 = st.columns(3)
        sel_dist = selected_act.get("distance")
        safe_dist = round(((sel_dist if sel_dist is not None else 0) / 1000), 2)
        col_info1.metric("Distance", f"{safe_dist} km")
        
        sel_time = selected_act.get("moving_time")
        safe_time = int((sel_time if sel_time is not None else 0) / 60)
        col_info2.metric("Moving Time", f"{safe_time} mins")
        
        avg_watts = selected_act.get("average_watts")
        safe_watts = f"{avg_watts} W" if avg_watts is not None else "N/A"
        col_info3.metric("Average Power", safe_watts)

        if st.button("🤖 Run Deep AI Activity Debrief", type="primary", use_container_width=True):
            with st.spinner("Analyzing activity metrics, power output, and pacing..."):
                debrief_prompt = f"""
                You are an elite cycling coach. Perform a deep, rigorous performance debrief for this specific activity:
                Activity Details: {selected_act}
                Target Event Goal: {st.session_state.goals['event_name']} ({st.session_state.goals['target_metric']})
                
                Evaluate: 1) Intensity distribution and power output, 2) Pacing efficiency, 3) Specific strengths demonstrated, and 4) Concrete areas for improvement for future group rides or climbing sessions.
                """
                try:
                    debrief_res, debrief_engine = execute_multiprovider_generation(debrief_prompt, preferred_provider=selected_provider)
                    st.session_state.selected_activity_analysis = f"### Debrief: {selected_act.get('name')}\n*{selected_act.get('start_date_local', '')[:10]}*\n\n{debrief_res}\n\n*(Engine: {debrief_engine})*"
                except Exception as e:
                    st.error(f"Analysis failed: {e}")

        if st.session_state.selected_activity_analysis:
            st.markdown("---")
            st.markdown(st.session_state.selected_activity_analysis)
            
            if st.button("💬 Clarify This Debrief with Coach", key="discuss_debrief_btn"):
                act_name = selected_act.get('name', 'Workout')
                act_dist = round((selected_act.get('distance') or 0) / 1000, 2)
                act_time = int((selected_act.get('moving_time') or 0) / 60)
                act_watts = selected_act.get('average_watts', 'N/A')
                
                st.session_state.messages.append({
                    "role": "user", 
                    "content": f"I want to ask some clarifications regarding my recent activity '{act_name}' ({act_dist} km, {act_time} mins, {act_watts}W avg power). Let's review how it impacts my climbing preparation."
                })
                st.success("Context loaded! Go to the **AI Coach & Sparring** tab to start chatting.")
    else:
        st.info("No activities found in your Intervals.icu sync history.")

# ================= TAB 6: ROUTE STRATEGIST =================
with tab_strat:
    st.markdown("### 🗺️ Route Pacing & Climbing Strategist")
    uploaded_gpx = st.file_uploader("Upload GPX Route File (.gpx)", type=["gpx"])
    
    def parse_gpx(file_bytes):
        try:
            xml_content = file_bytes.decode('utf-8', errors='ignore')
            root = ET.fromstring(xml_content)
            latlons, elevation_list = [], []
            for elem in root.iter():
                tag = elem.tag.split('}')[-1].lower()
                if tag in ['trkpt', 'rtept']:
                    lat_str = elem.attrib.get('lat') or elem.attrib.get('latitude')
                    lon_str = elem.attrib.get('lon') or elem.attrib.get('longitude')
                    if lat_str and lon_str:
                        latlons.append((float(lat_str), float(lon_str)))
                        ele_val = elevation_list[-1] if elevation_list else 0.0
                        for child in elem:
                            if child.tag.split('}')[-1].lower() in ['ele', 'elevation', 'alt']:
                                try: ele_val = float(child.text)
                                except: pass
                                break
                        elevation_list.append(ele_val)
            if not latlons: return None
            total_ele_gain = sum(max(0, elevation_list[i] - elevation_list[i-1]) for i in range(1, len(elevation_list)))
            total_dist_km = sum(6371.0 * (2 * math.asin(math.sqrt(math.sin(math.radians(latlons[i][0]-latlons[i-1][0])/2)**2 + math.cos(math.radians(latlons[i-1][0])) * math.cos(math.radians(latlons[i][0])) * math.sin(math.radians(latlons[i][1]-latlons[i-1][1])/2)**2))) for i in range(1, len(latlons)))
            return {"distance_km": round(max(total_dist_km, 0.1), 2), "elevation_gain_m": round(total_ele_gain, 1), "max_elevation": round(max(elevation_list), 1) if elevation_list else 0}
        except Exception: return None

    if uploaded_gpx:
        route_metrics = parse_gpx(uploaded_gpx.read())
        if route_metrics:
            c1, c2, c3 = st.columns(3)
            c1.metric("Distance", f"{route_metrics['distance_km']} km")
            c2.metric("Elevation Gain", f"{route_metrics['elevation_gain_m']} m")
            c3.metric("Max Elevation", f"{route_metrics['max_elevation']} m")
            
            if st.button("🤖 Generate Climbing Strategy", type="primary"):
                with st.spinner("Analyzing route profile..."):
                    strat_prompt = f"""
                    Analyze this route profile for climbing performance: Distance {route_metrics['distance_km']} km, Elevation Gain {route_metrics['elevation_gain_m']} m.
                    Objective: {st.session_state.goals['target_metric']}
                    Provide precise power pacing targets and climbing strategies to maintain group ride cohesion.
                    """
                    try:
                        strat_res, strat_model = execute_multiprovider_generation(strat_prompt, preferred_provider=selected_provider)
                        st.markdown("---")
                        st.markdown(strat_res)
                        st.caption(f"Generated via: {strat_model}")
                    except Exception as e:
                        st.error(f"Strategy generation failed: {e}")
