import os
import re
import json
import math
import base64
import datetime as dt
import xml.etree.ElementTree as ET

import requests
import pandas as pd
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


# ============================================================
# CONFIGURATION
# ============================================================

st.set_page_config(
    page_title="AI Performance Coach • Elite Suite",
    page_icon="🚴‍♂️",
    layout="wide",
)

SUPABASE_URL = st.secrets.get("SUPABASE_URL", os.getenv("SUPABASE_URL"))
SUPABASE_KEY = st.secrets.get("SUPABASE_KEY", os.getenv("SUPABASE_KEY"))

PRIMARY_GEMINI_KEY = (
    st.secrets.get("GEMINI_API_KEY")
    or st.secrets.get("PRIMARY_GEMINI_KEY")
    or os.getenv("GEMINI_API_KEY")
    or os.getenv("PRIMARY_GEMINI_KEY")
)

SECONDARY_GEMINI_KEY = (
    st.secrets.get("SECONDARY_GEMINI_KEY")
    or os.getenv("SECONDARY_GEMINI_KEY")
)

TERTIARY_GEMINI_KEY = (
    st.secrets.get("TERTIARY_GEMINI_KEY")
    or os.getenv("TERTIARY_GEMINI_KEY")
)

OPENAI_KEY = st.secrets.get("OPENAI_API_KEY", os.getenv("OPENAI_API_KEY"))
ANTHROPIC_KEY = st.secrets.get("ANTHROPIC_API_KEY", os.getenv("ANTHROPIC_API_KEY"))

GEMINI_MODEL = st.secrets.get(
    "GEMINI_MODEL",
    os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
)

INTERVALS_TIMEOUT = 6
AI_TIMEOUT = 25

if SUPABASE_URL and SUPABASE_KEY and create_client:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
    except Exception:
        supabase = None
else:
    supabase = None

localS = LocalStorage() if LocalStorage else None


# ============================================================
# STYLING
# ============================================================

st.markdown(
    """
<style>
.stCard {
    background-color: #ffffff;
    border: 1px solid rgba(128,128,128,.15);
    border-radius: 12px;
    padding: 20px;
    margin-bottom: 16px;
    box-shadow: 0 4px 12px rgba(0,0,0,.03);
}
div[data-testid="stMetric"] {
    background-color: rgba(128,128,128,.02);
    border: 1px solid rgba(128,128,128,.08);
    padding: 12px 16px;
    border-radius: 10px;
}
</style>
""",
    unsafe_allow_html=True,
)


# ============================================================
# SESSION STATE
# ============================================================

DEFAULT_GOALS = {
    "event_name": "Bintan Round Island",
    "target_metric": "Survive steep climbs on group rides & improve threshold power",
    "race_date": "2026-10-24",
}

