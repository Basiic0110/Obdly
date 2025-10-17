# repair_options.py — DIY-first flow with Pro fallback + download guide

import streamlit as st
import urllib.parse
import re
import io
from datetime import datetime

# ═══════════════════ DIFFICULTY ASSESSMENT ═══════════════════


def assess_repair_difficulty(ai_response: str,
                             fault_description: str = "") -> str:
    """
    Decide if repair is DIY-friendly or needs professional help.
    Returns one of: 'diy' | 'intermediate' | 'professional'
    """
    text = f"{ai_response} {fault_description}".lower()

    # Professional-only (safety-critical / heavy-labour / special tools)
    professional_keywords = [
        # powertrain & timing
        'timing belt',
        'timing chain',
        'clutch replacement',
        'dual mass flywheel',
        'gearbox',
        'transmission rebuild',
        'dsg service',
        'valve timing',
        'head gasket',
        'engine rebuild',
        # safety systems & chassis
        'airbag',
        'srs',
        'abs module',
        'brake line',
        'brake fluid flush',
        'steering rack',
        'subframe',
        'wheel bearing press',
        'ball joint press',
        # high voltage / hybrids
        'hybrid battery',
        'high voltage',
        'inverter',
        # forced induction & fuel system deeper work
        'turbo replacement',
        'supercharger',
        'injector coding',
        'high pressure fuel pump',
        # general danger markers
        'dangerous',
        'urgent',
        'safety critical',
        'immediately',
        'tow',
        # emissions complex
        'dpf replacement',
        'scr system',
    ]

    # Easy DIY
    diy_keywords = [
        'air filter', 'cabin filter', 'pollen filter', 'wiper blade', 'bulb',
        'light bulb', 'fuse', 'top up', 'check level', 'battery replacement',
        'key fob battery', 'washer fluid', 'oil change', 'tyre pressure',
        'simple', 'easy', 'straightforward'
    ]

    # Intermediate DIY
    intermediate_keywords = [
        'brake pad',
        'brake disc',
        'spark plug',
        'coil pack',
        'ignition coil',
        'thermostat',
        'o2 sensor',
        'lambda sensor',
        'map sensor',
        'maf sensor',
        'egr valve clean',
        'pcv',
        'throttle body clean',
        'hose',
        'belt',
        'mount',
        'engine mount',
        'filter replacement',
        'fluid change',
        'minor leak',
        'bleed',
        'radiator fan',
        'aux belt',
        'tensioner',
        'drop link',
        'anti roll bar link',
    ]

    # Decision
    if any(k in text for k in professional_keywords):
        return 'professional'
    if any(k in text for k in diy_keywords):
        return 'diy'
    if any(k in text for k in intermediate_keywords):
        return 'intermediate'
    # Fall back based on tone hints
    if any(k in text
           for k in ['complex', 'special tool', 'press', 'calibration']):
        return 'professional'
    return 'intermediate'


# ═══════════════════ LIGHT PARSERS ═══════════════════

_CURRENCY_RE = re.compile(
    r"(£\s?\d{1,3}(?:[,.\s]?\d{3})*(?:\.\d{2})?)"
    r"(?:\s?-\s?(£\s?\d{1,3}(?:[,.\s]?\d{3})*(?:\.\d{2})?))?"
    r"|\bfrom\s+(£\s?\d{1,4})\b"
    r"|\b(£\s?\d{1,4})\s*\+?\s*vat\b", re.IGNORECASE)


def parse_costs(text: str) -> str:
    """Return a neat cost string if we can find one."""
    m = _CURRENCY_RE.search(text or "")
    if not m:
        return ""
    s = m.group(0)
    # Normalise spacing/case
    s = re.sub(r"\s+", " ", s, flags=re.I).strip()
    s = s.replace("Vat", "VAT").replace("vat", "VAT")
    return s


def extract_tools_from_response(text: str):
    common_tools = [
        'spanner', 'wrench', 'socket set', 'screwdriver', 'jack',
        'jack stands', 'torque wrench', 'pliers', 'hammer', 'ratchet',
        'multimeter', 'oil filter wrench', 'funnel', 'drain pan', 'wire brush',
        'obd scanner'
    ]
    t = (text or "").lower()
    found = [tool for tool in common_tools if tool in t]
    # Add safety basics if working under car
    if any(x in t
           for x in ['wheel', 'brake', 'suspension', 'undertray', 'subframe']):
        if 'axle stands' not in found and 'jack stands' not in found:
            found.append('jack stands')
        if 'wheel chocks' not in found:
            found.append('wheel chocks')
    return found[:8]


def extract_parts_from_response(text: str):
    common_parts = [
        'filter', 'spark plug', 'oil', 'coolant', 'brake pad', 'brake disc',
        'battery', 'bulb', 'fuse', 'belt', 'hose', 'sensor', 'coil pack',
        'thermostat', 'gasket', 'seal', 'fluid', 'pcv', 'throttle body gasket'
    ]
    t = (text or "").lower()
    found = [p for p in common_parts if p in t]
    return found[:6]


