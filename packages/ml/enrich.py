"""
Enrich decision/incident training records with the real multimodal signals
backfilled in Phase 3 (weather, telemetry, team-radio, race-control).

Joins each record to its DB incident by doc_id and attaches:
  - openf1.weather_data  : real rainfall + air/track temp, humidity, wind
  - openf1.laps          : real tyre compound for the involved driver
  - telemetry_features   : top speed + tyre life (FastF1 lap_features)
  - radio_features       : mean sentiment / urgency of the driver's incident radio
  - rc_features          : race-control message count + flag presence

All real data — pre-2023 incidents (no OpenF1 coverage) simply get no extra
signal and fall back to the existing defaults.
"""
from __future__ import annotations

import os
from typing import Any

import psycopg2


def enrich_with_db(records: list[dict[str, Any]]) -> list[dict[str, Any]]:
    doc_ids = [r["doc_id"] for r in records if r.get("doc_id")]
    if not doc_ids:
        return records

    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    cur = conn.cursor()

    # One incident per decision (prefer the one carrying a session_key).
    cur.execute(
        """SELECT doc_id, incident_id, session_key, lap, drivers, weather_context
           FROM incidents WHERE doc_id = ANY(%s)""",
        (doc_ids,),
    )
    inc_by_doc: dict[str, dict] = {}
    for doc_id, iid, sk, lap, drivers, wctx in cur.fetchall():
        cur_inc = inc_by_doc.get(doc_id)
        if cur_inc is None or (sk is not None and cur_inc["session_key"] is None):
            num = None
            if drivers and isinstance(drivers, list) and drivers:
                num = drivers[0].get("number")
            inc_by_doc[doc_id] = {
                "incident_id": iid, "session_key": sk, "lap": lap,
                "driver_number": num, "weather": wctx,
            }

    incident_ids = [v["incident_id"] for v in inc_by_doc.values()]

    # Telemetry aggregates per (session_key, driver_number).
    tel: dict[tuple, dict] = {}
    session_keys = list({v["session_key"] for v in inc_by_doc.values() if v["session_key"]})
    if session_keys:
        cur.execute(
            """SELECT session_key, driver_number,
                      MAX(speed_st), MAX(tyre_life_laps),
                      MODE() WITHIN GROUP (ORDER BY compound)
               FROM lap_features
               WHERE session_key = ANY(%s) AND driver_number IS NOT NULL
               GROUP BY session_key, driver_number""",
            (session_keys,),
        )
        for sk, dn, max_st, max_tyre, comp in cur.fetchall():
            tel[(sk, dn)] = {
                "top_speed_kph": float(max_st or 0.0),
                "tyre_life": int(max_tyre or 0),
                "compound": comp,
            }

    # Radio sentiment/urgency per incident.
    radio: dict[str, dict] = {}
    if incident_ids:
        cur.execute(
            """SELECT incident_id, AVG(sentiment_score), AVG(urgency_score), COUNT(*)
               FROM team_radio_clips WHERE incident_id = ANY(%s) GROUP BY incident_id""",
            (incident_ids,),
        )
        for iid, s, u, n in cur.fetchall():
            radio[iid] = {"sentiment": float(s or 0.0), "urgency": float(u or 0.0), "n": int(n)}

    # Race-control signal per incident.
    rc: dict[str, dict] = {}
    if incident_ids:
        cur.execute(
            """SELECT incident_id, COUNT(*), BOOL_OR(flag IS NOT NULL AND flag <> '')
               FROM race_control_messages WHERE incident_id = ANY(%s) GROUP BY incident_id""",
            (incident_ids,),
        )
        for iid, n, f in cur.fetchall():
            rc[iid] = {"n": int(n), "has_flag": bool(f)}

    conn.close()

    enriched = []
    for r in records:
        doc_id = r.get("doc_id")
        info = inc_by_doc.get(doc_id) if doc_id else None
        r = dict(r)
        if info:
            w = info["weather"] or {}
            t = tel.get((info["session_key"], info["driver_number"]), {})
            rd = radio.get(info["incident_id"], {})
            rcd = rc.get(info["incident_id"], {})
            r["openf1"] = {
                "weather_data": {
                    "rainfall": bool(w.get("rainfall")),
                    "air_temp": w.get("air_temp"),
                    "track_temp": w.get("track_temp"),
                    "humidity": w.get("humidity"),
                    "wind_speed": w.get("wind_speed"),
                },
                "laps": [{"compound": t["compound"]}] if t.get("compound") else [],
            }
            r["telemetry_features"] = {
                "top_speed_kph": t.get("top_speed_kph", 0.0),
                "tyre_life": t.get("tyre_life", 0),
            }
            r["radio_features"] = {
                "sentiment": rd.get("sentiment", 0.0),
                "urgency": rd.get("urgency", 0.0),
                "n_clips": rd.get("n", 0),
            }
            r["rc_features"] = {
                "n_messages": rcd.get("n", 0),
                "has_flag": int(rcd.get("has_flag", False)),
            }
        enriched.append(r)
    return enriched
