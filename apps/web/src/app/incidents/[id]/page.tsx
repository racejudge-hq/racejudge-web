import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const PENALTY_COLORS: Record<string, string> = {
  NFA:  "text-gray-600 dark:text-gray-400 border-gray-300 dark:border-gray-700",
  REP:  "text-yellow-400 border-yellow-800",
  "5s": "text-orange-400 border-orange-800",
  "10s":"text-orange-500 border-orange-700",
  DT:   "text-red-400 border-red-800",
  GRID: "text-red-500 border-red-700",
  DSQ:  "text-red-600 border-red-600",
};

interface DriverRef { code?: string; full_name?: string; number?: number }

interface RadioClip {
  clip_id: string;
  driver_number: number;
  date: string;
  transcript: string | null;
  speaker_label: string | null;
}

interface RCMessage {
  message_id: string;
  date: string;
  category: string | null;
  message: string;
  flag: string | null;
}

interface IncidentDetailData {
  incident_id: string;
  doc_id: string;
  drivers: DriverRef[];
  session_key: number | null;
  lap: number | null;
  corner: string | null;
  article_cited: string[];
  infraction_category: string | null;
  penalty_type: string | null;
  penalty_seconds: number | null;
  penalty_points: number;
  contact: boolean | null;
  reasoning_text: string;
  weather_context: Record<string, unknown> | null;
  grid_positions: number | null;
  position_change: number | null;
  race_control_messages: RCMessage[];
  radio_clips: RadioClip[];
}

async function fetchIncident(id: string): Promise<IncidentDetailData | null> {
  try {
    const res = await fetch(`${API_BASE}/v1/incidents/${id}`, {
      next: { revalidate: 3600 },
    });
    if (res.status === 404) return null;
    if (!res.ok) throw new Error(`API ${res.status}`);
    return await res.json();
  } catch {
    return null;
  }
}

async function fetchSimilar(id: string) {
  try {
    const res = await fetch(`${API_BASE}/v1/precedents/${id}/similar?limit=5`, {
      next: { revalidate: 3600 },
    });
    if (!res.ok) return [];
    return await res.json();
  } catch {
    return [];
  }
}

function PenaltyBadge({ type }: { type: string | null }) {
  if (!type) return null;
  const cls = PENALTY_COLORS[type] ?? "text-gray-600 dark:text-gray-400 border-gray-300 dark:border-gray-700";
  return (
    <span className={`inline-block text-sm font-mono font-bold border rounded px-3 py-1 ${cls}`}>
      {type}
    </span>
  );
}

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const incident = await fetchIncident(id);
  if (!incident) return { title: "Incident not found" };

  const drivers = incident.drivers.map((d) => d.code ?? d.full_name ?? "unknown").join(" / ");
  const penalty = incident.penalty_type ?? "NFA";
  const title   = `${drivers} — ${incident.infraction_category ?? "Incident"} · ${penalty}`;

  return {
    title,
    description: `F1 stewards' decision: ${title}. ${incident.reasoning_text.slice(0, 140)}…`,
    openGraph: { title, description: `Penalty: ${penalty} · Lap ${incident.lap ?? "?"} · ${incident.corner ?? ""}` },
  };
}