def init_state():
    defaults = {
        "user": None,
        "user_credentials": None,
        "messages": [],
        "active_nav": "📊 Command Center",
        "athlete_gear": "",
        "athlete_limitations": "",
        "goals": DEFAULT_GOALS.copy(),
        "user_supplements": [
            {"name": "Creatine", "timing": "Post-Workout", "notes": "Cellular ATP replenishment & sprint power"},
            {"name": "Protein", "timing": "Post-Workout (<45m)", "notes": "Muscle repair & glycogen resynthesis"},
            {"name": "Turmeric", "timing": "Morning with Fats", "notes": "Systemic inflammation control"},
            {"name": "Fish Oil", "timing": "Morning & Evening", "notes": "Cardiovascular & nocturnal recovery"},
            {"name": "NMN", "timing": "Morning (Fasted)", "notes": "Cellular NAD+ & mitochondrial support"},
        ],
        "cached_trend_analysis": None,
        "trend_analysis_timestamp": None,
        "selected_activity_analysis": None,
        "onboarding_done": False,
        "ai_test_result": None,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value

init_state()


# ============================================================
# HELPERS
# ============================================================

def safe_secret(name, default=None):
    try:
        value = st.secrets.get(name)
        if value:
            return value
    except Exception:
        pass
    return os.getenv(name, default)


def normalize_role(role):
    return "assistant" if role in ("model", "assistant") else "user"


def clean_chat_content(text):
    if not text:
        return ""
    text = re.sub(r"```xml\s*<\?xml.*?</workout_file>\s*```", "", text, flags=re.S | re.I)
    text = re.sub(r"```\s*<workout_file>.*?</workout_file>\s*```", "", text, flags=re.S | re.I)
    text = re.sub(r"<icu_workout>.*?</icu_workout>", "", text, flags=re.S | re.I)
    return text.strip()


def ensure_initial_message():
    if not st.session_state.messages:
        st.session_state.messages = [{
            "role": "assistant",
            "content": (
                "Hello! I am your autonomous AI Performance Coach. "
                "Ask me about your training, recovery, climbing, threshold work, "
                "or how to approach your upcoming event."
            ),
        }]


# ============================================================
# GEMINI REST API
# ============================================================

def gemini_generate(prompt, api_key, model=None, timeout=AI_TIMEOUT):
    if not api_key:
        raise RuntimeError("Gemini API key is not configured.")

    model = model or GEMINI_MODEL
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [{"text": prompt}],
            }
        ]
    }

    response = requests.post(
        url,
        headers={
            "Content-Type": "application/json",
            "x-goog-api-key": api_key,
        },
        json=payload,
        timeout=timeout,
    )

    if response.status_code != 200:
        try:
            detail = response.json()
        except Exception:
            detail = response.text
        raise RuntimeError(f"Gemini HTTP {response.status_code}: {detail}")

    data = response.json()

    candidates = data.get("candidates") or []
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {data}")

    parts = (
        candidates[0]
        .get("content", {})
        .get("parts", [])
    )

    text_parts = [
        p.get("text", "")
        for p in parts
        if isinstance(p, dict) and p.get("text")
    ]

    text = "\n".join(text_parts).strip()

    if not text:
        raise RuntimeError(f"Gemini returned an empty response: {data}")

    return text


def execute_ai(prompt, preferred_provider="Google Gemini (Flash)"):
    """
    Bounded AI router.

    Chat is intentionally independent from Intervals.icu.
    The router only contacts the selected AI provider.
    """
    errors = []

    if "Google" in preferred_provider or "Auto" in preferred_provider:
        keys = [
            ("Guest/Primary Gemini", PRIMARY_GEMINI_KEY),
            ("Secondary Gemini", SECONDARY_GEMINI_KEY),
            ("Tertiary Gemini", TERTIARY_GEMINI_KEY),
        ]

        seen = set()
        for name, key in keys:
            if not key or key in seen:
                continue
            seen.add(key)
            try:
                return gemini_generate(prompt, key), name
            except Exception as exc:
                errors.append(f"{name}: {exc}")

        if "Google" in preferred_provider:
            raise RuntimeError(" | ".join(errors) if errors else "No Gemini key configured.")

    if ("OpenAI" in preferred_provider or "Auto" in preferred_provider) and OPENAI_KEY:
        try:
            # REST call avoids requiring the OpenAI Python SDK version to match.
            response = requests.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "gpt-4o-mini",
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 1200,
                },
                timeout=AI_TIMEOUT,
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"OpenAI HTTP {response.status_code}: {response.text}"
                )
            data = response.json()
            text = data["choices"][0]["message"]["content"].strip()
            if not text:
                raise RuntimeError("OpenAI returned an empty response.")
            return text, "OpenAI GPT-4o-mini"
        except Exception as exc:
            errors.append(f"OpenAI: {exc}")

    if ("Anthropic" in preferred_provider or "Auto" in preferred_provider) and ANTHROPIC_KEY:
        try:
            response = requests.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_KEY,
                    "anthropic-version": "2023-06-01",
                    "Content-Type": "application/json",
                },
                json={
                    "model": "claude-3-5-sonnet-20241022",
                    "max_tokens": 1200,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=AI_TIMEOUT,
            )
            if response.status_code != 200:
                raise RuntimeError(
                    f"Anthropic HTTP {response.status_code}: {response.text}"
                )
            data = response.json()
            text = "\n".join(
                block.get("text", "")
                for block in data.get("content", [])
                if block.get("type") == "text"
            ).strip()
            if not text:
                raise RuntimeError("Anthropic returned an empty response.")
            return text, "Anthropic Claude"
        except Exception as exc:
            errors.append(f"Anthropic: {exc}")

    raise RuntimeError("All selected AI providers failed: " + " | ".join(errors))


# ============================================================
# INTERVALS.ICU -- ONLY CALLED OUTSIDE CHAT
# ============================================================

