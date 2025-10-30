# expert_tools.py
# Lightweight local expert helpers for OBDly
# - Small RAG over obdly_fault_data.csv + procedures.md (pure-Python TF-IDF)
# - OBD code decoder (obd_codes.json)
# - Triage/category classifier
# - Cost helper
# - “Next test” interactive stepper
#
# No third-party deps. Safe to import anywhere.

from __future__ import annotations

import os
import csv
import json
import math
import re
from dataclasses import dataclass
from typing import Dict, List, Tuple, Optional
from pathlib import Path
from collections import defaultdict, Counter


# -----------------------------
# Data structure for retrieved chunks
# -----------------------------
@dataclass
class DocChunk:
    text: str
    source: str  # filename or logical source
    meta: Dict[str, str]  # small dict (e.g., Make/Model/Fault, etc.)


# -----------------------------
# Globals (in-memory caches)
# -----------------------------
_INDEX_BUILT = False
_CHUNKS: List[DocChunk] = []
_VOCAB: Dict[str, int] = {}  # token -> column index
_DF: Counter = Counter()  # document frequency
_IDF: Dict[str, float] = {}
_TF: List[Counter] = []  # per-chunk term frequencies
_TFIDF_NORM: List[float] = []  # per-chunk vector L2 norms
_OBD_CODES_CACHE: Dict[str, Dict] | None = None

# -----------------------------
# Basic text utilities
# -----------------------------
_TOKEN_RE = re.compile(r"[a-z0-9]+")


def _norm_text(s: str) -> str:
    return (s or "").lower()


def _tokenize(s: str) -> List[str]:
    return _TOKEN_RE.findall(_norm_text(s))


def _split_into_chunks(text: str, *, max_tokens: int = 220) -> List[str]:
    """Split text into ~max_tokens chunks by whitespace tokens."""
    toks = _tokenize(text)
    if not toks:
        return []
    chunks = []
    for i in range(0, len(toks), max_tokens):
        part = " ".join(toks[i:i + max_tokens])
        if part.strip():
            chunks.append(part)
    return chunks


# -----------------------------
# Loaders
# -----------------------------
def _load_csv_chunks(path: Path) -> List[DocChunk]:
    out: List[DocChunk] = []
    if not path.exists():
        return out
    try:
        with path.open("r", encoding="utf-8") as f:
            rdr = csv.DictReader(f)
            for row in rdr:
                # Build a readable line using typical columns if present
                fields = []
                for key in ("Make", "Model", "Year", "Fault", "Symptom",
                            "Cause", "Suggested Fix", "Warning Light?"):
                    val = (row.get(key) or "").strip()
                    if val:
                        fields.append(f"{key}: {val}")
                blob = ". ".join(fields)
                if not blob:
                    continue
                for piece in _split_into_chunks(blob, max_tokens=200):
                    out.append(
                        DocChunk(text=piece,
                                 source=path.name,
                                 meta={
                                     "Make": (row.get("Make") or ""),
                                     "Model": (row.get("Model") or ""),
                                     "Year": (row.get("Year") or ""),
                                     "Fault": (row.get("Fault") or ""),
                                 }))
    except Exception:
        pass
    return out


def _load_md_chunks(path: Path) -> List[DocChunk]:
    out: List[DocChunk] = []
    if not path.exists():
        return out
    try:
        text = path.read_text(encoding="utf-8")
        # Split by headings as soft sections, then chunk
        sections = re.split(r"\n#{1,6}\s+", text)
        for sec in sections:
            sec = sec.strip()
            if not sec:
                continue
            for piece in _split_into_chunks(sec, max_tokens=220):
                out.append(DocChunk(text=piece, source=path.name, meta={}))
    except Exception:
        pass
    return out


# -----------------------------
# Index builder (pure-Python TF-IDF)
# -----------------------------
def _build_index_if_needed():
    global _INDEX_BUILT, _CHUNKS, _VOCAB, _DF, _IDF, _TF, _TFIDF_NORM
    if _INDEX_BUILT:
        return
    _CHUNKS.clear()
    _VOCAB.clear()
    _DF.clear()
    _IDF.clear()
    _TF.clear()
    _TFIDF_NORM.clear()

    # Load known sources if present
    csv_path = Path("obdly_fault_data.csv")
    md_path = Path("procedures.md")

    _CHUNKS.extend(_load_csv_chunks(csv_path))
    _CHUNKS.extend(_load_md_chunks(md_path))

    # If nothing loaded, keep an empty index (retriever will degrade gracefully)
    if not _CHUNKS:
        _INDEX_BUILT = True
        return

    # Build vocab & TF
    for chunk in _CHUNKS:
        tokens = _tokenize(chunk.text)
        tf = Counter(tokens)
        _TF.append(tf)
        for w in tf.keys():
            _DF[w] += 1

    # Vocabulary (column order is stable)
    for i, w in enumerate(_DF.keys()):
        _VOCAB[w] = i

    # IDF (log smoothing)
    N = max(1, len(_CHUNKS))
    for w, df in _DF.items():
        _IDF[w] = math.log((N + 1) / (df + 1)) + 1.0  # +1 smoothing

    # Precompute norms
    for tf in _TF:
        s = 0.0
        for w, cnt in tf.items():
            idf = _IDF.get(w, 0.0)
            val = (1.0 + math.log(1.0 + cnt)) * idf  # log tf
            s += val * val
        _TFIDF_NORM.append(math.sqrt(s))

    _INDEX_BUILT = True


