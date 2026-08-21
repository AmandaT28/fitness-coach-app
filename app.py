import datetime, os, math, re, base64, json, requests
import xml.etree.ElementTree as ET
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from google import genai
from supabase import create_client, Client
from streamlit_local_storage import LocalStorage

load_dotenv()

# --- INITIALIZATION & CREDENTIALS ---
st.set_page_config(page_title="Elite Suite • AI Coach", page_icon="🚴‍♂️", layout="wide")

SUPABASE_URL = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
if not SUPABASE_URL or not SUPABASE_KEY:
    st.error("❌ Supabase credentials missing!")
    st.stop()

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# Google Keys Only
P_KEY = st.secrets.get("google_keys", {}).get("primary_key") or os.getenv("PRIMARY_KEY")
S_KEY = st.secrets.get("google_keys", {}).get("secondary_key") or os.getenv("SECONDARY_KEY")
T_KEY = st.secrets.get("google_keys", {}).get("tertiary_key") or os.getenv("TERTIARY_KEY")

g_clients = {
    "Primary": genai.Client(api_key=P_KEY) if P_KEY else None,
    "Secondary": genai.Client(api_key=S_KEY) if S_KEY else None,
    "Tertiary": genai.Client(api_key=T_KEY) if T_KEY else None
}

# --- PURE GEMINI AI ROUTER ---
def execute_ai(prompt, provider="Google Gemini"):
    errors = []
    
    # Prioritizes 3.x models but maintains a safety net down to 1.5-flash
    models = ["gemini-3.7-flash", "gemini-3.6-flash", "gemini-3.5-flash", "gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-flash"]
    
    for name, client in g_clients.items():
        if not client: continue
        for m in models:
            try:
                res = client.models.generate_content(model=m, contents=prompt)
                # Check if response is valid, otherwise it was likely blocked by safety filters
                if res and hasattr(res, "text") and res.text:
                    return res.text, f"Google {m} ({name})"
                else:
                    errors.append(f"{name} ({m}): Empty response (Safety Block / Drop)")
            except Exception as e:
                errors.append(f"{name} ({m}): {str(e)}")
                
    raise Exception(f"Google Engine Failed. Diagnostics: {' | '.join(errors)}")

localS = LocalStorage()

# --- STATE MANAGEMENT ---
def init_state(key, default):
    if key not in st.session_state: st.session_state[key] = default

init_state("user", None)
init_state("user_credentials", localS.getItem("athlete_profile_config"))
init_state("messages", [])
init_state("active_nav", "📊 Command Center")
init_state("auto_debriefed", None)
init_state("goals", {"event_name": "Bintan Round Island", "target_metric": "Survive steep climbs", "race_date": "2026-10-24"})
init_state("supplements", [{"name": "Protein", "timing": "Post-Workout"}])

# --- AUTHENTICATION ---
if not st.session_state.user and not st.session_state.user_credentials:
    st.markdown("### 🔐 Elite Athlete Portal")
    with st.form("login_form"):
        email, pwd = st.text_input("Email"), st.text_input("Password", type="password")
        if st.form_submit_button("Log In"):
            try:
                st.session_state.user = supabase.auth.sign_in_with_password({"email": email, "password": pwd}).user
                st.rerun()
            except Exception as e: st.error(str(e))
    st.stop()

# Load User Vars
if st.session_state.user:
    db_prof = supabase.table("profiles").select("*").eq("id", st.session_state.user.id).execute().data[0]
    ICU_KEY, ICU_ID = db_prof.get("intervals_api_key"), db_prof.get("intervals_athlete_id")
    GEAR, LIMITS = db_prof.get("gear_notes", ""), db_prof.get("limitations_notes", "")
else:
    creds = st.session_state.user_credentials
    ICU_KEY, ICU_ID = creds["icu_key"], creds["icu_id"]
    GEAR, LIMITS = creds.get("gear", ""), creds.get("limitations", "")

# --- DATA FETCHING (INTERVALS.ICU) ---
@st.cache_data(ttl=300)
def fetch_telemetry(aid, key):
    try:
        t = datetime.date.today()
        p = {"oldest": (t - datetime.timedelta(days=30)).isoformat(), "newest": (t + datetime.timedelta(days=14)).isoformat()}
        auth = ("API_KEY", key)
        w = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/wellness", params=p, auth=auth).json()
        a = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/activities", params=p, auth=auth).json()
        e = requests.get(f"https://intervals.icu/api/v1/athlete/{aid}/events", params=p, auth=auth).json()
        return w, a, e
    except: return [], [], []

wellness, activities, events = fetch_telemetry(ICU_ID, ICU_KEY)
latest_w = wellness[-1] if wellness else {}
ctl, atl, tsb = latest_w.get("ctl", 0), latest_w.get("atl", 0), latest_w.get("tsb", 0)

# --- SIDEBAR NAV & SETTINGS ---
with st.sidebar:
    st.markdown("### ⚡ Navigation")
    nav_opts = ["📊 Command Center", "🤖 AI Coach Chat", "📅 Calendar", "🔍 Activity Debrief"]
    st.session_state.active_nav = st.radio("Menu", nav_opts, index=nav_opts.index(st.session_state.active_nav))
    
    st.markdown("---")
    # Simplified AI Model selection to only show Gemini
    ai_model = st.selectbox("AI Engine", ["Google Gemini (Flash Cascade)"])
    persona = st.selectbox("Coach Persona", ["Sports Scientist", "Collaborative Peer", "Drill Sergeant"])
    
    if st.button("🗑️ Clear Chat History"):
        st.session_state.messages = []
        st.rerun()
    if st.button("Log Out"):
        st.session_state.clear()
        st.rerun()

