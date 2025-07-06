import os
import csv
import json
import requests
import xml.etree.ElementTree as ET
from datetime import datetime
import streamlit as st
from openai import OpenAI

client = OpenAI(api_key=os.environ["OBDLY_key2"])

# --- FUNCTIONS ---


def get_car_info_from_reg(reg_number):
    api_key = os.environ["REGCHECK_KEY"]
    url = f"https://www.regcheck.org.uk/api/reg.asmx/Check?RegistrationNumber={reg_number}&username={api_key}"
    response = requests.get(url)

    if response.status_code == 200:
        try:
            root = ET.fromstring(response.text)
            ns = {"ns": "http://regcheck.org.uk"}
            vehicle_json_str = root.findtext("ns:vehicleJson", namespaces=ns)
            if vehicle_json_str:
                data = json.loads(vehicle_json_str)
                make = data.get("Make", "").lower()
                model = data.get("Model", "").lower()
                if not make or not model:
                    desc = data.get("Description", "")
                    parts = desc.lower().split()
                    if len(parts) >= 2:
                        make, model = parts[:2]
                return {
                    "make": make,
                    "model": model,
                    "year": str(data.get("RegistrationYear", ""))
                }
        except Exception as e:
            st.error(f"❌ Vehicle data error: {e}")
    return None


def load_fault_data(filepath):
    try:
        with open(filepath, "r") as f:
            return list(csv.DictReader(f))
    except Exception as e:
        st.error(f"❌ CSV loading failed: {e}")
        return []


def find_fix_from_csv(user_input, faults):
    user_words = set(user_input.lower().split())
    best_match = None
    highest_overlap = 0
    for row in faults:
        text = f"{row['Make']} {row['Model']} {row['Year']} {row['Fault']}".lower(
        )
        row_words = set(text.split())
        overlap = len(user_words & row_words)
        if overlap > highest_overlap and overlap >= 3:
            best_match, highest_overlap = row, overlap
    if best_match:
        return f"""📋 **OBDly Match**  
**Car:** {best_match['Make']} {best_match['Model']} {best_match['Year']}  
**Fault:** {best_match['Fault']}  
**Fix:** {best_match['Suggested Fix']}  
**Urgency:** {best_match['Urgency']}  
**Warning Light?:** {best_match['Warning Light?']}"""
    return None


def ask_obdly_ai(query):
    reply = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[{
            "role":
            "system",
            "content":
            "You are a helpful car repair assistant and manual specialist. Provide clear, simple advice for car faults in plain English like a top rated 5 star mechanic would."
        }, {
            "role": "user",
            "content": query
        }])
    return reply.choices[0].message.content


def log_query(reg, issue, source, response):
    with open("query_log.csv", "a", newline='', encoding='utf-8') as f:
        writer = csv.writer(f)
        if f.tell() == 0:
            writer.writerow(
                ["Timestamp", "Reg", "Issue", "Source", "Response"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"), reg, issue, source,
            response.replace("\n", " ")
        ])


def view_logs():
    if not os.path.exists("query_log.csv"):
        st.warning("📭 No queries logged yet.")
        return
    with open("query_log.csv", "r", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
        if not rows:
            st.info("📂 Log is empty.")
            return
        view_option = st.radio("Filter logs by:",
                               ["Show All", "Reg Plate", "Keyword", "Source"])
        if view_option == "Reg Plate":
            reg = st.text_input("Enter reg (e.g. YH13ABC)").lower()
            rows = [r for r in rows if r["Reg"].lower() == reg]
        elif view_option == "Keyword":
            kw = st.text_input("Enter keyword").lower()
            rows = [r for r in rows if kw in r["Issue"].lower()]
        elif view_option == "Source":
            src = st.selectbox("Choose source", ["CSV", "AI"])
            rows = [r for r in rows if r["Source"] == src]
        if not rows:
            st.warning("No matching results.")
        else:
            for r in rows:
                st.markdown(
                    f"🕒 `{r['Timestamp']}` — **{r['Reg']}**: {r['Issue']}")
                st.markdown(
                    f"🔹 *{r['Source']}*: {r['Response'][:300]}...\n---")


# --- UI LAYOUT ---

st.set_page_config(page_title="OBDly", layout="centered")
st.title("🚗 OBDly - Find & Fix Car Problems")
st.caption(
    "Quick answers for car problems. UK reg lookup + smart suggestions.")

st.divider()
choice = st.radio("How would you like to begin?",
                  ["Enter UK Registration Plate", "Describe the Issue"])

faults = load_fault_data("obdly_fault_data.csv")
reg = ""
issue = ""

if choice == "Enter UK Registration Plate":
    reg = st.text_input("Enter your reg plate (e.g. YH13ABC)").strip()
    if reg:
        car = get_car_info_from_reg(reg)
        if car:
            st.success(
                f"✅ Found: {car['make'].title()} {car['model'].title()} ({car['year']})"
            )
            issue = st.text_input("Describe the issue you're having:")
            user_input = f"{car['make']} {car['model']} {car['year']} {issue}"
        else:
            st.error("🚫 Car not found. Try describing the issue manually.")
            issue = st.text_input("Describe the problem:")
            user_input = issue
    else:
        user_input = ""
elif choice == "Describe the Issue":
    issue = st.text_input("Describe your car problem:")
    user_input = issue

if user_input:
    if st.button("🔍 Find Fix"):
        csv_match = find_fix_from_csv(user_input, faults)
        if csv_match:
            st.success("✅ Found in OBDly database")
            st.markdown(csv_match)
            log_query(reg or "N/A", issue, "CSV", csv_match)
        else:
            st.info("🤖 No match in database. Asking OBDly AI...")
            ai_response = ask_obdly_ai(user_input)
            st.markdown(ai_response)
            log_query(reg or "N/A", issue, "AI", ai_response)

# Optional: View logs
st.divider()
if st.button("📑 View Previous Queries"):
    st.subheader("📋 Past Queries")
    view_logs()
