import { getDecisions } from "@/lib/api";
import DecisionsTable from "@/components/DecisionsTable";
import { Button } from "@/components/ui/button";
import NotificationOptIn from "@/components/NotificationOptIn";

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
        <p className="text-gray-600 dark:text-gray-400 text-sm mt-1">
          FIA stewards&apos; decisions — searchable and browsable
        </p>
        <div className="mt-3">
          <NotificationOptIn />
        </div>
      </header>

      {/* Search form */}
      <form method="get" className="flex gap-2">
        <input
          name="q"
          defaultValue={params.q}
          placeholder="Search decisions…"
          className="flex-1 px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded text-sm focus:outline-none focus:border-gray-400"
        />
        <select
          name="season"
          defaultValue={params.season ?? ""}
          aria-label="Filter by season"
          className="px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-300 dark:border-gray-700 rounded text-sm"
        >
          <option value="">All seasons</option>
          {[2026, 2025, 2024, 2023, 2022, 2021, 2020, 2019].map((y) => (
            <option key={y} value={y}>{y}</option>
          ))}
        </select>
        <Button type="submit">Search</Button>
      </form>

      {/* Results */}
      {decisions.length === 0 ? (
        <p className="text-gray-500">No decisions found.</p>
      ) : (
        <DecisionsTable decisions={decisions} />
      )}

      {/* Pagination */}
      <div className="flex gap-4 text-sm pt-4">
        {page > 1 && (
          <a
            href={`?q=${params.q ?? ""}&season=${params.season ?? ""}&page=${page - 1}`}
            className="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"
          >
            ← Previous
          </a>
        )}
        {decisions.length === limit && (
          <a
            href={`?q=${params.q ?? ""}&season=${params.season ?? ""}&page=${page + 1}`}
            className="text-gray-600 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white ml-auto"
          >
            Next →
          </a>
        )}
      </div>
    </main>
  );
}
