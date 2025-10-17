# reddit_data_collector.py — Fix-focused Reddit collector for OBDly (PRAW + Append-to-DB)

from __future__ import annotations
import os, re, csv, time
from datetime import datetime, timedelta
from typing import List, Dict, Any, Tuple

import praw  # pip install praw
import streamlit as st

# ---------- Heuristics & dictionaries ----------

DEFAULT_SUBS = [
    "MechanicAdvice", "Cartalk", "AskMechanics", "Justrolledintotheshop",
    "autorepair", "Volkswagen", "GolfGTI", "Golf_R", "VAG", "tdi"
]

RESOLVED_FLAIRS = {"solved", "resolved", "fix", "fixed", "how to", "solution"}
RESOLVED_PHRASES = [
    "solved", "resolved", "fix", "fixed", "found the issue", "solution",
    "update:", "edit:", "turns out", "the cause was"
]

COMPONENT_KEYWORDS = {
    "engine": ["misfire", "knock", "idle", "stall", "timing", "cam", "crank"],
    "turbo": ["turbo", "boost", "wastegate", "actuator", "dv valve", "pcv"],
    "fuel": ["injector", "fuel pump", "rail", "pressure", "maf", "map"],
    "ignition": ["coil", "coilpack", "spark plug", "plug", "ignition"],
    "cooling": ["coolant", "thermostat", "radiator", "water pump", "overheat"],
    "brakes": ["brake", "pad", "disc", "caliper", "abs"],
    "suspension": ["suspension", "strut", "shock", "control arm", "bushing"],
    "electrical": ["electrical", "battery", "alternator", "wiring", "ground"],
    "transmission": ["gearbox", "transmission", "dsg", "clutch", "flywheel"],
    "exhaust": ["exhaust", "dpf", "cat", "lambda", "o2 sensor"],
    "hvac": ["heater", "ac", "a/c", "climate", "blower"],
    "body": ["door", "window", "lock", "trim", "leak"],
}

SYMPTOM_KEYWORDS = [
    "misfire", "rough idle", "won't start", "no start", "hard start",
    "overheat", "smoke", "noise", "whine", "clunk", "vibration", "hesitation",
    "stall", "warning light", "epc", "check engine", "cel", "leak",
    "loss of power"
]

MAKE_ALIASES = {
    "vw": "volkswagen",
    "merc": "mercedes",
    "mb": "mercedes",
    "land rover": "landrover",
    "vauxhall": "opel",
}


def _norm(s: str) -> str:
    s = (s or "").lower()
    for k, v in MAKE_ALIASES.items():
        s = s.replace(k, v)
    return s


def _component_label(text: str) -> str:
    t = _norm(text)
    for label, keys in COMPONENT_KEYWORDS.items():
        if any(k in t for k in keys): return label
    return ""


def _symptom_label(text: str) -> str:
    t = _norm(text)
    for s in SYMPTOM_KEYWORDS:
        if s in t: return s
    return ""


_YEAR_RE = re.compile(r"\b(20[0-4]\d|19[8-9]\d)\b")  # 1980–2049 window


def _extract_year(text: str) -> str:
    m = _YEAR_RE.search(text or "")
    return m.group(0) if m else ""


def _likely_resolved(title: str, body: str, flair: str) -> bool:
    if (flair or "").strip().lower() in RESOLVED_FLAIRS:
        return True
    txt = f"{title}\n{body}".lower()
    return any(p in txt for p in RESOLVED_PHRASES)


def _is_image_url(url: str) -> bool:
    u = (url or "").lower()
    return any(
        u.endswith(ext) for ext in (".jpg", ".jpeg", ".png", ".gif",
                                    ".webp")) or "i.redd.it" in u


def _collapse(s: str, limit: int = 600) -> str:
    s = (s or "").replace("\r", " ").replace("\n", " ").strip()
    s = re.sub(r"\s+", " ", s)
    return (s[:limit] + "…") if len(s) > limit else s


# ---------- Confidence scoring ----------


def score_confidence(r: Dict[str, Any]) -> int:
    """
    0–100 confidence that a row is a good, fix-oriented candidate to add to the main DB.
    Transparent heuristic:
      +40 if resolved (flair/phrases)
      + up to 30 for upvotes (scaled vs 50: min(30, upvotes*30/50))
      +10 if component detected
      +10 if symptom detected
      +5  if not an image-only style post
      +5  if fix_summary is reasonably detailed (>120 chars)
    """
    score = 0
    if r.get("is_resolved"): score += 40
    score += min(30, int((r.get("upvotes", 0) or 0) * 30 / 50))
    if r.get("component"): score += 10
    if r.get("symptom"): score += 10
    if not r.get("is_image"): score += 5
    if len((r.get("fix_summary") or "")) > 120: score += 5
    return max(0, min(100, score))


