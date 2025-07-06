import os
import csv
import requests
import xml.etree.ElementTree as ET
import json
from datetime import datetime
from openai import OpenAI

client = OpenAI(api_key=os.environ["OBDLY_key2"])

def get_car_info_from_reg(reg_number):
    api_key = os.environ["REGCHECK_KEY"]
    url = f"https://www.regcheck.org.uk/api/reg.asmx/Check?RegistrationNumber={reg_number}&username={api_key}"

    response = requests.get(url)
    print(f"📡 Response Code: {response.status_code}")
    print(f"🧾 Response Body: {response.text[:300]}...")

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
                    description = vehicle_data.get("Description", "")
                    parts = description.lower().split()
                    if len(parts) >= 2:
                        make = parts[0]
                        model = parts[1]

                return {
                    "make": make,
                    "model": model,
                    "year": str(vehicle_data.get("RegistrationYear", ""))
                }

            else:
                print("❌ Could not find <vehicleJson> in XML.")
        except Exception as e:
            print(f"❌ Error parsing vehicle data: {e}")
    else:
        print("❌ Failed to fetch car info.")

    return None

def load_fault_data(file_path):
    faults = []
    try:
        with open(file_path, mode='r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                faults.append(row)
    except Exception as e:
        print(f"❌ Error loading CSV: {e}")
    return faults

def find_fix_from_csv(user_input, faults):
    user_words = set(user_input.lower().split())
    best_match = None
    highest_overlap = 0

    for row in faults:
        row_text = f"{row['Make']} {row['Model']} {row['Year']} {row['Fault']}".lower()
        row_words = set(row_text.split())
        overlap_words = user_words & row_words
        overlap = len(overlap_words)

        if overlap > highest_overlap and overlap >= 3:
            best_match = row
            highest_overlap = overlap

    if best_match:
        return f"""📋 OBDly Match:
{best_match['Make']} {best_match['Model']} {best_match['Year']}
Fault: {best_match['Fault']}
Fix: {best_match['Suggested Fix']}
Urgency: {best_match['Urgency']}
Warning Light: {best_match['Warning Light?']}"""

    return None

def ask_obdly_ai(user_input):
    response = client.chat.completions.create(
        model="gpt-3.5-turbo",
        messages=[
            {"role": "system", "content": "You are a helpful car repair assistant and manual specialist. Provide clear, simple advice for car faults in plain English like a top rated 5 star mechanic would."},
            {"role": "user", "content": user_input}
        ]
    )
    return response.choices[0].message.content

def log_query(reg, issue, source, response_text):
    with open("query_log.csv", mode='a', newline='', encoding='utf-8') as logfile:
        writer = csv.writer(logfile)
        if logfile.tell() == 0:
            writer.writerow(["Timestamp", "Reg", "Issue", "Source", "Response"])
        writer.writerow([
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            reg,
            issue,
            source,
            response_text.strip().replace("\n", " ")
        ])

def view_previous_queries():
    print("\n📂 OBDly Query Log Viewer")
    if not os.path.exists("query_log.csv"):
        print("⚠️ No queries have been logged yet.")
        return

    with open("query_log.csv", mode='r', encoding='utf-8') as logfile:
        reader = list(csv.DictReader(logfile))
        if not reader:
            print("⚠️ Log file is empty.")
            return

        print(f"\n🔍 What do you want to search?")
        print("1. Show all")
        print("2. Filter by reg")
        print("3. Search by keyword in issue")
        print("4. Show only AI or CSV results")
        choice = input("Enter option number: ")

        if choice == "1":
            results = reader
        elif choice == "2":
            reg = input("Enter reg plate (e.g. YH13ABC): ").lower()
            results = [row for row in reader if row["Reg"].lower() == reg]
        elif choice == "3":
            keyword = input("Enter keyword (e.g. brake): ").lower()
            results = [row for row in reader if keyword in row["Issue"].lower()]
        elif choice == "4":
            source = input("Type 'AI' or 'CSV': ").upper()
            results = [row for row in reader if row["Source"].upper() == source]
        else:
            print("❌ Invalid option.")
            return

        if not results:
            print("😕 No matching results found.")
        else:
            print(f"\n📋 Found {len(results)} matching record(s):\n")
            for row in results:
                print(f"[{row['Timestamp']}] {row['Reg']} — {row['Issue']}")
                print(f"Source: {row['Source']}")
                print(f"Response: {row['Response'][:200]}...\n")

# MAIN PROGRAM
csv_file_path = "obdly_fault_data.csv"
faults = load_fault_data(csv_file_path)

try:
    view_logs = input("📑 Do you want to view previous queries? (y/n): ")
    if view_logs.lower() == "y":
        view_previous_queries()

    mode = input("🔧 Type 1 to search by UK registration plate, or 2 to describe your issue: ")

    reg = ""
    issue = ""
    user_input = ""

    if mode == "1":
        reg = input("Enter your UK reg plate (e.g. YH13ABC): ")
        car = get_car_info_from_reg(reg)

        if car:
            print(f"✅ Found: {car['make'].title()} {car['model'].title()} {car['year']}")
            issue = input("Describe the problem you're having: ")
            user_input = f"{car['make']} {car['model']} {car['year']} {issue}"
        else:
            print("⚠️ Couldn't find that car. Try option 2.")
            issue = input("Please describe your car problem: ")
            user_input = issue
    else:
        issue = input("Please describe your car problem: ")
        user_input = issue

    csv_match = find_fix_from_csv(user_input, faults)
    if csv_match:
        print("\n✅ Found in database:\n")
        print(csv_match)
        log_query(reg or "N/A", issue or "N/A", "CSV", csv_match)
    else:
        print("\n🤖 No match in database. Here's what OBDly AI says:\n")
        ai_reply = ask_obdly_ai(user_input)
        print(ai_reply)
        log_query(reg or "N/A", issue or "N/A", "AI", ai_reply)

except Exception as e:
    print(f"❌ Unexpected error: {e}")
