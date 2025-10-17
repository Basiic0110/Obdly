import streamlit as st
import os
import csv
import requests
from datetime import datetime
from openai import OpenAI

# ---------- BOOT ----------
st.set_page_config(page_title="OBDly - Find & Fix Car Problems",
                   page_icon="🚗",
                   layout="centered")
print("✅ DVLA KEY in use:", os.environ.get("DVLA_KEY"))

# ---------- OPENAI ----------
client = OpenAI(api_key=os.environ.get("OBDLY_key2"))

# ---------- SESSION (chat memory) ----------
if "chat_history" not in st.session_state:
    st.session_state.chat_history = [{
        "role":
        "system",
        "content":
        ("You're OBDly, a friendly UK car diagnostic assistant. Speak like a knowledgeable mechanic, "
         "use simple English, give practical steps, and say when DIY is okay vs. see a pro."
         )
    }]


# ---------- HELPERS ----------
def get_car_info_from_dvla(reg_number: str):
    api_key = os.environ.get("DVLA_KEY")
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    data = {"registrationNumber": reg_number}
    try:
        resp = requests.post(
            "https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles",
            headers=headers,
            json=data,
            timeout=15)
        print("🔍 DVLA Response Code:", resp.status_code)
        print("📦 DVLA Response Body:", resp.text)
        if resp.status_code == 200:
            return resp.json()
        elif resp.status_code == 403:
            st.error(
                "DVLA API access denied (403). Are you using the live endpoint with a live key?"
            )
        else:
            st.warning(f"DVLA API error: {resp.status_code}")
    except Exception as e:
        st.warning(f"DVLA API call failed: {e}")
    return None


def display_car_details(vehicle: dict):
    with st.expander("📋 Full Vehicle Details", expanded=True):
        st.markdown(f"""
**Make:** {vehicle.get('make', 'N/A').title()}  
**Model:** {vehicle.get('model', 'N/A').title()}  
**Year:** {vehicle.get('yearOfManufacture', 'N/A')}  
**Colour:** {vehicle.get('colour', 'N/A').title()}  
**Fuel Type:** {vehicle.get('fuelType', 'N/A')}  
**Engine Capacity:** {vehicle.get('engineCapacity', 'N/A')}cc  
**CO2 Emissions:** {vehicle.get('co2Emissions', 'N/A')} g/km  
**Tax Status:** {vehicle.get('taxStatus', 'N/A')}  
**Tax Due Date:** {vehicle.get('taxDueDate', 'N/A')}  
**MOT Status:** {vehicle.get('motStatus', 'N/A')}  
**MOT Expiry Date:** {vehicle.get('motExpiryDate', 'N/A')}  
**Registration Number:** {vehicle.get('registrationNumber', 'N/A')}  
**Type Approval:** {vehicle.get('typeApproval', 'N/A')}  
**Export Marked:** {vehicle.get('markedForExport', 'N/A')}  
**Date of Last V5C Issued:** {vehicle.get('dateOfLastV5CIssued', 'N/A')}  
**Revenue Weight:** {vehicle.get('revenueWeight', 'N/A')} kg  
**Wheelplan:** {vehicle.get('wheelplan', 'N/A')}  
**First Registration Month:** {vehicle.get('monthOfFirstRegistration', 'N/A')}
""")


def load_fault_data():
    faults = []
    try:
        with open("obdly_fault_data.csv", mode='r', encoding="utf-8") as f:
            reader = csv.DictReader(f)
            for row in reader:
                faults.append(row)
        st.info(
            f"Loaded {len(faults)} fault rows from obdly_fault_data.csv.\n\nColumns: {list(reader.fieldnames)}"
        )
    except Exception as e:
        st.warning(
            f"Could not load obdly_fault_data.csv ({e}). CSV search will be skipped."
        )
    return faults