@st.cache_data(ttl=300, show_spinner=False)
def fetch_intervals_data(athlete_id, api_key):
    if not athlete_id or not api_key:
        return [], [], [], "Intervals.icu credentials are missing."

    try:
        today = dt.date.today()
        start_90 = (today - dt.timedelta(days=90)).isoformat()
        start_7 = (today - dt.timedelta(days=7)).isoformat()
        end_14 = (today + dt.timedelta(days=14)).isoformat()

        base = f"https://intervals.icu/api/v1/athlete/{athlete_id}"

        endpoints = [
            ("wellness", f"{base}/wellness?oldest={start_90}&newest={end_14}"),
            ("activities", f"{base}/activities?oldest={start_90}&newest={end_14}"),
            ("events", f"{base}/events?oldest={start_7}&newest={end_14}"),
        ]

        results = []

        for _, url in endpoints:
            r = requests.get(
                url,
                auth=("API_KEY", api_key),
                timeout=INTERVALS_TIMEOUT,
            )

            if r.status_code != 200:
                results.append([])
                continue

            try:
                results.append(r.json())
            except Exception:
                results.append([])

        return results[0], results[1], results[2], ""

    except requests.Timeout:
        return [], [], [], "Intervals.icu request timed out."
    except Exception as exc:
        return [], [], [], f"Intervals.icu error: {exc}"


# ============================================================
# LOGIN / GUEST SETUP
# ============================================================

def load_guest_token():
    try:
        token = st.query_params.get("token")
        if not token or st.session_state.user_credentials:
            return

        decoded = base64.urlsafe_b64decode(token.encode("utf-8"))
        config = json.loads(decoded.decode("utf-8"))

        if config.get("icu_key") and config.get("icu_id"):
            st.session_state.user_credentials = config
            if localS:
                try:
                    localS.setItem("athlete_profile_config", config)
                except Exception:
                    pass
            st.rerun()
    except Exception:
        pass


load_guest_token()

if not st.session_state.user and not st.session_state.user_credentials and localS:
    try:
        stored = localS.getItem("athlete_profile_config")
        if stored:
            st.session_state.user_credentials = stored
    except Exception:
        pass


def login_portal():
    st.markdown("## 🔐 Elite Athlete Portal")

    owner_tab, guest_tab = st.tabs(
        ["👑 Owner Login", "⚙️ Friend / Guest Setup"]
    )

    with owner_tab:
        if not supabase:
            st.warning(
                "Supabase is not configured. Add SUPABASE_URL and SUPABASE_KEY "
                "to Streamlit Secrets if you want owner login."
            )
        else:
            with st.form("supabase_login_form"):
                email = st.text_input("Email")
                password = st.text_input("Password", type="password")

                if st.form_submit_button(
                    "Log In with Supabase",
                    use_container_width=True,
                ):
                    try:
                        result = supabase.auth.sign_in_with_password(
                            {"email": email, "password": password}
                        )
                        st.session_state.user = result.user
                        st.rerun()
                    except Exception as exc:
                        st.error(f"Login failed: {exc}")

    with guest_tab:
        st.info(
            "Guest mode keeps the Intervals.icu and Gemini credentials in "
            "this browser session."
        )

        with st.form("guest_setup_form"):
            name = st.text_input("Your Name / Identifier")
            icu_key = st.text_input("Intervals.icu API Key", type="password")
            icu_id = st.text_input("Intervals.icu Athlete ID")
            gemini_key = st.text_input(
                "Google Gemini API Key",
                type="password",
            )

            if st.form_submit_button(
                "Save & Launch Guest Session",
                use_container_width=True,
            ):
                if not icu_key or not icu_id:
                    st.error("Intervals.icu API key and Athlete ID are required.")
                else:
                    config = {
                        "name": name.strip() or "Guest Athlete",
                        "icu_key": icu_key.strip(),
                        "icu_id": icu_id.strip(),
                        "gemini_key": gemini_key.strip(),
                        "gear": "",
                        "limitations": "",
                        "onboarding_done": True,
                    }

                    st.session_state.user_credentials = config

                    if localS:
                        try:
                            localS.setItem("athlete_profile_config", config)
                        except Exception:
                            pass

                    st.rerun()


if not st.session_state.user and not st.session_state.user_credentials:
    login_portal()
    st.stop()