# -----------------------------
# Retrieval
# -----------------------------
def _tfidf_query_vec(q: str) -> Dict[str, float]:
    qtf = Counter(_tokenize(q))
    vec: Dict[str, float] = {}
    for w, cnt in qtf.items():
        idf = _IDF.get(w, 0.0)
        if idf <= 0:
            continue
        vec[w] = (1.0 + math.log(1.0 + cnt)) * idf
    return vec


def _l2(vec: Dict[str, float]) -> float:
    return math.sqrt(sum(v * v for v in vec.values()))


def _cosine(qvec: Dict[str, float], qnorm: float, tf: Counter,
            dnorm: float) -> float:
    if qnorm == 0 or dnorm == 0:
        return 0.0
    dot = 0.0
    for w, qv in qvec.items():
        if w not in tf:
            continue
        idf = _IDF.get(w, 0.0)
        dv = (1.0 + math.log(1.0 + tf[w])) * idf
        dot += qv * dv
    return dot / (qnorm * dnorm)


def retrieve_context(query: str, k: int = 5) -> List[DocChunk]:
    """
    Return top-k DocChunk objects relevant to the query from local CSV/MD docs.
    """
    _build_index_if_needed()

    if not _CHUNKS:
        return []

    qvec = _tfidf_query_vec(query or "")
    qnorm = _l2(qvec)

    scores = []
    for i, tf in enumerate(_TF):
        s = _cosine(qvec, qnorm, tf, _TFIDF_NORM[i])
        if s > 0:
            scores.append((s, i))

    scores.sort(reverse=True, key=lambda x: x[0])
    top = [_CHUNKS[i] for (_, i) in scores[:max(1, k)]]
    return top


# -----------------------------
# OBD code decoder
# -----------------------------
def _load_obd_codes(path: str = "obd_codes.json") -> Dict[str, Dict]:
    global _OBD_CODES_CACHE
    if _OBD_CODES_CACHE is not None:
        return _OBD_CODES_CACHE
    try:
        p = Path(path)
        if not p.exists():
            _OBD_CODES_CACHE = {}
            return _OBD_CODES_CACHE
        _OBD_CODES_CACHE = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        _OBD_CODES_CACHE = {}
    return _OBD_CODES_CACHE


def decode_code(pcode: str, make: str = "", model: str = "") -> Dict:
    code = (pcode or "").strip().upper().replace(" ", "")
    if not code:
        return {}

    db = _load_obd_codes()
    out = {
        "code": code,
        "title": "",
        "desc": "",
        "common_causes": [],
        "tests": [],
        "severity": "unknown",
        "notes": []
    }

    if code in db:
        d = db[code] or {}
        out.update({
            "title": d.get("title", ""),
            "desc": d.get("desc", ""),
            "common_causes": d.get("common_causes", []),
            "tests": d.get("tests", []),
            "severity": d.get("severity", "unknown"),
        })
        if make or model:
            out["notes"].append(
                f"Tip: search {make} {model} {code} for TSBs or common fixes.")
        return out

    # Family (e.g., P03xx)
    family = code[:3] + "xx" if len(code) >= 3 else code
    if family in db:
        d = db[family] or {}
        out.update({
            "title": d.get("title", f"{code} (family guidance)"),
            "desc": d.get("desc", ""),
            "common_causes": d.get("common_causes", []),
            "tests": d.get("tests", []),
            "severity": d.get("severity", "unknown"),
        })
        out["notes"].append(f"No exact match. Using {family} family guidance.")
        return out

    system_map = {
        "P": "Powertrain",
        "B": "Body",
        "C": "Chassis",
        "U": "Network"
    }
    out["title"] = f"{system_map.get(code[:1], 'Unknown')} DTC {code}"
    out["desc"] = "Generic OBD-II fault code. Not found in local database."
    out["notes"].append(
        "Check freeze-frame data and manufacturer service info.")
    return out


