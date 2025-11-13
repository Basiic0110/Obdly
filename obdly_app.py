# obdly_app.py — OBDly v3.3 (OBD Code Library + Caching + Resume Chat)

import os
import csv
import html
import time
import difflib
import hashlib
import unicodedata
import requests
import json
import re
import base64, pathlib
from glob import glob
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
.block-container{max-width:900px;padding-top:4rem;padding-bottom:4rem;}
.user-message{background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);color:#fff;padding:12px 16px;border-radius:18px 18px 4px 18px;margin:8px 0 8px auto;max-width:80%;width:fit-content;box-shadow:0 2px 8px rgba(102,126,234,.3);}
.ai-message{background:rgba(255,255,255,.08);border:1px solid rgba(255,255,255,.12);color:#e2e8f0;padding:12px 16px;border-radius:18px 18px 18px 4px;margin:8px auto 8px 0;max-width:85%;width:fit-content;box-shadow:0 2px 8px rgba(0,0,0,.1);}
.csv-message{background:linear-gradient(135deg,#f093fb 0%,#f5576c 100%);border:2px solid rgba(240,147,251,.5);color:#fff;padding:14px 18px;border-radius:18px;margin:12px auto;max-width:90%;box-shadow:0 4px 12px rgba(240,147,251,.3);}
.code-message{background:linear-gradient(135deg,#38bdf8 0%,#6366f1 100%);border:2px solid rgba(99,102,241,.45);color:#fff;padding:14px 18px;border-radius:18px;margin:12px auto;max-width:90%;box-shadow:0 4px 12px rgba(99,102,241,.25);}
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
.typing-indicator{display:inline-block;padding:8px 0;margin:8px 0 8px 16px;position:relative;height:20px;width:80px;}
.typing-indicator .scanner-container{position:relative;width:100%;height:4px;background:rgba(0,0,0,0.3);border-radius:2px;overflow:hidden;box-shadow:inset 0 0 5px rgba(0,0,0,0.5);}
.typing-indicator .scanner-light{position:absolute;width:40px;height:100%;background:linear-gradient(90deg, transparent, #ff0000 20%, #ff0000 80%, transparent);box-shadow:0 0 10px #ff0000, 0 0 20px #ff0000, 0 0 30px #ff0000;animation:kitt-scan 1.5s infinite ease-in-out;}
@keyframes kitt-scan{0%{left:-40px;}50%{left:100%;}100%{left:-40px;}}
.stButton>button{border-radius:10px;width:100%;font-weight:600;}
.stSuccess,.stWarning,.stError{border-radius:10px;}
/* Only uppercase registration input */
.stTextInput input[placeholder*="CDE"]{text-transform:uppercase !important;}
/* Normal case for all other inputs */
.stTextInput input{text-transform:none !important;}
</style>
""",
            unsafe_allow_html=True)

# ───────────────────────── API Keys ─────────────────────────
DVLA_KEY = os.environ.get("DVLA_KEY")
OPENAI_KEY = os.environ.get("OBDLY_key2")
MODEL_NAME = os.environ.get("OBDLY_MODEL", "gpt-4o-mini")

if not OPENAI_KEY:
    st.error("⚠️ OpenAI API key not configured (OBDLY_key2).")
    st.stop()
client = OpenAI(api_key=OPENAI_KEY)

if not DVLA_KEY:
    st.warning(
        "⚠️ DVLA API key not found. Registration lookup fallback disabled.")

# Check MOT OAuth setup
if not (os.environ.get("MOT_API_KEY") and os.environ.get("MOT_CLIENT_ID") and
        os.environ.get("MOT_CLIENT_SECRET") and os.environ.get("MOT_TOKEN_URL")
        and os.environ.get("MOT_SCOPE_URL")):
    st.sidebar.warning(
        "⚠️ MOT OAuth not fully configured (need MOT_API_KEY, MOT_CLIENT_ID, MOT_CLIENT_SECRET, MOT_TOKEN_URL, MOT_SCOPE_URL)."
    )

# ═══════════════════ MAINTENANCE MODE (for future updates) ═══════════════════
MAINTENANCE_MODE = False  # Set to True to enable maintenance mode

if MAINTENANCE_MODE:
    st.markdown("## 🔒 Obdly - Temporary Maintenance")
    st.info("""
    **We're performing a quick update to improve your experience.**
    
    Expected back online: Within 30 minutes
    
    Thanks for your patience!
    """)
    st.stop()
# ═════════════════════════════════════════════════════════════════════════════

# ───────────────────────── Session State ─────────────────────────
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
ss.setdefault("scroll_needed", False)
ss.setdefault("current_conversation_id", None)
ss.setdefault("obd_codes", {})  # NEW: merged OBD code dict
ss.setdefault("last_detected_codes", [])  # NEW: last codes found in user text
ss.setdefault("logged_in", False)
ss.setdefault("username", None)
ss.setdefault("user_id", None)

if ss.api_counter_day != date.today().isoformat():
    ss.api_counter_day = date.today().isoformat()
    ss.api_calls_today = 0


# ───────────────────────── User Authentication ─────────────────────────
def hash_password(password: str) -> str:
    """Hash a password for storing."""
    return hashlib.sha256(password.encode()).hexdigest()


def load_users():
    """Load users from JSON file."""
    try:
        with open("users.json", "r", encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        return {"users": {}, "conversations": {}}


def save_users(data):
    """Save users to JSON file."""
    try:
        with open("users.json", "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        st.error(f"Error saving users: {e}")


def create_user(username: str, password: str) -> tuple[bool, str]:
    """Create a new user account."""
    data = load_users()

    if username in data["users"]:
        return False, "Username already exists"

    data["users"][username] = {
        "password_hash": hash_password(password),
        "user_id": str(uuid.uuid4()),
        "created": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    }

    save_users(data)
    return True, "Account created successfully"


def verify_user(username: str, password: str) -> tuple[bool, str | None]:
    """Verify user credentials and return user_id if valid."""
    data = load_users()

    if username not in data["users"]:
        return False, None

    user = data["users"][username]
    if user["password_hash"] == hash_password(password):
        return True, user["user_id"]

    return False, None


def get_user_conversations(user_id: str) -> dict:
    """Get conversations for a specific user."""
    data = load_users()
    return data.get("conversations", {}).get(user_id, {})


def save_user_conversation(user_id: str, conv_id: str, conversation: dict):
    """Save a conversation for a specific user."""
    data = load_users()

    if "conversations" not in data:
        data["conversations"] = {}

    if user_id not in data["conversations"]:
        data["conversations"][user_id] = {}

    data["conversations"][user_id][conv_id] = conversation
    save_users(data)


def delete_user_conversation(user_id: str, conv_id: str):
    """Delete a conversation for a specific user."""
    data = load_users()

    if user_id in data.get("conversations",
                           {}) and conv_id in data["conversations"][user_id]:
        del data["conversations"][user_id][conv_id]
        save_users(data)


# ───────────────────────── System prompt ─────────────────────────
SYS_PROMPT = (
    "You're OBDly, a friendly UK-based car diagnostic assistant with deep automotive expertise. "
    "Be conversational but specific. Ask clarifying questions for vague inputs. "
    "CRITICAL INSTRUCTIONS FOR ACCURACY:\n"
    "- Give SPECIFIC repair steps, not generic advice. Include exact part names, torque specs when relevant, and tool requirements.\n"
    "- Cost estimates MUST be realistic for UK (2024-2025): labour £50–80/hr, parts vary by make/model. Always give ranges.\n"
    "- If you're unsure about a specific model's quirks, SAY SO and recommend professional diagnosis.\n"
    "- Prioritise safety: clearly state when a repair is beyond DIY capability.\n"
    "- Use UK terminology: bonnet (not hood), boot (not trunk), petrol/diesel, MOT, registration.\n"
    "- Reference common UK parts suppliers (Halfords, Euro Car Parts) and typical garage rates.\n"
    "- For common issues, mention if it's a known problem for that make/model.\n"
    "- Be honest about complexity: 'This needs a diagnostic scanner' vs 'You can check this yourself'."
)


# ───────────────────────── Registration Detection ─────────────────────────
def detect_registration_request(text: str):
    """
    Detect if user is asking about a registration and extract it.
    Returns: (is_reg_query, registration_number)
    """
    text_lower = text.lower()
    reg_keywords = [
        'check', 'lookup', 'look up', 'find', 'search', 'what car',
        'what vehicle', 'tell me about', 'reg', 'registration', 'number plate',
        'vrm'
    ]
    has_keyword = any(keyword in text_lower for keyword in reg_keywords)

    reg_patterns = [
        r'\b([A-Z]{1,2}[0-9]{1,2}\s?[A-Z]{3})\b',  # AB12 CDE or AB12CDE
        r'\b([A-Z]{3}[0-9]{1,3}[A-Z])\b',  # ABC123D
        r'\b([A-Z][0-9]{1,3}[A-Z]{3})\b',  # A123BCD
    ]
    for pattern in reg_patterns:
        match = re.search(pattern, text.upper())
        if match:
            potential_reg = match.group(1).replace(' ', '')
            if 4 <= len(potential_reg) <= 8:
                return True, potential_reg
    return False, None


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


# ───────────────────────── Conversation Management ─────────────────────────
def save_conversation():
    """Save current conversation to user-specific storage"""
    if not ss.chat_messages:
        return

    # Only save to database if user is logged in
    if not ss.get("user_id"):
        # Anonymous users: chats stay in session only (temporary)
        return

    if "current_conversation_id" not in ss or not ss.current_conversation_id:
        ss.current_conversation_id = "conv_" + datetime.now().strftime(
            "%Y%m%d_%H%M%S")

    conv_id = ss.current_conversation_id

    # Get existing conversations for this user
    data = load_users()
    user_convs = data.get("conversations", {}).get(ss.user_id, {})

    first_msg = next(
        (m["content"] for m in ss.chat_messages if m["role"] == "user"), "")

    conversation = {
        "id":
        conv_id,
        "created":
        user_convs.get(conv_id,
                       {}).get("created",
                               datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
        "updated":
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "vehicle": (ss.vehicle or {}).get("registrationNumber", "N/A"),
        "messages":
        ss.chat_messages,
        "first_message":
        first_msg[:50]
    }

    save_user_conversation(ss.user_id, conv_id, conversation)


# ───────────────────────── Data helpers (CSV + OBD Codes) ─────────────────────────
@st.cache_resource(show_spinner=False)
def _cached_load_fault_csv():
    rows = []
    try:
        with open("obdly_fault_data.csv", "r", encoding="utf-8") as f:
            rows = list(csv.DictReader(f))
    except FileNotFoundError:
        rows = []
    return rows


def load_fault_data():
    rows = _cached_load_fault_csv()
    if rows:
        st.sidebar.success(f"✅ Loaded {len(rows)} known faults")
    else:
        st.sidebar.warning("⚠️ obdly_fault_data.csv not found.")
    ss.csv_rows = rows


# NEW: Load OBD code libraries from JSON files in root
_OBD_CODE_KEY_RE = re.compile(r'^[PBCU]\d{4}$', re.IGNORECASE)


def _looks_like_code_dict(d: dict) -> bool:
    if not isinstance(d, dict): return False
    # Heuristic: at least one P/B/C/U code key
    return any(_OBD_CODE_KEY_RE.match(str(k)) for k in d.keys())


@st.cache_resource(show_spinner=False)
def _cached_load_obd_libraries():
    merged = {}
    # Conservative patterns; we’ll also scan *.json and filter
    patterns = ["obd_codes*.json", "*_codes.json", "*obd*.json", "*.json"]
    seen = set()
    for pat in patterns:
        for path in glob(pat):
            if path in seen:
                continue
            seen.add(path)
            try:
                with open(path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict) and _looks_like_code_dict(data):
                    for k, v in data.items():
                        k_up = str(k).upper()
                        if _OBD_CODE_KEY_RE.match(k_up):
                            # normalise structure
                            if isinstance(v, dict):
                                merged[k_up] = {
                                    "title":
                                    v.get("title") or v.get("name") or "",
                                    "description":
                                    v.get("description") or v.get("desc")
                                    or v.get("meaning") or "",
                                    "causes":
                                    v.get("causes") or v.get("possible_causes")
                                    or v.get("common_causes") or [],
                                    "fixes":
                                    v.get("fixes") or v.get("solutions")
                                    or v.get("recommended_fixes") or [],
                                    "severity":
                                    v.get("severity") or "",
                                    "symptoms":
                                    v.get("symptoms") or [],
                                }
                            else:
                                merged[k_up] = {
                                    "title": "",
                                    "description": str(v),
                                    "causes": [],
                                    "fixes": [],
                                    "severity": "",
                                    "symptoms": []
                                }
            except Exception:
                # ignore non-parseable JSONs silently
                pass
    return merged


def ensure_obd_loaded():
    if not ss.obd_codes:
        ss.obd_codes = _cached_load_obd_libraries()
        if ss.obd_codes:
            st.sidebar.success(f"✅ Loaded {len(ss.obd_codes):,} OBD codes")
        else:
            st.sidebar.warning("⚠️ No OBD code libraries found in JSON files.")


_CODE_FINDER_RE = re.compile(r'\b([PBCU]\d{4})\b', re.IGNORECASE)


def find_obd_codes_in_text(text: str):
    if not text:
        return []
    codes = list({m.group(1).upper() for m in _CODE_FINDER_RE.finditer(text)})
    return codes


# NOW render_code_card starts...
def render_code_card(code: str,
                     entry: dict,
                     keep_make: str | None = None) -> str:
    """
    FIXED: More aggressive brand filtering
    """
    # Normalize keep_make
    if keep_make:
        keep_make = keep_make.lower().strip()
        # Handle common aliases
        if keep_make in ("mercedes-benz", "merc", "mb"):
            keep_make = "mercedes"
        elif keep_make in ("vw", ):
            keep_make = "volkswagen"
        elif keep_make == "land rover":
            keep_make = "landrover"

    def _strip_other_brands(text: str) -> str:
        """FIXED: More aggressive brand filtering"""
        if not text:
            return ""

        # If no keep_make specified, return original (no filtering)
        if not keep_make:
            return text

        # Split into sentences
        sentences = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text)]
        filtered_sentences = []

        # List of all possible makes (normalized)
        all_makes = [
            "ford", "bmw", "mercedes", "volkswagen", "audi", "vauxhall",
            "opel", "peugeot", "citroen", "renault", "toyota", "honda",
            "nissan", "mazda", "hyundai", "kia", "skoda", "seat", "volvo",
            "mini", "jaguar", "landrover", "fiat", "alfa romeo", "dacia",
            "tesla", "mitsubishi", "suzuki", "subaru", "lexus", "porsche",
            "saab"
        ]

        for sentence in sentences:
            sentence_lower = sentence.lower()

            # Check if sentence mentions ANY car make
            mentions_car_make = any(make in sentence_lower
                                    for make in all_makes)

            if mentions_car_make:
                # If it mentions a make, keep ONLY if it's the target make
                if keep_make in sentence_lower:
                    filtered_sentences.append(sentence)
                # Otherwise, skip this sentence entirely
            else:
                # No car make mentioned = generic advice = keep it
                filtered_sentences.append(sentence)

        return " ".join(filtered_sentences)

    def _fmt_severity(s: str) -> str:
        if not s: return ""
        s = s.replace("_", " ")
        return s[:1].upper() + s[1:]

    # Extract and filter all fields
    title = html.escape(entry.get("title") or "")
    raw_desc = entry.get("description") or ""
    desc = html.escape(_strip_other_brands(raw_desc))
    sev = html.escape(_fmt_severity(entry.get("severity") or ""))

    # Filter lists (causes, symptoms, fixes)
    def _filter_list(items):
        if not items or not keep_make:
            return items
        filtered = []
        for item in items:
            item_str = str(item).lower()
            # Check if mentions any car make
            mentions_make = any(make in item_str for make in [
                "ford", "bmw", "mercedes", "volkswagen", "audi", "vauxhall",
                "peugeot", "citroen", "renault", "toyota", "honda", "nissan"
            ])
            if mentions_make:
                # Only keep if it's our target make
                if keep_make in item_str:
                    filtered.append(item)
            else:
                # Generic advice - keep it
                filtered.append(item)
        return filtered

    symptoms = _filter_list(entry.get("symptoms") or [])
    causes = _filter_list(entry.get("causes") or [])
    fixes = _filter_list(entry.get("fixes") or [])

    def _ul(items):
        if not items: return "—"
        safe = [f"<li>{html.escape(str(i))}</li>" for i in items[:8]]
        return "<ul style='margin:6px 0 0 18px; padding-left:0'>" + "".join(
            safe) + "</ul>"

    parts = [
        f"<strong>{html.escape(code)}</strong> {('— ' + title) if title else ''}",
        f"<div style='opacity:.95;margin:6px 0'>{desc or 'No description available.'}</div>",
        f"<div><strong>Severity:</strong> {sev or 'Not specified'}</div>",
        f"<div style='margin-top:6px'><strong>Typical Symptoms:</strong> {_ul(symptoms)}</div>",
        f"<div style='margin-top:6px'><strong>Common Causes:</strong> {_ul(causes)}</div>",
        f"<div style='margin-top:6px'><strong>Suggested Fixes:</strong> {_ul(fixes)}</div>",
    ]
    return "<div class='code-message'>" + "<br>".join(parts) + "</div>"


# --- Vehicle make/model detection from free text (FIXED with model-to-make mapping) ---
_MAKES = [
    "audi", "bmw", "mercedes", "mercedes-benz", "vw", "volkswagen", "ford",
    "fiat", "vauxhall", "opel", "peugeot", "citroen", "renault", "toyota",
    "honda", "nissan", "mazda", "hyundai", "kia", "skoda", "seat", "volvo",
    "mini", "jaguar", "land rover", "landrover", "mitsubishi", "suzuki",
    "subaru", "lexus", "porsche", "saab", "alfa romeo", "alfa-romeo", "dacia",
    "tesla"
]

# FIXED: Comprehensive model-to-make mapping
_MODEL_TO_MAKE = {
    # Ford
    "fiesta": "ford",
    "focus": "ford",
    "mondeo": "ford",
    "kuga": "ford",
    "puma": "ford",
    "ranger": "ford",
    "transit": "ford",
    "ecosport": "ford",
    "mustang": "ford",
    "ka": "ford",
    "galaxy": "ford",
    "s-max": "ford",
    "edge": "ford",
    "explorer": "ford",
    "bronco": "ford",
    "escort": "ford",
    "sierra": "ford",
    "orion": "ford",
    "fusion": "ford",
    "c-max": "ford",

    # BMW
    "320d": "bmw",
    "330d": "bmw",
    "520d": "bmw",
    "x1": "bmw",
    "x3": "bmw",
    "x5": "bmw",
    "z4": "bmw",
    "m3": "bmw",
    "m5": "bmw",
    "i3": "bmw",
    "1 series": "bmw",
    "2 series": "bmw",
    "3 series": "bmw",
    "4 series": "bmw",
    "5 series": "bmw",
    "7 series": "bmw",
    "x2": "bmw",
    "x4": "bmw",
    "x6": "bmw",

    # Mercedes
    "a-class": "mercedes",
    "c-class": "mercedes",
    "e-class": "mercedes",
    "s-class": "mercedes",
    "cla": "mercedes",
    "gla": "mercedes",
    "glc": "mercedes",
    "gle": "mercedes",
    "gls": "mercedes",
    "amg": "mercedes",
    "sprinter": "mercedes",
    "vito": "mercedes",
    "b-class": "mercedes",
    "cls": "mercedes",
    "glb": "mercedes",

    # VW
    "golf": "volkswagen",
    "polo": "volkswagen",
    "passat": "volkswagen",
    "tiguan": "volkswagen",
    "touareg": "volkswagen",
    "arteon": "volkswagen",
    "t-roc": "volkswagen",
    "up": "volkswagen",
    "jetta": "volkswagen",
    "caddy": "volkswagen",
    "transporter": "volkswagen",
    "touran": "volkswagen",
    "sharan": "volkswagen",
    "beetle": "volkswagen",
    "scirocco": "volkswagen",

    # Audi
    "a1": "audi",
    "a3": "audi",
    "a4": "audi",
    "a5": "audi",
    "a6": "audi",
    "a7": "audi",
    "a8": "audi",
    "q2": "audi",
    "q3": "audi",
    "q5": "audi",
    "q7": "audi",
    "q8": "audi",
    "tt": "audi",
    "r8": "audi",
    "rs3": "audi",
    "rs4": "audi",
    "rs5": "audi",
    "rs6": "audi",
    "s3": "audi",
    "s4": "audi",

    # Vauxhall/Opel
    "corsa": "vauxhall",
    "astra": "vauxhall",
    "insignia": "vauxhall",
    "mokka": "vauxhall",
    "crossland": "vauxhall",
    "grandland": "vauxhall",
    "vivaro": "vauxhall",
    "combo": "vauxhall",
    "zafira": "vauxhall",
    "vectra": "vauxhall",
    "meriva": "vauxhall",
    "antara": "vauxhall",

    # Peugeot
    "208": "peugeot",
    "308": "peugeot",
    "2008": "peugeot",
    "3008": "peugeot",
    "5008": "peugeot",
    "508": "peugeot",
    "partner": "peugeot",
    "rifter": "peugeot",
    "107": "peugeot",
    "207": "peugeot",
    "307": "peugeot",
    "407": "peugeot",

    # Citroen
    "c1": "citroen",
    "c3": "citroen",
    "c4": "citroen",
    "c5": "citroen",
    "berlingo": "citroen",
    "dispatch": "citroen",
    "c3 aircross": "citroen",
    "c5 aircross": "citroen",
    "spacetourer": "citroen",

    # Renault
    "clio": "renault",
    "megane": "renault",
    "captur": "renault",
    "kadjar": "renault",
    "scenic": "renault",
    "koleos": "renault",
    "zoe": "renault",
    "twingo": "renault",
    "trafic": "renault",
    "kangoo": "renault",
    "laguna": "renault",

    # Toyota
    "yaris": "toyota",
    "corolla": "toyota",
    "camry": "toyota",
    "rav4": "toyota",
    "highlander": "toyota",
    "prius": "toyota",
    "aygo": "toyota",
    "hilux": "toyota",
    "land cruiser": "toyota",
    "avensis": "toyota",
    "auris": "toyota",
    "verso": "toyota",

    # Honda
    "civic": "honda",
    "accord": "honda",
    "cr-v": "honda",
    "hr-v": "honda",
    "jazz": "honda",
    "insight": "honda",
    "fr-v": "honda",

    # Nissan
    "micra": "nissan",
    "juke": "nissan",
    "qashqai": "nissan",
    "x-trail": "nissan",
    "leaf": "nissan",
    "navara": "nissan",
    "note": "nissan",
    "370z": "nissan",
    "gt-r": "nissan",

    # Mazda
    "mx-5": "mazda",
    "mazda2": "mazda",
    "mazda3": "mazda",
    "mazda6": "mazda",
    "cx-3": "mazda",
    "cx-5": "mazda",
    "cx-30": "mazda",
    "rx-8": "mazda",

    # Hyundai
    "i10": "hyundai",
    "i20": "hyundai",
    "i30": "hyundai",
    "tucson": "hyundai",
    "kona": "hyundai",
    "santa fe": "hyundai",
    "ioniq": "hyundai",
    "i40": "hyundai",

    # Kia
    "picanto": "kia",
    "rio": "kia",
    "ceed": "kia",
    "sportage": "kia",
    "sorento": "kia",
    "niro": "kia",
    "stonic": "kia",
    "soul": "kia",

    # Skoda
    "fabia": "skoda",
    "octavia": "skoda",
    "superb": "skoda",
    "kodiaq": "skoda",
    "karoq": "skoda",
    "kamiq": "skoda",
    "citigo": "skoda",

    # Seat
    "ibiza": "seat",
    "leon": "seat",
    "arona": "seat",
    "ateca": "seat",
    "tarraco": "seat",
    "mii": "seat",
    "alhambra": "seat",

    # Volvo
    "v40": "volvo",
    "v60": "volvo",
    "v90": "volvo",
    "s60": "volvo",
    "s90": "volvo",
    "xc40": "volvo",
    "xc60": "volvo",
    "xc90": "volvo",
    "v70": "volvo",
    "s80": "volvo",

    # Fiat
    "500": "fiat",
    "panda": "fiat",
    "tipo": "fiat",
    "punto": "fiat",
    "500x": "fiat",
    "500l": "fiat",
    "doblo": "fiat",
    "bravo": "fiat",

    # Mini
    "cooper": "mini",
    "countryman": "mini",
    "clubman": "mini",
    "one": "mini",

    # Jaguar
    "xe": "jaguar",
    "xf": "jaguar",
    "xj": "jaguar",
    "f-pace": "jaguar",
    "e-pace": "jaguar",
    "i-pace": "jaguar",
    "f-type": "jaguar",
    "x-type": "jaguar",

    # Land Rover
    "defender": "landrover",
    "discovery": "landrover",
    "freelander": "landrover",
    "range rover": "landrover",
    "evoque": "landrover",
    "velar": "landrover",
    "sport": "landrover",
    "discovery sport": "landrover",

    # Alfa Romeo
    "giulietta": "alfa romeo",
    "giulia": "alfa romeo",
    "stelvio": "alfa romeo",
    "mito": "alfa romeo",
    "147": "alfa romeo",
    "156": "alfa romeo",
    "159": "alfa romeo",

    # Dacia
    "sandero": "dacia",
    "duster": "dacia",
    "logan": "dacia",
    "stepway": "dacia",

    # Tesla
    "model s": "tesla",
    "model 3": "tesla",
    "model x": "tesla",
    "model y": "tesla",
}


def detect_make_model_from_text(text: str) -> tuple[str | None, str | None]:
    """
    FIXED: Now checks model names first (most specific), then make names
    """
    t = (text or "").lower()
    make_hit = None
    model_hit = None

    # PRIORITY 1: Check if we have vehicle data in session
    if ss.vehicle:
        vmake = (ss.vehicle.get("make") or "").lower().strip()
        vmodel = (ss.vehicle.get("model") or "").lower().strip()
        if vmake:
            make_hit = vmake
        if vmodel:
            model_hit = vmodel
        if make_hit:  # If we found make from session, use it and return early
            return make_hit, model_hit

    # PRIORITY 2: Check for model names (most specific - "Fiesta" → "Ford")
    for model, make in _MODEL_TO_MAKE.items():
        if model in t:
            make_hit = make
            model_hit = model
            break

    # PRIORITY 3: If no model found, check for make names directly
    if not make_hit:
        for mk in _MAKES:
            if mk in t:
                make_hit = "mercedes" if mk in (
                    "mercedes-benz", "mercedes") else (
                        "landrover" if mk == "land rover" else mk)
                break

    # PRIORITY 4: If we found a make but no model, try to grab the word after the make
    if make_hit and not model_hit:
        parts = t.split()
        for i, w in enumerate(parts):
            if w == make_hit or (make_hit == "mercedes"
                                 and w.startswith("mercedes")):
                if i + 1 < len(parts):
                    nxt = parts[i + 1]
                    if not _CODE_FINDER_RE.match(
                            nxt.upper()) and nxt.isalpha():
                        model_hit = nxt
                break

    return make_hit, model_hit


# --- Quick next-step rules for common codes (extendable) ---
NEXT_STEPS_RULES = {
    "P0300": {
        "generic": [
            "Read freeze-frame data; note RPM, load, fuel trims.",
            "Check for obvious vacuum leaks (split PCV hose, intake boots).",
            "Inspect spark plugs for wear/fouling; set correct gap; replace if aged.",
            "Swap coil packs between cylinders to see if misfire follows the coil.",
            "Fuel quality: add fresh fuel; consider injector cleaner; on DI engines, consider injector balance test.",
            "Check compression on suspect cylinders; if low, perform a wet test.",
        ],
        "ford": [
            "Fiesta petrols: coil pack and HT leads are common; try swapping coils first.",
            "EcoBoost: check plug gap (often closes up), cam cover PCV hose splits, and intake manifold gasket leaks.",
            "If rough cold idle only, check for MAP sensor contamination and small vac leaks at purge lines.",
        ],
        "ford_diesel": [
            "Check injector leak-off (return) rates; uneven return suggests injector issue.",
            "Inspect glow plugs and harness (cold start misfires).",
            "Check EGR sticking/sooting and boost hoses for splits.",
        ]
    }
}


# ───────────────────────── CSV match helper ─────────────────────────
def csv_match(text: str):
    rows = ss.csv_rows or []
    if not rows:
        return None, 0
    text_lower = _normalise_text(text)

    fault_words = [
        'problem', 'issue', 'fault', 'broken', 'not working', 'warning',
        'light', 'error', 'noise', 'smell', 'leak', 'vibration', 'shaking',
        'stalling', "won't start", 'rough', 'hesitating', 'knocking', 'smoke',
        'overheating', 'grinding', 'squealing', 'clicking', 'burning', 'dying',
        'cutting out', 'juddering', 'misfiring'
    ]
    info_words = [
        'petrol', 'diesel', 'fuel type', 'what engine', 'how many',
        'tell me about', 'information', 'specs', 'is this', 'is it',
        'what type', 'which fuel', 'engine size', 'how much'
    ]
    if not any(w in text_lower
               for w in fault_words) or any(w in text_lower
                                            for w in info_words):
        return None, 0

    user_tokens = set(text_lower.split())
    stop = {
        'the', 'a', 'an', 'is', 'my', 'has', 'have', 'with', 'and', 'or',
        'when', 'problem', 'issue', 'car', 'making', 'noise', 'for', 'of',
        'to', 'in', 'on', 'at', 'it', 'from', 'sound'
    }
    user_tokens -= stop
    symptom_words = [w for w in user_tokens if len(w) > 3]

    best_row, best_final = None, -1
    for r in rows:
        make = _normalise_text(r.get('Make', ''))
        model = _normalise_text(r.get('Model', ''))
        year = (r.get('Year', '') or '').lower()
        fault = _normalise_text(r.get('Fault', ''))
        if not make: continue

        make_ok = (make in text_lower) or (_fuzzy_ratio(make, text_lower)
                                           >= 80)
        if not make_ok: continue
        model_ok = bool(model) and ((model in text_lower) or
                                    (_fuzzy_ratio(model, text_lower) >= 80))

        fault_tokens = set(fault.split()) - stop
        overlap = len(set(symptom_words) & fault_tokens)
        if overlap == 0: continue

        score = overlap * 15 + (6 if make_ok else 0) + (4 if model_ok else 0)
        if year and any(y and y in text_lower for y in year.split('-')):
            score += 3
        fuzzy = _fuzzy_ratio(" ".join(sorted(symptom_words)),
                             " ".join(sorted(fault_tokens)))
        final = score * 10 + fuzzy
        if final > best_final:
            best_row, best_final = r, final

    if not best_row or best_final < 200:
        return None, 0

    confidence = max(55, min(95, 40 + best_final // 5))
    card = (
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
    return card, best_final


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
        if not rows: return ""
        lines = [
            f"- {(r.get('component') or 'component?')} | {(r.get('symptom') or 'symptom?')} | {(r.get('fix_summary') or '')[:200]}"
            for r in rows
        ]
        return "Known community fixes (recent Reddit):\n" + "\n".join(lines)
    except Exception:
        return ""


# ───────────────────────── AI + logging ─────────────────────────
def ask_ai(user_text: str, csv_context: str | None, codes_context: str | None):
    if ss.api_calls_today > 100:
        return "⚠️ Daily usage limit reached. Please try again tomorrow."
    msgs = [{"role": "system", "content": SYS_PROMPT}]
    for m in ss.chat_messages[-50:]:
        if m["role"] in ("user", "assistant"):
            msgs.append({"role": m["role"], "content": m["content"]})

    v = ss.vehicle
    note = ""
    if v:
        note = (
            f"\n\n[Vehicle Context: {(v.get('make','') or '').title()} "
            f"{(v.get('model','') or '').title()} {str(v.get('yearOfManufacture') or '')}, "
            f"{str(v.get('fuelType') or '')}, Engine: {str(v.get('engineCapacity') or '')}cc]"
        )
        comm = top_reddit_insight_blob(v.get('make', ''), v.get('model', ''))
        if comm:
            note += f"\n\n[Community Insights]\n{comm}"
    if csv_context:
        note += "\n\n[Database Match Found: A known issue was matched from our CSV.]"
    if codes_context:
        note += f"\n\n[OBD Codes]\n{codes_context}"

    msgs.append({"role": "user", "content": user_text + note})
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


# ───────────────────────── MOT OAuth + DVLA fallback ─────────────────────────
def _get_mot_access_token() -> str | None:
    cid = os.environ.get("MOT_CLIENT_ID", "")
    csec = os.environ.get("MOT_CLIENT_SECRET", "")
    tok = os.environ.get("MOT_TOKEN_URL", "")
    scope = os.environ.get("MOT_SCOPE_URL", "")
    if not (cid and csec and tok and scope):
        return None
    try:
        data = {
            "client_id": cid,
            "client_secret": csec,
            "grant_type": "client_credentials",
            "scope": scope
        }
        r = requests.post(tok, data=data, timeout=12)
        st.sidebar.caption(f"🔑 MOT token status: {r.status_code}")
        if r.ok:
            return r.json().get("access_token")
        else:
            try:
                st.sidebar.code(r.text[:400])
            except Exception:
                pass
    except Exception as e:
        st.sidebar.caption(f"Token error: {e}")
    return None


@st.cache_data(show_spinner=False, ttl=900)
def _mot_lookup_cached(vrm: str) -> dict | None:
    mot_key = os.environ.get("MOT_API_KEY", "")
    if not mot_key:
        return None
    token = _get_mot_access_token()
    if not token:
        return None
    try:
        st.sidebar.markdown(f"🔎 **MOT API** called for `{vrm}` →")
        headers = {
            "x-api-key": mot_key,
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        }
        r = requests.get(
            f"https://history.mot.api.gov.uk/v1/trade/vehicles/registration/{vrm}",
            headers=headers,
            timeout=12)
        st.sidebar.caption(f"Status: {r.status_code}")

        if r.ok:
            data = r.json()
            if isinstance(data, list) and data:
                v = data[0] or {}
            elif isinstance(data, dict):
                v = data
            else:
                return None
            return {
                "registrationNumber":
                vrm,
                "make": (v.get("make") or "").title(),
                "model": (v.get("model") or "").title(),
                "primaryColour": (v.get("primaryColour") or "").title(),
                "colour": (v.get("primaryColour") or "").title(),
                "fuelType":
                v.get("fuelType") or "",
                "engineCapacity":
                str(v.get("engineSize") or v.get("cylinderCapacity") or ""),
                "yearOfManufacture": (v.get("registrationDate")
                                      or v.get("firstUsedDate") or "")[:4],
                "motStatus":
                "Valid" if v.get("motTests") else "No Current MOT",
                "motExpiryDate":
                v.get("motTestExpiryDate") or "",
                "_source":
                "MOT",
            }
        else:
            st.sidebar.warning(f"⚠️ MOT API failed → {r.status_code}")
            try:
                st.sidebar.code(r.text[:400])
            except Exception:
                pass
    except Exception as e:
        st.sidebar.caption(f"MOT error: {e}")
    return None


@st.cache_data(show_spinner=False, ttl=900)
def _dvla_lookup_cached(vrm: str, dvla_key: str) -> dict | None:
    try:
        st.sidebar.markdown(f"🔎 **DVLA API** called for `{vrm}` →")
        headers = {
            "x-api-key": dvla_key,
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        r = requests.post(
            "https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles",
            headers=headers,
            json={"registrationNumber": vrm},
            timeout=12)
        st.sidebar.caption(f"Status: {r.status_code}")
        if r.ok:
            dvla = r.json() or {}
            dvla["_source"] = "DVLA"
            return dvla
        else:
            st.sidebar.warning("⚠️ DVLA API failed →")
            try:
                st.sidebar.code(r.text[:400])
            except Exception:
                pass
    except Exception as e:
        st.sidebar.caption(f"DVLA error: {e}")
    return None


def vehicle_lookup(reg_number: str) -> dict | None:
    vrm = (reg_number or "").replace(" ", "").upper()
    mot = _mot_lookup_cached(vrm)
    if mot:
        return mot
    if DVLA_KEY:
        dvla = _dvla_lookup_cached(vrm, DVLA_KEY)
        if dvla:
            return dvla
    return None


# ───────────────────────── UI helpers ─────────────────────────
def display_chat_message(role, content, message_type="normal", timestamp=None):
    timestamp = timestamp or datetime.now().strftime("%H:%M")
    if message_type == "csv":
        st.markdown(
            f'<div class="csv-message">{content}<div class="message-time">{html.escape(timestamp)}</div></div>',
            unsafe_allow_html=True)
        return
    if message_type == "code":
        st.markdown(
            f'{content}<div class="message-time">{html.escape(timestamp)}</div>',
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
logo_html = _inline_svg(str(svg)) if svg.exists() else (
    _inline_png(str(png_main), 200) if png_main.exists() else
    (_inline_png(str(png2x), 200) if png2x.exists() else
     (_inline_png(str(png), 200) if png.exists(
     ) else "<h1 style='margin:0'>obd<strong>ly</strong></h1>")))

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

# ────────────── OPTIONAL LOGIN SECTION ──────────────
if not ss.logged_in:
    with st.sidebar.expander("💾 Save Your Chats (Optional)", expanded=False):
        st.caption(
            "Create a free account to save conversations permanently. Continue without an account for temporary chats."
        )

        tab1, tab2 = st.tabs(["Login", "Sign Up"])

        with tab1:
            login_username = st.text_input("Username", key="login_username")
            login_password = st.text_input("Password",
                                           type="password",
                                           key="login_password")

            if st.button("Login", use_container_width=True, type="primary"):
                if login_username and login_password:
                    success, user_id = verify_user(login_username,
                                                   login_password)
                    if success:
                        ss.logged_in = True
                        ss.username = login_username
                        ss.user_id = user_id
                        st.success(f"✅ Welcome back, {login_username}!")
                        time.sleep(0.5)
                        st.rerun()
                    else:
                        st.error("❌ Invalid username or password")
                else:
                    st.warning("Please enter both username and password")

        with tab2:
            st.caption("🔒 Privacy: We don't collect emails or personal info.")

            signup_username = st.text_input("Choose Username",
                                            key="signup_username")
            signup_password = st.text_input("Choose Password (min 6 chars)",
                                            type="password",
                                            key="signup_password")
            signup_password2 = st.text_input("Confirm Password",
                                             type="password",
                                             key="signup_password2")

            if st.button("Create Account",
                         use_container_width=True,
                         type="primary"):
                if signup_username and signup_password and signup_password2:
                    if len(signup_username) < 3:
                        st.error("Username must be at least 3 characters")
                    elif len(signup_password) < 6:
                        st.error("Password must be at least 6 characters")
                    elif signup_password != signup_password2:
                        st.error("Passwords don't match")
                    else:
                        success, message = create_user(signup_username,
                                                       signup_password)
                        if success:
                            st.success(f"✅ {message}")
                            st.info("You can now login with your credentials!")
                        else:
                            st.error(f"❌ {message}")
                else:
                    st.warning("Please fill in all fields")

        st.markdown("---")

# ────────────── LOGGED IN USER SECTION ──────────────
else:
    st.sidebar.success(f"👤 Logged in as: **{ss.username}**")
    if st.sidebar.button("🚪 Logout", use_container_width=True):
        # Clear all user data
        ss.logged_in = False
        ss.username = None
        ss.user_id = None
        ss.chat_messages = []
        ss.vehicle = None
        ss.conversation_started = False
        ss.current_conversation_id = None
        st.success("Logged out successfully!")
        time.sleep(0.5)
        st.rerun()

    st.sidebar.markdown("---")

# ← NOTICE: No st.stop() here! Everyone can continue using the app


def _norm(s: str) -> str:
    if s is None: return ""
    s = unicodedata.normalize("NFKC", s).replace("\r", "").replace("\n", "")
    return s.strip()


# Only show admin panel if already admin or in development mode
if ss.get("is_admin", False) or os.environ.get("ADMIN_DEBUG_MODE") == "true":
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

# Cleaner navigation without radio buttons
st.sidebar.markdown("### 📋 Navigate")
page_options = [
    "💬 Chat with OBDly", "🛠️ Share Your Fix", "📊 Chat History", "ℹ️ About"
]

# Add admin pages if user is admin
if ss.is_admin:
    page_options += [
        "🔍 Reddit Collector", "🗄️ Database Manager", "📋 Review Submissions"
    ]

page = st.sidebar.selectbox("Choose a page",
                            page_options,
                            label_visibility="collapsed")

if st.sidebar.button("🔄 New Conversation"):
    ss.chat_messages = []
    ss.vehicle = None
    ss.conversation_started = False
    ss.show_repair_options = False
    ss.csv_match_found = False
    ss.processing_query = False
    ss.current_issue = None
    ss.current_conversation_id = None
    ss.last_detected_codes = []
    st.rerun()

if ss.vehicle:
    v = ss.vehicle
    st.sidebar.markdown("---")
    st.sidebar.markdown("### 🚗 Your Vehicle")
    make = (v.get('make', '') or '').title()
    model = (v.get('model', '') or v.get('wheelplan', '') or '').title()
    year = str(v.get('yearOfManufacture') or '')
    vehicle_name = (make + (" " + model if model else "") +
                    (" " + year if year else "")).strip()
    st.sidebar.caption(vehicle_name)

    fuel = str(v.get('fuelType') or '')
    colour = (v.get('colour') or v.get('primaryColour') or '').title()
    engine = str(v.get('engineCapacity') or '')
    details = [d for d in [fuel, colour, (engine and f"{engine}cc")] if d]
    if details:
        st.sidebar.caption(" • ".join(details))

st.sidebar.markdown("---")
st.sidebar.caption(f"API Calls: {ss.api_calls_today}/100")

if ss.get("is_premium", False):
    sidebar_images_text = "📸 Images: ∞ (Premium)"
else:
    images_left = max(0, 3 - ss.get("images_today", 0))
    sidebar_images_text = f"📸 Images: {images_left}/3 today"
st.sidebar.caption(sidebar_images_text)

# Load data (cached)
if not ss.csv_rows:
    load_fault_data()
ensure_obd_loaded()

# ───────────────────────── Import pages ─────────────────────────
try:
    from user_submission_page import submission_page, admin_review_page, check_admin_access
    from reddit_data_collector import reddit_collector_page
    from database_manager import database_manager_page
    from repair_options import show_repair_options
    from image_analysis import analyze_car_image, log_image_analysis, show_premium_promo, show_car_identification_confirmation
except Exception as e:
    st.sidebar.caption(f"Modules note: {e}")

# ───────────────────────── Routing ─────────────────────────
if page == "ℹ️ About":
    st.markdown("## About OBDly")
    st.markdown(
        "OBDly is your AI-powered car diagnostic assistant built for UK drivers."
    )

elif page == "📊 Chat History":
    st.markdown("## 💬 Chat History")

    if not ss.get("user_id"):
        st.info("💾 **Chat history is only saved for registered users.**")
        st.markdown("""
        Your current conversation works perfectly and is private to your browser session, 
        but it will be lost when you close the tab.
        
        **Create a free account to:**
        ✅ Save conversations permanently  
        ✅ Access them from any device  
        ✅ Resume chats anytime  
        
        👈 Use the "Save Your Chats" option in the sidebar to get started!
        """)
        st.stop()

    # Code for LOGGED-IN users below:
    try:
        conversations = get_user_conversations(ss.user_id)

        if not conversations:
            st.info(
                "No chat history yet. Start a conversation to see it here!")
        else:
            sorted_convs = sorted(conversations.items(),
                                  key=lambda x: x[1].get("updated", ""),
                                  reverse=True)
            st.caption(
                f"📚 {len(sorted_convs)} conversation{'s' if len(sorted_convs) != 1 else ''} saved"
            )

            for conv_id, conv in sorted_convs:
                created = conv.get("created", "Unknown")
                vehicle = conv.get("vehicle", "N/A")
                first_msg = conv.get("first_message", "")
                msg_count = len(conv.get("messages", []))

                with st.expander(
                        f"🚗 {vehicle} • {created[:10]} • {msg_count} messages",
                        expanded=False):
                    st.markdown(f"**Started:** {created}")
                    st.markdown(f"**Vehicle:** {vehicle}")
                    st.markdown(f"**First message:** {first_msg}...")

                    col1, col2, col3 = st.columns([2, 2, 3])
                    with col1:
                        if st.button("▶️ Resume Chat",
                                     key=f"resume_{conv_id}",
                                     use_container_width=True):
                            ss.chat_messages = conv.get("messages", [])
                            ss.conversation_started = True
                            ss.current_conversation_id = conv_id
                            if vehicle and vehicle != "N/A":
                                ss.vehicle = {"registrationNumber": vehicle}
                            st.success(
                                f"✅ Loaded conversation from {created[:10]}")
                            st.info("👉 Go to 'Chat with OBDly' to continue")
                            time.sleep(1)
                            st.rerun()
                    with col2:
                        if st.button("🗑️ Delete",
                                     key=f"delete_{conv_id}",
                                     use_container_width=True):
                            delete_user_conversation(ss.user_id, conv_id)
                            st.success("Deleted!")
                            time.sleep(0.5)
                            st.rerun()
                    with col3:
                        st.caption(
                            f"Last updated: {conv.get('updated', 'Unknown')[:16]}"
                        )

                    st.markdown("---")
                    st.markdown("**Conversation Preview:**")
                    for msg in conv.get("messages", [])[-6:]:
                        role_icon = "👤" if msg["role"] == "user" else "🤖"
                        st.markdown(
                            f"{role_icon} **{msg['role'].title()}:** {msg['content'][:150]}..."
                        )
                    if len(conv.get("messages", [])) > 6:
                        st.caption(
                            f"... and {len(conv.get('messages', [])) - 6} more messages"
                        )
    except Exception as e:
        st.error(f"Error loading chat history: {e}")

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
    # Registration lookup - CENTERED & STYLED
    if not ss.vehicle and not ss.conversation_started:
        st.markdown("<div class='obd-card'>", unsafe_allow_html=True)
        st.markdown(
            "<div class='obd-title' style='text-align:center;'>🔎 Quick Start: Lookup by Registration (Optional)</div>",
            unsafe_allow_html=True)
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            reg = st.text_input("Enter your registration",
                                placeholder="AB12 CDE",
                                label_visibility="collapsed",
                                key="reg_input")
            if st.button("Look Up",
                         use_container_width=True,
                         key="reg_lookup_btn"):
                if reg.strip():
                    with st.spinner("Looking up vehicle..."):
                        v = vehicle_lookup(reg.strip().replace(" ",
                                                               "").upper())
                        if v:
                            ss.vehicle = v
                            make = (v.get('make') or '').title()
                            model = (v.get('model') or '').title()
                            year = str(v.get('yearOfManufacture') or '')
                            colour = (v.get('colour') or v.get('primaryColour')
                                      or '').title()
                            fuel = str(v.get('fuelType') or '')
                            engine = str(v.get('engineCapacity') or '')
                            desc = f"✅ Vehicle found: {make}"
                            if model: desc += f" {model}"
                            if year: desc += f" {year}"
                            extras = [
                                d for d in
                                [colour, fuel, (engine and f'[{engine}cc]')]
                                if d
                            ]
                            if extras: desc += " • " + " ".join(extras)
                            src = v.get("_source") or "DVLA"
                            desc += f"  •  Source: {src}"
                            ss.chat_messages.append({
                                "role":
                                "system",
                                "content":
                                desc,
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

    # Anchor for scroll + Chat header
    st.markdown("<div id='chat-anchor'></div>", unsafe_allow_html=True)
    st.markdown("### 💬 Chat with OBDly")

    # Show messages
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

    # Thinking indicator
    if ss.processing_query:
        st.markdown('''
        <style>
        @keyframes kitt-scan{0%{left:-60px;}50%{left:calc(100% - 0px);}100%{left:-60px;}}
        .scanner-light{animation:kitt-scan 1s infinite ease-in-out !important;}
        </style>
        <div class="typing-indicator">
          <div class="scanner-container"><div class="scanner-light"></div></div>
        </div>
        ''',
                    unsafe_allow_html=True)

    st.markdown("---")

    # Chat input
    user_input = st.chat_input("Type your car problem or question here...")

    if user_input and not ss.processing_query:
        ss.processing_query = True
        ss.conversation_started = True
        ss.scroll_needed = True
        ss.chat_messages.append({
            "role": "user",
            "content": user_input,
            "timestamp": datetime.now().strftime("%H:%M")
        })
        ss.current_issue = user_input
        st.rerun()

    # Process after indicator render
    if ss.processing_query and not user_input:
        last_user_msg = next(
            (m["content"]
             for m in reversed(ss.chat_messages) if m["role"] == "user"), None)
        if last_user_msg:
            # 1) REG DETECTION & LOOKUP
            is_reg_query, detected_reg = detect_registration_request(
                last_user_msg)
            if is_reg_query and detected_reg:
                with st.spinner(f"🔍 Looking up {detected_reg}..."):
                    v = vehicle_lookup(detected_reg)
                    if v:
                        ss.vehicle = v
                        make = (v.get('make') or '').title()
                        model = (v.get('model') or '').title()
                        year = str(v.get('yearOfManufacture') or '')
                        colour = (v.get('colour') or v.get('primaryColour')
                                  or '').title()
                        fuel = str(v.get('fuelType') or '')
                        engine = str(v.get('engineCapacity') or '')

                        vehicle_info = f"🚗 **Vehicle Found: {detected_reg}**\n\n"
                        vehicle_info += f"**Make & Model:** {make} {model}\n"
                        if year: vehicle_info += f"**Year:** {year}\n"
                        if colour: vehicle_info += f"**Colour:** {colour}\n"
                        if fuel: vehicle_info += f"**Fuel Type:** {fuel}\n"
                        if engine: vehicle_info += f"**Engine:** {engine}cc\n"

                        mot_status = v.get('motStatus', '')
                        if mot_status:
                            vehicle_info += f"**MOT Status:** {mot_status}\n"
                        mot_expiry = v.get('motExpiryDate', '')
                        if mot_expiry:
                            vehicle_info += f"**MOT Expiry:** {mot_expiry}\n"
                        src = v.get("_source") or "DVLA"
                        vehicle_info += f"\n*Data source: {src}*"

                        ss.chat_messages.append({
                            "role":
                            "assistant",
                            "content":
                            vehicle_info,
                            "timestamp":
                            datetime.now().strftime("%H:%M")
                        })
                        follow_up = f"Great! I've loaded the details for your {make} {model}. What can I help you with? Any issues or questions about this vehicle?"
                        ss.chat_messages.append({
                            "role":
                            "assistant",
                            "content":
                            follow_up,
                            "timestamp":
                            datetime.now().strftime("%H:%M")
                        })
                        save_conversation()
                        ss.processing_query = False
                        st.rerun()
                    else:
                        error_msg = (
                            f"❌ Sorry, I couldn't find any vehicle details for registration **{detected_reg}**.\n\n"
                            f"This could mean:\n- The registration doesn't exist\n- There's a typo in the registration\n- The vehicle isn't registered in the UK\n\n"
                            f"Could you double-check the registration number? Or feel free to tell me about your car issue and I can still help!"
                        )
                        ss.chat_messages.append({
                            "role":
                            "assistant",
                            "content":
                            error_msg,
                            "timestamp":
                            datetime.now().strftime("%H:%M")
                        })
                        save_conversation()
                        ss.processing_query = False
                        st.rerun()

                        # 2) OBD CODE DETECTION & CARDS
            ensure_obd_loaded()
            detected_codes = find_obd_codes_in_text(last_user_msg)
            ss.last_detected_codes = detected_codes or []

            # Infer make/model from the user's message; prefer actual VRM if present
            inf_make, inf_model = detect_make_model_from_text(last_user_msg)
            if ss.vehicle and (ss.vehicle.get("make")
                               or ss.vehicle.get("model")):
                vmake = (ss.vehicle.get("make") or "").lower()
                vmodel = (ss.vehicle.get("model") or "").lower()
                if vmake:
                    inf_make = vmake
                if vmodel:
                    inf_model = vmodel

            vehicle_hint = None
            if inf_make:
                vehicle_hint = (inf_make or "") + (" " + (inf_model or "")
                                                   if inf_model else "")
                ss.chat_messages.append({
                    "role":
                    "assistant",
                    "content":
                    f"ℹ️ Interpreting for **{vehicle_hint.title()}** based on your message.",
                    "timestamp":
                    datetime.now().strftime("%H:%M")
                })

            codes_card_html = ""
            codes_context_text = ""
            if detected_codes:
                blocks = []
                for c in detected_codes:
                    entry = ss.obd_codes.get(c)
                    if entry:
                        # IMPORTANT: keep_make filters out off-brand lines (e.g., 'Mercedes...')
                        blocks.append(
                            render_code_card(c, entry, keep_make=inf_make))
                        short_causes = ", ".join(
                            map(str,
                                entry.get("causes") or []))[:220]
                        short_fixes = ", ".join(
                            map(str,
                                entry.get("fixes") or []))[:220]
                        line = f"{c}: {entry.get('title') or entry.get('description') or ''}".strip(
                        )
                        if short_causes: line += f" | causes: {short_causes}"
                        if short_fixes: line += f" | fixes: {short_fixes}"
                        codes_context_text += ("- " + line + "\n")
                    else:
                        blocks.append(
                            f"<div class='code-message'><strong>{html.escape(c)}</strong> — No local details found.</div>"
                        )
                        codes_context_text += f"- {c}: (no local details found)\n"
                codes_card_html = "<div style='display:flex;flex-direction:column;gap:8px'>" + "".join(
                    blocks) + "</div>"
                ss.chat_messages.append({
                    "role":
                    "assistant",
                    "content":
                    codes_card_html,
                    "type":
                    "code",
                    "timestamp":
                    datetime.now().strftime("%H:%M")
                })

            # 3) CSV KNOWN-FAULT MATCH
            enriched = last_user_msg
            if ss.vehicle:
                v = ss.vehicle
                enriched = f"{v.get('make','')} {v.get('model','')} {v.get('yearOfManufacture','')} {last_user_msg}"
            csv_card, _score = csv_match(enriched)
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

            # 4) AI ANSWER (first)
            extra_user = last_user_msg  # safe default
            if inf_make:
                extra_user = f"{inf_make} {inf_model or ''} {last_user_msg}".strip(
                )
            ai_response = ask_ai(
                extra_user, csv_card,
                (codes_context_text if detected_codes else None))
            ss.chat_messages.append({
                "role":
                "assistant",
                "content":
                ai_response,
                "timestamp":
                datetime.now().strftime("%H:%M")
            })

            # 5) Quick, vehicle-aware NEXT STEPS (after the AI answer)
            if detected_codes:
                for code in detected_codes:
                    rules = NEXT_STEPS_RULES.get(code.upper())
                    if not rules:
                        continue
                    lines = list(rules.get("generic", []))
                    if inf_make == "ford":
                        if ("diesel" in last_user_msg.lower()
                                or "tdci" in last_user_msg.lower()):
                            lines += rules.get("ford_diesel", [])
                        else:
                            lines += rules.get("ford", [])
                    if lines:
                        bullets = "\n".join([f"• {x}" for x in lines])
                        next_steps_msg = (
                            f"**Next steps for {code.upper()}**"
                            f"{(' — ' + vehicle_hint.title()) if vehicle_hint else ''}:\n\n"
                            f"{bullets}\n\n"
                            f"Typical UK costs: plugs £12–20 each, coil packs £25–60 each; indie labour £50–£80/hr."
                        )
                        ss.chat_messages.append({
                            "role":
                            "assistant",
                            "content":
                            next_steps_msg,
                            "timestamp":
                            datetime.now().strftime("%H:%M")
                        })

            log_interaction(last_user_msg, ai_response, ss.csv_match_found)
            save_conversation()
            ss.show_repair_options = True
            ss.processing_query = False
            st.rerun()

    # Scroll after new turn
    if ss.get("scroll_needed", False) and len(
            ss.chat_messages) > 1 and ss.conversation_started:
        components.html("""
        <script>
          setTimeout(() => {
            const el = document.getElementById('chat-anchor');
            if (el) {
              const y = el.getBoundingClientRect().top + window.pageYOffset - 20;
              window.scrollTo({top: y, behavior: 'smooth'});
            }
          }, 200);
        </script>
        """,
                        height=0)
        ss.scroll_needed = False

    # Image upload (collapsed expander)
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
                            try:
                                if not ss.get("is_premium", False):
                                    ss.images_today = ss.get(
                                        "images_today", 0) + 1
                                analysis = analyze_car_image(
                                    uploaded_file, context)
                                log_image_analysis(uploaded_file.name,
                                                   analysis)
                                show_car_identification_confirmation()
                                ss.conversation_started = True
                                ss.chat_messages.append({
                                    "role":
                                    "user",
                                    "content":
                                    f"📸 [Uploaded image: {uploaded_file.name}]"
                                    + (f"\n{context}" if context else ""),
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
                                ss.scroll_needed = True
                                save_conversation()
                                st.rerun()
                            except Exception as e:
                                st.error(f"Image analysis unavailable: {e}")

    # Premium promo & repair options
    if not ss.processing_query:
        try:
            if not ss.get("is_premium", False):
                show_premium_promo()
        except Exception:
            pass

    if ss.show_repair_options and len(
            ss.chat_messages) > 1 and not ss.processing_query:
        last_ai_message = next(
            (m for m in reversed(ss.chat_messages)
             if m["role"] == "assistant" and m.get("type") != "csv"), None)
        if last_ai_message and ss.current_issue:
            try:
                with st.expander("🛠️ How Would You Like to Fix This?",
                                 expanded=False):
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
