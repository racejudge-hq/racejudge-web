"""
Populate incidents.session_key by linking each 2023+ FIA decision to its OpenF1
session. Foundation for the race-control / radio / weather backfills.
(2019-2022 incidents are skipped — OpenF1 has no data before 2023.) Temp script.

Robust: caches OpenF1 lookups to disk, and opens a FRESH DB connection right
before writing (Neon closes connections idle during the long lookup loop).
"""
from __future__ import annotations
import json, os, re
from pathlib import Path
from dotenv import load_dotenv; load_dotenv(".env")
import psycopg2
from psycopg2.extras import execute_batch
from packages.pipeline.linkers.decision_linker import GP_TO_CIRCUIT
from packages.pipeline.linkers.openf1_client import OpenF1Client

CACHE = Path("data/linked/_sk_cache.json")
CACHE.parent.mkdir(parents=True, exist_ok=True)
cache: dict[str, int | None] = json.loads(CACHE.read_text()) if CACHE.exists() else {}
cli = OpenF1Client(delay=1.0)
DB = os.environ["DATABASE_URL"]


def circuit_of(gp: str) -> str | None:
    g = gp.lower()
    for k, v in GP_TO_CIRCUIT.items():
        if k in g or g in k:
            return v
    return None


def sessions_of(s: str) -> list[str] | None:
    s = s.lower().strip()
    if "reconnaissance" in s or s == "race":
        return ["Race"]
    if "sprint qualifying" in s or "sprint shootout" in s:
        return ["Sprint Qualifying", "Sprint Shootout"]
    if "sprint" in s:
        return ["Sprint"]
    if "qualifying" in s:
        return ["Qualifying"]
    m = re.search(r"practice\s*(\d)", s)
    if m:
        return [f"Practice {m.group(1)}"]
    return None


def lookup(year: int, circuit: str, cands: list[str]) -> int | None:
    key = f"{year}|{circuit}|{','.join(cands)}"
    if key in cache:
        return cache[key]
    res = None
    for sess in cands:
        try:
            r = cli.session_key_for_gp(year, circuit, sess)
            if r:
                res = r; break
        except Exception:
            pass
    cache[key] = res
    CACHE.write_text(json.dumps(cache))
    return res


# 1) fetch rows, then CLOSE the connection (no idle conn during lookups)
conn = psycopg2.connect(DB); cur = conn.cursor()
cur.execute("""SELECT i.incident_id, d.season, d.raw_text
               FROM incidents i JOIN decisions d ON i.doc_id=d.doc_id
               WHERE d.season >= 2023 AND length(d.raw_text) > 200""")
rows = cur.fetchall(); conn.close()
print(f"2023+ incidents to map: {len(rows)}", flush=True)

# 2) resolve (cached)
updates = []
no_gp = no_sess = no_circ = no_sk = 0
for iid, season, rt in rows:
    m = re.search(r"20\d\d\s+([A-Z][A-Za-z ]+?)\s+GRAND PRIX", rt)
    if not m: no_gp += 1; continue
    circ = circuit_of(m.group(1).strip())
    if not circ: no_circ += 1; continue
    sm = re.search(r"Session\s+([A-Za-z0-9 ]+)", rt)
    cands = sessions_of(sm.group(1)) if sm else None
    if not cands: no_sess += 1; continue
    sk = lookup(season, circ, cands)
    if not sk: no_sk += 1; continue
    updates.append((sk, iid))
Path("data/linked/_sk_updates.json").write_text(json.dumps(updates))
print(f"resolved {len(updates)} | no_gp={no_gp} no_circuit={no_circ} no_session={no_sess} no_openf1_match={no_sk}", flush=True)

# 3) FRESH connection right before writing
w = psycopg2.connect(DB); wc = w.cursor()
execute_batch(wc, "UPDATE incidents SET session_key=%s WHERE incident_id=%s", updates, page_size=200)
w.commit()
wc.execute("SELECT count(session_key), count(DISTINCT session_key) FROM incidents")
sk_n, sess_n = wc.fetchone()
print(f"DONE — {sk_n} incidents linked across {sess_n} distinct OpenF1 sessions", flush=True)
w.close()
