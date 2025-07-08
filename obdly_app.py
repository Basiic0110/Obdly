import streamlit as st
import os
import csv
import json
import requests
from datetime import datetime
from openai import OpenAI

print("✅ DVLA KEY in use:", os.environ.get("DVLA_KEY"))

# --- PAGE SETUP ---
st.set_page_config(page_title="OBDly - AI Car Assistant",
                   page_icon="🚗",
                   layout="centered")
st.title("🚗 OBDly - Find & Fix Car Problems")
st.markdown(
    "Quick answers for car problems. UK reg lookup + smart suggestions.")

# --- OPENAI CLIENT ---
client = OpenAI(api_key=os.environ.get("OBDLY_key2"))

# --- SIDEBAR MENU ---
st.sidebar.title("📑 OBDly Menu")
menu = st.sidebar.radio("Choose an option",
                        ["🔧 Diagnose a Car", "📑 View Previous Queries"])


# --- FUNCTIONS ---
def get_car_info_from_dvla(reg_number):
    api_key = os.environ.get("DVLA_KEY")
    headers = {"x-api-key": api_key, "Content-Type": "application/json"}
    data = {"registrationNumber": reg_number}
    try:
        response = requests.post(
            "https://driver-vehicle-licensing.api.gov.uk/vehicle-enquiry/v1/vehicles",
            headers=headers,
            json=data)

        # Debug logs
        print("🔍 DVLA Response Code:", response.status_code)
        print("📦 DVLA Response Body:", response.text)
        print("🛠 Request Headers:", headers)
        print("🛠 Request Body:", data)

        if response.status_code == 200:
            return response.json()
        elif response.status_code == 403:
            st.error(
                "DVLA API access denied (403). Check if you're using a test key or wrong endpoint."
            )
        else:
            st.warning(f"DVLA API error: {response.status_code}")
    except Exception as e:
        st.warning(f"DVLA API call failed: {str(e)}")
    return None


def display_car_details(vehicle):
    with st.expander("📋 Full Vehicle Details"):
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
        row_text = f"{row['Make']} {row['Model']} {row['Year']} {row['Fault']}".lower(
        )
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
            messages=[{
                "role":
                "system",
                "content":
                "You are a top-rated car repair assistant. Help in simple English."
            }, {
                "role": "user",
                "content": prompt
            }])
        return response.choices[0].message.content
    except:
        return "Sorry, OBDly AI couldn’t respond at this time."


def log_query(reg, issue, source, response):
    with open("query_log.csv", mode='a', newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if f.tell() == 0:
            writer.writerow(
                ["Timestamp", "Reg", "Issue", "Source", "Response"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reg or "N/A", issue,
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

    col1, col2 = st.columns(2)
    with col1:
        reg_filter = st.text_input(
            "🔍 Filter by reg plate (leave blank to skip)").lower()
    with col2:
        issue_filter = st.text_input("🔎 Keyword in issue (optional)").lower()

    source_filter = st.selectbox("📦 Source", ["All", "CSV", "AI"])

    results = reader
    if reg_filter:
        results = [row for row in results if reg_filter in row["Reg"].lower()]
    if issue_filter:
        results = [
            row for row in results if issue_filter in row["Issue"].lower()
        ]
    if source_filter != "All":
        results = [
            row for row in results if row["Source"].upper() == source_filter
        ]

    if not results:
        st.info("No matching queries.")
        return

    for row in reversed(results[-50:]):
        st.markdown(f"**[{row['Timestamp']}] {row['Reg']}**")
        st.markdown(f"**Issue:** {row['Issue']}")
        st.markdown(f"**Source:** {row['Source']}")
        st.markdown(f"**Response:** {row['Response'][:200]}...\n")
        st.markdown("---")


# --- MAIN LOGIC ---
if menu == "🔧 Diagnose a Car":
    faults = load_fault_data()
    mode = st.radio("How would you like to begin?",
                    ["Enter UK Registration Plate", "Describe the Issue"])
    reg, issue = "", ""

    if mode == "Enter UK Registration Plate":
        reg = st.text_input("Enter your reg plate (e.g. YH13ABC)")
        if reg:
            vehicle = get_car_info_from_dvla(reg)
            if vehicle:
                st.success(
                    f"Found: {vehicle['make'].title()} {vehicle.get('model', '').title()} {vehicle.get('yearOfManufacture', '')} ({vehicle.get('colour', '').title()})"
                )
                display_car_details(vehicle)
                issue = st.text_input("Describe the issue")
            else:
                st.warning("Car not found. Try manual issue mode.")
    else:
        issue = st.text_input("Describe your car issue")

    if st.button("🔧 Diagnose Now") and issue:
        user_input = f"{vehicle.get('make', '')} {vehicle.get('model', '')} {vehicle.get('yearOfManufacture', '')} {issue}" if reg and 'vehicle' in locals(
        ) else issue
        csv_result = find_fix_from_csv(user_input, faults)
        if csv_result:
            st.success(csv_result)
            log_query(reg, issue, "CSV", csv_result)
        else:
            st.info("No match found in database. Let’s ask OBDly AI...")
            ai_reply = ask_obdly_ai(user_input)
            st.markdown(ai_reply)
            log_query(reg, issue, "AI", ai_reply)

elif menu == "📑 View Previous Queries":
    view_log()