# ============================================================
# RESOLVE ATHLETE
# ============================================================

user_profile = {}

if st.session_state.user:
    USER_ID = st.session_state.user.id

    if supabase:
        try:
            result = (
                supabase.table("profiles")
                .select("*")
                .eq("id", USER_ID)
                .execute()
            )
            user_profile = result.data[0] if result.data else {}
        except Exception:
            user_profile = {}

    INTERVALS_API_KEY = user_profile.get("intervals_api_key")
    ATHLETE_ID = user_profile.get("intervals_athlete_id")
    display_name = user_profile.get("name") or "Athlete"

    st.session_state.athlete_gear = (
        st.session_state.athlete_gear
        or user_profile.get("gear_notes")
        or ""
    )

    st.session_state.athlete_limitations = (
        st.session_state.athlete_limitations
        or user_profile.get("limitations_notes")
        or ""
    )

    st.session_state.goals["event_name"] = (
        user_profile.get("event_name") or DEFAULT_GOALS["event_name"]
    )
    st.session_state.goals["target_metric"] = (
        user_profile.get("target_metric") or DEFAULT_GOALS["target_metric"]
    )
    st.session_state.goals["race_date"] = (
        user_profile.get("race_date") or DEFAULT_GOALS["race_date"]
    )

    # Owner profile can override the global Gemini key.
    owner_gemini = user_profile.get("gemini_api_key")
    if owner_gemini:
        PRIMARY_GEMINI_KEY = owner_gemini

else:
    creds = st.session_state.user_credentials
    INTERVALS_API_KEY = creds.get("icu_key", "")
    ATHLETE_ID = creds.get("icu_id", "")
    display_name = creds.get("name", "Guest Athlete")

    if creds.get("gemini_key"):
        # Guest key takes priority over deployment keys.
        PRIMARY_GEMINI_KEY = creds.get("gemini_key")

    st.session_state.athlete_gear = (
        st.session_state.athlete_gear or creds.get("gear", "")
    )
    st.session_state.athlete_limitations = (
        st.session_state.athlete_limitations
        or creds.get("limitations", "")
    )


ensure_initial_message()


# ============================================================
# NAVIGATION
# ============================================================

NAV_OPTIONS = [
    "📊 Command Center",
    "🤖 AI Coach & Sparring",
    "📅 Training Calendar",
    "🔍 Activity Inspector",
    "💊 Recovery & Supplements",
    "🗺️ Route Strategist",
]

top_nav = st.radio(
    "Navigation",
    NAV_OPTIONS,
    index=NAV_OPTIONS.index(st.session_state.active_nav),
    horizontal=True,
    label_visibility="collapsed",
    key="top_nav",
)

if top_nav != st.session_state.active_nav:
    st.session_state.active_nav = top_nav
    st.rerun()

selected_nav = st.session_state.active_nav


# ============================================================
# CRITICAL ARCHITECTURE:
# DO NOT FETCH INTERVALS DATA ON CHAT PAGE.
# ============================================================

if selected_nav == "🤖 AI Coach & Sparring":
    wellness_list = []
    activities_data = []
    planned_events = []
    intervals_status = "Skipped on chat page for responsiveness."
else:
    wellness_list, activities_data, planned_events, intervals_status = (
        fetch_intervals_data(ATHLETE_ID, INTERVALS_API_KEY)
    )


# ============================================================
# METRICS
# ============================================================

ctl = atl = tsb = sleep_score = 0

if wellness_list:
    latest = wellness_list[-1] or {}
    ctl = latest.get("ctl", 0) or 0
    atl = latest.get("atl", 0) or 0
    tsb = latest.get("tsb", 0) or 0

    for row in reversed(wellness_list):
        if sleep_score == 0 and row.get("sleepScore"):
            sleep_score = row.get("sleepScore")


try:
    race_date_obj = dt.datetime.strptime(
        st.session_state.goals["race_date"],
        "%Y-%m-%d",
    ).date()
except Exception:
    race_date_obj = dt.date(2026, 10, 24)

days_left = (race_date_obj - dt.date.today()).days


# ============================================================
# SIDEBAR
# ============================================================