export default async function IncidentDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;

  const [incident, similar] = await Promise.all([
    fetchIncident(id),
    fetchSimilar(id),
  ]);

  if (!incident) notFound();

  const driverNames = incident.drivers
    .map((d) => d.full_name || d.code || `#${d.number}`)
    .join(" vs ");

  return (
    <main className="max-w-4xl mx-auto px-4 py-10 space-y-8">
      <Link href="/precedents" className="text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white">
        ← Precedents
      </Link>

      {/* Header */}
      <header className="space-y-3">
        <div className="flex items-start justify-between gap-4">
          <div className="space-y-1">
            <p className="text-xs text-gray-400 dark:text-gray-600 uppercase tracking-wider font-mono">
              {incident.infraction_category?.replace(/_/g, " ") ?? "Incident"}
            </p>
            <h1 className="text-xl font-bold leading-tight">
              {driverNames || "Unknown drivers"}
            </h1>
          </div>
          <PenaltyBadge type={incident.penalty_type} />
        </div>

        {/* Meta row */}
        <div className="flex flex-wrap gap-4 text-xs text-gray-500">
          {incident.lap && <span>Lap {incident.lap}</span>}
          {incident.corner && <span>{incident.corner}</span>}
          {incident.session_key && <span className="font-mono">Session {incident.session_key}</span>}
          {incident.contact === true && (
            <span className="text-orange-500">Contact</span>
          )}
          {incident.penalty_seconds && (
            <span className="text-orange-400">{incident.penalty_seconds}s penalty</span>
          )}
          {incident.penalty_points > 0 && (
            <span className="text-red-400">{incident.penalty_points} penalty pts</span>
          )}
          {incident.grid_positions && incident.grid_positions > 0 && (
            <span>{incident.grid_positions} grid place{incident.grid_positions > 1 ? "s" : ""}</span>
          )}
          {incident.article_cited.length > 0 && (
            <span>Art. {incident.article_cited.join(", ")}</span>
          )}
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Main column */}
        <div className="lg:col-span-2 space-y-6">

          {/* Stewards reasoning */}
          {incident.reasoning_text && (
            <section className="space-y-2">
              <h2 className="text-xs text-gray-500 uppercase tracking-wider">
                Stewards reasoning
              </h2>
              <div className="border border-gray-200 dark:border-gray-800 rounded-lg p-4">
                <p className="text-sm text-gray-700 dark:text-gray-300 leading-relaxed whitespace-pre-wrap">
                  {incident.reasoning_text}
                </p>
              </div>
            </section>
          )}

          {/* Race control messages */}
          {incident.race_control_messages.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs text-gray-500 uppercase tracking-wider">
                Race control messages ({incident.race_control_messages.length})
              </h2>
              <div className="space-y-1">
                {incident.race_control_messages.map((msg) => (
                  <div
                    key={msg.message_id}
                    className="border border-gray-200 dark:border-gray-800 rounded p-3 flex items-start gap-3"
                  >
                    <span className="text-xs text-gray-400 dark:text-gray-600 font-mono shrink-0 pt-0.5">
                      {new Date(msg.date).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </span>
                    <div className="space-y-0.5 min-w-0">
                      {msg.flag && (
                        <span className={`text-xs font-bold ${
                          msg.flag === "RED" ? "text-red-500"
                          : msg.flag === "YELLOW" ? "text-yellow-400"
                          : msg.flag === "GREEN" ? "text-green-500"
                          : "text-gray-600 dark:text-gray-400"
                        }`}>
                          {msg.flag} FLAG
                        </span>
                      )}
                      <p className="text-sm text-gray-700 dark:text-gray-300">{msg.message}</p>
                      {msg.category && (
                        <p className="text-xs text-gray-400 dark:text-gray-600">{msg.category}</p>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Team radio transcripts */}
          {incident.radio_clips.length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs text-gray-500 uppercase tracking-wider">
                Team radio ({incident.radio_clips.length} clips)
              </h2>
              <div className="space-y-1">
                {incident.radio_clips.map((clip) => (
                  <div
                    key={clip.clip_id}
                    className="border border-gray-200 dark:border-gray-800 rounded p-3 space-y-1"
                  >
                    <div className="flex items-center gap-2 text-xs text-gray-500">
                      <span className="font-mono">
                        Driver #{clip.driver_number}
                      </span>
                      {clip.speaker_label && (
                        <span className="text-gray-500 dark:text-gray-700">{clip.speaker_label}</span>
                      )}
                      <span>{new Date(clip.date).toLocaleTimeString()}</span>
                    </div>
                    {clip.transcript ? (
                      <p className="text-sm text-gray-700 dark:text-gray-300 italic">
                        &ldquo;{clip.transcript}&rdquo;
                      </p>
                    ) : (
                      <p className="text-xs text-gray-500 dark:text-gray-700">No transcript available</p>
                    )}
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Weather context */}
          {incident.weather_context && Object.keys(incident.weather_context).length > 0 && (
            <section className="space-y-2">
              <h2 className="text-xs text-gray-500 uppercase tracking-wider">
                Weather context
              </h2>
              <div className="border border-gray-200 dark:border-gray-800 rounded p-3 grid grid-cols-2 gap-2 text-xs">
                {Object.entries(incident.weather_context).map(([k, v]) => (
                  <div key={k} className="flex justify-between">
                    <span className="text-gray-400 dark:text-gray-600">{k.replace(/_/g, " ")}</span>
                    <span className="text-gray-700 dark:text-gray-300 font-mono">{String(v)}</span>
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* Link to decision */}
          <div className="pt-2">
            <Link
              href={`/decisions/${incident.doc_id}`}
              className="text-xs text-gray-500 hover:text-gray-900 dark:hover:text-white transition-colors"
            >
              View full decision document →
            </Link>
          </div>
        </div>

        {/* Sidebar — similar precedents */}
        <div className="space-y-3">
          <h2 className="text-xs text-gray-500 uppercase tracking-wider">
            Similar precedents
          </h2>

          {similar.length === 0 ? (
            <p className="text-xs text-gray-500 dark:text-gray-700">
              Precedent links are computed nightly. Check back after the embedding
              pipeline has run.
            </p>
          ) : (
            <div className="space-y-2">
              {similar.map((p: {
                incident_id: string;
                title: string;
                season: number;
                penalty_type: string | null;
                similarity_score: number;
                reasoning_snippet?: string;
              }) => (
                <Link
                  key={p.incident_id}
                  href={`/incidents/${p.incident_id}`}
                  className="block border border-gray-200 dark:border-gray-800 rounded p-3 space-y-1 hover:border-gray-300 dark:hover:border-gray-600 transition-colors"
                >
                  <p className="text-xs font-medium line-clamp-2 leading-snug">
                    {p.title}
                  </p>
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-gray-400 dark:text-gray-600">{p.season}</span>
                    <div className="flex items-center gap-2">
                      {p.penalty_type && (
                        <span className="text-xs font-mono text-gray-500">
                          {p.penalty_type}
                        </span>
                      )}
                      <span className="text-xs text-gray-500 dark:text-gray-700 font-mono">
                        {(p.similarity_score * 100).toFixed(0)}%
                      </span>
                    </div>
                  </div>
                  {p.reasoning_snippet && (
                    <p className="text-xs text-gray-400 dark:text-gray-600 line-clamp-2">
                      {p.reasoning_snippet}
                    </p>
                  )}
                </Link>
              ))}

              <Link
                href={`/precedents`}
                className="text-xs text-gray-400 dark:text-gray-600 hover:text-gray-900 dark:hover:text-white transition-colors"
              >
                Search all precedents →
              </Link>
            </div>
          )}

          {/* Predict this incident */}
          <div className="pt-2 border-t border-gray-100 dark:border-gray-900">
            <Link
              href="/predict"
              className="block border border-gray-200 dark:border-gray-800 rounded p-3 text-xs text-gray-500 hover:border-gray-300 dark:hover:border-gray-600 hover:text-gray-900 dark:hover:text-white transition-colors"
            >
              <span className="font-medium">Predict similar incident →</span>
              <p className="text-gray-500 dark:text-gray-700 mt-0.5">
                Use the predictor to estimate penalty for a new incident
              </p>
            </Link>
          </div>
        </div>
      </div>
    </main>
  );
}
