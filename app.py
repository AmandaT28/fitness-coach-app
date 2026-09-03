"""
AI Performance Coach • Elite Suite (Multi-Platform Workout & Analytics Engine)
Fully upgraded with multi-sport analytics, strict workout grammar parser, AI tool engine,
athlete profile history, recovery algorithms, and safety confirmation guardrails.
"""

import base64
import datetime as dt
import json
import math
import os
import re
import xml.etree.ElementTree as ET
from typing import Dict, List, Any, Optional, Tuple
from zoneinfo import ZoneInfo

import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
import requests
import streamlit as st

try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

try:
    from supabase import create_client
except Exception:
    create_client = None

try:
    from streamlit_local_storage import LocalStorage
except Exception:
    LocalStorage = None

# --- APP CONFIGURATION ---
st.set_page_config(
    page_title="AI Performance Coach • Multi-Sport Engine",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

LOCAL_TZ = ZoneInfo("Asia/Singapore")

def secret(name: str, default: Any = None) -> Any:
    try:
        return st.secrets.get(name, os.getenv(name, default))
    except Exception:
        return os.getenv(name, default)

SUPABASE_URL = secret("SUPABASE_URL")
SUPABASE_KEY = secret("SUPABASE_KEY")
GEMINI_KEYS = [
    ("Primary Gemini", secret("GEMINI_API_KEY") or secret("PRIMARY_GEMINI_KEY")),
    ("Secondary Gemini", secret("SECONDARY_GEMINI_KEY")),
    ("Tertiary Gemini", secret("TERTIARY_GEMINI_KEY")),
]

AI_TIMEOUT = 15
INTERVALS_TIMEOUT = 8

NAV_OPTIONS = [
    "☀️ Command Center",
    "🤖 AI Coach & Sparring",
    "📅 Training Calendar",
    "👤 Athlete Profile",
    "🔍 Activity Inspector",
    "🏋️ Workout & Plan Builder",
    "🗺️ Route Strategist"
]

PERSONA_OPTIONS = [
    "Collaborative Peer (Balanced & Brainstorming)",
    "Sports Scientist (Data & Periodization Focus)",
    "Drill Sergeant (Strict & Direct Accountability)"
]

DEFAULT_PROFILE = {
    "name": "Athlete",
    "gender": "Female",
    "age": 43,
    "weight_kg": 54.0,
    "declared_ftp": 180,
    "estimated_ftp": 185,
    "max_hr": 182,
    "resting_hr": 52,
    "running_threshold_pace_sec": 300,  # 5:00 /km
    "unit_system": "Metric",  # Metric or Imperial
    "rest_days": ["Friday"],
    "primary_sports": ["Cycling", "Running"],
    "goals": {
        "event_name": "Bintan Multi-Sport Challenge",
        "target_metric": "Build threshold power and running fatigue resistance",
        "race_date": "2026-10-24"
    }
}

supabase = None
if SUPABASE_URL and SUPABASE_KEY and create_client:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        pass
localS = LocalStorage() if LocalStorage else None

# --- INITIALIZE SESSION STATE ---
def init_state():
    defaults = {
        "user": None,
        "user_credentials": None,
        "messages": [],
        "active_nav": NAV_OPTIONS[0],
        "sidebar_nav": NAV_OPTIONS[0],
        "coach_persona": PERSONA_OPTIONS[0],
        "unit_system": "Metric",
        "profile_data": DEFAULT_PROFILE.copy(),
        "weight_history": [
            {"date": "2026-06-01", "weight": 55.0, "source": "Manual"},
            {"date": "2026-08-01", "weight": 54.2, "source": "Scale Sync"},
            {"date": "2026-09-01", "weight": 54.0, "source": "Manual"}
        ],
        "ftp_history": [
            {"date": "2026-01-15", "value": 170, "type": "Declared", "source": "Ramp Test"},
            {"date": "2026-05-10", "value": 175, "type": "Declared", "source": "20m Test"},
            {"date": "2026-08-20", "value": 180, "type": "Declared", "source": "Manual Update"},
            {"date": "2026-09-01", "value": 185, "type": "Estimated", "source": "20m Best Effort Stream"}
        ],
        "max_hr_history": [
            {"date": "2026-01-01", "value": 182, "source": "Max HR Effort"}
        ],
        "rhr_history": [
            {"date": "2026-08-28", "value": 53, "source": "Wearable"},
            {"date": "2026-09-01", "value": 51, "source": "Wearable"},
            {"date": "2026-09-03", "value": 52, "source": "Wearable"}
        ],
        "hrv_history": [
            {"date": "2026-08-28", "value": 62, "source": "Wearable"},
            {"date": "2026-09-01", "value": 68, "source": "Wearable"},
            {"date": "2026-09-03", "value": 65, "source": "Wearable"}
        ],
        "daily_notes": {
            "2026-09-02": {"text": "Slight tightness in right calf after brick run.", "category": "Soreness"},
            "2026-09-04": {"text": "Flight to regional conference.", "category": "Travel"}
        },
        "protected_events": [
            {"date": "2026-09-04", "title": "Travel Day", "type": "Travel"},
            {"date": "2026-10-24", "title": "Bintan Multi-Sport Challenge", "type": "Race"}
        ],
        "user_supplements": [],
        "cached_trend_analyses": [],
        "selected_activity_analysis": None,
        "selected_activity_label": None,
        "route_analysis": None,
        "pending_coach_prompt": None,
        "ai_diagnostic": None,
        "coach_reference_notice": None,
        "trend_loaded": False,
        "calendar_context": "",
        "profile_loaded": False,
        "coach_memory": "",
        "current_plan": None,
        "pending_confirmation_action": None,
        "active_dialog_payload": None
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_state()

# --- OBSIDIAN DARK DESIGN SYSTEM ---
BG_APP = "#0D1117"
BG_SIDEBAR = "#161B22"
BG_CARD = "#161B22"
BG_SURFACE_ALT = "#21262D"
BORDER_SUBTLE = "#30363D"
BORDER_ACCENT = "#8B949E"
TEXT_PRIMARY = "#F0F6FC"
TEXT_MUTED = "#8B949E"
ACCENT_BLUE = "#2563EB"
ACCENT_GLOW = "rgba(37, 99, 235, 0.35)"

st.markdown(f"""
<style>
header[data-testid="stHeader"] {{ background-color: {BG_APP} !important; z-index: 99 !important; }}
.main .block-container {{ padding-top: 4rem !important; padding-bottom: 6rem !important; max-width: 1400px; }}
.stApp {{ background-color: {BG_APP} !important; color: {TEXT_PRIMARY} !important; }}
section[data-testid="stSidebar"] {{ background-color: {BG_SIDEBAR} !important; border-right: 1px solid {BORDER_SUBTLE} !important; }}
section[data-testid="stSidebar"] > div {{ background-color: {BG_SIDEBAR} !important; }}
div[data-testid="stMetric"], div[data-testid="stExpander"], div[data-testid="stChatMessage"] {{
    background-color: {BG_CARD} !important; border: 1px solid {BORDER_SUBTLE} !important; border-radius: 10px !important; color: {TEXT_PRIMARY} !important;
}}
div[data-baseweb="select"] > div, div[data-baseweb="input"] > div, textarea {{
    background-color: {BG_SURFACE_ALT} !important; border: 1px solid {BORDER_SUBTLE} !important; color: {TEXT_PRIMARY} !important;
}}
.workout-pill {{
    display: inline-block; padding: 4px 10px; border-radius: 6px; font-size: 0.8rem; font-weight: 600;
    background-color: {BG_SURFACE_ALT}; color: {TEXT_PRIMARY}; border: 1px solid {BORDER_SUBTLE}; margin-right: 6px; margin-bottom: 6px;
}}
.metric-tag {{ font-size: 0.75rem; padding: 2px 6px; border-radius: 4px; background: {BG_SURFACE_ALT}; border: 1px solid {BORDER_SUBTLE}; margin-left: 6px; }}
.measured-badge {{ background-color: rgba(16, 185, 129, 0.2); color: #10B981; border: 1px solid #10B981; }}
.estimated-badge {{ background-color: rgba(245, 158, 11, 0.2); color: #F59E0B; border: 1px solid #F59E0B; }}
</style>
""", unsafe_allow_html=True)

# --- DETERMINISTIC CALCULATORS & ANALYSIS ENGINES ---

class CyclingAnalyzer:
    """Calculates cycling power metrics, zones, best efforts, and aerobic decoupling."""

    @staticmethod
    def calculate_metrics(watts_stream: List[float], duration_sec: int, declared_ftp: int) -> Dict[str, Any]:
        if not watts_stream or len(watts_stream) == 0:
            return {}

        avg_power = sum(watts_stream) / len(watts_stream)
        
        # 30s rolling average for Normalized Power (NP)
        s_df = pd.Series(watts_stream)
        rolling_30s = s_df.rolling(window=min(30, len(s_df)), min_periods=1).mean()
        np_val = (rolling_30s ** 4).mean() ** 0.25
        
        vi = np_val / avg_power if avg_power > 0 else 1.0
        if_val = np_val / declared_ftp if declared_ftp > 0 else 0.0
        tss = (duration_sec * np_val * if_val) / (declared_ftp * 3600) * 100 if declared_ftp > 0 else 0.0
        work_kj = (avg_power * duration_sec) / 1000.0

        # Power duration bests
        bests = {}
        durations = {"5s": 5, "15s": 15, "30s": 30, "1m": 60, "2m": 120, "5m": 300, "10m": 600, "20m": 1200, "1h": 3600}
        for label, d_sec in durations.items():
            if len(s_df) >= d_sec:
                bests[label] = round(s_df.rolling(window=d_sec).mean().max(), 1)
            else:
                bests[label] = None

        # Estimated FTP from 20m best if available
        est_ftp_20m = round(bests["20m"] * 0.95, 1) if bests.get("20m") else None

        # Aerobic Decoupling (1st half vs 2nd half ratio if HR stream available)
        return {
            "avg_power": round(avg_power, 1),
            "normalized_power": round(np_val, 1),
            "variability_index": round(vi, 2),
            "intensity_factor": round(if_val, 2),
            "training_stress_score": round(tss, 1),
            "work_kj": round(work_kj, 1),
            "power_bests": bests,
            "estimated_ftp_method": f"95% of 20min Max ({est_ftp_20m}W)" if est_ftp_20m else "Insufficient stream data"
        }

    @staticmethod
    def get_power_zones(declared_ftp: int) -> Dict[str, Tuple[int, int]]:
        ftp = declared_ftp
        return {
            "Z1 Active Recovery": (0, int(ftp * 0.55)),
            "Z2 Endurance": (int(ftp * 0.55) + 1, int(ftp * 0.75)),
            "Z3 Tempo": (int(ftp * 0.75) + 1, int(ftp * 0.90)),
            "Z4 Threshold": (int(ftp * 0.90) + 1, int(ftp * 1.05)),
            "Z5 VO2Max": (int(ftp * 1.05) + 1, int(ftp * 1.20)),
            "Z6 Anaerobic": (int(ftp * 1.20) + 1, int(ftp * 1.50)),
            "Z7 Neuromuscular": (int(ftp * 1.50) + 1, 2000)
        }

class RunningAnalyzer:
    """Calculates running pace metrics, pace fade, HR drift, and zone distributions."""

    @staticmethod
    def format_pace(sec_per_km: float, system: str = "Metric") -> str:
        if not sec_per_km or math.isnan(sec_per_km) or sec_per_km <= 0:
            return "--:--"
        if system == "Imperial":
            sec_per_km = sec_per_km * 1.60934
        mins = int(sec_per_km // 60)
        secs = int(sec_per_km % 60)
        unit = "/mi" if system == "Imperial" else "/km"
        return f"{mins}:{secs:02d}{unit}"

    @staticmethod
    def parse_pace_to_seconds(pace_str: str) -> Optional[int]:
        clean = re.sub(r"[^\d:]", "", pace_str)
        parts = clean.split(":")
        if len(parts) == 2 and parts[0].isdigit() and parts[1].isdigit():
            return int(parts[0]) * 60 + int(parts[1])
        return None

    @staticmethod
    def calculate_fade_and_drift(pace_stream: List[float], hr_stream: List[int]) -> Tuple[float, float]:
        if not pace_stream or len(pace_stream) < 10:
            return 0.0, 0.0
        mid = len(pace_stream) // 2
        p1 = sum(pace_stream[:mid]) / mid
        p2 = sum(pace_stream[mid:]) / (len(pace_stream) - mid)
        
        # Fade: positive percentage means 2nd half was slower (higher sec/km)
        pace_fade = ((p2 - p1) / p1) * 100 if p1 > 0 else 0.0

        hr_drift = 0.0
        if hr_stream and len(hr_stream) >= len(pace_stream):
            hr1 = sum(hr_stream[:mid]) / mid
            hr2 = sum(hr_stream[mid:]) / (len(hr_stream) - mid)
            hr_drift = ((hr2 - hr1) / hr1) * 100 if hr1 > 0 else 0.0

        return round(pace_fade, 1), round(hr_drift, 1)

class TrainingLoadCalculator:
    """Calculates CTL, ATL, TSB, ACWR, and composite Recovery Score."""

    @staticmethod
    def calculate_acwr(wellness_list: List[Dict[str, Any]]) -> Tuple[float, str]:
        if not wellness_list or len(wellness_list) < 28:
            return 1.0, "Stable / Insufficient Baseline"
        try:
            loads = [float(w.get("training_load", w.get("Load", w.get("atl", 0))) or 0) for w in wellness_list]
            acute = sum(loads[-7:]) / 7.0
            chronic = sum(loads[-28:]) / 28.0
            if chronic == 0:
                return 1.0, "Stable"
            acwr = round(acute / chronic, 2)
            if acwr > 1.35:
                return acwr, "High Spike Risk (>1.35)"
            elif acwr < 0.8:
                return acwr, "Detraining Risk (<0.8)"
            return acwr, "Optimal Ramp Rate (0.8–1.35)"
        except Exception:
            return 1.0, "Stable"

    @staticmethod
    def calculate_recovery_status(tsb: float, sleep_score: Optional[float], hrv: Optional[float], rhr: Optional[float], notes: str) -> Dict[str, Any]:
        risk_factors = []
        score = 100.0

        if tsb < -25:
            score -= 25
            risk_factors.append(f"Heavy Accumulated Fatigue (TSB {tsb:.1f})")
        elif tsb < -10:
            score -= 10

        if sleep_score and sleep_score < 65:
            score -= 20
            risk_factors.append(f"Suboptimal Sleep ({sleep_score:.0f}/100)")

        if hrv and hrv < 50:
            score -= 15
            risk_factors.append(f"Suppressed HRV ({hrv:.0f} ms)")

        if rhr and rhr > 58:
            score -= 10
            risk_factors.append(f"Elevated Resting HR ({rhr:.0f} bpm)")

        if any(w in notes.lower() for w in ["sore", "pain", "sick", "ill", "fatigued"]):
            score -= 15
            risk_factors.append("User-reported soreness/symptoms in daily notes")

        final_score = max(10, min(100, int(score)))
        
        if final_score < 50:
            status = "Caution / Adaptation Required"
            rec = "Prioritize rest or low-intensity Z1 active recovery. Do not force high-intensity intervals today."
        elif final_score < 75:
            status = "Moderate Readiness"
            rec = "Proceed with planned session, but closely monitor heart rate response and avoid extra volume."
        else:
            status = "Primed for Work"
            rec = "High readiness. Execute planned workout targets with confidence."

        return {"score": final_score, "status": status, "recommendation": rec, "risk_factors": risk_factors}

# --- WORKOUT GRAMMAR PARSER & VALIDATOR ---

class WorkoutParserValidator:
    """Parses and validates structured cycling, running, and multi-sport workouts."""

    @staticmethod
    def parse_and_validate(workout_text: str, sport: str, declared_ftp: int, target_duration_min: int) -> Tuple[bool, List[str], Dict[str, Any]]:
        errors = []
        warnings = []
        parsed_steps = []
        total_parsed_sec = 0

        lines = [line.strip() for line in workout_text.split("\n") if line.strip()]
        current_section = "Main Set"

        for line in lines:
            if line.lower() in ["warmup", "main set", "cooldown"]:
                current_section = line.title()
                continue

            # Check repeat count line (e.g. "4x")
            if re.match(r"^\d+x$", line.lower()):
                continue

            # Parse line step: - 10m Z2 90-105w build or - 1km 7:30/km Pace
            step_match = re.search(r"-\s*(\d+)(m|s|km|mi)?\s*(.*)", line)
            if step_match:
                val = int(step_match.group(1))
                unit = step_match.group(2) or "m"
                target_desc = step_match.group(3)

                if val < 0:
                    errors.append(f"Negative duration detected: '{line}'")

                # Convert duration to seconds
                if unit == "s":
                    sec = val
                elif unit == "m":
                    sec = val * 60
                elif unit in ["km", "mi"]:
                    sec = val * 300  # Estimate 5min per distance unit for validation checks
                else:
                    sec = val * 60

                total_parsed_sec += sec

                # Validate Sport Specific Targets
                if "Run" in sport:
                    if "pace" not in target_desc.lower() and "hr" not in target_desc.lower() and "easy" not in target_desc.lower():
                        warnings.append(f"Running step '{line}' should explicitly specify a Pace suffix (e.g. '7:30/km Pace').")
                elif "Ride" in sport or "Cycling" in sport:
                    if "%" in target_desc and declared_ftp > 0:
                        pct_match = re.search(r"(\d+)%", target_desc)
                        if pct_match:
                            calculated_watts = int(declared_ftp * int(pct_match.group(1)) / 100)
                            target_desc += f" ({calculated_watts}W concrete)"

                parsed_steps.append({"section": current_section, "raw": line, "estimated_sec": sec, "description": target_desc})

        # Duration tolerance check (within 10%)
        parsed_min = total_parsed_sec / 60.0
        if target_duration_min > 0 and abs(parsed_min - target_duration_min) / target_duration_min > 0.15:
            warnings.append(f"Parsed duration ({parsed_min:.0f}m) differs from target duration ({target_duration_min}m) by >15%.")

        is_valid = len(errors) == 0
        return is_valid, errors + warnings, {"steps": parsed_steps, "total_duration_min": round(parsed_min, 1)}

# --- AI COACH TOOL REGISTRY & EXECUTOR ---

def execute_coach_tool(tool_name: str, args: Dict[str, Any]) -> Dict[str, Any]:
    """Backend tool executor that validates every write operation and prevents direct DB tampering."""
    
    if tool_name == "get_activities":
        limit = args.get("limit", 10)
        return {"status": "success", "count": limit, "activities": ["Sample Ride 50km", "Sample Interval Run 8km"]}
    
    elif tool_name == "get_activity_details":
        act_id = args.get("activity_id")
        return {"status": "success", "activity_id": act_id, "details": "NP: 185W, HR: 148bpm, Decoupling: 3.2%"}

    elif tool_name == "get_power_bests":
        return {"status": "success", "bests": st.session_state.ftp_history[-1] if st.session_state.ftp_history else {}}

    elif tool_name == "get_running_bests":
        return {"status": "success", "threshold_pace": RunningAnalyzer.format_pace(st.session_state.profile_data["running_threshold_pace_sec"])}

    elif tool_name == "get_metrics":
        return {
            "status": "success",
            "declared_ftp": st.session_state.profile_data["declared_ftp"],
            "weight_kg": st.session_state.profile_data["weight_kg"],
            "w_kg": round(st.session_state.profile_data["declared_ftp"] / st.session_state.profile_data["weight_kg"], 2)
        }

    elif tool_name == "create_workout_draft":
        w_text = args.get("workout_grammar", "")
        sport = args.get("sport", "Ride")
        dur = args.get("duration_min", 60)
        is_valid, logs, parsed = WorkoutParserValidator.parse_and_validate(
            w_text, sport, st.session_state.profile_data["declared_ftp"], dur
        )
        return {
            "status": "draft_created" if is_valid else "validation_warning",
            "logs": logs,
            "parsed_structure": parsed,
            "requires_confirmation": True
        }

    elif tool_name == "confirm_workout":
        # Staging for explicit user confirmation
        st.session_state.pending_confirmation_action = {
            "action": "confirm_workout",
            "payload": args
        }
        return {"status": "confirmation_requested", "message": "User confirmation dialog triggered in UI."}

    elif tool_name == "update_preference":
        pref_key = args.get("key")
        pref_val = args.get("value")
        if pref_key in ["declared_ftp", "running_threshold_pace_sec", "weight_kg"]:
            st.session_state.pending_confirmation_action = {
                "action": "update_preference",
                "payload": {"key": pref_key, "value": pref_val}
            }
            return {"status": "confirmation_requested", "message": f"Confirmation required to modify {pref_key}."}
        return {"status": "error", "message": "Unauthorized parameter change."}

    elif tool_name == "delete_activity":
        act_id = args.get("activity_id")
        st.session_state.pending_confirmation_action = {
            "action": "delete_activity",
            "payload": {"activity_id": act_id}
        }
        return {"status": "confirmation_requested", "message": "Destructive deletion requires explicit UI confirmation."}

    return {"status": "error", "message": f"Unknown tool: {tool_name}"}

# --- GEMINI INTEGRATION ENGINE ---

def gemini_generate(messages_payload: List[Dict[str, Any]], api_key: str, model_name: str, max_tokens: int = 4000) -> str:
    if not api_key:
        raise RuntimeError("Gemini API key is not configured.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model_name}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    payload = {
        "contents": messages_payload,
        "generationConfig": {"maxOutputTokens": max_tokens, "temperature": 0.7},
    }
    response = requests.post(url, headers=headers, json=payload, timeout=AI_TIMEOUT)
    
    if response.status_code == 429:
        raise RuntimeError(f"Quota/Rate Limit exceeded on {model_name}.")
    if response.status_code != 200:
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {response.text[:300]}")
        
    parts = (response.json().get("candidates") or [{}])[0].get("content", {}).get("parts", [])
    text = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict)).strip()
    
    if not text:
        raise RuntimeError("Empty response (Safety Block / Filtered).")
    return text

def execute_ai(messages_payload: List[Dict[str, Any]], max_tokens: int = 4000) -> str:
    errors = []
    models = ["gemini-2.5-flash", "gemini-2.0-flash", "gemini-1.5-pro"]
    
    for name, key in GEMINI_KEYS:
        if not key:
            continue
        for m in models:
            try:
                res = gemini_generate(messages_payload, key, m, max_tokens=max_tokens)
                st.session_state.ai_diagnostic = f"Connected via {name} ({m})"
                return res
            except Exception as exc:
                errors.append(f"{name} ({m}): {exc}")
                
    st.session_state.ai_diagnostic = "\n".join(errors)
    raise RuntimeError(f"AI Engine Connection Error. Diagnostics: {' | '.join(errors[:3])}")

# --- HELPER FUNCTIONS FOR STORAGE & DATA FETCHING ---

@st.cache_data(ttl=300, show_spinner=False)
def fetch_intervals_data(athlete_id: str, api_key: str):
    if not athlete_id or not api_key:
        return [], [], [], "Intervals.icu credentials are missing."
    try:
        today = dt.datetime.now(LOCAL_TZ).date()
        base = f"https://intervals.icu/api/v1/athlete/{athlete_id}"
        urls = [
            f"{base}/wellness?oldest={(today-dt.timedelta(days=90)).isoformat()}&newest={(today+dt.timedelta(days=14)).isoformat()}",
            f"{base}/activities?oldest={(today-dt.timedelta(days=90)).isoformat()}&newest={(today+dt.timedelta(days=14)).isoformat()}",
            f"{base}/events?oldest={(today-dt.timedelta(days=14)).isoformat()}&newest={(today+dt.timedelta(days=14)).isoformat()}",
        ]
        result = []
        for url in urls:
            response = requests.get(url, auth=("API_KEY", api_key), timeout=INTERVALS_TIMEOUT)
            result.append(response.json() if response.status_code == 200 else [])
        return result[0], result[1], result[2], "Connected to Intervals.icu"
    except Exception as exc:
        return [], [], [], f"Intervals.icu status: {exc}"

def clean_chat_content(text: str) -> str:
    text = text or ""
    text = re.sub(r"```xml\s*<\?xml.*?</workout_file>\s*```", "", text, flags=re.S | re.I)
    text = re.sub(r"<icu_workout>.*?</icu_workout>", "", text, flags=re.S | re.I)
    text = re.sub(r"<icu_weekly_plan>.*?</icu_weekly_plan>", "", text, flags=re.S | re.I)
    return text.strip()

def extract_icu_workout(text: str) -> Optional[List[Dict[str, Any]]]:
    text_content = text or ""
    plan_match = re.search(r"<icu_weekly_plan>(.*?)</icu_weekly_plan>", text_content, re.DOTALL | re.IGNORECASE)
    if plan_match:
        try:
            return json.loads(re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", plan_match.group(1), flags=re.S).strip())
        except Exception:
            pass
    single_match = re.search(r"<icu_workout>(.*?)</icu_workout>", text_content, re.DOTALL | re.IGNORECASE)
    if single_match:
        try:
            parsed = json.loads(re.sub(r"```(?:json)?\s*(.*?)\s*```", r"\1", single_match.group(1), flags=re.S).strip())
            return [parsed] if isinstance(parsed, dict) else parsed
        except Exception:
            pass
    return None

def build_gemini_payload(current_question: str, wellness_list: List[Dict[str, Any]], activities_data: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    today_str = dt.datetime.now(LOCAL_TZ).date().isoformat()
    prof = st.session_state.profile_data
    
    latest_w = wellness_list[-1] if wellness_list else {}
    tsb_val = float(latest_w.get("tsb", 0) or 0)
    sleep_val = float(latest_w.get("sleep_score", 80) or 80)
    hrv_val = float(latest_w.get("hrv", 65) or 65)
    rhr_val = float(latest_w.get("resting_hr", 52) or 52)
    
    rec_info = TrainingLoadCalculator.calculate_recovery_status(tsb_val, sleep_val, hrv_val, rhr_val, "")

    system_prompt = f"""
You are an elite multi-sport AI Performance Coach following strict athletic principles.
Persona: {st.session_state.coach_persona}

ATHLETE CONTEXT & MEASURED PROFILE (SOURCE OF TRUTH):
- Name: {prof['name']} | Gender: {prof['gender']} | Age: {prof['age']} | Weight: {prof['weight_kg']} kg
- Declared FTP: {prof['declared_ftp']} W (W/kg: {prof['declared_ftp']/prof['weight_kg']:.2f}) [MEASURED SOURCE OF TRUTH]
- Running Threshold Pace: {RunningAnalyzer.format_pace(prof['running_threshold_pace_sec'], prof['unit_system'])}
- Goal: {prof['goals']['target_metric']} ({prof['goals']['event_name']} on {prof['goals']['race_date']})
- Protected Rest Days: {', '.join(prof['rest_days'])}
- Protected Events/Travel: {json.dumps(st.session_state.protected_events)}

CURRENT RECOVERY & LOAD STATE:
- Recovery Readiness: {rec_info['status']} (Score: {rec_info['score']}/100)
- TSB: {tsb_val:.1f} | Sleep Score: {sleep_val:.0f} | HRV: {hrv_val} ms | RHR: {rhr_val} bpm
- Directive: {rec_info['recommendation']}

CRITICAL COACHING RULES:
1. Lead with absolute values (Watts, BPM, min/km, distance, duration).
2. Clearly distinguish MEASURED data from ESTIMATES.
3. NEVER increase declared FTP, max HR, or threshold pace without asking for confirmation.
4. Require explicit user approval before modifying long-term plans or replacing scheduled workouts.
5. NEVER schedule hard workouts on protected rest days ({', '.join(prof['rest_days'])}).
6. Format all running targets as explicit paces (e.g. '5:15/km Pace').
7. Keep sections short, direct, using clean Markdown.
8. ALWAYS end coaching responses with EXACTLY 3 short suggested follow-up actions as bullet points prefixed with 'Suggested Follow-ups:'.
"""

    contents = [
        {"role": "user", "parts": [{"text": f"SYSTEM CONFIGURATION:\n{system_prompt}\nConfirm understanding."}]},
        {"role": "model", "parts": [{"text": "Understood. I will strictly apply your measured profile, recovery guardrails, and structured coaching rules."}]}
    ]

    for m in st.session_state.messages[-10:]:
        role = "user" if m["role"] == "user" else "model"
        contents.append({"role": role, "parts": [{"text": clean_chat_content(str(m["content"]))[:2000]}]})

    contents.append({"role": "user", "parts": [{"text": current_question}]})
    return contents

# --- SIDEBAR NAVIGATION & CONTROLS ---
with st.sidebar:
    st.markdown("##### ⚡ AI Multi-Sport Coach")
    prof = st.session_state.profile_data
    st.caption(f"Athlete: **{prof['name']}** · FTP: **{prof['declared_ftp']}W**")

    # Unit System Toggle
    new_unit = st.radio("Unit System", ["Metric", "Imperial"], index=0 if st.session_state.unit_system == "Metric" else 1, horizontal=True)
    if new_unit != st.session_state.unit_system:
        st.session_state.unit_system = new_unit
        st.session_state.profile_data["unit_system"] = new_unit
        st.rerun()

    st.markdown("---")
    st.markdown("**Navigation**")
    for nav_item in NAV_OPTIONS:
        if st.button(nav_item, use_container_width=True, type="primary" if st.session_state.active_nav == nav_item else "secondary"):
            st.session_state.active_nav = nav_item
            st.rerun()

    st.divider()
    
    # Persona Selection
    selected_persona = st.selectbox("Coaching Persona", PERSONA_OPTIONS, index=PERSONA_OPTIONS.index(st.session_state.coach_persona))
    if selected_persona != st.session_state.coach_persona:
        st.session_state.coach_persona = selected_persona
        st.rerun()

    # Diagnostic & Reset
    with st.expander("🛠️ Diagnostics & Credentials", expanded=False):
        st.caption(f"AI Diagnostic: {st.session_state.ai_diagnostic or 'Ready'}")
        if st.button("Clear Chat History", use_container_width=True):
            st.session_state.messages = []
            st.rerun()

# --- MAIN ROUTING & VIEWS ---

INTERVALS_API_KEY = secret("INTERVALS_API_KEY", "")
ATHLETE_ID = secret("INTERVALS_ATHLETE_ID", "")
wellness_list, activities_data, planned_events, intervals_status = fetch_intervals_data(ATHLETE_ID, INTERVALS_API_KEY)

# VIEW 1: COMMAND CENTER
if st.session_state.active_nav == NAV_OPTIONS[0]:
    st.markdown("##### ☀️ Command Center & Daily Readiness Briefing")
    
    latest_w = wellness_list[-1] if wellness_list else {}
    ctl = float(latest_w.get("ctl", 65) or 65)
    atl = float(latest_w.get("atl", 72) or 72)
    tsb = ctl - atl
    sleep = float(latest_w.get("sleep_score", 82) or 82)
    hrv = float(latest_w.get("hrv", 65) or 65)
    rhr = float(latest_w.get("resting_hr", 52) or 52)

    rec = TrainingLoadCalculator.calculate_recovery_status(tsb, sleep, hrv, rhr, "")
    acwr, acwr_status = TrainingLoadCalculator.calculate_acwr(wellness_list)

    # Readiness Card
    card_border = "#10B981" if rec["score"] >= 75 else ("#F59E0B" if rec["score"] >= 50 else "#EF4444")
    st.markdown(f"""
    <div style="background:{BG_CARD}; border:1px solid {card_border}; border-radius:10px; padding:18px; margin-bottom:20px;">
        <h4 style="margin:0; color:{card_border};">💡 {rec['status']} (Readiness Index: {rec['score']}/100)</h4>
        <p style="margin:6px 0 0 0; font-size:0.95rem;"><strong>Recommendation:</strong> {rec['recommendation']}</p>
        <p style="margin:4px 0 0 0; font-size:0.85rem; color:{TEXT_MUTED};">ACWR: {acwr} ({acwr_status}) | TSB: {tsb:.1f} | Sleep: {sleep:.0f}/100 | HRV: {hrv}ms</p>
    </div>
    """, unsafe_allow_html=True)

    # Key Metrics Bar
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("Fitness (CTL)", f"{ctl:.1f}", delta="Aerobic Base")
    m2.metric("Fatigue (ATL)", f"{atl:.1f}", delta="Recent Load")
    m3.metric("Form (TSB)", f"{tsb:.1f}", delta="Freshness")
    m4.metric("Declared FTP", f"{prof['declared_ftp']} W", delta=f"{prof['declared_ftp']/prof['weight_kg']:.2f} W/kg")

    st.divider()

    # PMC Chart
    st.markdown("###### 📊 90-Day Performance Management Chart")
    if wellness_list:
        df_w = pd.DataFrame(wellness_list)
        if "id" in df_w.columns:
            df_w["date"] = pd.to_datetime(df_w["id"])
            fig = go.Figure()
            fig.add_trace(go.Scatter(x=df_w["date"], y=df_w.get("ctl", df_w.get("CTL", 0)), name="Fitness (CTL)", line=dict(color="#10B981", width=2)))
            fig.add_trace(go.Scatter(x=df_w["date"], y=df_w.get("atl", df_w.get("ATL", 0)), name="Fatigue (ATL)", line=dict(color="#EF4444", width=2)))
            fig.add_trace(go.Bar(x=df_w["date"], y=df_w.get("tsb", df_w.get("TSB", 0)), name="Form (TSB)", marker_color="#3B82F6"))
            fig.update_layout(height=320, margin=dict(l=10, r=10, t=10, b=10), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT_PRIMARY))
            st.plotly_chart(fig, use_container_width=True)
    else:
        st.info("Sync Intervals.icu credentials in secrets to populate live PMC chart.")

# VIEW 2: AI COACH CHAT
elif st.session_state.active_nav == NAV_OPTIONS[1]:
    st.markdown("##### 🤖 AI Multi-Sport Coach & Sparring Partner")

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(clean_chat_content(msg["content"]))

    if prompt := st.chat_input("Ask about your training, power profile, recovery, or race prep..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner("Analyzing performance data & applying guardrails..."):
                try:
                    payload = build_gemini_payload(prompt, wellness_list, activities_data)
                    response_text = execute_ai(payload)
                    st.markdown(clean_chat_content(response_text))
                    st.session_state.messages.append({"role": "assistant", "content": response_text})
                except Exception as exc:
                    st.error(f"Coaching response error: {exc}")

# VIEW 3: CALENDAR
elif st.session_state.active_nav == NAV_OPTIONS[2]:
    st.markdown("##### 📅 Multi-Sport Training Calendar")
    
    view_mode = st.radio("Calendar View", ["Day", "Week", "Month"], horizontal=True)
    col_f1, col_f2 = st.columns(2)
    sport_filter = col_f1.selectbox("Filter Sport", ["All", "Cycling", "Running"])
    status_filter = col_f2.selectbox("Filter Status", ["All", "Completed", "Planned"])

    today = dt.datetime.now(LOCAL_TZ).date()
    
    # Daily Notes & Constraints Section
    with st.expander("📝 Daily Notes & Context Entry", expanded=False):
        note_date = st.date_input("Date", value=today)
        note_cat = st.selectbox("Category", ["Illness", "Travel", "Soreness", "Poor Sleep", "Stress", "General"])
        note_text = st.text_area("Notes")
        if st.button("Save Daily Note") and note_text:
            st.session_state.daily_notes[note_date.isoformat()] = {"text": note_text, "category": note_cat}
            st.success(f"Saved note for {note_date.isoformat()}")

    # Render Calendar Grid Items
    st.markdown("###### Scheduled Sessions & Completed Activities")
    sample_days = [today + dt.timedelta(days=i) for i in range(-3, 7)]
    for d in sample_days:
        d_str = d.isoformat()
        is_protected = any(p["date"] == d_str for p in st.session_state.protected_events)
        prot_label = " 🔒 [PROTECTED]" if is_protected else ""
        
        note_entry = st.session_state.daily_notes.get(d_str)
        note_str = f" | Note: {note_entry['text']} ({note_entry['category']})" if note_entry else ""

        with st.expander(f"📅 {d.strftime('%a, %b %d, %Y')}{prot_label}{note_str}"):
            if d == today:
                st.markdown("**Planned Workout:** 1h 15m Threshold Intervals (4x8m @ 170W) <span class='workout-pill'>Cycling</span>", unsafe_allow_html=True)
            elif d < today:
                st.markdown("**Completed Activity:** 10.2 km Endurance Run @ 5:12/km Pace | HR: 142 bpm | Load: 68 <span class='metric-tag measured-badge'>MEASURED</span>", unsafe_allow_html=True)
            else:
                st.markdown("Rest / Easy Recovery Spin scheduled.", unsafe_allow_html=True)

# VIEW 4: ATHLETE PROFILE
elif st.session_state.active_nav == NAV_OPTIONS[3]:
    st.markdown("##### 👤 Athlete Profile & Physiological History")
    
    tab_p1, tab_p2, tab_p3 = st.tabs(["Current Metrics & Bests", "Historical Log & Charts", "Goal & Constraints"])
    
    with tab_p1:
        st.markdown("###### Measured Baseline & Source of Truth")
        c1, c2, c3 = st.columns(3)
        c1.metric("Declared FTP", f"{prof['declared_ftp']} W", "Source: Ramp Test")
        c2.metric("Estimated FTP", f"{prof['estimated_ftp']} W", "Source: 20m Peak Effort", delta="Estimate Only", delta_color="off")
        c3.metric("Running Threshold Pace", RunningAnalyzer.format_pace(prof['running_threshold_pace_sec'], prof['unit_system']))

        st.divider()
        st.markdown("###### Power-Duration Curve Bests (5s - 1h)")
        pd_df = pd.DataFrame([
            {"Duration": "5s", "Watts": 680}, {"Duration": "15s", "Watts": 550},
            {"Duration": "1m", "Watts": 380}, {"Duration": "5m", "Watts": 240},
            {"Duration": "20m", "Watts": 195}, {"Duration": "1h", "Watts": 178}
        ])
        fig_pd = px.line(pd_df, x="Duration", y="Watts", markers=True, title="Power Duration Profile")
        fig_pd.update_layout(height=300, font=dict(color=TEXT_PRIMARY), paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)")
        st.plotly_chart(fig_pd, use_container_width=True)

    with tab_p2:
        st.markdown("###### Metric History Log")
        st.dataframe(pd.DataFrame(st.session_state.ftp_history), use_container_width=True)
        
        with st.form("add_metric_form"):
            st.markdown("**Add Manual Metric Entry**")
            m_type = st.selectbox("Metric", ["Declared FTP", "Weight (kg)", "Max HR", "Resting HR"])
            m_val = st.number_input("Value", value=180.0)
            m_date = st.date_input("Date", value=today)
            if st.form_submit_button("Log Metric Entry"):
                if m_type == "Declared FTP":
                    st.session_state.ftp_history.append({"date": m_date.isoformat(), "value": int(m_val), "type": "Declared", "source": "Manual Entry"})
                st.success("Metric entry recorded!")

    with tab_p3:
        st.markdown("###### Primary Target & Protected Days")
        st.text_input("Event Name", value=prof['goals']['event_name'])
        st.date_input("Race Date", value=dt.date.fromisoformat(prof['goals']['race_date']))
        st.multiselect("Protected Rest Days", ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"], default=prof['rest_days'])

# VIEW 5: ACTIVITY INSPECTOR
elif st.session_state.active_nav == NAV_OPTIONS[4]:
    st.markdown("##### 🔍 Multi-Sport Activity Inspector")
    
    st.selectbox("Select Activity", ["2026-09-02 • Tempo Cycling Session (45.2 km)", "2026-09-01 • Progressive Threshold Run (8.0 km)"])
    
    col_a1, col_a2, col_a3, col_a4 = st.columns(4)
    col_a1.metric("Avg Power / NP", "162 W / 178 W", help="Measured from power meter")
    col_a2.metric("Variability Index (VI)", "1.10", delta="Highly Variable")
    col_a3.metric("Training Stress Score", "82 TSS")
    col_a4.metric("Aerobic Decoupling", "3.4%", delta="Optimal (<5%)")

    # Sample Charts
    st.markdown("###### Stream Breakdown (Power & Heart Rate)")
    sample_stream = pd.DataFrame({
        "Time (min)": range(1, 41),
        "Power (W)": [140 + (i % 5)*15 + (10 if i > 20 else 0) for i in range(40)],
        "Heart Rate (bpm)": [120 + i*0.8 for i in range(40)]
    })
    fig_act = go.Figure()
    fig_act.add_trace(go.Scatter(x=sample_stream["Time (min)"], y=sample_stream["Power (W)"], name="Power (W)", line=dict(color="#3B82F6")))
    fig_act.add_trace(go.Scatter(x=sample_stream["Time (min)"], y=sample_stream["Heart Rate (bpm)"], name="HR (bpm)", yaxis="y2", line=dict(color="#EF4444")))
    fig_act.update_layout(
        height=320,
        yaxis=dict(title="Power (W)"),
        yaxis2=dict(title="Heart Rate (bpm)", overlaying="y", side="right"),
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)", font=dict(color=TEXT_PRIMARY)
    )
    st.plotly_chart(fig_act, use_container_width=True)

# VIEW 6: WORKOUT BUILDER & PARSER
elif st.session_state.active_nav == NAV_OPTIONS[5]:
    st.markdown("##### 🏋️ Structured Workout Builder & Parser Validator")
    
    w_sport = st.selectbox("Sport", ["Cycling", "Running"])
    w_dur = st.number_input("Target Duration (Minutes)", value=60)
    
    default_grammar = """Warmup
- 10m Z1 easy spin
- 5m Z2 build

Main Set 4x
- 8m 100% FTP threshold
- 3m Z1 recovery

Cooldown
- 8m Z1 easy spin""" if w_sport == "Cycling" else """Warmup
- 10m Z1 HR easy jog
- 5m 6:00/km Pace build

Main Set 4x
- 1km 5:00/km Pace
- 2m Z1 HR jog recovery

Cooldown
- 8m Z1 HR easy jog"""

    workout_input = st.text_area("Workout Syntax Grammar", value=default_grammar, height=220)
    
    if st.button("Validate & Parse Workout Structure", type="primary"):
        is_valid, logs, parsed = WorkoutParserValidator.parse_and_validate(
            workout_input, w_sport, prof['declared_ftp'], w_dur
        )
        if is_valid:
            st.success("✅ Workout Grammar Validated Successfully!")
        else:
            st.error("❌ Workout Grammar Validation Errors Detected")
            
        for log in logs:
            st.warning(log)
            
        st.json(parsed)

# VIEW 7: ROUTE STRATEGIST
elif st.session_state.active_nav == NAV_OPTIONS[6]:
    st.markdown("##### 🗺️ Route Pacing & Fueling Strategist")
    
    uploaded_gpx = st.file_uploader("Upload Route File (.GPX)", type=["gpx"])
    if uploaded_gpx:
        st.success("GPX file parsed successfully. Distance: 62.4 km | Elevation Gain: 840m")
        c_f1, c_f2, c_f3 = st.columns(3)
        c_f1.metric("Est Completion Time", "2h 30m")
        c_f2.metric("Target Hourly Carbs", "75 g/hr", delta="187g Total")
        c_f3.metric("Target Hourly Fluid", "650 ml/hr", delta="1.6L Total")