with st.sidebar:
    st.markdown(f"👤 **{display_name}**")

    sidebar_nav = st.radio(
        "Secondary Navigation",
        NAV_OPTIONS,
        index=NAV_OPTIONS.index(selected_nav),
        label_visibility="collapsed",
        key="sidebar_nav",
    )

    if sidebar_nav != selected_nav:
        st.session_state.active_nav = sidebar_nav
        st.rerun()

    st.markdown("---")

    st.subheader("⚙️ Athlete Profile")

    with st.form("gear_profile_form"):
        gear = st.text_area(
            "Bike Build & Gear Notes",
            value=st.session_state.athlete_gear,
        )
        limitations = st.text_area(
            "Physical Limitations / Notes",
            value=st.session_state.athlete_limitations,
        )

        if st.form_submit_button(
            "Save Profile",
            use_container_width=True,
        ):
            st.session_state.athlete_gear = gear
            st.session_state.athlete_limitations = limitations

            if st.session_state.user and supabase:
                try:
                    (
                        supabase.table("profiles")
                        .update({
                            "gear_notes": gear,
                            "limitations_notes": limitations,
                        })
                        .eq("id", USER_ID)
                        .execute()
                    )
                    st.success("Saved to Supabase.")
                except Exception as exc:
                    st.error(f"Supabase save failed: {exc}")
            else:
                creds = st.session_state.user_credentials
                creds["gear"] = gear
                creds["limitations"] = limitations

                if localS:
                    try:
                        localS.setItem("athlete_profile_config", creds)
                    except Exception:
                        pass

                st.success("Saved locally.")

    st.markdown("---")

    coach_persona = st.selectbox(
        "🎭 Coaching Persona",
        [
            "Collaborative Peer (Balanced & Brainstorming)",
            "Sports Scientist (Data & Periodization Focus)",
            "Drill Sergeant (Strict & Direct Accountability)",
        ],
    )

    selected_provider = st.selectbox(
        "⚡ AI Engine",
        [
            "Google Gemini (Flash)",
            "⚡ Auto-Fallback Chain",
            "OpenAI GPT-4o-mini",
            "Anthropic Claude",
        ],
    )

    st.markdown("---")

    with st.expander("🔧 AI Diagnostics", expanded=False):
        st.write(
            f"Guest Gemini key: "
            f"{'configured' if st.session_state.user_credentials and st.session_state.user_credentials.get('gemini_key') else 'not configured'}"
        )
        st.write(
            f"Primary Gemini: {'configured' if PRIMARY_GEMINI_KEY else 'not configured'}"
        )
        st.write(
            f"OpenAI: {'configured' if OPENAI_KEY else 'not configured'}"
        )
        st.write(
            f"Anthropic: {'configured' if ANTHROPIC_KEY else 'not configured'}"
        )
        st.caption(f"Gemini model: {GEMINI_MODEL}")

        if st.button(
            "🧪 Test Gemini",
            use_container_width=True,
            key="test_gemini",
        ):
            if not PRIMARY_GEMINI_KEY:
                st.session_state.ai_test_result = (
                    "❌ No Gemini API key is configured."
                )
            else:
                try:
                    test_response = gemini_generate(
                        "Reply with exactly: AI connection successful.",
                        PRIMARY_GEMINI_KEY,
                    )
                    st.session_state.ai_test_result = (
                        "✅ Gemini responded:\n\n" + test_response
                    )
                except Exception as exc:
                    st.session_state.ai_test_result = (
                        "❌ Gemini test failed:\n\n"
                        f"{type(exc).__name__}: {exc}"
                    )

        if st.session_state.ai_test_result:
            st.code(st.session_state.ai_test_result)

    st.markdown("---")

    if st.button(
        "🗑️ Clear Chat History",
        use_container_width=True,
    ):
        st.session_state.messages = []
        ensure_initial_message()
        st.rerun()

    if st.button(
        "🚪 Log Out / Switch Account",
        use_container_width=True,
    ):
        if st.session_state.user and supabase:
            try:
                supabase.auth.sign_out()
            except Exception:
                pass

        st.session_state.user = None
        st.session_state.user_credentials = None

        if localS:
            try:
                localS.deleteItem("athlete_profile_config")
            except Exception:
                pass

        st.rerun()


# ============================================================
# VIEW 1 — COMMAND CENTER
# ============================================================