# ---------- Collector ----------


class RedditDataCollector:
    """
    Legal data collection from Reddit's mechanic communities
    Uses official Reddit API (PRAW) — compliant with ToS
    """

    def __init__(self):
        self.client_id = os.environ.get("REDDIT_CLIENT_ID")
        self.client_secret = os.environ.get("REDDIT_CLIENT_SECRET")
        self.user_agent = os.environ.get("REDDIT_USER_AGENT",
                                         "OBDly:v1.2 (by u/OB_twice)")

        if not all([self.client_id, self.client_secret]):
            st.warning(
                "⚠️ Reddit API credentials not configured. Add REDDIT_CLIENT_ID and REDDIT_CLIENT_SECRET."
            )
            self.reddit = None
            return

        try:
            self.reddit = praw.Reddit(
                client_id=self.client_id,
                client_secret=self.client_secret,
                user_agent=self.user_agent,
            )
            _ = self.reddit.read_only  # sanity check
            st.success("✅ Connected to Reddit API")
        except Exception as e:
            st.error(f"Reddit API connection failed: {e}")
            self.reddit = None

    def _fetch_for_sub(self, sub: str, make: str, model: str, days: int,
                       limit_each: int):
        """Fetch potentially fix-oriented posts from a subreddit."""
        query = f'{make} {model} (fix OR solved OR resolved OR "how to" OR repair)'
        after_ts = int((datetime.utcnow() - timedelta(days=days)).timestamp())
        out: List[Dict[str, Any]] = []

        for post in self.reddit.subreddit(sub).search(query,
                                                      sort="relevance",
                                                      time_filter="year",
                                                      limit=limit_each):
            try:
                created = int(getattr(post, "created_utc", time.time()))
                if created < after_ts:
                    continue

                title = post.title or ""
                body = getattr(post, "selftext", "") or ""
                flair = getattr(post, "link_flair_text", "") or ""
                url = getattr(post, "url", "") or ""
                permalink = getattr(post, "permalink", "") or ""

                full = f"{title}\n{body}"
                row = {
                    "make": make.lower(),
                    "model": model.lower(),
                    "year": _extract_year(full),
                    "component": _component_label(full),
                    "symptom": _symptom_label(full),
                    "fix_summary": _collapse(body or title, 320),
                    "subreddit": getattr(post, "subreddit", sub).__str__(),
                    "flair": flair,
                    "upvotes": int(getattr(post, "score", 0)),
                    "comments": int(getattr(post, "num_comments", 0)),
                    "url": url or f"https://www.reddit.com{permalink}",
                    "permalink": f"https://www.reddit.com{permalink}",
                    "created_utc": created,
                    "is_resolved": _likely_resolved(title, body, flair),
                    "is_image": _is_image_url(url),
                }
                row["confidence"] = score_confidence(row)
                out.append(row)
            except Exception:
                continue
        return out

    def collect(self, make: str, model: str, subs: List[str], days: int,
                limit_each: int) -> List[Dict[str, Any]]:
        if not self.reddit:
            st.error("Reddit API not initialized")
            return []
        rows: List[Dict[str, Any]] = []
        for s in subs:
            try:
                rows.extend(
                    self._fetch_for_sub(s, make, model, days, limit_each))
                time.sleep(0.6)  # rate friendly
            except Exception as e:
                st.warning(f"Error searching r/{s}: {e}")
        return rows


# ---------- Filtering / CSV ----------


def filter_rows(rows: List[Dict[str, Any]], min_upvotes: int,
                only_resolved: bool) -> List[Dict[str, Any]]:
    out, seen = [], set()
    for r in rows:
        if r["upvotes"] < min_upvotes:
            continue
        if only_resolved and not r["is_resolved"]:
            continue
        if r["is_image"] and len((r["fix_summary"] or "")) < 40:
            continue
        key = r["permalink"] or r["url"]
        if key in seen:
            continue
        seen.add(key)
        out.append(r)
    return out


def save_csv(rows: List[Dict[str, Any]], path: str):
    fields = [
        "make", "model", "year", "component", "symptom", "fix_summary",
        "subreddit", "flair", "upvotes", "comments", "url", "permalink",
        "created_utc", "is_resolved", "is_image", "confidence"
    ]
    with open(path, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, quoting=csv.QUOTE_MINIMAL)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in fields})


