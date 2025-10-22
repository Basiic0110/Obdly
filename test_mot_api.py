# test_mot_api.py
import os, sys, json, requests


def shout(msg):
    print(f"\n=== {msg} ===")


REQUIRED = {
    "MOT_CLIENT_ID": os.environ.get("MOT_CLIENT_ID"),
    "MOT_CLIENT_SECRET": os.environ.get("MOT_CLIENT_SECRET"),
    "MOT_TOKEN_URL": os.environ.get("MOT_TOKEN_URL"),
    "MOT_SCOPE_URL": os.environ.get(
        "MOT_SCOPE_URL"),  # usually https://tapi.dvsa.gov.uk/.default
    "MOT_API_KEY": os.environ.get("MOT_API_KEY"),
}
missing = [k for k, v in REQUIRED.items() if not v]
shout("STARTING MOT OAUTH TEST")
print("Python:", sys.version)
print("Secrets present:", ", ".join(k for k in REQUIRED if REQUIRED[k])
      or "NONE")

if missing:
    shout("MISSING SECRETS")
    for k in missing:
        print(f"- {k} is not set")
    sys.exit(1)

TOKEN_URL = REQUIRED["MOT_TOKEN_URL"]
SCOPE_URL = REQUIRED["MOT_SCOPE_URL"]
CLIENT_ID = REQUIRED["MOT_CLIENT_ID"]
CLIENT_SECRET = REQUIRED["MOT_CLIENT_SECRET"]
API_KEY = REQUIRED["MOT_API_KEY"]

TEST_REG = os.environ.get("MOT_TEST_REG", "YA12XLL").upper()

# 1) Get token
shout("REQUESTING OAUTH TOKEN")
print("POST", TOKEN_URL)
try:
    t = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": SCOPE_URL
        },
        timeout=15,
    )
    print("Token status:", t.status_code)
    print("Token raw:", t.text[:400])
except Exception as e:
    print("Token request error:", e)
    sys.exit(1)

if t.status_code != 200:
    print("❌ Token request failed.")
    sys.exit(1)

token_json = t.json()
access_token = token_json.get("access_token")
if not access_token:
    print("❌ No access_token in token response.")
    sys.exit(1)

print("✅ Got access token.")

# 2) Call MOT endpoint
MOT_URL = "https://beta.check-mot.service.gov.uk/trade/vehicles/mot-tests"
params = {"registration": TEST_REG}
headers = {
    "Authorization": f"Bearer {access_token}",
    "x-api-key": API_KEY,
    "Accept": "application/json",
}

shout("CALLING MOT API")
print("GET", MOT_URL, params)
try:
    r = requests.get(MOT_URL, params=params, headers=headers, timeout=15)
    print("MOT status:", r.status_code)
    try:
        js = r.json()
        print("JSON:", json.dumps(js, indent=2)[:1200])
    except Exception:
        print("Text:", r.text[:1200])
except Exception as e:
    print("MOT request error:", e)
    sys.exit(1)

if r.status_code == 200:
    shout("SUCCESS")
    print("✅ MOT API working. You should see make & model in the JSON above.")
elif r.status_code == 403:
    shout("FORBIDDEN (403)")
    print(
        "Likely API key or client credentials issue. Double-check the **API key** and OAuth values."
    )
elif r.status_code == 401:
    shout("UNAUTHORIZED (401)")
    print(
        "Access token invalid/expired. Confirm TOKEN_URL & SCOPE_URL exactly match DVSA email."
    )
else:
    shout("FAILED")
    print("Unexpected status. See payload above.")
