"use client";

import Link from "next/link";
import { useState, useTransition } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface PrecedentResult {
  incident_id: string;
  doc_id: string;
  title: string;
  season: number;
  published_at: string | null;
  pdf_url: string | null;
  drivers: { code?: string; full_name?: string }[];
  infraction_category: string | null;
  penalty_type: string | null;
  penalty_seconds: number | null;
  penalty_points: number;
  article_cited: string[] | null;
  lap: number | null;
  corner: string | null;
  contact: boolean | null;
  reasoning_snippet: string;
  similarity_score: number;
}

interface SearchResponse {
  results: PrecedentResult[];
  total: number;
  mode: string;
  query: string;
}

// Ordered by severity. WARN/FINE/SG were added once the extractor could record
// them — see migration 0010; before that they were stored as NULL.
const PENALTY_COLORS: Record<string, string> = {
  NFA: "text-gray-500 border-gray-300 dark:border-gray-700",
  WARN: "text-yellow-400 border-yellow-900",
  REP: "text-yellow-500 border-yellow-800",
  FINE: "text-blue-400 border-blue-800",
  "5s": "text-orange-400 border-orange-800",
  "10s": "text-orange-500 border-orange-700",
  DT: "text-red-400 border-red-800",
  SG: "text-red-500 border-red-800",
  GRID: "text-red-500 border-red-700",
  DSQ: "text-red-600 border-red-600",
};

function PenaltyBadge({ type }: { type: string | null }) {
  if (!type) return null;
  const cls = PENALTY_COLORS[type] ?? "text-gray-600 dark:text-gray-400 border-gray-300 dark:border-gray-700";
  return (
    <span className={`text-xs font-mono px-2 py-0.5 border rounded ${cls}`}>
      {type}
    </span>
  );
}

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 bg-gray-100 dark:bg-gray-800 rounded-full overflow-hidden">
        <div
          className="h-full bg-red-600 rounded-full"
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-gray-400 dark:text-gray-600 font-mono">{(score * 100).toFixed(1)}%</span>
    </div>
  );
}

const QUICK_QUERIES = [
  "causing a collision at high speed",
  "unsafe release from pit lane",
  "track limits advantage gained",
  "impeding under yellow flags",
  "ignoring blue flags",
  "dangerous driving under safety car",
];

const PENALTY_TYPES = ["NFA", "WARN", "REP", "FINE", "5s", "10s", "DT", "SG", "GRID", "DSQ"];
const SEASONS = [2025, 2024, 2023, 2022, 2021, 2020, 2019, 2018];