# ---------- Append to main OBDly DB ----------

DB_DEFAULT_HEADERS = [
    "Make", "Model", "Year", "Fault", "Suggested Fix", "Urgency",
    "Cost Estimate", "Difficulty", "Warning Light?", "Permalink", "Subreddit",
    "Upvotes"
]


def _read_db_headers(db_path: str) -> List[str]:
    if not os.path.exists(db_path):
        return DB_DEFAULT_HEADERS
    with open(db_path, "r", encoding="utf-8") as f:
        first = f.readline()
        if not first:
            return DB_DEFAULT_HEADERS
        headers = [h.strip() for h in first.strip().split(",")]
        return headers if headers else DB_DEFAULT_HEADERS


def _load_existing_keys(db_path: str) -> set:
    """
    Build a set of existing unique identifiers to avoid duplicates.
    We dedupe by Permalink if available, else (Make,Model,Year,Fault).
    """
    keys = set()
    if not os.path.exists(db_path):
        return keys
    try:
        with open(db_path, "r", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                p = (row.get("Permalink") or row.get("URL") or "").strip()
                if p:
                    keys.add(("permalink", p))
                else:
                    keys.add(
                        ("combo", (row.get("Make",
                                           "").lower(), row.get("Model",
                                                                "").lower(),
                                   row.get("Year", ""), row.get("Fault",
                                                                "").lower())))
    except Exception:
        pass
    return keys


def _map_row_to_db(r: Dict[str, Any]) -> Dict[str, Any]:
    """Map a Reddit row into your main DB schema."""
    make = (r["make"] or "").title()
    model = (r["model"] or "").title()
    year = r.get("year", "")
    # Fault line: component + symptom if both, else whichever exists, else a safe placeholder
    comp, sym = r.get("component", ""), r.get("symptom", "")
    if comp and sym:
        fault = f"{comp}: {sym}"
    else:
        fault = comp or sym or "community-reported issue"
    fix = r.get("fix_summary", "") or ""
    mapped = {
        "Make": make,
        "Model": model,
        "Year": year,
        "Fault": fault,
        "Suggested Fix": fix,
        "Urgency": "",
        "Cost Estimate": "",
        "Difficulty": "",
        "Warning Light?": "Yes" if "warning light" in sym else "",
        "Permalink": r.get("permalink", "") or r.get("url", ""),
        "Subreddit": r.get("subreddit", ""),
        "Upvotes": r.get("upvotes", 0),
    }
    return mapped


def append_candidates_to_db(candidates: List[Dict[str, Any]],
                            db_path: str) -> Tuple[int, int]:
    """
    Append mapped candidates to obdly_fault_data.csv, deduping by permalink or (make,model,year,fault).
    Returns (appended_count, skipped_as_duplicates)
    """
    headers = _read_db_headers(db_path)
    existing_keys = _load_existing_keys(db_path)

    # Ensure all headers exist in output
    # If DB has fewer columns, we will only write those keys that exist
    def trim_to_headers(d: Dict[str, Any]) -> Dict[str, Any]:
        return {h: d.get(h, "") for h in headers}

    appended, skipped = 0, 0
    mode = "a" if os.path.exists(db_path) and os.path.getsize(
        db_path) > 0 else "w"
    with open(db_path, mode, newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=headers)
        if mode == "w":
            w.writeheader()
        for r in candidates:
            mapped = _map_row_to_db(r)
            permalink = mapped.get("Permalink", "").strip()
            if permalink:
                key = ("permalink", permalink)
            else:
                key = ("combo",
                       (mapped["Make"].lower(), mapped["Model"].lower(),
                        mapped["Year"], mapped["Fault"].lower()))
            if key in existing_keys:
                skipped += 1
                continue
            w.writerow(trim_to_headers(mapped))
            existing_keys.add(key)
            appended += 1
    return appended, skipped


# ---------- Streamlit page ----------


def reddit_collector_page():
    st.markdown("## 🔍 Reddit Collector (Fix-focused)")
    st.caption(
        "Pulls likely *solution* threads and labels them for OBDly. Then optionally append high-confidence rows to your main DB."
    )

    collector = RedditDataCollector()
    if not collector.reddit:
        st.error("Configure Reddit API first.")
        st.markdown("""
**Setup**  
1) https://www.reddit.com/prefs/apps → create *script* app  
2) Add to Secrets: `REDDIT_CLIENT_ID`, `REDDIT_CLIENT_SECRET`  
3) (Optional) `REDDIT_USER_AGENT`
        """)
        return

    with st.expander("⚙️ Search settings", expanded=True):
        c1, c2, c3 = st.columns([1, 1, 1])
        with c1:
            make = st.text_input("Make", value="VW")
        with c2:
            model = st.text_input("Model", value="Golf R")
        with c3:
            year_hint = st.text_input("Year (optional)", value="")

        subs = st.multiselect("Subreddits",
                              options=DEFAULT_SUBS,
                              default=DEFAULT_SUBS)
        c4, c5, c6, c7 = st.columns([1, 1, 1, 1])
        with c4:
            days = st.number_input("Lookback days",
                                   min_value=7,
                                   max_value=365,
                                   value=180,
                                   step=7)
        with c5:
            min_upvotes = st.number_input("Min upvotes",
                                          min_value=0,
                                          max_value=2000,
                                          value=10,
                                          step=5)
        with c6:
            only_resolved = st.checkbox("Only resolved/solved", value=True)
        with c7:
            limit_each = st.slider("Max per subreddit",
                                   min_value=10,
                                   max_value=100,
                                   value=40,
                                   step=10)

        run = st.button("🔎 Search Reddit", use_container_width=True)

    if not run:
        return

    st.info(
        f"🔎 Searching Reddit for **{make} {model}** across {len(subs)} sub(s)…"
    )
    rows = collector.collect(make, model, subs, int(days), int(limit_each))

    # Year bias
    if year_hint:
        y = _extract_year(year_hint)
        if y:
            for r in rows:
                if not r["year"]:
                    r["year"] = y

    filtered = filter_rows(rows, int(min_upvotes), bool(only_resolved))
    if not filtered:
        st.warning(
            "No suitable posts found. Try widening the date range or lowering min upvotes."
        )
        return

    # Save a clean CSV of the filtered Reddit results
    out_path = "reddit_insights.csv"
    save_csv(filtered, out_path)
    st.success(f"✅ Saved {len(filtered)} rows to `{out_path}`")

    # Build preview table
    import pandas as pd
    preview = [{
        "Make": r["make"].title(),
        "Model": r["model"].upper(),
        "Year": r["year"],
        "Component": r["component"],
        "Symptom": r["symptom"],
        "Confidence": r.get("confidence", 0),
        "Up": r["upvotes"],
        "Com": r["comments"],
        "Sub": r["subreddit"],
        "Resolved": "Yes" if r["is_resolved"] else "No",
        "Link": r["permalink"],
    } for r in filtered]
    df = pd.DataFrame(preview).sort_values(
        by=["Confidence", "Up"], ascending=False).reset_index(drop=True)

    st.markdown("### 📊 Preview")
    st.dataframe(df.head(100))

    # ==== Append-to-DB controls ====
    st.markdown("---")
    st.markdown("### ➕ Append high-confidence rows to your main database")
    db_path = "obdly_fault_data.csv"

    default_threshold = 65
    threshold = st.slider("Minimum confidence to append", 40, 95,
                          default_threshold, 5)
    candidates = [r for r in filtered if r.get("confidence", 0) >= threshold]

    st.caption(
        f"{len(candidates)} candidate(s) meet the confidence threshold ≥ {threshold}."
    )
    if st.checkbox("Show candidates that will be appended", value=False):
        df2 = pd.DataFrame([{
            "Make":
            r["make"].title(),
            "Model":
            r["model"].upper(),
            "Year":
            r["year"],
            "Fault (derived)": (r.get("component") or "") +
            (": " + r.get("symptom") if r.get("symptom") else ""),
            "Fix summary":
            r.get("fix_summary", "")[:150],
            "Confidence":
            r.get("confidence", 0),
            "Subreddit":
            r.get("subreddit", ""),
            "Permalink":
            r.get("permalink", ""),
        } for r in candidates])
        st.dataframe(df2)

    if st.button(f"📥 Append {len(candidates)} row(s) to obdly_fault_data.csv",
                 use_container_width=True,
                 disabled=(len(candidates) == 0)):
        appended, skipped = append_candidates_to_db(candidates, db_path)
        st.success(f"✅ Appended {appended} new row(s) to `{db_path}`.")
        if skipped:
            st.info(
                f"ℹ️ Skipped {skipped} duplicate(s) based on permalink or (make, model, year, fault)."
            )
        st.balloons()

    # Download button for the raw Reddit insights
    st.download_button(label="⬇️ Download reddit_insights.csv",
                       data=open(out_path, "rb").read(),
                       file_name=out_path,
                       mime="text/csv",
                       use_container_width=True)


# Backwards compat export for router
def reddit_collector_page_wrapper():
    reddit_collector_page()
