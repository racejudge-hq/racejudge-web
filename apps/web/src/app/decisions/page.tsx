import { getDecisions } from "@/lib/api";
import { DecisionCard } from "@/components/DecisionCard";

interface Props {
  searchParams: Promise<{ season?: string; q?: string; page?: string }>;
}

export default async function DecisionsPage({ searchParams }: Props) {
  const params = await searchParams;
  const page   = Math.max(1, Number(params.page ?? 1));
  const limit  = 50;
  const offset = (page - 1) * limit;

  const decisions = await getDecisions({
    season: params.season ? Number(params.season) : undefined,
    q:      params.q,
    limit,
    offset,
  });

  return (
    <main className="max-w-3xl mx-auto px-4 py-10 space-y-6">
      <header>
        <h1 className="text-3xl font-bold">
          RACE<span className="rj-brand-red">JUDGE</span>
        </h1>
        <p className="text-gray-400 text-sm mt-1">
          FIA stewards&apos; decisions — searchable and browsable
        </p>
      </header>

      {/* Search form */}
      <form method="get" className="flex gap-2">
        <input
          name="q"
          defaultValue={params.q}
          placeholder="Search decisions…"
          className="flex-1 px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm focus:outline-none focus:border-gray-400"
        />
        <select
          name="season"
          defaultValue={params.season ?? ""}
          aria-label="Filter by season"
          className="px-3 py-2 bg-gray-900 border border-gray-700 rounded text-sm"
        >
          <option value="">All seasons</option>
          {[2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019].map((y) => (
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
      {decisions.length === 0 ? (
        <p className="text-gray-500">No decisions found.</p>
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-gray-600">{decisions.length} results</p>
          {decisions.map((d) => (
            <DecisionCard key={d.doc_id} d={d} />
          ))}
        </div>
      )}

      {/* Pagination */}
      <div className="flex gap-4 text-sm pt-4">
        {page > 1 && (
          <a
            href={`?q=${params.q ?? ""}&season=${params.season ?? ""}&page=${page - 1}`}
            className="text-gray-400 hover:text-white"
          >
            ← Previous
          </a>
        )}
        {decisions.length === limit && (
          <a
            href={`?q=${params.q ?? ""}&season=${params.season ?? ""}&page=${page + 1}`}
            className="text-gray-400 hover:text-white ml-auto"
          >
            Next →
          </a>
        )}
      </div>
    </main>
  );
}