def find_fix_from_csv(user_input: str, faults: list):
    if not faults:
        return None, 0
    user_words = set(user_input.lower().split())
    best = None
    best_overlap = 0
    for row in faults:
        row_text = f"{row.get('Make','')} {row.get('Model','')} {row.get('Year','')} {row.get('Fault','')}".lower(
        )
        overlap = len(user_words & set(row_text.split()))
        if overlap > best_overlap and overlap >= 3:
            best = row
            best_overlap = overlap
    if not best:
        return None, 0
    pretty = (
        f"**Match Found (confidence ~{min(95, best_overlap*10)}%)**  \n"
        f"**Car:** {best.get('Make','').title()} {best.get('Model','').title()} {best.get('Year','')}  \n"
        f"**Fault:** {best.get('Fault','')}  \n"
        f"**Fix:** {best.get('Suggested Fix','Not scraped yet')}  \n"
        f"**Urgency:** {best.get('Urgency','Unknown')}  \n"
        f"**Warning Light:** {best.get('Warning Light?','Unknown')}")
    return pretty, best_overlap


def ask_obdly_ai(prompt: str):
    try:
        st.session_state.chat_history.append({
            "role": "user",
            "content": prompt
        })
        resp = client.chat.completions.create(
            model="gpt-3.5-turbo", messages=st.session_state.chat_history)
        reply = resp.choices[0].message.content
        st.session_state.chat_history.append({
            "role": "assistant",
            "content": reply
        })
        return reply
    except Exception as e:
        return f"⚠️ OBDly AI couldn't respond: {e}"


def log_query(reg, issue, source, response):
    try:
        with open("query_log.csv", mode='a', newline='',
                  encoding='utf-8') as f:
            w = csv.writer(f)
            if f.tell() == 0:
                w.writerow(["Timestamp", "Reg", "Issue", "Source", "Response"])
            w.writerow([
                datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reg or "N/A",
                issue, source, (response or "").strip().replace("\n", " ")
            ])
    except Exception as e:
        st.warning(f"Couldn't write to log: {e}")


def view_log():
    try:
        with open("query_log.csv", mode='r', encoding='utf-8') as f:
            rows = list(csv.DictReader(f))
    except:
        st.warning("No queries logged yet.")
        return
    if not rows:
        st.warning("Log is empty.")
        return
    st.markdown("### 🧾 Previous Queries")
    col1, col2 = st.columns(2)
    with col1:
        reg_filter = st.text_input(
            "🔍 Filter by reg plate (leave blank to skip)").lower()
    with col2:
        issue_filter = st.text_input("🔎 Keyword in issue (optional)").lower()
    source_filter = st.selectbox("📦 Source", ["All", "CSV", "AI"])
    results = rows
    if reg_filter:
        results = [r for r in results if reg_filter in r["Reg"].lower()]
    if issue_filter:
        results = [r for r in results if issue_filter in r["Issue"].lower()]
    if source_filter != "All":
        results = [r for r in results if r["Source"].upper() == source_filter]
    if not results:
        st.info("No matching queries.")
        return
    for r in reversed(results[-50:]):
        st.markdown(f"**[{r['Timestamp']}] {r['Reg']}**")
        st.markdown(f"**Issue:** {r['Issue']}")
        st.markdown(f"**Source:** {r['Source']}")
        st.markdown(f"**Response:** {r['Response'][:200]}...\n")
        st.markdown("---")


# ---------- BRAND / HEADER ----------
logo_path = "obdly_logo.png"  # upload your PNG in the root (Files) pane with this exact filename
with st.container():
    c = st.columns([1, 3, 1])
    with c[1]:
        if os.path.exists(logo_path):
            st.image(logo_path, width=140)
        st.markdown(
            "<div style='text-align:center; margin-top:-6px; color:#cbd5e1;'>Find &amp; Fix Car Problems</div>",
            unsafe_allow_html=True,
        )

st.write("")  # small breathing space

# ---------- SIDEBAR ----------
st.sidebar.title("📑 OBDly Menu")
menu = st.sidebar.radio("Choose an option",
                        ["🔧 Diagnose a Car", "📑 View Previous Queries"])