def estimate_repair_time(text: str) -> str:
    t = (text or "").lower()
    if any(w in t for w in ['minutes', 'quick', 'simple', 'easy']):
        return "15–30 minutes"
    if any(w in t for w in ['hour', 'moderate']):
        return "1–2 hours"
    if any(w in t for w in ['complex', 'involved', 'several', 'subframe']):
        return "2–4 hours"
    return "1–2 hours"


def contains_warning_light(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in [
        'warning light', 'check engine', 'cel', 'epc', 'abs light',
        'airbag light'
    ])


# ═══════════════════ DIY GUIDE GENERATOR ═══════════════════


def _compose_guide_text(issue: str, ai_response: str, difficulty: str,
                        cost_hint: str) -> str:
    """Plaintext guide (for download button)."""
    lines = []
    lines.append(
        f"OBDly DIY Guide — {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    lines.append(f"Issue: {issue}")
    lines.append(f"Difficulty: {difficulty.upper()}")
    if cost_hint:
        lines.append(f"Estimated Cost: {cost_hint}")
    lines.append("")
    lines.append("What You'll Need:")
    tools = extract_tools_from_response(ai_response)
    parts = extract_parts_from_response(ai_response)
    lines.append("  Tools: " + (", ".join(tools) if tools else
                                "Basic tool set, safety glasses, gloves"))
    lines.append("  Parts: " +
                 (", ".join(parts) if parts else "Refer to diagnosis above"))
    lines.append("")
    lines.append(f"Estimated Time: {estimate_repair_time(ai_response)}")
    lines.append("")
    lines.append("Safety:")
    lines.append(
        "  • Work on level ground, chock wheels, never rely on a jack only.")
    lines.append("  • Disconnect the battery for electrical work.")
    lines.append("  • Wear eye protection and gloves.")
    lines.append("")
    lines.append("Steps:")
    lines.append(ai_response.strip())
    lines.append("")
    lines.append("Videos: Search YouTube for: " + f"how to fix {issue}")
    return "\n".join(lines)


def generate_diy_guide(issue: str, ai_response: str):
    """Render a structured DIY guide panel (with download)."""
    st.markdown("### 🔧 DIY Repair Guide")

    difficulty = assess_repair_difficulty(ai_response, issue)
    if difficulty == 'diy':
        st.success("✅ **Difficulty: EASY** — Most people can do this.")
    elif difficulty == 'intermediate':
        st.warning(
            "⚠️ **Difficulty: INTERMEDIATE** — Some mechanical knowledge helpful."
        )
    else:
        st.error("⛔ **Difficulty: ADVANCED** — Consider professional help.")

    # What you'll need
    st.markdown("#### 📋 What You'll Need")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("**🔧 Tools:**")
        tools = extract_tools_from_response(ai_response)
        if tools:
            for t in tools:
                st.markdown(f"- {t}")
        else:
            st.markdown("- Basic tool set\n- Safety glasses\n- Gloves")
    with col2:
        st.markdown("**🔩 Parts:**")
        parts = extract_parts_from_response(ai_response)
        if parts:
            for p in parts:
                st.markdown(f"- {p}")
        else:
            st.markdown("- Refer to diagnosis above")

    # Time & safety
    st.info(f"⏱️ **Estimated Time:** {estimate_repair_time(ai_response)}")

    if 'safety' in (ai_response or '').lower() or difficulty == 'professional':
        st.error("**⚠️ SAFETY FIRST:**\n"
                 "- Work in a well-ventilated, level area\n"
                 "- Use axle/jack stands (never just a jack)\n"
                 "- Disconnect the battery for electrical work\n"
                 "- Wear safety glasses and gloves\n"
                 "- If unsure, stop and consult a professional")

    # Steps (we show the AI response as-is so it stays rich)
    st.markdown("#### 📝 Steps")
    st.markdown(ai_response)

    # Where to buy parts (UK)
    st.markdown("---")
    st.markdown("#### 🛒 Where to Buy Parts")
    q = urllib.parse.quote(issue)
    cols = st.columns(3)
    with cols[0]:
        st.markdown(
            f"<a href='https://www.amazon.co.uk/s?k={q}' target='_blank' "
            f"style='display:block;background:#FF9900;color:white;padding:10px;border-radius:8px;"
            f"text-align:center;text-decoration:none;font-weight:600;'>🛒 Amazon UK</a>",
            unsafe_allow_html=True)
    with cols[1]:
        st.markdown(
            f"<a href='https://www.eurocarparts.com/search?q={q}' target='_blank' "
            f"style='display:block;background:#E31837;color:white;padding:10px;border-radius:8px;"
            f"text-align:center;text-decoration:none;font-weight:600;'>🔧 Euro Car Parts</a>",
            unsafe_allow_html=True)
    with cols[2]:
        st.markdown(
            f"<a href='https://www.halfords.com/search?q={q}' target='_blank' "
            f"style='display:block;background:#005AA9;color:white;padding:10px;border-radius:8px;"
            f"text-align:center;text-decoration:none;font-weight:600;'>🛠️ Halfords</a>",
            unsafe_allow_html=True)

    # Video tutorials
    st.markdown("---")
    st.markdown("#### 📺 Video Tutorials")
    yt = urllib.parse.quote(f"how to fix {issue}")
    st.markdown(
        f"<a href='https://www.youtube.com/results?search_query={yt}' target='_blank' "
        f"style='display:inline-block;background:#FF0000;color:white;padding:10px 20px;border-radius:8px;"
        f"text-decoration:none;font-weight:600;'>▶️ Search YouTube Tutorials</a>",
        unsafe_allow_html=True)

    # Download as TXT
    st.markdown("---")
    cost_hint = parse_costs(ai_response)
    txt = _compose_guide_text(issue, ai_response, difficulty, cost_hint)
    buf = io.BytesIO(txt.encode("utf-8"))
    st.download_button(
        "⬇️ Download DIY Guide (.txt)",
        data=buf,
        file_name=
        f"OBDly_DIY_Guide_{datetime.now().strftime('%Y%m%d_%H%M')}.txt",
        mime="text/plain",
        use_container_width=True)

    st.info(
        "🤔 **Still unsure?** No shame in getting help! Try the *Find a Mechanic* tab."
    )


# ═══════════════════ MECHANIC FINDER ═══════════════════


def show_mechanic_finder(issue: str, estimated_cost: str = ""):
    """Show mechanic finder with context and tips."""
    st.markdown("### 🗺️ Find a Professional Mechanic")

    if estimated_cost:
        st.info(
            f"💰 **Estimated Cost:** {estimated_cost}\n\n*Knowing the likely fix helps avoid overcharging.*"
        )

    st.markdown("""
    **Why use a professional for this job?**
    - Requires specialist tools or ramps
    - Safety-critical repair
    - Complex diagnosis needed
    - Warranty/guarantee on parts & labour
    """)

    col1, col2 = st.columns([3, 1])
    with col1:
        location = st.text_input("Enter your postcode or area",
                                 placeholder="e.g. SW1A 1AA or Manchester",
                                 key="mechanic_location_input")
    with col2:
        if st.button("🔍 Find",
                     use_container_width=True,
                     key="find_mechanics_btn"):
            if location:
                maps_url = f"https://www.google.com/maps/search/car+mechanic+garage+near+{urllib.parse.quote(location)}"
                st.markdown(
                    f"<a href='{maps_url}' target='_blank' "
                    f"style='display:inline-block;background:linear-gradient(135deg,#667eea 0%,#764ba2 100%);"
                    f"color:white;padding:12px 24px;border-radius:8px;text-decoration:none;font-weight:600;margin:10px 0;'>"
                    f"View Mechanics on Google Maps →</a>",
                    unsafe_allow_html=True)

    st.markdown("---")
    colL, colR = st.columns(2)
    with colL:
        st.markdown("""
        **✅ Good Signs**
        - 4.5★+ with recent reviews
        - Specialists in your make
        - Clear, written quotes
        - Shows you old parts
        - Warranty on work
        """)
    with colR:
        st.markdown("""
        **🚩 Red Flags**
        - No online presence
        - Pushy upsells
        - Vague diagnosis
        - “Must fix immediately”
        - Much cheaper than others
        """)

    st.success(
        "💡 **Pro tip:** Ask the garage to confirm the suspected fault. If their diagnosis is totally different, consider a second opinion."
    )


# ═══════════════════ MAIN DECISION INTERFACE ═══════════════════


def show_repair_options(issue: str,
                        ai_response: str,
                        csv_match_found: bool = False,
                        vehicle=None):
    """
    Main panel shown after diagnosis.
    Intelligently recommends DIY vs Pro and offers both paths.
    """
    difficulty = assess_repair_difficulty(ai_response, issue)
    estimated_cost = parse_costs(ai_response)

    st.markdown("---")
    st.markdown("## 🛠️ How Would You Like to Fix This?")

    # Recommendation banner
    if csv_match_found:
        st.markdown(
            "🧠 **Known-issue match found in OBDly database** — solution below may be popular for your model."
        )

    if difficulty == 'diy':
        st.success(
            "✅ **Good news!** This looks DIY-friendly. Try it yourself first.")
    elif difficulty == 'professional':
        st.warning(
            "⛔ **Heads up!** This typically needs professional tools/skills. Consider booking a mechanic."
        )
    else:
        st.info(
            "💭 **You have options.** Handy DIYers can attempt this, or book a professional."
        )

    # Tabs
    tab1, tab2 = st.tabs(["🔧 DIY It Yourself", "🗺️ Find a Mechanic"])

    with tab1:
        generate_diy_guide(issue, ai_response)

    with tab2:
        show_mechanic_finder(issue, estimated_cost)
