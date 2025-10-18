# obdly_app.py — OBDly v2.8 (ALL ISSUES FIXED)

import os
import csv
import html
import time
import difflib
import hashlib
import unicodedata
import requests
from datetime import datetime, date

import streamlit as st
from openai import OpenAI
import streamlit.components.v1 as components

# Optional: faster fuzzy matching if available
try:
    from rapidfuzz.fuzz import token_set_ratio
    _HAVE_RAPIDFUZZ = True
except Exception:
    _HAVE_RAPIDFUZZ = False

# ───────────────────────── Page config + styles ─────────────────────────
st.set_page_config(page_title="OBDly - Find & Fix Car Problems",
                   page_icon="🚗",
                   layout="centered")

st.markdown("""
<style>
.block-container{max-width:900px;padding-top:2rem;padding-bottom:4rem;}
.user-message{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:12px 16px;border-radius:18px 18px 4px 18px;margin:8px 0 8px auto;max-width:80%;width:fit-content;box-shadow:0 2px 8px rgba(102,126,234,.3);}
.ai-message{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);color:#e2e8f0;padding:12px 16px;border-radius:18px 18px 18px 4px;margin:8px auto 8px 0;max-width:85%;width:fit-content;box-shadow:0 2px 8px rgba(0,0,0,.1);}
.csv-message{background:linear-gradient(135deg,#f093fb 0%,#f5576c 100%);border:2px solid rgba(240,147,251,.5);color:#fff;padding:14px 18px;border-radius:18px;margin:12px auto;max-width:90%;box-shadow:0 4px 12px rgba(240,147,251,.3);}
.system-message{background:rgba(59,130,246,.1);border:1px solid rgba(59,130,246,.3);color:#93c5fd;padding:10px 14px;border-radius:10px;margin:8px auto;max-width:90%;text-align:center;font-size:.9rem;font-style:italic;}
.message-time{font-size:.75rem;opacity:.6;margin-top:4px;}
.obd-card{background:rgba(255,255,255,.05);border:1px solid rgba(255,255,255,.12);border-radius:14px;padding:24px;margin-bottom:20px;box-shadow:0 2px 8px rgba(0,0,0,.1);}
.obd-divider{display:flex;align-items:center;gap:1rem;margin:28px 0;}
.obd-divider:before,.obd-divider:after{content:"";height:2px;background:rgba(255,255,255,.25);flex:1;}
.obd-divider span{opacity:.85;font-size:1rem;font-weight:600;padding:0 12px;letter-spacing:.05em;}
.obd-title{font-size:1rem;opacity:.95;margin-bottom:12px;font-weight:600;}
.obd-header{text-align:center;margin-bottom:18px;}
.obd-logo{width:200px;max-width:70%;height:auto;display:block;margin:0 auto;}
.obd-strap{color:#cbd5e1;text-align:center;margin-top:8px;font-size:1.05rem;opacity:.85;}
.disclaimer-box{background:rgba(255,200,0,.1);border:1px solid rgba(255,200,0,.3);border-radius:10px;padding:12px 16px;margin-bottom:20px;}
.typing-indicator{display:inline-block;padding:12px 0;margin:8px 0 8px 16px;position:relative;height:40px;}
.typing-indicator .dot-container{position:relative;width:35px;height:30px;display:inline-block;}
.typing-indicator span{height:10px;width:10px;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);border-radius:50%;position:absolute;animation:pulse 1.5s infinite ease-in-out;box-shadow:0 0 8px rgba(102,126,234,.5);}
.typing-indicator span:nth-child(1){left:50%;top:0;transform:translate(-50%,0);animation-delay:0s;}
.typing-indicator span:nth-child(2){left:2px;bottom:0;animation-delay:.3s;}
.typing-indicator span:nth-child(3){right:2px;bottom:0;animation-delay:.6s;}
@keyframes pulse{0%,100%{transform:scale(.8);opacity:.5}50%{transform:scale(1.2);opacity:1;box-shadow:0 0 15px rgba(102,126,234,.8);}}
.stButton>button{border-radius:10px;width:100%;font-weight:600;}
.stSuccess,.stWarning,.stError{border-radius:10px;}
</style>
""",
            unsafe_allow_html=True)