# =========================================================
#                      PAGES
# =========================================================
if menu == "📑 View Previous Queries":
    view_log()
else:
    # ---- Load CSV once
    faults = load_fault_data()

    # ---- LANDING / ISSUE FORM (ENTER now submits)
    with st.container():
        st.write("")  # tiny spacer

        with st.form("issue_form", clear_on_submit=False):
            issue_text = st.text_input(
                "Describe the issue",
                placeholder="e.g. 'Ford Focus 2019 lumpy transmission'")
            submitted = st.form_submit_button("Diagnose Now",
                                              use_container_width=False)

        st.markdown(
            "<div style='text-align:center; opacity:0.6; margin:6px 0;'>OR</div>",
            unsafe_allow_html=True)
        go_reg = st.link_button("SEARCH BY REG",
                                url="#reg",
                                help="Jump to reg look-up")
        st.button(
            "Previous Queries", on_click=lambda: None,
            key="dummy_prev_btn")  # simple visual; use sidebar for real log

    st.markdown("<hr style='opacity:.15;'>", unsafe_allow_html=True)

    # ---- ICONS ROW (simple 3-col grid)
    colA, colB, colC = st.columns(3)

    def icon_block(col, img, title, subtitle):
        with col:
            if os.path.exists(img):
                st.image(img, width=90)
            st.markdown(f"**{title}**  \n{subtitle}")

    icon_block(colA, "AI car manual.png", "AI", "Car Manual")
    icon_block(colB, "Car Buying Advice.png", "Car Buying",
               "Advice & Comparisons")
    icon_block(colC, "Service Assistant.png", "Service", "Assistant")

    st.markdown("<hr style='opacity:.15;'>", unsafe_allow_html=True)

    # ---- On submit from the issue form
    if submitted and issue_text.strip():
        # 1) CSV quick match
        csv_card, score = find_fix_from_csv(issue_text.strip(), faults)
        if csv_card:
            st.success(csv_card)

        # 2) Ask AI (always, but we prefix with known match if any)
        prefix = ""
        if csv_card:
            prefix = ("Known issue match from our database:\n"
                      f"{csv_card}\n\n"
                      "User issue: ")
        ai_reply = ask_obdly_ai(prefix + issue_text.strip())
        st.markdown(ai_reply)
        log_query(reg=None,
                  issue=issue_text.strip(),
                  source="CSV+AI" if csv_card else "AI",
                  response=ai_reply)

    # ---- REG LOOKUP AREA (anchor for link)
    st.markdown("<div id='reg'></div>", unsafe_allow_html=True)
    st.subheader("🔎 By Registration")
    reg = st.text_input("Enter your reg (e.g. OE65 HHK)", key="reg_input")
    if st.button("Look up & Diagnose", key="reg_btn"):
        vehicle = None
        if reg.strip():
            vehicle = get_car_info_from_dvla(reg.strip().replace(" ",
                                                                 "").upper())
        if vehicle:
            st.success(
                f"Found: {vehicle.get('make','').title()} {vehicle.get('model','N/A').title()} "
                f"{vehicle.get('yearOfManufacture','')} ({vehicle.get('colour','').title()})"
            )
            display_car_details(vehicle)
            follow_issue = st.text_input("Describe the issue for this car",
                                         key="issue_after_reg")
            if st.button("Diagnose for this car",
                         key="diagnose_after_reg") and follow_issue.strip():
                user_input = f"{vehicle.get('make','')} {vehicle.get('model','')} {vehicle.get('yearOfManufacture','')} {follow_issue}".strip(
                )
                csv_card, score = find_fix_from_csv(user_input, faults)
                if csv_card:
                    st.success(csv_card)
                ai_reply = ask_obdly_ai(user_input)
                st.markdown(ai_reply)
                log_query(reg=reg.strip().upper(),
                          issue=follow_issue.strip(),
                          source="CSV+AI" if csv_card else "AI",
                          response=ai_reply)
        else:
            st.warning("Car not found. Try manual issue mode above.")