# -----------------------------
# Triage & category
# -----------------------------
_SEVERITY_RULES = [
    (["brake", "no brakes", "spongy", "pedal to floor"], "stop_driving"),
    (["overheat", "overheating", "coolant temp high",
      "red temp"], "stop_driving"),
    (["low oil pressure", "red oil", "no oil"], "stop_driving"),
    (["airbag", "srs"], "drive_sparingly"),
    (["misfire", "limp mode", "won't rev", "won’t rev",
      "judder"], "drive_sparingly"),
    (["battery light", "12v", "charging issue",
      "alternator"], "drive_sparingly"),
]

_CATEGORY_RULES = [
    (["no start", "won't start", "won’t start", "crank",
      "starter"], "starting"),
    (["gear", "transmission", "clutch", "driveshaft", "axle",
      "diff"], "drivetrain"),
    (["brake", "abs", "esp", "pads", "discs", "caliper"], "braking"),
    ([
        "battery", "alternator", "starter", "fuse", "relay", "wiring", "short",
        "dtc", "p0", "p1"
    ], "electrical"),
    (["oil", "coolant", "overheat", "leak", "fuel", "diesel",
      "petrol"], "fluids"),
    (["ac", "a/c", "hvac", "heater", "blower", "climate"], "hvac"),
]


def _pick_severity(text: str) -> str:
    t = (text or "").lower()
    for keys, sev in _SEVERITY_RULES:
        if any(k in t for k in keys):
            return sev
    return "safe"


def _pick_category(text: str) -> str:
    t = (text or "").lower()
    for keys, cat in _CATEGORY_RULES:
        if any(k in t for k in keys):
            return cat
    return "electrical"


def triage_and_rank(symptoms_text: str,
                    vehicle: Optional[Dict] = None) -> List[Dict]:
    """
    Returns list of candidates:
      { "fault": str, "score": 0..1, "severity": str, "category": str, "source": str, "snippet": str }
    Uses retrieve_context() to add local matches.
    """
    query = symptoms_text or ""
    if vehicle:
        mk = (vehicle.get("make") or "").strip()
        md = (vehicle.get("model") or "").strip()
        yr = str(vehicle.get("yearOfManufacture") or "").strip()
        if mk or md or yr:
            query = f"{mk} {md} {yr} :: {query}"

    docs = retrieve_context(query, k=5) or []
    base_sev = _pick_severity(symptoms_text)
    base_cat = _pick_category(symptoms_text)

    out = []
    n = max(1, len(docs))
    for i, d in enumerate(docs):
        rank_bonus = (n - i) / n
        guess_fault = d.meta.get("Fault") or d.meta.get(
            "component") or "Relevant diagnostic"
        out.append({
            "fault": str(guess_fault),
            "score": round(0.55 + 0.45 * rank_bonus, 3),
            "severity": base_sev,
            "category": base_cat,
            "source": d.source,
            "snippet": d.text[:320]
        })

    if not out:
        out = [{
            "fault":
            "General diagnostic path",
            "score":
            0.6,
            "severity":
            base_sev,
            "category":
            base_cat,
            "source":
            "heuristic",
            "snippet":
            "No exact local matches. Follow general triage steps first."
        }]
    return out


# -----------------------------
# Cost helper
# -----------------------------
def estimate_cost(parts_range: Tuple[float, float] | None,
                  hours: float | Tuple[float, float] | None) -> str:
    """
    UK-style string: 'DIY £x–y / Garage £x–y'
    Labour rate via OBDLY_LABOUR_RATE env (default £70/hr).
    """
    labour_rate = float(os.environ.get("OBDLY_LABOUR_RATE", "70"))

    # Parts
    if isinstance(parts_range, (list, tuple)) and len(parts_range) == 2:
        pmin, pmax = float(parts_range[0]), float(parts_range[1])
    elif isinstance(parts_range, (int, float)):
        pmin = pmax = float(parts_range)
    else:
        pmin = pmax = 0.0

    # Hours
    if isinstance(hours, (list, tuple)) and len(hours) == 2:
        hmin, hmax = float(hours[0]), float(hours[1])
    elif isinstance(hours, (int, float)):
        hmin = hmax = float(hours)
    else:
        hmin = hmax = 0.0

    def _gbp(v: float) -> str:
        return f"£{int(round(max(0.0, v), 0))}"

    diy_min, diy_max = max(0.0, pmin), max(0.0, pmax, pmin)
    gar_min = max(0.0, pmin + hmin * labour_rate)
    gar_max = max(0.0, pmax + hmax * labour_rate, gar_min)

    if diy_min == diy_max and gar_min == gar_max:
        return f"DIY {_gbp(diy_min)} / Garage {_gbp(gar_min)}"
    return f"DIY {_gbp(diy_min)}–{_gbp(diy_max)} / Garage {_gbp(gar_min)}–{_gbp(gar_max)}"


