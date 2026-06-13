import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const PENALTY_CLASSES = ["NFA", "REP", "5s", "10s", "DT", "GRID", "DSQ"];

interface DriverIncident {
  incident_id: string;
  title: string;
  season: number;
  published_at: string | null;
  penalty_type: string | null;
  penalty_points: number;
  infraction_category: string | null;
  article_cited: string[] | null;
  reasoning_snippet: string;
}

interface DriverStats {
  code: string;
  full_name: string;
  total_incidents: number;
  total_penalty_points: number;
  current_season_points: number;
  ban_risk: "none" | "low" | "medium" | "high";
  by_penalty: Record<string, number>;
  incidents: DriverIncident[];
}

async function fetchDriverStats(code: string): Promise<DriverStats | null> {
  try {
    const res = await fetch(`${API_BASE}/v1/drivers/${code.toUpperCase()}/stats`, {
      next: { revalidate: 300 },
    });
    if (res.ok) return await res.json();
  } catch {
    // fall through to null
  }
  return null;
}

function BanRiskBadge({ risk }: { risk: DriverStats["ban_risk"] }) {
  const styles: Record<string, string> = {
    none:   "text-gray-500 border-gray-200 dark:border-gray-800",
    low:    "text-green-600 border-green-900",
    medium: "text-yellow-500 border-yellow-800",
    high:   "text-red-500 border-red-800",
  };
  return (
    <span className={`text-xs border rounded px-2 py-0.5 font-mono ${styles[risk]}`}>
      {risk} ban risk
    </span>
  );
}

function PenaltyPointsBar({ current, max = 12 }: { current: number; max?: number }) {
  const pct = Math.min(100, (current / max) * 100);
  const color = pct >= 75 ? "bg-red-600" : pct >= 50 ? "bg-orange-500" : "bg-green-600";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-500">
        <span>Season penalty points</span>
        <span className="font-mono">{current} / {max}</span>
      </div>
      <div className="h-2 bg-gray-50 dark:bg-gray-900 rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <p className="text-xs text-gray-500 dark:text-gray-700">
        {max - current} points until race ban
      </p>
    </div>
  );
}

export default async function DriverPage({
  params,
}: {
  params: Promise<{ code: string }>;
}) {
  const { code } = await params;
  const stats = await fetchDriverStats(code);

  if (!stats) {
    return (
      <main className="max-w-3xl mx-auto px-4 py-10 space-y-6">
        <Link href="/" className="text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white">← Home</Link>
        <p className="text-gray-500">
          No data found for driver <span className="font-mono">{code.toUpperCase()}</span>.
          Driver data is available once incidents have been linked to the driver registry.
        </p>
      </main>
    );
  }

  return (
    <main className="max-w-3xl mx-auto px-4 py-10 space-y-8">
      <Link href="/" className="text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white">
        ← Home
      </Link>

      {/* Header */}
      <header className="space-y-3">
        <div className="flex items-start justify-between">
          <div>
            <p className="text-xs text-gray-400 dark:text-gray-600 font-mono">{stats.code}</p>
            <h1 className="text-3xl font-bold">{stats.full_name}</h1>
          </div>
          <BanRiskBadge risk={stats.ban_risk} />
        </div>

        <PenaltyPointsBar current={stats.current_season_points} />
      </header>

      {/* Stats grid */}
      <div className="grid grid-cols-3 gap-3">
        <div className="border border-gray-200 dark:border-gray-800 rounded p-3 text-center">
          <div className="text-2xl font-mono font-bold">{stats.total_incidents}</div>
          <div className="text-xs text-gray-400 dark:text-gray-600">Total incidents</div>
        </div>
        <div className="border border-gray-200 dark:border-gray-800 rounded p-3 text-center">
          <div className="text-2xl font-mono font-bold">{stats.total_penalty_points}</div>
          <div className="text-xs text-gray-400 dark:text-gray-600">All-time points</div>
        </div>
        <div className="border border-gray-200 dark:border-gray-800 rounded p-3 text-center">
          <div className="text-2xl font-mono font-bold">{stats.current_season_points}</div>
          <div className="text-xs text-gray-400 dark:text-gray-600">2025 points</div>
        </div>
      </div>

      {/* Penalty breakdown */}
      <section className="space-y-3">
        <h2 className="text-xs text-gray-500 uppercase tracking-wider">Penalty breakdown</h2>
        <div className="flex flex-wrap gap-2">
          {PENALTY_CLASSES.map((cls) => {
            const count = stats.by_penalty[cls] ?? 0;
            if (count === 0) return null;
            return (
              <div key={cls} className="border border-gray-200 dark:border-gray-800 rounded p-3 text-center min-w-[60px]">
                <div className="text-lg font-mono font-bold">{count}</div>
                <div className="text-xs text-gray-400 dark:text-gray-600 font-mono">{cls}</div>
              </div>
            );
          })}
        </div>
      </section>

      {/* Incident log */}
      <section className="space-y-2">
        <h2 className="text-xs text-gray-500 uppercase tracking-wider">
          Incident history ({stats.incidents.length})
        </h2>
        <div className="space-y-1">
          {stats.incidents.map((inc) => (
            <div
              key={inc.incident_id}
              className="border border-gray-200 dark:border-gray-800 rounded p-3 space-y-1 hover:border-gray-300 dark:hover:border-gray-700 transition-colors"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium leading-snug line-clamp-1">{inc.title}</span>
                <div className="flex items-center gap-2 shrink-0">
                  <span className="text-xs text-gray-400 dark:text-gray-600">{inc.season}</span>
                  {inc.penalty_type && (
                    <span className="text-xs font-mono border border-gray-300 dark:border-gray-700 rounded px-1.5 py-0.5">
                      {inc.penalty_type}
                    </span>
                  )}
                  {inc.penalty_points > 0 && (
                    <span className="text-xs text-red-500 font-mono">
                      +{inc.penalty_points}pts
                    </span>
                  )}
                </div>
              </div>
              {inc.infraction_category && (
                <p className="text-xs text-gray-400 dark:text-gray-600">
                  {inc.infraction_category.replace(/_/g, " ")}
                  {inc.article_cited?.length ? ` · Art. ${inc.article_cited.join(", ")}` : ""}
                </p>
              )}
            </div>
          ))}
        </div>
      </section>
    </main>
  );
}