# ───────────────────────── API keys ─────────────────────────
DVLA_KEY = os.environ.get("DVLA_KEY")
OPENAI_KEY = os.environ.get("OBDLY_key2")
MODEL_NAME = os.environ.get("OBDLY_MODEL", "gpt-4o-mini")

if not OPENAI_KEY:
    st.error("⚠️ OpenAI API key not configured (OBDLY_key2).")
    st.stop()
client = OpenAI(api_key=OPENAI_KEY)

if not DVLA_KEY:
    st.warning(
        "⚠️ DVLA API key not found. Registration lookup will be disabled.")
else:
    if not os.environ.get("MOT_API_KEY"):
        st.sidebar.info("💡 Tip: Add MOT_API_KEY for better vehicle model data")

# ───────────────────────── Session state ─────────────────────────
ss = st.session_state
ss.setdefault("chat_messages", [])
ss.setdefault("csv_rows", [])
ss.setdefault("vehicle", None)
ss.setdefault("api_calls_today", 0)
ss.setdefault("api_counter_day", date.today().isoformat())
ss.setdefault("conversation_started", False)
ss.setdefault("current_issue", None)
ss.setdefault("show_repair_options", False)
ss.setdefault("csv_match_found", False)
ss.setdefault("is_admin", False)
ss.setdefault("images_today", 0)
ss.setdefault("image_counter_day", date.today().isoformat())
ss.setdefault("is_premium", False)
ss.setdefault("processing_query", False)
ss.setdefault("scroll_needed", False)  # NEW: Scroll trigger flag

if ss.api_counter_day != date.today().isoformat():
    ss.api_counter_day = date.today().isoformat()
    ss.api_calls_today = 0

# ───────────────────────── System prompt ─────────────────────────
SYS_PROMPT = (
    "You're OBDly, a friendly UK-based car diagnostic assistant. "
    "Speak like a knowledgeable mechanic, use plain English, list practical steps, "
    "highlight safety concerns, and mention when to DIY vs. see a professional. "
    "Prefer UK terms (bonnet, MOT, petrol/diesel). Include rough UK cost estimates where useful."
)


# ───────────────────────── Fuzzy helpers ─────────────────────────
def _fuzzy_ratio(a: str, b: str) -> int:
    if _HAVE_RAPIDFUZZ:
        try:
            return int(token_set_ratio(a, b))
        except Exception:
            pass
    return int(difflib.SequenceMatcher(None, a, b).ratio() * 100)


def _normalise_text(s: str) -> str:
    s = (s or "").lower()
    aliases = {
        "vw": "volkswagen",
        "merc": "mercedes",
        "mb": "mercedes",
        "land rover": "landrover",
        "vauxhall": "opel"
    }
    for k, v in aliases.items():
        s = s.replace(k, v)
    return s.replace("/", " ").replace(",", " ").replace("-", " ")


