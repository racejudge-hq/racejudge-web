"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface PredictionResult {
  predicted_class: string;
  confidence: number;
  proba: Record<string, number>;
  model_version: string;
  disclaimer: string;
}

interface PrecedentResult {
  incident_id: string;
  title: string;
  season: number;
  penalty_type: string | null;
  reasoning_snippet: string;
  similarity_score: number;
}

const PENALTY_CLASSES = ["NFA", "REP", "5s", "10s", "DT", "GRID", "DSQ"];

const PENALTY_BAR_COLORS: Record<string, string> = {
  NFA:  "bg-gray-600",
  REP:  "bg-yellow-600",
  "5s": "bg-orange-500",
  "10s":"bg-orange-600",
  DT:   "bg-red-500",
  GRID: "bg-red-600",
  DSQ:  "bg-red-700",
};

const PENALTY_TEXT_COLORS: Record<string, string> = {
  NFA:  "text-gray-600 dark:text-gray-400",
  REP:  "text-yellow-400",
  "5s": "text-orange-400",
  "10s":"text-orange-500",
  DT:   "text-red-400",
  GRID: "text-red-500",
  DSQ:  "text-red-600",
};

const INFRACTION_OPTIONS = [
  "causing_a_collision",
  "track_limits",
  "unsafe_release",
  "pit_lane_speeding",
  "impeding",
  "blue_flag_violation",
  "dangerous_driving",
  "overtaking_under_safety_car",
  "false_start",
  "parc_ferme_violation",
];

const SESSION_OPTIONS = ["Race", "Sprint", "Qualifying", "Practice"];

function ProbabilityBar({ label, prob, predicted }: { label: string; prob: number; predicted: boolean }) {
  const pct = Math.round(prob * 100);
  const barColor = predicted ? (PENALTY_BAR_COLORS[label] ?? "bg-gray-500") : "bg-gray-700";
  return (
    <div className="flex items-center gap-3">
      <span className={`text-xs font-mono w-8 shrink-0 ${predicted ? "text-gray-900 dark:text-white font-bold" : "text-gray-500"}`}>
        {label}
      </span>
      <div className="flex-1 h-2 bg-gray-50 dark:bg-gray-900 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all duration-500 ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className={`text-xs font-mono w-10 text-right ${predicted ? "text-gray-900 dark:text-white" : "text-gray-400 dark:text-gray-600"}`}>
        {pct}%
      </span>
    </div>
  );
}

const DEFAULT_FORM = {
  infraction_type: "",
  session_type: "Race",
  lap_number: "",
  total_laps: "57",
  article_cited: "",
  speed_diff_kph: "",
  braking_point_delta_m: "",
  overlap_s: "",
  drs_deployed: false,
  position_change: "",
  safety_car_out: false,
  vsc_out: false,
  weather: "",
  penalty_points_ytd: "",
  repeat_infraction: false,
  season: "2025",
  incident_description: "",
};

