import Link from "next/link";
import { searchDecisions } from "@/lib/api";

interface Props {
  searchParams: Promise<{ q?: string; season?: string }>;
}

export default async function SearchPage({ searchParams }: Props) {
  const { q: qRaw = "", season: seasonParam } = await searchParams;
  const q = qRaw.trim();
  const season = seasonParam ? Number(seasonParam) : undefined;

  const results = q.length >= 2
    ? await searchDecisions(q, season, 30).catch(() => [])
    : [];

  return (
    <main className="max-w-3xl mx-auto px-4 py-10 space-y-6">
      <Link href="/" className="text-sm text-gray-500 hover:text-white">
        ← Home
      </Link>

      <h1 className="text-2xl font-bold">
        RACE<span className="rj-brand-red">JUDGE</span> Search
      </h1>

      {/* Search form */}
      <form method="get" className="flex gap-2">
        <input
          autoFocus
          name="q"
          defaultValue={q}
          placeholder="e.g. causing a collision, track limits, unsafe release…"
          className="flex-1 px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm focus:outline-none focus:border-gray-400"
        />
        <select
          name="season"
          defaultValue={seasonParam ?? ""}
          aria-label="Filter by season"
          className="px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm"
        >
          <option value="">All seasons</option>
          {[2025, 2024, 2023, 2022, 2021, 2020, 2019].map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
        <button
          type="submit"
          className="px-4 py-2 bg-white text-black rounded text-sm font-medium hover:bg-gray-200"
        >
          Search
        </button>
      </form>

      {/* Results */}
      {q.length < 2 ? (
        <div className="space-y-2">
          <p className="text-gray-500 text-sm">Enter a search term to begin.</p>
          <div className="flex flex-wrap gap-2 text-xs">
            {[
              "causing a collision",
              "track limits",
              "unsafe release",
              "pit lane speeding",
              "impeding",
              "blue flag",
              "safety car",
              "disqualification",
            ].map((term) => (
              <a
                key={term}
                href={`?q=${encodeURIComponent(term)}`}
                className="px-2 py-1 border border-gray-800 rounded hover:border-gray-600 text-gray-400 hover:text-white transition-colors"
              >
                {term}
              </a>
            ))}
          </div>
        </div>
      ) : results.length === 0 ? (
        <p className="text-gray-500 text-sm">No results for &quot;{q}&quot;.</p>
      ) : (
        <div className="space-y-1">
          <p className="text-xs text-gray-600 mb-3">
            {results.length} results for &quot;{q}&quot;
            {season ? ` in ${season}` : ""}
          </p>
          {results.map((r) => (
            <Link
              key={r.doc_id}
              href={`/decisions/${r.doc_id}`}
              className="block border border-gray-800 rounded p-4 hover:border-gray-600 transition-colors space-y-1"
            >
              <div className="flex items-start justify-between gap-4">
                <span className="text-sm font-medium leading-snug">{r.title}</span>
                <span className="text-xs text-gray-600 shrink-0 font-mono">
                  {r.season}
                </span>
              </div>
              {r.snippet && (
                <p className="text-xs text-gray-500 leading-relaxed line-clamp-2">
                  {r.snippet}
                </p>
              )}
              <div className="flex items-center gap-3 text-xs text-gray-700 pt-1">
                <span>score: {r.score.toFixed(3)}</span>
                {r.published_at && <span>{r.published_at}</span>}
              </div>
            </Link>
          ))}
        </div>
      )}
    </main>
  );
}