# -----------------------------
# “Next test” stepper
# -----------------------------
_DEFAULT_FLOWS: Dict[str, List[str]] = {
    "starting": [
        "Check battery voltage at rest (≥12.4V). Is it ≥12.4V?",
        "Does the starter crank strongly (not just a click)?",
        "Scan for DTCs. Any P0335/P0340 crank/cam sensor or P03xx misfire?",
        "Fuel pressure at key-on within spec? (gauge or PID)"
    ],
    "braking": [
        "Is brake fluid between MIN–MAX?",
        "Any visible leaks at calipers/lines/master?",
        "With engine running, does the pedal sink slowly under steady pressure?",
        "ABS light on? Pull codes from ABS module."
    ],
    "fluids": [
        "Any visible leaks after overnight parking?",
        "Is coolant at the 'COLD' mark on expansion tank?",
        "Oil level between MIN–MAX on dipstick?",
        "Any white/blue smoke from exhaust?"
    ],
    "electrical": [
        "Battery voltage at rest (≥12.4V). Is it ≥12.4V?",
        "Alternator output at idle (13.8–14.6V). In range?",
        "Any blown fuses for the affected circuit?",
        "Wiggle-test the harness. Does the symptom change?"
    ],
    "drivetrain": [
        "Any gearbox warning lights or DTCs?",
        "Fluid level/condition OK (not burnt/black)?",
        "Symptom change with engine load vs road speed?",
        "CV joints/propshaft play or noises on full lock?"
    ],
    "hvac": [
        "Does blower run on all speeds?", "A/C clutch engages with A/C ON?",
        "Cabin pollen filter clean and seated?",
        "Any DTCs in HVAC/Body module?"
    ],
    "generic": [
        "Scan all modules for DTCs + freeze-frame.",
        "Check fuses/relays related to the circuit.",
        "Visual inspection: damage/loose connectors?",
        "Reproduce symptom in a controlled test."
    ]
}


def _build_flow(category: str, seed_tests: Optional[List[str]]) -> List[str]:
    if seed_tests:
        base = seed_tests[:]
    else:
        base = _DEFAULT_FLOWS.get(category, _DEFAULT_FLOWS["generic"])[:]
    return base[:4]  # keep concise


def next_action(plan_state: Optional[Dict],
                *,
                category_hint: Optional[str] = None,
                seed_tests: Optional[List[str]] = None) -> Tuple[str, Dict]:
    """
    Returns (question_text, new_state).
    plan_state:
      {"category": str, "steps": [str], "answers": [bool|None], "i": int}
    """
    state = plan_state or {}
    category = state.get("category") or (category_hint or "generic")
    steps = state.get("steps")
    answers = state.get("answers")

    if not steps:
        steps = _build_flow(category, seed_tests)
        answers = [None] * len(steps)
        i = 0
    else:
        i = int(state.get("i", 0))

    if i >= len(steps):
        return (
            "That completes this test path. We can re-triage with your results or try another subsystem.",
            {
                "category": category,
                "steps": steps,
                "answers": answers,
                "i": i
            })

    question = steps[i]
    new_state = {
        "category": category,
        "steps": steps,
        "answers": answers,
        "i": i
    }
    return (question, new_state)


def apply_step_answer(plan_state: Dict, answer_yes: bool) -> Dict:
    if not plan_state:
        return {"i": 0, "steps": [], "answers": []}
    i = int(plan_state.get("i", 0))
    steps = plan_state.get("steps", [])
    answers = plan_state.get("answers", [])
    if 0 <= i < len(steps):
        answers[i] = bool(answer_yes)
    plan_state["answers"] = answers
    plan_state["i"] = i + 1
    return plan_state


# -----------------------------
# Quick self-test (optional)
# -----------------------------
if __name__ == "__main__":
    # Smoke test retrieval
    print("Building index...")
    _build_index_if_needed()
    print(f"Chunks loaded: {len(_CHUNKS)}")
    res = retrieve_context("Volkswagen Golf misfire at idle", k=3)
    for r in res:
        print(">", r.source, "|", r.meta.get("Fault", ""), "|", r.text[:80],
              "...")

    # Triage
    tri = triage_and_rank("engine overheating at idle, coolant loss")
    print("Triage:", tri[:2])

    # Cost
    print("Cost:", estimate_cost((30, 120), (1.2, 2.0)))

    # Stepper
    q, stt = next_action(None, category_hint="starting")
    print("Step 1:", q)
    stt = apply_step_answer(stt, True)
    q2, stt = next_action(stt)
    print("Step 2:", q2)

    # Decoder
    print("Decode P0301:", decode_code("P0301", "Ford", "Focus"))