export default function PredictPage() {
  const [form, setForm] = useState(DEFAULT_FORM);
  const [prediction, setPrediction] = useState<PredictionResult | null>(null);
  const [precedents, setPrecedents] = useState<PrecedentResult[]>([]);
  const [explanation, setExplanation] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const setField = (k: string, v: string | boolean) =>
    setForm((prev) => ({ ...prev, [k]: v }));

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setPrediction(null);
    setPrecedents([]);
    setExplanation("");

    startTransition(async () => {
      try {
        const predictBody = {
          infraction_type:       form.infraction_type || null,
          session_type:          form.session_type || null,
          lap_number:            form.lap_number ? Number(form.lap_number) : null,
          total_laps:            form.total_laps ? Number(form.total_laps) : null,
          article_cited:         form.article_cited || null,
          speed_diff_kph:        form.speed_diff_kph ? Number(form.speed_diff_kph) : 0,
          braking_point_delta_m: form.braking_point_delta_m ? Number(form.braking_point_delta_m) : 0,
          overlap_s:             form.overlap_s ? Number(form.overlap_s) : 0,
          drs_deployed:          form.drs_deployed,
          position_change:       form.position_change ? Number(form.position_change) : 0,
          safety_car_out:        form.safety_car_out,
          vsc_out:               form.vsc_out,
          weather:               form.weather || null,
          penalty_points_ytd:    form.penalty_points_ytd ? Number(form.penalty_points_ytd) : 0,
          repeat_infraction:     form.repeat_infraction,
          season:                form.season ? Number(form.season) : null,
        };

        const hasDescription = form.incident_description.trim().length >= 3;
        const precedentBody = hasDescription
          ? { query: form.incident_description.trim(), limit: 3 }
          : null;

        const [predictRes, precRes] = await Promise.all([
          fetch(`${API_BASE}/v1/predict`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(predictBody),
          }),
          precedentBody
            ? fetch(`${API_BASE}/v1/precedents/search`, {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify(precedentBody),
              })
            : Promise.resolve(null),
        ]);

        if (!predictRes.ok) {
          const data = await predictRes.json().catch(() => ({}));
          throw new Error(data.detail ?? `API error ${predictRes.status}`);
        }

        const predData: PredictionResult = await predictRes.json();
        setPrediction(predData);

        let topPrecedents: PrecedentResult[] = [];
        if (precRes?.ok) {
          const precData = await precRes.json();
          topPrecedents = (precData.results ?? []).slice(0, 3);
          setPrecedents(topPrecedents);
        }

        // RAG explanation — fire-and-forget, non-blocking
        if (hasDescription) {
          fetch(`${API_BASE}/v1/predict/explain`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              incident_description: form.incident_description.trim(),
              predicted_class:      predData.predicted_class,
              confidence:           predData.confidence,
              precedents:           topPrecedents,
            }),
          })
            .then((r) => (r.ok ? r.json() : null))
            .then((d) => { if (d?.explanation) setExplanation(d.explanation); })
            .catch(() => {});
        }
      } catch (err) {
        setError(err instanceof Error ? err.message : "Prediction failed");
      }
    });
  };

  return (
    <main className="max-w-3xl mx-auto px-4 py-10 space-y-8">
      <Link href="/" className="text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white">
        ← Home
      </Link>

      <header className="space-y-1">
        <h1 className="text-2xl font-bold">
          RACE<span className="rj-brand-red">JUDGE</span>{" "}
          <span className="font-normal text-gray-600 dark:text-gray-400">Predictor</span>
        </h1>
        <p className="text-sm text-gray-500">
          XGBoost + LLM ensemble — 7-class penalty prediction
        </p>
      </header>

      <form onSubmit={handleSubmit} className="space-y-5">
        {/* Free-text description */}
        <div className="space-y-1.5">
          <label className="text-xs text-gray-500 uppercase tracking-wider">
            Incident description <span className="normal-case text-gray-500 dark:text-gray-700">(improves precedent matching)</span>
          </label>
          <textarea
            rows={2}
            value={form.incident_description}
            onChange={(e) => setField("incident_description", e.target.value)}
            placeholder="e.g. VER overtook HAM at Turn 1 by going outside track limits, gaining significant advantage…"
            className="w-full px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded text-sm focus:outline-none focus:border-gray-300 dark:focus:border-gray-600 resize-none"
          />
        </div>

        {/* Grid of structured fields */}
        <div className="grid grid-cols-2 gap-3">
          <div className="space-y-1">
            <label htmlFor="infraction_type" className="text-xs text-gray-400 dark:text-gray-600">Infraction type</label>
            <select
              id="infraction_type"
              aria-label="Infraction type"
              value={form.infraction_type}
              onChange={(e) => setField("infraction_type", e.target.value)}
              className="w-full px-2 py-1.5 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded text-xs"
            >
              <option value="">— select —</option>
              {INFRACTION_OPTIONS.map((o) => (
                <option key={o} value={o}>{o.replace(/_/g, " ")}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label htmlFor="session_type" className="text-xs text-gray-400 dark:text-gray-600">Session</label>
            <select
              id="session_type"
              aria-label="Session type"
              value={form.session_type}
              onChange={(e) => setField("session_type", e.target.value)}
              className="w-full px-2 py-1.5 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded text-xs"
            >
              {SESSION_OPTIONS.map((o) => (
                <option key={o} value={o}>{o}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-xs text-gray-400 dark:text-gray-600">Lap number</label>
            <input
              type="number" min={1} max={80}
              value={form.lap_number}
              onChange={(e) => setField("lap_number", e.target.value)}
              placeholder="e.g. 3"
              className="w-full px-2 py-1.5 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded text-xs"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="season" className="text-xs text-gray-400 dark:text-gray-600">Season</label>
            <select
              id="season"
              aria-label="Season"
              value={form.season}
              onChange={(e) => setField("season", e.target.value)}
              className="w-full px-2 py-1.5 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded text-xs"
            >
              {[2025,2024,2023,2022,2021,2020,2019,2018].map((y) => (
                <option key={y} value={y}>{y}</option>
              ))}
            </select>
          </div>

          <div className="space-y-1">
            <label className="text-xs text-gray-400 dark:text-gray-600">Speed delta (km/h)</label>
            <input
              type="number" step="0.1"
              value={form.speed_diff_kph}
              onChange={(e) => setField("speed_diff_kph", e.target.value)}
              placeholder="0.0"
              className="w-full px-2 py-1.5 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded text-xs"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs text-gray-400 dark:text-gray-600">Penalty points YTD</label>
            <input
              type="number" min={0} max={12}
              value={form.penalty_points_ytd}
              onChange={(e) => setField("penalty_points_ytd", e.target.value)}
              placeholder="0"
              className="w-full px-2 py-1.5 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded text-xs"
            />
          </div>

          <div className="space-y-1">
            <label className="text-xs text-gray-400 dark:text-gray-600">Article cited</label>
            <input
              value={form.article_cited}
              onChange={(e) => setField("article_cited", e.target.value)}
              placeholder="e.g. 38.1"
              className="w-full px-2 py-1.5 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded text-xs"
            />
          </div>

          <div className="space-y-1">
            <label htmlFor="weather" className="text-xs text-gray-400 dark:text-gray-600">Weather</label>
            <select
              id="weather"
              aria-label="Weather condition"
              value={form.weather}
              onChange={(e) => setField("weather", e.target.value)}
              className="w-full px-2 py-1.5 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded text-xs"
            >
              <option value="">Unknown</option>
              <option value="dry">Dry</option>
              <option value="wet">Wet</option>
              <option value="mixed">Mixed</option>
            </select>
          </div>
        </div>

        {/* Boolean toggles */}
        <div className="flex flex-wrap gap-5 text-xs text-gray-500">
          {[
            { key: "safety_car_out",    label: "Safety car out" },
            { key: "vsc_out",           label: "VSC out" },
            { key: "drs_deployed",      label: "DRS deployed" },
            { key: "repeat_infraction", label: "Repeat infraction" },
          ].map(({ key, label }) => (
            <label key={key} className="flex items-center gap-1.5 cursor-pointer select-none">
              <input
                type="checkbox"
                checked={form[key as keyof typeof form] as boolean}
                onChange={(e) => setField(key, e.target.checked)}
                className="accent-red-600"
              />
              {label}
            </label>
          ))}
        </div>

        <button
          type="submit"
          disabled={isPending}
          className="w-full py-2.5 bg-white text-black rounded font-medium text-sm hover:bg-gray-200 disabled:opacity-40 transition-colors"
        >
          {isPending ? "Predicting…" : "Predict Penalty"}
        </button>
      </form>

      {error && (
        <div className="border border-red-900 rounded p-4 text-sm text-red-400">
          {error.includes("503") || error.includes("ENABLE_PREDICTIONS")
            ? "Prediction model not yet enabled — model training required before predictions are available."
            : error}
        </div>
      )}

      {prediction && (
        <section className="space-y-6 border-t border-gray-200 dark:border-gray-800 pt-6">
          {/* Headline result */}
          <div className="flex items-end gap-6">
            <div>
              <div className="text-xs text-gray-400 dark:text-gray-600 mb-1">Predicted outcome</div>
              <div className={`text-5xl font-mono font-bold ${PENALTY_TEXT_COLORS[prediction.predicted_class] ?? "text-gray-900 dark:text-white"}`}>
                {prediction.predicted_class}
              </div>
            </div>
            <div>
              <div className="text-xs text-gray-400 dark:text-gray-600 mb-1">Confidence</div>
              <div className="text-3xl font-bold">
                {Math.round(prediction.confidence * 100)}%
              </div>
            </div>
          </div>

          {/* Probability bars */}
          <div className="space-y-2.5">
            <p className="text-xs text-gray-400 dark:text-gray-600 uppercase tracking-wider">
              Full distribution
            </p>
            {PENALTY_CLASSES.map((cls) => (
              <ProbabilityBar
                key={cls}
                label={cls}
                prob={prediction.proba[cls] ?? 0}
                predicted={cls === prediction.predicted_class}
              />
            ))}
          </div>

          {/* RAG explanation */}
          {explanation && (
            <div className="border border-gray-200 dark:border-gray-800 rounded-lg p-4 space-y-1.5">
              <p className="text-xs text-gray-500 uppercase tracking-wider">
                Stewards reasoning
              </p>
              <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed">{explanation}</p>
            </div>
          )}

          {/* Precedents */}
          {precedents.length > 0 && (
            <div className="space-y-2">
              <p className="text-xs text-gray-500 uppercase tracking-wider">
                Similar precedents
              </p>
              {precedents.map((p) => (
                <div key={p.incident_id} className="border border-gray-200 dark:border-gray-800 rounded p-3 space-y-1">
                  <div className="flex items-center justify-between gap-2">
                    <span className="text-sm font-medium leading-snug line-clamp-1">{p.title}</span>
                    <div className="flex items-center gap-2 shrink-0">
                      <span className="text-xs text-gray-400 dark:text-gray-600">{p.season}</span>
                      {p.penalty_type && (
                        <span className="text-xs font-mono border border-gray-300 dark:border-gray-700 rounded px-1.5 py-0.5">
                          {p.penalty_type}
                        </span>
                      )}
                    </div>
                  </div>
                  {p.reasoning_snippet && (
                    <p className="text-xs text-gray-500 line-clamp-2">{p.reasoning_snippet}</p>
                  )}
                  <p className="text-xs text-gray-500 dark:text-gray-700">
                    similarity: {(p.similarity_score * 100).toFixed(1)}%
                  </p>
                </div>
              ))}
              <Link
                href={`/precedents`}
                className="text-xs text-gray-500 hover:text-gray-900 dark:hover:text-white transition-colors"
              >
                Search all precedents →
              </Link>
            </div>
          )}

          <p className="text-xs text-gray-500 dark:text-gray-700 border-t border-gray-100 dark:border-gray-900 pt-4">
            {prediction.disclaimer}
          </p>
        </section>
      )}
    </main>
  );
}