if selected_nav == "📊 Command Center":

    st.markdown("### ☀️ AI Performance Coach • Command Center")

    st.info(f"Intervals.icu status: {intervals_status}")

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Fitness (CTL)", round(ctl, 1))
    c2.metric("Fatigue (ATL)", round(atl, 1))
    c3.metric("Form (TSB)", round(tsb, 1))
    c4.metric(
        "Sleep Score",
        f"{sleep_score}/100" if sleep_score else "N/A",
    )

    st.markdown("---")

    st.markdown(
        f"""
**Target Race:** {st.session_state.goals['event_name']}

**Race Date:** {race_date_obj.strftime('%B %d, %Y')}  
**Days Left:** {days_left}

**Objective:** {st.session_state.goals['target_metric']}
"""
    )

    if st.button(
        "🚀 Run 90-Day Trend Synthesis",
        type="primary",
    ):
        payload = f"""
You are an elite cycling sports science coach.

Analyze this athlete's training trend.

CTL: {ctl}
ATL: {atl}
TSB: {tsb}

Recent activities:
{activities_data[:15]}

Goal:
{st.session_state.goals['target_metric']}

Race:
{st.session_state.goals['event_name']}

Provide:
1. Fitness trajectory
2. Training consistency
3. Fatigue/form interpretation
4. Climbing readiness
5. Practical next steps
"""
        with st.spinner("Analyzing..."):
            try:
                result, engine = execute_ai(
                    payload,
                    selected_provider,
                )
                st.session_state.cached_trend_analysis = result
                st.session_state.trend_analysis_timestamp = (
                    dt.datetime.now().strftime("%Y-%m-%d %H:%M")
                )
                st.success(f"Generated via {engine}")
            except Exception as exc:
                st.error(f"Analysis failed: {exc}")

    if st.session_state.cached_trend_analysis:
        st.markdown(st.session_state.cached_trend_analysis)


# ============================================================
# VIEW 2 — AI COACH
# THIS PAGE HAS NO INTERVALS.ICU CALL.
# ============================================================

elif selected_nav == "🤖 AI Coach & Sparring":

    st.markdown("### 🤖 AI Coach & Collaborative Sparring Partner")

    st.caption(
        f"Persona: **{coach_persona}** · "
        "Chat is isolated from Intervals.icu so AI responses are not blocked by telemetry."
    )

    # --------------------------------------------------------
    # Render history FIRST
    # --------------------------------------------------------

    for index, message in enumerate(st.session_state.messages):
        role = normalize_role(message.get("role"))
        content = clean_chat_content(message.get("content", ""))

        if not content:
            continue

        with st.chat_message(role):
            st.markdown(content)

    # --------------------------------------------------------
    # CHAT INPUT
    # --------------------------------------------------------

    prompt = st.chat_input(
        "Ask your coach anything...",
        key="coach_chat_input",
    )

    if prompt:

        prompt = prompt.strip()

        if not prompt:
            st.stop()

        # ====================================================
        # CRITICAL:
        # SAVE USER MESSAGE BEFORE AI CALL.
        # NEVER POP IT ON FAILURE.
        # ====================================================

        st.session_state.messages.append({
            "role": "user",
            "content": prompt,
        })

        # Show it immediately in the current Streamlit run.
        with st.chat_message("user"):
            st.markdown(prompt)

        # ====================================================
        # BUILD SMALL, FAST PROMPT
        # NO INTERVALS DATA IS FETCHED HERE.
        # ====================================================

        recent_history = st.session_state.messages[-7:]

        history_text = "\n".join(
            f"{normalize_role(m['role']).upper()}: {m['content']}"
            for m in recent_history
        )

        coach_prompt = f"""
You are an elite cycling performance coach.

Coaching persona:
{coach_persona}

Athlete:
{display_name}

Primary goal:
{st.session_state.goals['target_metric']}

Target event:
{st.session_state.goals['event_name']}

Race date:
{st.session_state.goals['race_date']}

Bike / gear:
{st.session_state.athlete_gear or 'Not provided'}

Limitations / notes:
{st.session_state.athlete_limitations or 'Not provided'}

Recent conversation:
{history_text}

Current athlete question:
{prompt}

Give a direct, useful coaching answer.
Do not produce XML.
Do not produce JSON.
Do not claim to have changed Intervals.icu.
Do not invent telemetry that has not been provided.
"""

        # ====================================================
        # AI CALL
        # ====================================================

        with st.chat_message("assistant"):
            placeholder = st.empty()
            placeholder.markdown("🤔 **Coach is thinking...**")

            try:
                response, engine = execute_ai(
                    coach_prompt,
                    selected_provider,
                )

                placeholder.markdown(response)

                st.session_state.messages.append({
                    "role": "assistant",
                    "content": response,
                })

                st.caption(f"Engine: {engine}")

            except Exception as exc:

                error_text = (
                    "⚠️ **Coach could not respond.**\n\n"
                    f"`{type(exc).__name__}: {exc}`"
                )

                placeholder.markdown(error_text)

                # IMPORTANT:
                # The user message remains in history.
                st.session_state.messages.append({
                    "role": "assistant",
                    "content": error_text,
                })


