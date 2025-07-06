import streamlit as st
import os
import csv
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
from openai import OpenAI

# --- INIT ---
st.set_page_config(page_title="OBDly - AI Car Assistant", page_icon="🚗", layout="centered")
st.title("🚗 OBDly - Find & Fix Car Problems")
st.markdown("Quick answers for car problems. UK reg lookup + smart suggestions.")

client = OpenAI(api_key=os.environ.get("OBDLY_key2"))

# --- HELPERS ---
def get_car_info_from_reg(reg_number):
    api_key = os.environ.get("REGCHECK_KEY")
    url = f"https://www.regcheck.org.uk/api/reg.asmx/Check?RegistrationNumber={reg_number}&username={api_key}"
    response = requests.get(url)
    if response.status_code == 200:
        try:
            root = ET.fromstring(response.text)
            ns = {"ns": "http://regcheck.org.uk"}
            vehicle_json_str = root.findtext("ns:vehicleJson", namespaces=ns)
            if vehicle_json_str:
                vehicle_data = json.loads(vehicle_json_str)
                make = vehicle_data.get("Make", "").lower()
                model = vehicle_data.get("Model", "").lower()
                if not make or not model:
                    desc = vehicle_data.get("Description", "").lower().split()
                    if len(desc) >= 2:
                        make, model = desc[0], desc[1]
                return {"make": make, "model": model, "year": str(vehicle_data.get("RegistrationYear", ""))}
        except Exception:
            pass
    return None

def load_fault_data():
    faults = []
    try:
        with open("obdly_fault_data.csv", mode='r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                faults.append(row)
    except:
        pass
    return faults

def find_fix_from_csv(user_input, faults):
    user_words = set(user_input.lower().split())
    best_match = None
    highest_overlap = 0
    for row in faults:
        row_text = f"{row['Make']} {row['Model']} {row['Year']} {row['Fault']}".lower()
        row_words = set(row_text.split())
        overlap = len(user_words & row_words)
        if overlap > highest_overlap and overlap >= 3:
            best_match = row
            highest_overlap = overlap
    if best_match:
        return f"""📋 **Match Found**
**Car:** {best_match['Make'].title()} {best_match['Model'].title()} {best_match['Year']}
**Fault:** {best_match['Fault']}
**Fix:** {best_match['Suggested Fix']}
**Urgency:** {best_match['Urgency']}
**Warning Light:** {best_match['Warning Light?']}"""
    return None

def ask_obdly_ai(prompt):
    try:
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[
                {"role": "system", "content": "You are a top-rated car repair assistant. Help in simple English."},
                {"role": "user", "content": prompt}
            ]
        )
        return response.choices[0].message.content
    except:
        return "Sorry, OBDly AI couldn’t respond at this time."

def log_query(reg, issue, source, response):
    with open("query_log.csv", mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if f.tell() == 0:
            writer.writerow(["Timestamp", "Reg", "Issue", "Source", "Response"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            reg or "N/A",
            issue,
            source,
            response.strip().replace("\n", " ")
        ])

def view_log():
    if not os.path.exists("query_log.csv"):
        st.warning("No queries logged yet.")
        return
    with open("query_log.csv", mode='r', encoding='utf-8') as f:
        reader = list(csv.DictReader(f))
        if not reader:
            st.warning("Log is empty.")
            return
        st.markdown("### 🧾 Previous Queries")
        for row in reversed(reader[-20:]):
            st.markdown(f"**[{row['Timestamp']}] {row['Reg']}**")
            st.markdown(f"**Issue:** {row['Issue']}")
            st.markdown(f"**Source:** {row['Source']}")
            st.markdown(f"**Response:** {row['Response'][:200]}...\n")

# --- SIDEBAR ---
st.sidebar.title("📑 OBDly Menu")
menu = st.sidebar.radio("What would you like to do?", ["🔍 Diagnose a Car", "📑 View Previous Queries"])

if menu == "📑 View Previous Queries":
    view_log()
    st.stop()

# --- MAIN FORM ---
faults = load_fault_data()
mode = st.radio("How would you like to begin?", ["Enter UK Registration Plate", "Describe the Issue"])
reg, issue = "", ""

if mode == "Enter UK Registration Plate":
    reg = st.text_input("Enter your reg plate (e.g. YH13ABC)")
    if reg:
        car = get_car_info_from_reg(reg)
        if car:
            st.success(f"Found: {car['make'].title()} {car['model'].title()} {car['year']}")
            issue = st.text_input("Describe the issue")
        else:
            st.warning("Car not found. Try manual issue mode.")
else:
    issue = st.text_input("Describe your car issue")

if st.button("🔧 Diagnose Now") and issue:
    user_input = f"{car['make']} {car['model']} {car['year']} {issue}" if reg and car else issue
    csv_result = find_fix_from_csv(user_input, faults)
    if csv_result:
        st.success(csv_result)
        log_query(reg, issue, "CSV", csv_result)
    else:
        st.info("No match found in database. Let’s ask OBDly AI...")
        ai_reply = ask_obdly_ai(user_input)
        st.markdown(ai_reply)
        log_query(reg, issue, "AI", ai_reply)