# ───────────────────────── Data helpers ─────────────────────────
def load_fault_data():
    rows = []
    try:
        with open("obdly_fault_data.csv", "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
        if rows:
            st.sidebar.success(f"✅ Loaded {len(rows)} known faults")
    except FileNotFoundError:
        st.sidebar.warning("⚠️ obdly_fault_data.csv not found.")
    ss.csv_rows = rows


def csv_match(text: str):
    rows = ss.csv_rows or []
    if not rows:
        return None, 0

    text_lower = _normalise_text(text)

    # CRITICAL: Must have fault-related keywords to trigger CSV match
    fault_keywords = [
        'problem', 'issue', 'fault', 'broken', 'not working', 'warning',
        'light', 'error', 'noise', 'smell', 'leak', 'vibration', 'shaking',
        'stalling', 'won\'t start', 'rough', 'hesitating', 'knocking', 'smoke',
        'overheating', 'grinding', 'squealing', 'clicking', 'burning', 'dying',
        'cutting out', 'juddering', 'misfiring'
    ]

    has_fault_keyword = any(keyword in text_lower
                            for keyword in fault_keywords)

    # CRITICAL: Block general/informational questions
    info_questions = [
        'petrol', 'diesel', 'fuel type', 'what engine', 'how many',
        'tell me about', 'information', 'specs', 'is this', 'is it', 'so its',
        'so it\'s', 'confirm', 'correct', 'right', 'what type', 'which fuel',
        'what fuel', 'engine size', 'how much'
    ]
    has_info_question = any(q in text_lower for q in info_questions)

    # Only proceed if has fault keywords AND doesn't have info questions
    if not has_fault_keyword or has_info_question:
        return None, 0

    user_tokens = set(text_lower.split())
    stop = {
        'the', 'a', 'an', 'is', 'my', 'has', 'have', 'with', 'and', 'or',
        'when', 'problem', 'issue', 'car', 'making', 'noise', 'for', 'of',
        'to', 'in', 'on', 'at', 'it', 'from', 'sound'
    }
    user_tokens -= stop

    # CRITICAL: Extract key symptom words from user query
    symptom_words = [w for w in user_tokens if w in text_lower and len(w) > 3]

    best_row, best_final = None, -1
    for r in rows:
        make = _normalise_text(r.get('Make', ''))
        model = _normalise_text(r.get('Model', ''))
        year = (r.get('Year', '') or '').lower()
        fault = _normalise_text(r.get('Fault', ''))

        if not make:
            continue

        # Make matching
        make_ok = (make in text_lower) or (_fuzzy_ratio(make, text_lower)
                                           >= 80)
        if not make_ok:
            continue

        # Model matching (optional but gives bonus points)
        model_ok = bool(model) and ((model in text_lower) or
                                    (_fuzzy_ratio(model, text_lower) >= 80))

        # CRITICAL: Fault must have significant overlap with user's symptom
        fault_tokens = set(fault.split()) - stop
        symptom_overlap = len(set(symptom_words) & fault_tokens)

        # Require at least ONE matching symptom word
        if symptom_overlap == 0:
            continue

        # Calculate match score
        match_score = (symptom_overlap *
                       15) + (6 if make_ok else 0) + (4 if model_ok else 0)

        # Year bonus
        if year and any(y and y in text_lower for y in year.split('-')):
            match_score += 3

        # Fuzzy comparison
        user_str = " ".join(sorted(symptom_words))
        fault_str = " ".join(sorted(fault_tokens))
        fuzzy = _fuzzy_ratio(user_str, fault_str)

        final_score = match_score * 10 + fuzzy

        if final_score > best_final:
            best_row, best_final = r, final_score

    # CRITICAL: Require much higher threshold - must be a GOOD match
    if not best_row or best_final < 200:
        return None, 0

    confidence = max(55, min(95, 40 + best_final // 5))
    pretty = (
        f"🎯 <strong>Known Issue Match</strong> (Confidence: ~{confidence}%)<br><br>"
        f"<strong>Car:</strong> {html.escape((best_row.get('Make','') or '').title())} "
        f"{html.escape((best_row.get('Model','') or '').title())} {html.escape(best_row.get('Year','') or '')}<br>"
        f"<strong>Fault:</strong> {html.escape(best_row.get('Fault','') or '')}<br>"
        f"<strong>Fix:</strong> {html.escape(best_row.get('Suggested Fix','Not available yet') or '')}<br>"
        f"<strong>Urgency:</strong> {html.escape(best_row.get('Urgency','Unknown') or '')} | "
        f"<strong>Cost:</strong> {html.escape(best_row.get('Cost Estimate','TBD') or '')} | "
        f"<strong>Difficulty:</strong> {html.escape(best_row.get('Difficulty','Unknown') or '')}<br>"
        f"<strong>Warning Light:</strong> {html.escape(best_row.get('Warning Light?','Unknown') or '')}"
    )
    return pretty, best_final


def top_reddit_insight_blob(make: str, model: str, max_rows: int = 3) -> str:
    try:
        with open("reddit_insights.csv", "r", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            rows = [
                r for r in rdr
                if r.get("make", "").lower() == (make or "").lower()
                and r.get("model", "").lower() == (model or "").lower()
            ]
        rows.sort(
            key=lambda r:
            (int(r.get("confidence", 0) or 0), int(r.get("upvotes", 0) or 0)),
            reverse=True)
        rows = rows[:max_rows]
        if not rows:
            return ""
        lines = [
            f"- {(r.get('component') or 'component?')} | {(r.get('symptom') or 'symptom?')} | {(r.get('fix_summary') or '')[:200]}"
            for r in rows
        ]
        return "Known community fixes (recent Reddit):\n" + "\n".join(lines)
    except Exception:
        return ""


# ───────────────────────── AI + logging ─────────────────────────
def ask_ai(user_text: str, csv_context: str | None):
    if ss.api_calls_today > 100:
        return "⚠️ Daily usage limit reached. Please try again tomorrow."
    msgs = [{"role": "system", "content": SYS_PROMPT}]
    for m in ss.chat_messages[-50:]:
        if m["role"] in ("user", "assistant"):
            msgs.append({"role": m["role"], "content": m["content"]})
    v = ss.vehicle
    context_note = ""
    if v:
        context_note = (
            f"\n\n[Vehicle Context: {(v.get('make','') or '').title()} "
            f"{(v.get('model','') or '').title()} {v.get('yearOfManufacture','')}, "
            f"{v.get('fuelType','')}, Engine: {v.get('engineCapacity','')}cc]")
        community = top_reddit_insight_blob(v.get('make', ''),
                                            v.get('model', ''))
        if community:
            context_note += f"\n\n[Community Insights]\n{community}"
    if csv_context:
        context_note += "\n\n[Database Match Found: A known issue was matched from our CSV.]"
    msgs.append({"role": "user", "content": user_text + context_note})
    try:
        resp = client.chat.completions.create(model=MODEL_NAME,
                                              messages=msgs,
                                              temperature=0.6)
        ss.api_calls_today += 1
        return resp.choices[0].message.content
    except Exception as e:
        return f"⚠️ Sorry, I couldn't process that. Error: {e}"


def log_interaction(user_msg, ai_response, csv_match_found=False):
    try:
        with open("chat_log.csv", "a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if f.tell() == 0:
                w.writerow([
                    "Timestamp", "Reg", "User Message", "AI Response",
                    "CSV Match", "Feedback"
                ])
            w.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                (ss.vehicle or {}).get("registrationNumber",
                                       "N/A"), user_msg[:200],
                ai_response[:200], "Yes" if csv_match_found else "No", ""
            ])
    except Exception:
        pass


# ───────────────────────── Vehicle lookup ─────────────────────────
def vehicle_lookup(reg_number: str):
    """
    Vehicle lookup - Uses MOT API if key available, otherwise DVLA
    """
    # Try MOT History API first (has make + model)
    mot_key = os.environ.get("MOT_API_KEY")
    if mot_key:
        try:
            r = requests.get(
                f"https://beta.check-mot.service.gov.uk/trade/vehicles/mot-tests",
                params={"registration": reg_number},
                headers={"x-api-key": mot_key},
                timeout=10)
            if r.status_code == 200:
                data = r.json()
                if data and len(data) > 0:
                    vehicle = data[0]
                    # MOT API returns great data including model
                    return {
                        "registrationNumber":
                        reg_number,
                        "make":
                        vehicle.get("make", ""),
                        "model":
                        vehicle.get("model", ""),
                        "colour":
                        vehicle.get("primaryColour", ""),
                        "fuelType":
                        vehicle.get("fuelType", ""),
                        "engineCapacity":
                        vehicle.get("engineSize", ""),
                        "yearOfManufacture":
                        vehicle.get("registrationDate", "")[:4]
                        if vehicle.get("registrationDate") else "",
                        "motStatus":
                        vehicle.get("motStatus", ""),
                        "motExpiryDate":
                        vehicle.get("motExpiryDate", "")
                    }
        except Exception:
            pass  # Fall through to DVLA

    # Use DVLA API (current default until MOT key is available)
    if DVLA_KEY:
        try:
            headers = {
                "x-api-key": DVLA_KEY,
                "Content-Type": "application/json"
            }
            r = requests.post(
                "https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles",
                headers=headers,
                json={"registrationNumber": reg_number},
                timeout=15)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass

    return None


# ───────────────────────── UI helpers ─────────────────────────
def display_chat_message(role, content, message_type="normal", timestamp=None):
    timestamp = timestamp or datetime.now().strftime("%H:%M")
    if message_type == "csv":
        st.markdown(
            f'<div class="csv-message">{content}<div class="message-time">{html.escape(timestamp)}</div></div>',
            unsafe_allow_html=True)
        return
    safe = html.escape(str(content)).replace("\n", "<br>")
    if message_type == "system":
        st.markdown(f'<div class="system-message">{safe}</div>',
                    unsafe_allow_html=True)
    elif role == "user":
        st.markdown(
            f'<div class="user-message">{safe}<div class="message-time">{html.escape(timestamp)}</div></div>',
            unsafe_allow_html=True)
    else:
        st.markdown(
            f'<div class="ai-message">{safe}<div class="message-time">{html.escape(timestamp)}</div></div>',
            unsafe_allow_html=True)


# ────────────── HEADER ──────────────
import base64, pathlib


def _inline_svg(path: str) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"<img class='obd-logo' src='data:image/svg+xml;base64,{b64}' alt='OBDly'/>"


def _inline_png(path: str, width_px: int = 200) -> str:
    with open(path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode()
    return f"<img class='obd-logo' style='width:{width_px}px' src='data:image/png;base64,{b64}' alt='OBDly'/>"


svg = pathlib.Path("obdly_logo.svg")
png2x = pathlib.Path("obdly_logo@2x.png")
png = pathlib.Path("obdly_logo.png")
png_main = pathlib.Path("logo.png")

logo_html = ""
if svg.exists():
    logo_html = _inline_svg(str(svg))
elif png_main.exists():
    logo_html = _inline_png(str(png_main), 200)
elif png2x.exists():
    logo_html = _inline_png(str(png2x), 200)
elif png.exists():
    logo_html = _inline_png(str(png), 200)
else:
    logo_html = "<h1 style='margin:0'>obd<strong>ly</strong></h1>"

st.markdown(
    f"<div class='obd-header'>{logo_html}<div class='obd-strap'>Find &amp; Fix Car Problems</div></div>",
    unsafe_allow_html=True)

st.markdown("""
<div class='disclaimer-box'>
⚠️ <strong>Important:</strong> OBDly provides guidance only. Always consult a qualified mechanic for safety-critical issues or if you're unsure about any repair.
</div>
""",
            unsafe_allow_html=True)

# ───────────────────────── Sidebar ─────────────────────────
st.sidebar.title("📑 Menu")


def _norm(s: str) -> str:
    if s is None: return ""
    s = unicodedata.normalize("NFKC", s).replace("\r", "").replace("\n", "")
    return s.strip()


with st.sidebar.expander("Admin", expanded=False):
    admin_key_input_main = st.text_input("Enter admin key",
                                         type="password",
                                         key="admin_key_input_main")
    if st.button("Login", key="admin_unlock_btn_main"):
        admin_secret = (os.environ.get("OBDLY_ADMIN_KEY")
                        or os.environ.get("ADMIN_PASSWORD")
                        or os.environ.get("ADMIN_KEY"))
        if not admin_secret:
            st.error("No admin secret found (OBDLY_ADMIN_KEY).")
        elif _norm(admin_key_input_main) == _norm(admin_secret):
            ss.is_admin = True
            st.success("✅ Admin unlocked")
        else:
            st.error("Incorrect password")

page = st.sidebar.radio("Navigate", [
    "💬 Chat with OBDly", "🛠️ Share Your Fix", "🔍 Reddit Collector",
    "🗄️ Database Manager", "📋 Review Submissions", "📊 Chat History", "ℹ️ About"
])

if st.sidebar.button("🔄 New Conversation"):
    ss.chat_messages = []
    ss.vehicle = None
    ss.conversation_started = False
    ss.show_repair_options = False
    ss.csv_match_found = False
    ss.processing_query = False
    st.rerun()

if ss.vehicle:
    v = ss.vehicle
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🚗 Your Vehicle")

    # Build full vehicle description
    make = (v.get('make', '') or '').title()
    model = (v.get('model', '') or v.get('wheelplan', '') or '').title()
    year = v.get('yearOfManufacture', '')

    vehicle_name = make
    if model:
        vehicle_name += f" {model}"
    vehicle_name += f" {year}"

    st.sidebar.caption(vehicle_name)

    # Additional details
    fuel = v.get('fuelType', '')
    colour = (v.get('colour', '') or '').title()
    engine = v.get('engineCapacity', '')

    details = []
    if fuel:
        details.append(fuel)
    if colour:
        details.append(colour)
    if engine:
        details.append(f"{engine}cc")

    if details:
        st.sidebar.caption(" • ".join(details))

st.sidebar.markdown("---")
st.sidebar.caption(f"API Calls: {ss.api_calls_today}/100")

if not ss.get("is_premium", False):
    remaining = 3 - ss.get("images_today", 0)
    st.sidebar.caption(f"📸 Images: {max(0, remaining)}/3 today")
else:
    st.sidebar.caption(f"📸 Images: ∞ (Premium)")

try:
    from rapidfuzz.fuzz import token_set_ratio
    st.sidebar.success("🔎 Fuzzy match: RapidFuzz active")
except Exception:
    st.sidebar.info("🔎 Fuzzy match: Python fallback")

if not ss.csv_rows:
    load_fault_data()

# ───────────────────────── Import pages ─────────────────────────
try:
    from user_submission_page import submission_page, admin_review_page, check_admin_access
    from reddit_data_collector import reddit_collector_page
    from database_manager import database_manager_page
    from repair_options import show_repair_options
    from image_analysis import analyze_car_image, log_image_analysis, show_premium_promo
except ImportError as e:
    st.sidebar.error(f"Module import error: {e}")

# ───────────────────────── Routing ─────────────────────────
if page == "ℹ️ About":
    st.markdown("## About OBDly")
    st.markdown(
        "OBDly is your AI-powered car diagnostic assistant built for UK drivers."
    )

elif page == "📊 Chat History":
    st.markdown("## 💬 Chat History")
    try:
        with open("chat_log.csv", "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except Exception:
        rows = []
    if not rows:
        st.info("No chat history yet.")
    else:
        for r in reversed(rows[-50:]):
            with st.expander(
                    f"[{r.get('Timestamp','')}] {r.get('User Message','')[:50]}..."
            ):
                st.markdown(
                    f"**Vehicle:** {html.escape(r.get('Reg','') or '')}")
                st.markdown(
                    f"**User:** {html.escape(r.get('User Message','') or '')}")
                st.markdown(
                    f"**OBDly:** {html.escape(r.get('AI Response','') or '')}")

elif page == "🛠️ Share Your Fix":
    try:
        submission_page()
    except Exception as e:
        st.error(f"Page error: {e}")

elif page == "🔍 Reddit Collector":
    if ss.is_admin:
        try:
            reddit_collector_page()
        except Exception as e:
            st.error(f"Page error: {e}")
    else:
        st.error("🔒 Admin access only")

elif page == "🗄️ Database Manager":
    try:
        if check_admin_access():
            database_manager_page()
        else:
            st.error("🔒 Admin access only")
    except Exception as e:
        st.error(f"Page error: {e}")

elif page == "📋 Review Submissions":
    try:
        if check_admin_access():
            admin_review_page()
        else:
            st.error("🔒 Admin access only")
    except Exception as e:
        st.error(f"Page error: {e}")

else:  # 💬 Chat with OBDly
    # Registration lookup
    if not ss.vehicle and not ss.conversation_started:
        st.markdown("<div class='obd-card'>", unsafe_allow_html=True)
        st.markdown(
            "<div class='obd-title'>🔎 Quick Start: Lookup by Registration (Optional)</div>",
            unsafe_allow_html=True)
        col1, col2 = st.columns([3, 1])
        with col1:
            reg = st.text_input("Enter your registration",
                                placeholder="e.g. AB12 CDE",
                                label_visibility="collapsed",
                                key="reg_input")
        with col2:
            if st.button("Look Up",
                         use_container_width=True,
                         key="reg_lookup_btn") and reg.strip():
                with st.spinner("Looking up vehicle..."):
                    v = vehicle_lookup(reg.strip().replace(" ", "").upper())
                    if v:
                        # DEBUG: Show what API actually returns
                        with st.expander("🔍 DEBUG: Raw API Data",
                                         expanded=False):
                            st.json(v)

                        ss.vehicle = v

                        # Build vehicle display
                        make = (v.get('make') or '').title()
                        model = (v.get('model') or '').title()
                        year = v.get('yearOfManufacture', '')
                        colour = (v.get('colour') or '').title()
                        fuel = v.get('fuelType', '')

                        # Build vehicle description
                        vehicle_desc = f"✅ Vehicle found: {make}"
                        if model:
                            vehicle_desc += f" {model}"
                        vehicle_desc += f" {year}"
                        if colour:
                            vehicle_desc += f" ({colour})"
                        if fuel:
                            vehicle_desc += f" - {fuel}"

                        # Add MOT warning if expired
                        if v.get('motStatus') == 'No details held by DVLA':
                            vehicle_desc += "\n⚠️ MOT: Expired or No Current MOT"

                        ss.chat_messages.append({
                            "role":
                            "system",
                            "content":
                            vehicle_desc,
                            "timestamp":
                            datetime.now().strftime("%H:%M")
                        })
                        st.rerun()
                    else:
                        st.warning(
                            "Vehicle not found. You can still chat without registration."
                        )
        st.markdown("</div>", unsafe_allow_html=True)
        st.markdown("<div class='obd-divider'><span>OR</span></div>",
                    unsafe_allow_html=True)
        st.markdown(
            "<div style='text-align:center;margin:20px 0;opacity:0.6'>Skip and start chatting below ↓</div>",
            unsafe_allow_html=True)

    # CRITICAL: Anchor for scroll
    st.markdown("<div id='chat-anchor'></div>", unsafe_allow_html=True)
    st.markdown("### 💬 Chat with OBDly")

    # Display all chat messages
    if not ss.chat_messages:
        display_chat_message(
            "assistant",
            "👋 Hi! I'm OBDly, your AI car mechanic. What's going on with your car?",
            timestamp="Now")
    else:
        for msg in ss.chat_messages:
            display_chat_message(msg["role"], msg["content"],
                                 msg.get("type", "normal"),
                                 msg.get("timestamp", ""))

    # Show thinking indicator ONLY when processing
    if ss.processing_query:
        st.markdown('''
        <div class="typing-indicator">
          <div class="dot-container"><span></span><span></span><span></span></div>
        </div>
        ''',
                    unsafe_allow_html=True)

    st.markdown("---")

    # Chat input
    user_input = st.chat_input("Type your car problem or question here...")

    if user_input and not ss.processing_query:
        ss.processing_query = True
        ss.conversation_started = True
        ss.scroll_needed = True  # NEW: Flag to trigger scroll

        # Add user message
        ss.chat_messages.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().strftime("%H:%M")
        })
        ss.current_issue = user_input

        # Rerun to show thinking indicator
        st.rerun()

    # Process query if flag is set
    if ss.processing_query and not user_input:
        # Get the last user message
        last_user_msg = next(
            (m["content"]
             for m in reversed(ss.chat_messages) if m["role"] == "user"), None)

        if last_user_msg:
            enriched = last_user_msg
            if ss.vehicle:
                v = ss.vehicle
                enriched = f"{v.get('make','')} {v.get('model','')} {v.get('yearOfManufacture','')} {last_user_msg}"

            csv_card, _ = csv_match(enriched)
            ss.csv_match_found = bool(csv_card)

            if csv_card:
                ss.chat_messages.append({
                    "role":
                    "assistant",
                    "content":
                    csv_card,
                    "type":
                    "csv",
                    "timestamp":
                    datetime.now().strftime("%H:%M")
                })

            ai_response = ask_ai(last_user_msg, csv_card)
            ss.chat_messages.append({
                "role":
                "assistant",
                "content":
                ai_response,
                "timestamp":
                datetime.now().strftime("%H:%M")
            })

            log_interaction(last_user_msg, ai_response, ss.csv_match_found)
            ss.show_repair_options = True
            ss.processing_query = False

            st.rerun()

    # CRITICAL: Scroll after rendering - runs on EVERY rerun when needed
    if ss.get("scroll_needed", False):
        components.html("""
        <script>
          // Wait for page to fully render
          setTimeout(() => {
            const el = document.getElementById('chat-anchor');
            if (el) { 
              const yOffset = -20; // Small offset from top
              const y = el.getBoundingClientRect().top + window.pageYOffset + yOffset;
              window.scrollTo({top: y, behavior: 'smooth'});
            }
          }, 200);
        </script>
        """,
                        height=0)
        ss.scroll_needed = False

    # Image upload - ONLY show when NOT in middle of conversation
    if len(ss.chat_messages) <= 1 or not ss.processing_query:
        with st.expander("📎 Attach image (optional)", expanded=False):

            def _img_limit_inline():
                if ss.get("is_premium", False):
                    return True, "✨ Premium: Unlimited"
                remaining = 3 - ss.get("images_today", 0)
                return (remaining
                        > 0), (f"{remaining} remaining today" if remaining > 0
                               else "Limit reached. Upgrade to Premium!")

            can_upload, msg = _img_limit_inline()
            st.caption(msg)

            if can_upload:
                uploaded_file = st.file_uploader(
                    "Upload",
                    type=["png", "jpg", "jpeg", "heic"],
                    label_visibility="collapsed",
                    key="inline_image_upload")

                if uploaded_file:
                    st.image(uploaded_file, use_column_width=True)
                    context = st.text_input(
                        "Add context (optional)",
                        placeholder="e.g. 'This light just came on'",
                        key="img_context")

                    if st.button("🔍 Analyze Image",
                                 use_container_width=True,
                                 type="primary"):
                        with st.spinner("Analyzing…"):
                            if not ss.get("is_premium", False):
                                ss.images_today = ss.get("images_today", 0) + 1

                            analysis = analyze_car_image(
                                uploaded_file, context)
                            log_image_analysis(uploaded_file.name, analysis)

                            ss.conversation_started = True
                            ss.chat_messages.append({
                                "role":
                                "user",
                                "content":
                                f"📸 [Uploaded image: {uploaded_file.name}]" +
                                (f"\n{context}" if context else ""),
                                "timestamp":
                                datetime.now().strftime("%H:%M")
                            })
                            ss.chat_messages.append({
                                "role":
                                "assistant",
                                "content":
                                analysis,
                                "timestamp":
                                datetime.now().strftime("%H:%M")
                            })
                            ss.current_issue = f"Image: {uploaded_file.name}"
                            ss.show_repair_options = True
                            ss.scroll_needed = True  # NEW: Trigger scroll for images too

                            st.rerun()

    # Premium promo - ONLY at the very bottom, after chat
    if not ss.processing_query:
        try:
            if not ss.get("is_premium", False):
                show_premium_promo()
        except Exception:
            pass

    # Repair options
    if ss.show_repair_options and len(
            ss.chat_messages) > 1 and not ss.processing_query:
        last_ai_message = next(
            (m for m in reversed(ss.chat_messages)
             if m["role"] == "assistant" and m.get("type") != "csv"), None)
        if last_ai_message and ss.current_issue:
            with st.expander("🛠️ How Would You Like to Fix This?",
                             expanded=False):
                try:
                    show_repair_options(ss.current_issue,
                                        last_ai_message["content"],
                                        csv_match_found=ss.csv_match_found)
                except Exception as e:
                    st.warning(f"Repair options unavailable: {e}")

    # Feedback
    if len(ss.chat_messages) > 1 and not ss.processing_query:
        st.markdown("---")
        st.markdown("### Was this helpful?")
        c1, c2, _ = st.columns([1, 1, 3])
        with c1:
            if st.button("👍 Helpful", use_container_width=True):
                st.success("Thanks for your feedback!")
        with c2:
            if st.button("👎 Not Helpful", use_container_width=True):
                st.info("Thanks! We'll improve.")