# ============================================================
# VIEW 3 — TRAINING CALENDAR
# ============================================================

elif selected_nav == "📅 Training Calendar":

    st.markdown("### 📅 Training Calendar")

    if not planned_events:
        st.info("No upcoming Intervals.icu events were returned.")

    for event in planned_events:
        date = event.get("start_date_local", "")[:10]
        name = event.get("name", "Planned Workout")

        with st.expander(f"{date} — {name}"):
            st.write(event)

    st.markdown("---")

    focus = st.selectbox(
        "2-Week Block Focus",
        [
            "Threshold Power & Sweet Spot Progression",
            "Climbing Endurance & Resistance Blocks",
            "Recovery & Taper Structure",
            "Custom Indoor/Outdoor Balance",
        ],
    )

    if st.button(
        "🤖 Propose 2-Week Block",
        type="primary",
    ):
        st.session_state.messages.append({
            "role": "user",
            "content": (
                f"Please propose a complete 2-week training block focused on "
                f"'{focus}'. I want to review it before any syncing."
            ),
        })
        st.session_state.active_nav = "🤖 AI Coach & Sparring"
        st.rerun()


# ============================================================
# VIEW 4 — ACTIVITY INSPECTOR
# ============================================================

elif selected_nav == "🔍 Activity Inspector":

    st.markdown("### 🔍 Activity Inspector")

    if not activities_data:
        st.info("No activities found.")
    else:
        options = {}

        for activity in activities_data:
            name = activity.get("name", "Unnamed")
            date = activity.get("start_date_local", "")[:10]
            distance = round((activity.get("distance") or 0) / 1000, 1)

            label = f"{date} — {name} ({distance} km)"
            options[label] = activity

        selected = st.selectbox(
            "Choose an activity",
            list(options.keys()),
        )

        activity = options[selected]

        c1, c2, c3 = st.columns(3)
        c1.metric(
            "Distance",
            f"{round((activity.get('distance') or 0) / 1000, 2)} km",
        )
        c2.metric(
            "Moving Time",
            f"{int((activity.get('moving_time') or 0) / 60)} min",
        )
        c3.metric(
            "Average Power",
            f"{activity.get('average_watts', 'N/A')} W",
        )

        if st.button(
            "🤖 Run AI Debrief",
            type="primary",
        ):
            prompt = f"""
Perform a cycling performance debrief.

Activity:
{json.dumps(activity, indent=2)}

Athlete goal:
{st.session_state.goals['target_metric']}

Explain:
- execution
- intensity
- likely training stimulus
- strengths
- weaknesses
- recovery implications
- next training recommendation
"""
            with st.spinner("Analyzing activity..."):
                try:
                    result, engine = execute_ai(
                        prompt,
                        selected_provider,
                    )
                    st.session_state.selected_activity_analysis = result
                    st.success(f"Generated via {engine}")
                except Exception as exc:
                    st.error(f"Debrief failed: {exc}")

        if st.session_state.selected_activity_analysis:
            st.markdown("---")
            st.markdown(
                st.session_state.selected_activity_analysis
            )


# ============================================================
# VIEW 5 — RECOVERY / SUPPLEMENTS
# ============================================================

