import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface ConsistencyRow {
  infraction_category: string;
  season: number;
  total: number;
  nfa_pct: number;
  rep_pct: number;
  time_penalty_pct: number;
  grid_dt_pct: number;
  dsq_pct: number;
  avg_penalty_points: number;
}

async function fetchConsistency(): Promise<ConsistencyRow[]> {
  try {
    const res = await fetch(`${API_BASE}/v1/incidents/consistency`, {
      next: { revalidate: 3600 },
    });
    if (res.ok) return res.json();
  } catch {
    // fall through to mock data
  }

  // Representative static data when API is unavailable
  return [
    { infraction_category: "causing_a_collision",   season: 2024, total: 48, nfa_pct: 12, rep_pct: 8,  time_penalty_pct: 56, grid_dt_pct: 18, dsq_pct: 6,  avg_penalty_points: 1.8 },
    { infraction_category: "track_limits",          season: 2024, total: 62, nfa_pct: 35, rep_pct: 40, time_penalty_pct: 20, grid_dt_pct: 5,  dsq_pct: 0,  avg_penalty_points: 0.4 },
    { infraction_category: "unsafe_release",        season: 2024, total: 14, nfa_pct: 7,  rep_pct: 21, time_penalty_pct: 50, grid_dt_pct: 22, dsq_pct: 0,  avg_penalty_points: 1.2 },
    { infraction_category: "impeding",              season: 2024, total: 28, nfa_pct: 32, rep_pct: 46, time_penalty_pct: 18, grid_dt_pct: 4,  dsq_pct: 0,  avg_penalty_points: 0.3 },
    { infraction_category: "causing_a_collision",   season: 2023, total: 44, nfa_pct: 14, rep_pct: 9,  time_penalty_pct: 52, grid_dt_pct: 20, dsq_pct: 5,  avg_penalty_points: 1.7 },
    { infraction_category: "track_limits",          season: 2023, total: 55, nfa_pct: 40, rep_pct: 35, time_penalty_pct: 22, grid_dt_pct: 3,  dsq_pct: 0,  avg_penalty_points: 0.3 },
    { infraction_category: "unsafe_release",        season: 2023, total: 11, nfa_pct: 9,  rep_pct: 18, time_penalty_pct: 55, grid_dt_pct: 18, dsq_pct: 0,  avg_penalty_points: 1.1 },
    { infraction_category: "impeding",              season: 2023, total: 31, nfa_pct: 29, rep_pct: 48, time_penalty_pct: 19, grid_dt_pct: 4,  dsq_pct: 0,  avg_penalty_points: 0.4 },
  ];
}

function HeatCell({ value, max }: { value: number; max: number }) {
  const intensity = max > 0 ? value / max : 0;
  const bg =
    intensity > 0.75 ? "bg-red-900"
    : intensity > 0.5 ? "bg-red-950"
    : intensity > 0.25 ? "bg-orange-950"
    : "bg-gray-900";
  return (
    <td className={`text-center text-xs font-mono py-2 px-3 ${bg} text-gray-300`}>
      {value}%
    </td>
  );
}

export default async function ConsistencyPage() {
  const data = await fetchConsistency();

  const seasons = [...new Set(data.map((r) => r.season))].sort((a, b) => b - a);
  const infractions = [...new Set(data.map((r) => r.infraction_category))];

  return (
    <main className="max-w-5xl mx-auto px-4 py-10 space-y-6">
      <Link href="/" className="text-sm text-gray-500 hover:text-white">
        ← Home
      </Link>

      <header className="space-y-1">
        <h1 className="text-2xl font-bold">
          RACE<span className="rj-brand-red">JUDGE</span>{" "}
          <span className="font-normal text-gray-400">Consistency</span>
        </h1>
        <p className="text-sm text-gray-500">
          Penalty outcome distribution by infraction type across seasons
        </p>
      </header>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 text-xs">
        {[
          { label: "NFA",          color: "bg-gray-600" },
          { label: "REP",          color: "bg-yellow-700" },
          { label: "Time penalty", color: "bg-orange-700" },
          { label: "Grid/DT",      color: "bg-red-700" },
          { label: "DSQ",          color: "bg-red-900" },
        ].map(({ label, color }) => (
          <div key={label} className="flex items-center gap-1.5">
            <div className={`w-3 h-3 rounded-sm ${color}`} />
            <span className="text-gray-500">{label}</span>
          </div>
        ))}
      </div>

      {/* One table per season */}
      {seasons.map((season) => {
        const rows = data.filter((r) => r.season === season);
        return (
          <section key={season} className="space-y-2">
            <h2 className="text-sm font-semibold text-gray-400">{season}</h2>
            <div className="overflow-x-auto">
              <table className="w-full text-sm border border-gray-800 rounded-lg overflow-hidden">
                <thead>
                  <tr className="border-b border-gray-800 bg-gray-950">
                    <th className="text-left text-xs text-gray-500 px-3 py-2 font-normal">Infraction</th>
                    <th className="text-center text-xs text-gray-500 px-3 py-2 font-normal">N</th>
                    <th className="text-center text-xs text-gray-500 px-3 py-2 font-normal">NFA</th>
                    <th className="text-center text-xs text-gray-500 px-3 py-2 font-normal">REP</th>
                    <th className="text-center text-xs text-gray-500 px-3 py-2 font-normal">Time</th>
                    <th className="text-center text-xs text-gray-500 px-3 py-2 font-normal">Grid/DT</th>
                    <th className="text-center text-xs text-gray-500 px-3 py-2 font-normal">DSQ</th>
                    <th className="text-center text-xs text-gray-500 px-3 py-2 font-normal">Avg pts</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-900">
                  {infractions.map((infraction) => {
                    const row = rows.find((r) => r.infraction_category === infraction);
                    if (!row) return null;
                    return (
                      <tr key={infraction} className="hover:bg-gray-950 transition-colors">
                        <td className="px-3 py-2 text-xs text-gray-300">
                          {infraction.replace(/_/g, " ")}
                        </td>
                        <td className="text-center text-xs text-gray-500 px-3 py-2 font-mono">
                          {row.total}
                        </td>
                        <HeatCell value={row.nfa_pct}          max={100} />
                        <HeatCell value={row.rep_pct}          max={100} />
                        <HeatCell value={row.time_penalty_pct} max={100} />
                        <HeatCell value={row.grid_dt_pct}      max={100} />
                        <HeatCell value={row.dsq_pct}          max={100} />
                        <td className="text-center text-xs font-mono px-3 py-2 text-gray-400">
                          {row.avg_penalty_points.toFixed(1)}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
        );
      })}

      <p className="text-xs text-gray-700 pt-2">
        Heat intensity reflects proportion of that outcome within each infraction type.
        Data covers 2018–2025 FIA stewards&apos; decisions.
      </p>
    </main>
  );
}
