/**
 * RACEJUDGE k6 load test — Phase 8
 *
 * Usage:
 *   k6 run scripts/load_test.k6.js
 *   k6 run --env BASE_URL=https://api.racejudge.com scripts/load_test.k6.js
 *   k6 run --env API_KEY=rj_live_xxx scripts/load_test.k6.js
 *
 * Targets:
 *   p95 < 500ms for read endpoints
 *   p95 < 2000ms for RAG/prediction endpoints
 *   error rate < 1%
 */

import http from "k6/http";
import { check, sleep } from "k6";
import { Rate, Trend } from "k6/metrics";

const BASE_URL = __ENV.BASE_URL || "http://localhost:8000";
const API_KEY  = __ENV.API_KEY  || "";

// Custom metrics
const errorRate      = new Rate("error_rate");
const searchLatency  = new Trend("search_latency_ms",  true);
const predictLatency = new Trend("predict_latency_ms", true);

export const options = {
  stages: [
    { duration: "30s", target: 10  },  // ramp up
    { duration: "1m",  target: 50  },  // steady state
    { duration: "30s", target: 100 },  // peak
    { duration: "30s", target: 0   },  // ramp down
  ],
  thresholds: {
    // Overall p95 < 500ms; prediction endpoint allowed 2s
    http_req_duration:    ["p(95)<500"],
    search_latency_ms:    ["p(95)<500"],
    predict_latency_ms:   ["p(95)<2000"],
    error_rate:           ["rate<0.01"],
  },
};

const AUTH_HEADER = API_KEY
  ? { Authorization: `Bearer ${API_KEY}` }
  : {};

const SEARCH_QUERIES = [
  "unsafe pit lane entry",
  "track limits advantage",
  "collision in braking zone",
  "blue flag violation",
  "weaving under braking",
];

const PREDICT_PAYLOADS = [
  {
    infraction_category: "collision",
    driver_code:         "VER",
    season:              2024,
    session_type:        "race",
    is_repeat_offender:  false,
    circuit_id:          "monaco",
  },
  {
    infraction_category: "track_limits",
    driver_code:         "NOR",
    season:              2024,
    session_type:        "qualifying",
    is_repeat_offender:  false,
    circuit_id:          "silverstone",
  },
];

function randomItem(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

export default function () {
  const scenario = Math.random();

  if (scenario < 0.30) {
    // GET /health (baseline — should always be sub-10ms)
    const res = http.get(`${BASE_URL}/health`);
    const ok  = check(res, { "health 200": (r) => r.status === 200 });
    errorRate.add(!ok);

  } else if (scenario < 0.55) {
    // GET /v1/decisions (paginated list)
    const res = http.get(
      `${BASE_URL}/v1/decisions?limit=20&offset=0`,
      { headers: AUTH_HEADER },
    );
    const ok = check(res, {
      "decisions 200": (r) => r.status === 200,
      "decisions has items": (r) => {
        try { return Array.isArray(JSON.parse(r.body)); } catch { return false; }
      },
    });
    errorRate.add(!ok);

  } else if (scenario < 0.75) {
    // POST /v1/search (semantic search — uses HNSW index)
    const payload = JSON.stringify({
      query: randomItem(SEARCH_QUERIES),
      limit: 5,
    });
    const start = Date.now();
    const res   = http.post(
      `${BASE_URL}/v1/search`,
      payload,
      { headers: { ...AUTH_HEADER, "Content-Type": "application/json" } },
    );
    searchLatency.add(Date.now() - start);
    const ok = check(res, {
      "search 200": (r) => r.status === 200 || r.status === 422,
    });
    errorRate.add(res.status >= 500);
    void ok;

  } else if (scenario < 0.90) {
    // GET /v1/incidents/variance (Shannon entropy calc)
    const res = http.get(
      `${BASE_URL}/v1/incidents/variance?min_incidents=3`,
      { headers: AUTH_HEADER },
    );
    const ok = check(res, {
      "variance 200": (r) => r.status === 200 || r.status === 503,
    });
    errorRate.add(res.status >= 500);
    void ok;

  } else {
    // POST /v1/predict (ML prediction — most expensive)
    const payload = JSON.stringify(randomItem(PREDICT_PAYLOADS));
    const start   = Date.now();
    const res     = http.post(
      `${BASE_URL}/v1/predict`,
      payload,
      { headers: { ...AUTH_HEADER, "Content-Type": "application/json" } },
    );
    predictLatency.add(Date.now() - start);
    const ok = check(res, {
      "predict 200": (r) => r.status === 200 || r.status === 422 || r.status === 503,
    });
    errorRate.add(res.status >= 500);
    void ok;
  }

  sleep(0.5 + Math.random() * 0.5); // 500–1000ms think time
}

export function handleSummary(data) {
  return {
    stdout: JSON.stringify(
      {
        p50_ms:       data.metrics.http_req_duration?.values?.["p(50)"],
        p95_ms:       data.metrics.http_req_duration?.values?.["p(95)"],
        p99_ms:       data.metrics.http_req_duration?.values?.["p(99)"],
        error_rate:   data.metrics.error_rate?.values?.rate,
        vus_max:      data.metrics.vus_max?.values?.max,
        iterations:   data.metrics.iterations?.values?.count,
        search_p95:   data.metrics.search_latency_ms?.values?.["p(95)"],
        predict_p95:  data.metrics.predict_latency_ms?.values?.["p(95)"],
      },
      null,
      2,
    ),
  };
}