# --- HELPER: INTERVALS.ICU SYNC ---
def sync_to_icu(ai_response):
    matches = re.findall(r'<icu_workout>\s*(.*?)\s*</icu_workout>', ai_response, re.DOTALL)
    count = 0
    for match in matches:
        try:
            workouts = json.loads(match.replace("```json", "").replace("```", "").strip())
            if not isinstance(workouts, list): workouts = [workouts]
            for w in workouts:
                w['category'] = 'WORKOUT'
                if len(w.get('start_date_local','')) == 10: w['start_date_local'] += "T00:00:00"
                if requests.post(f"https://intervals.icu/api/v1/athlete/{ICU_ID}/events", json=w, auth=("API_KEY", ICU_KEY)).status_code == 200:
                    count += 1
        except: pass
    return count

# ================= VIEWS =================

if st.session_state.active_nav == "📊 Command Center":
    st.markdown("### ☀️ Command Center")
    c1, c2, c3 = st.columns(3)
    c1.metric("Fitness (CTL)", round(ctl, 1))
    c2.metric("Fatigue (ATL)", round(atl, 1))
    c3.metric("Form (TSB)", round(tsb, 1))
    
    st.markdown("---")
    if st.button("🚀 Synthesize 30-Day Trend", type="primary"):
        with st.spinner("Analyzing..."):
            try:
                prompt = f"Analyze my 30-day trend. CTL:{ctl}, ATL:{atl}, TSB:{tsb}. Goal: {st.session_state.goals['event_name']}."
                res, eng = execute_ai(prompt, ai_model)
                st.success(f"Generated by {eng}")
                st.markdown(res)
            except Exception as e: st.error(str(e))

elif st.session_state.active_nav == "🤖 AI Coach Chat":
    st.markdown("### 🤖 Coach Chat")
    
    # 1. Render History
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(re.sub(r"<icu_workout>.*?</icu_workout>", "*[Workout Payload Hidden]*", msg["content"], flags=re.DOTALL))
            
    # 2. Strict Input Handling
    if prompt := st.chat_input("Ask coach for a plan or advice..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"): st.markdown(prompt)
        
        with st.chat_message("assistant"):
            with st.spinner("Analyzing telemetry..."):
                history = "\n".join([f"{m['role']}: {m['content']}" for m in st.session_state.messages[-6:-1]])
                acts = activities[:5] if activities else 'None'
                
                payload = f"""You are an elite cycling coach ({persona}).
                METRICS: CTL={ctl}, ATL={atl}, TSB={tsb}.
                RECENT RIDES: {acts}
                GEAR: {GEAR}
                HISTORY: {history}
                
                CRITICAL DIRECTIVE: If the user explicitly asks for a ride analysis, you MUST ask them to confirm the key metrics (Distance, Speed, Power, HR, Cadence) BEFORE executing the deep analysis. If they ask for general advice or a training plan, answer normally.
                
                USER PROMPT: {prompt}"""
                
                try:
                    resp, eng = execute_ai(payload, ai_model)
                    synced = sync_to_icu(resp)
                    
                    full_resp = f"{resp}\n\n*(Engine: {eng})*"
                    if synced > 0: full_resp += f"\n\n✅ **Success:** {synced} workout(s) synced to Intervals.icu!"
                    
                    st.markdown(re.sub(r"<icu_workout>.*?</icu_workout>", "", full_resp, flags=re.DOTALL))
                    st.session_state.messages.append({"role": "model", "content": full_resp})
                except Exception as e:
                    st.error(f"Error: {str(e)}")
                    st.session_state.messages.pop() # Clean state on failure

elif st.session_state.active_nav == "🔍 Activity Debrief":
    st.markdown("### 🔍 Ride Debrief")
    if activities:
        opts = {f"{a.get('start_date_local','')[:10]} - {a.get('name','Ride')}": a for a in activities}
        sel = st.selectbox("Select Activity", list(opts.keys()))
        act = opts[sel]
        
        c1, c2, c3 = st.columns(3)
        c1.metric("Dist", f"{round((act.get('distance') or 0)/1000, 1)}km")
        c2.metric("Power", f"{act.get('average_watts', 'N/A')}W")
        c3.metric("Time", f"{int((act.get('moving_time') or 0)/60)}m")
        
        if st.button("🤖 AI Deep Debrief", type="primary"):
            st.session_state.active_nav = "🤖 AI Coach Chat"
            st.session_state.messages.append({"role": "user", "content": f"Please provide a deep ride analysis for my activity: {sel}. Here is the raw data: {act}"})
            st.rerun()
    else: st.info("No activities found.")

elif st.session_state.active_nav == "📅 Calendar":
    st.markdown("### 📅 Upcoming Training")
    for ev in [e for e in events if e.get('start_date_local','')[:10] >= datetime.date.today().isoformat()]:
        with st.expander(f"{ev.get('start_date_local','')[:10]} - {ev.get('name', 'Workout')}"):
            st.write(ev.get('description', 'No details.'))
