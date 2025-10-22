# test_mot_matrix.py
import os, sys, requests, json

CLIENT_ID = os.environ.get("MOT_CLIENT_ID")
CLIENT_SECRET = os.environ.get("MOT_CLIENT_SECRET")
TOKEN_URL = os.environ.get("MOT_TOKEN_URL")
SCOPE_URL = os.environ.get(
    "MOT_SCOPE_URL")  # usually https://tapi.dvsa.gov.uk/.default
API_KEY = os.environ.get("MOT_API_KEY")
REG = os.environ.get("MOT_TEST_REG", "YA12XLL").upper()

print("\n=== DVSA MOT MATRIX TEST ===")
print("Secrets present:", [
    k for k in [
        "MOT_CLIENT_ID", "MOT_CLIENT_SECRET", "MOT_TOKEN_URL", "MOT_SCOPE_URL",
        "MOT_API_KEY"
    ] if os.environ.get(k)
])

# 1) Get bearer token (for tapi host)
print("\n[1] Requesting OAuth token …")
token = None
try:
    t = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "scope": SCOPE_URL,
        },
        timeout=15,
    )
    print("Token status:", t.status_code)
    if t.status_code == 200:
        token = t.json().get("access_token")
        print("Token ok:", bool(token))
    else:
        print(t.text[:600])
except Exception as e:
    print("Token error:", e)


def try_call(title, url, headers, params):
    print(f"\n[TEST] {title}")
    print(
        "GET", url, params, "HEADERS:", {
            k: headers[k]
            for k in headers if k.lower() in [
                "accept", "x-api-key", "ocp-apim-subscription-key",
                "authorization"
            ]
        })
    try:
        r = requests.get(url, headers=headers, params=params, timeout=15)
        print("Status:", r.status_code)
        try:
            print("JSON:", json.dumps(r.json(), indent=2)[:1000])
        except Exception:
            print("Text:", r.text[:1000])
    except Exception as e:
        print("Request error:", e)


# 2) Legacy beta host (usually API key only)
beta_url = "https://beta.check-mot.service.gov.uk/trade/vehicles/mot-tests"
try_call(
    "beta host + x-api-key only",
    beta_url,
    {
        "x-api-key": API_KEY,
        "Accept": "application/json"
    },
    {"registration": REG},
)
# sometimes needs versioned accept:
try_call(
    "beta host + x-api-key + versioned Accept",
    beta_url,
    {
        "x-api-key": API_KEY,
        "Accept": "application/json+v10"
    },
    {"registration": REG},
)

# 3) New TAPI host (Bearer; some products ALSO require subscription key)
tapi_url = "https://tapi.dvsa.gov.uk/mot-history/v1/vehicles/mot-tests"
if token:
    try_call(
        "tapi host + Bearer only",
        tapi_url,
        {
            "Authorization": f"Bearer {token}",
            "Accept": "application/json"
        },
        {"registration": REG},
    )
    try_call(
        "tapi host + Bearer + x-api-key",
        tapi_url,
        {
            "Authorization": f"Bearer {token}",
            "x-api-key": API_KEY,
            "Accept": "application/json"
        },
        {"registration": REG},
    )
    try_call(
        "tapi host + Bearer + Ocp-Apim-Subscription-Key",
        tapi_url,
        {
            "Authorization": f"Bearer {token}",
            "Ocp-Apim-Subscription-Key": API_KEY,
            "Accept": "application/json"
        },
        {"registration": REG},
    )
else:
    print("\n(tapi tests skipped — no token)")