elif selected_nav == "💊 Recovery & Supplements":

    st.markdown("### 💊 Recovery & Supplement Protocol")

    with st.form(
        "add_supplement_form",
        clear_on_submit=True,
    ):
        c1, c2, c3 = st.columns([1, 1, 2])

        name = c1.text_input("Name")
        timing = c2.text_input("Timing")
        notes = c3.text_input("Notes")

        if st.form_submit_button(
            "➕ Add",
            use_container_width=True,
        ):
            if name.strip():
                st.session_state.user_supplements.append({
                    "name": name.strip(),
                    "timing": timing.strip() or "As needed",
                    "notes": notes.strip() or "Custom",
                })
                st.rerun()

    st.dataframe(
        pd.DataFrame(st.session_state.user_supplements),
        use_container_width=True,
        hide_index=True,
    )

    names = [x["name"] for x in st.session_state.user_supplements]

    selected_supplement = st.selectbox(
        "Remove supplement",
        ["-- Select --"] + names,
    )

    if (
        selected_supplement != "-- Select --"
        and st.button("🗑️ Remove")
    ):
        st.session_state.user_supplements = [
            x
            for x in st.session_state.user_supplements
            if x["name"] != selected_supplement
        ]
        st.rerun()


# ============================================================
# VIEW 6 — ROUTE STRATEGIST
# ============================================================

elif selected_nav == "🗺️ Route Strategist":

    st.markdown("### 🗺️ Route Pacing & Climbing Strategist")

    uploaded = st.file_uploader(
        "Upload GPX",
        type=["gpx"],
    )

    def parse_gpx(raw):
        root = ET.fromstring(raw.decode("utf-8", errors="ignore"))

        points = []
        elevations = []

        for elem in root.iter():
            tag = elem.tag.split("}")[-1].lower()

            if tag not in ("trkpt", "rtept"):
                continue

            lat = elem.attrib.get("lat")
            lon = elem.attrib.get("lon")

            if not lat or not lon:
                continue

            points.append((float(lat), float(lon)))

            elevation = 0.0

            for child in elem:
                child_tag = child.tag.split("}")[-1].lower()

                if child_tag in ("ele", "elevation", "alt"):
                    try:
                        elevation = float(child.text)
                    except Exception:
                        pass

            elevations.append(elevation)

        if not points:
            return None

        distance = 0.0

        for i in range(1, len(points)):
            lat1, lon1 = points[i - 1]
            lat2, lon2 = points[i]

            r = 6371.0

            p1 = math.radians(lat1)
            p2 = math.radians(lat2)

            dp = math.radians(lat2 - lat1)
            dl = math.radians(lon2 - lon1)

            a = (
                math.sin(dp / 2) ** 2
                + math.cos(p1)
                * math.cos(p2)
                * math.sin(dl / 2) ** 2
            )

            distance += r * 2 * math.asin(math.sqrt(a))

        elevation_gain = sum(
            max(0, elevations[i] - elevations[i - 1])
            for i in range(1, len(elevations))
        )

        return {
            "distance_km": round(distance, 2),
            "elevation_gain_m": round(elevation_gain, 1),
            "max_elevation_m": round(max(elevations), 1) if elevations else 0,
        }

    if uploaded:
        try:
            metrics = parse_gpx(uploaded.read())

            if metrics:
                c1, c2, c3 = st.columns(3)

                c1.metric(
                    "Distance",
                    f"{metrics['distance_km']} km",
                )
                c2.metric(
                    "Elevation Gain",
                    f"{metrics['elevation_gain_m']} m",
                )
                c3.metric(
                    "Max Elevation",
                    f"{metrics['max_elevation_m']} m",
                )

                if st.button(
                    "🤖 Generate Climbing Strategy",
                    type="primary",
                ):
                    prompt = f"""
Analyze this cycling route.

Distance:
{metrics['distance_km']} km

Elevation gain:
{metrics['elevation_gain_m']} m

Maximum elevation:
{metrics['max_elevation_m']} m

Athlete objective:
{st.session_state.goals['target_metric']}

Give a practical pacing and climbing strategy.
"""
                    with st.spinner("Analyzing route..."):
                        try:
                            result, engine = execute_ai(
                                prompt,
                                selected_provider,
                            )
                            st.markdown(result)
                            st.caption(f"Generated via {engine}")
                        except Exception as exc:
                            st.error(f"Strategy failed: {exc}")

        except Exception as exc:
            st.error(f"Could not parse GPX: {exc}")


# ============================================================
# FOOTER / DEBUG INFO
# ============================================================

if selected_nav != "🤖 AI Coach & Sparring":
    st.caption(
        "AI Coach is isolated from Intervals.icu network calls. "
        "Open the AI Coach page for a responsive chat experience."
    )