export default function PrecedentsPage() {
  const [query, setQuery] = useState("");
  const [season, setSeason] = useState<string>("");
  const [penaltyType, setPenaltyType] = useState<string>("");
  const [driver, setDriver] = useState<string>("");
  const [results, setResults] = useState<PrecedentResult[] | null>(null);
  const [mode, setMode] = useState<string>("");
  const [error, setError] = useState<string | null>(null);
  const [isPending, startTransition] = useTransition();

  const search = (q?: string, s?: string, pt?: string, d?: string) => {
    const effectiveQuery = q ?? query;
    if (effectiveQuery.trim().length < 3) return;

    startTransition(async () => {
      setError(null);
      try {
        const res = await fetch(`${API_BASE}/v1/precedents/search`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            query: effectiveQuery.trim(),
            season: (s ?? season) ? Number(s ?? season) : null,
            penalty_type: (pt ?? penaltyType) || null,
            driver: (d ?? driver) || null,
            limit: 20,
          }),
        });
        if (!res.ok) throw new Error(`API error ${res.status}`);
        const data: SearchResponse = await res.json();
        setResults(data.results);
        setMode(data.mode);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Search failed");
        setResults([]);
      }
    });
  };

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    search();
  };

  return (
    <main className="max-w-4xl mx-auto px-4 py-10 space-y-6">
      <Link href="/" className="text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white">
        ← Home
      </Link>

      <header className="space-y-1">
        <h1 className="text-2xl font-bold">
          RACE<span className="rj-brand-red">JUDGE</span>{" "}
          <span className="font-normal text-gray-600 dark:text-gray-400">Precedents</span>
        </h1>
        <p className="text-sm text-gray-500">
          Hybrid semantic + BM25 search over 1,000+ stewards&apos; incidents
        </p>
      </header>

      {/* Search form */}
      <form onSubmit={handleSubmit} className="space-y-3">
        <div className="flex gap-2">
          <input
            autoFocus
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="e.g. driver pushed off track at high-speed corner on lap 1…"
            className="flex-1 px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded text-sm focus:outline-none focus:border-gray-400"
          />
          <button
            type="submit"
            disabled={isPending || query.trim().length < 3}
            className="px-5 py-2 bg-white text-black rounded text-sm font-medium hover:bg-gray-200 disabled:opacity-40"
          >
            {isPending ? "Searching…" : "Search"}
          </button>
        </div>

        {/* Filters */}
        <div className="flex flex-wrap gap-2">
          <select
            value={season}
            onChange={(e) => setSeason(e.target.value)}
            aria-label="Season"
            className="px-3 py-1.5 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded text-xs"
          >
            <option value="">All seasons</option>
            {SEASONS.map((y) => (
              <option key={y} value={y}>{y}</option>
            ))}
          </select>

          <select
            value={penaltyType}
            onChange={(e) => setPenaltyType(e.target.value)}
            aria-label="Penalty type"
            className="px-3 py-1.5 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded text-xs"
          >
            <option value="">All penalties</option>
            {PENALTY_TYPES.map((p) => (
              <option key={p} value={p}>{p}</option>
            ))}
          </select>

          <input
            value={driver}
            onChange={(e) => setDriver(e.target.value.toUpperCase())}
            placeholder="Driver code (VER)"
            maxLength={3}
            className="w-32 px-3 py-1.5 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded text-xs"
          />
        </div>
      </form>

      {/* Quick query chips */}
      {results === null && (
        <div className="space-y-2">
          <p className="text-xs text-gray-400 dark:text-gray-600 uppercase tracking-wider">Quick searches</p>
          <div className="flex flex-wrap gap-2">
            {QUICK_QUERIES.map((q) => (
              <button
                key={q}
                onClick={() => { setQuery(q); search(q); }}
                className="text-xs px-3 py-1.5 border border-gray-200 dark:border-gray-800 rounded hover:border-gray-300 dark:hover:border-gray-600 text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors text-left"
              >
                {q}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <p className="text-sm text-red-400 border border-red-900 rounded p-3">{error}</p>
      )}

      {/* Results */}
      {results !== null && (
        <div className="space-y-2">
          {results.length === 0 ? (
            <p className="text-gray-500 text-sm">No precedents found.</p>
          ) : (
            <>
              <div className="flex items-center justify-between text-xs text-gray-400 dark:text-gray-600">
                <span>{results.length} precedents</span>
                <span className="font-mono uppercase">{mode}</span>
              </div>

              {results.map((r) => {
                const driverCodes = r.drivers.map((d) => d.code || d.full_name || "").filter(Boolean);
                return (
                  <div
                    key={r.incident_id}
                    className="border border-gray-200 dark:border-gray-800 rounded-lg p-4 hover:border-gray-300 dark:hover:border-gray-700 transition-colors space-y-2"
                  >
                    <div className="flex items-start justify-between gap-4">
                      <div className="space-y-0.5 min-w-0">
                        <p className="text-sm font-medium leading-snug truncate">{r.title}</p>
                        <div className="flex items-center gap-2 flex-wrap">
                          <span className="text-xs text-gray-400 dark:text-gray-600">{r.season}</span>
                          {driverCodes.length > 0 && (
                            <span className="text-xs text-gray-500 font-mono">
                              {driverCodes.join(" · ")}
                            </span>
                          )}
                          {r.infraction_category && (
                            <span className="text-xs text-gray-400 dark:text-gray-600">
                              {r.infraction_category.replace(/_/g, " ")}
                            </span>
                          )}
                        </div>
                      </div>
                      <div className="flex flex-col items-end gap-1 shrink-0">
                        <PenaltyBadge type={r.penalty_type} />
                        <ScoreBar score={r.similarity_score} />
                      </div>
                    </div>

                    {r.reasoning_snippet && (
                      <p className="text-xs text-gray-500 leading-relaxed line-clamp-2">
                        {r.reasoning_snippet}
                      </p>
                    )}

                    <div className="flex items-center gap-3 text-xs text-gray-500 dark:text-gray-700 pt-0.5">
                      {r.article_cited && r.article_cited.length > 0 && (
                        <span>Art. {r.article_cited.join(", ")}</span>
                      )}
                      {r.lap && <span>Lap {r.lap}</span>}
                      {r.corner && <span>{r.corner}</span>}
                      {r.penalty_points > 0 && (
                        <span>{r.penalty_points} penalty pts</span>
                      )}
                      {r.pdf_url && (
                        <a
                          href={r.pdf_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="ml-auto hover:text-gray-900 dark:hover:text-white transition-colors"
                        >
                          PDF ↗
                        </a>
                      )}
                    </div>
                  </div>
                );
              })}
            </>
          )}
        </div>
      )}
    </main>
  );
}
