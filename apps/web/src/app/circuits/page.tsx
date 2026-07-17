import Link from "next/link";
import CircuitMap, { type CircuitPoint } from "@/components/CircuitMap";
import { CIRCUITS } from "@/lib/circuits";

export const metadata = {
  title: "Circuits — RaceJudge",
  description: "Map of the Formula 1 circuits covered by RaceJudge stewards' decisions.",
};

export default function CircuitsPage() {
  // Dedup the aliases by circuit name → one real point per venue.
  const byName = new Map<string, CircuitPoint>();
  for (const c of Object.values(CIRCUITS)) {
    if (!byName.has(c.name)) {
      byName.set(c.name, { name: c.name, country: c.country, lngLat: c.lngLat });
    }
  }
  const points = [...byName.values()];

  return (
    <main className="max-w-5xl mx-auto px-4 py-10 space-y-6">
      <Link href="/" className="text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white">
        ← Home
      </Link>
      <header className="space-y-1">
        <h1 className="text-2xl font-bold">
          RACE<span className="rj-brand-red">JUDGE</span>{" "}
          <span className="font-normal text-gray-600 dark:text-gray-400">Circuits</span>
        </h1>
        <p className="text-sm text-gray-500">
          The {points.length} Formula 1 venues covered by the decisions database — real circuit
          locations. Click a marker for details.
        </p>
      </header>

      <CircuitMap points={points} />

      <p className="text-xs text-gray-500 dark:text-gray-700">
        Map © OpenStreetMap contributors · rendered with MapLibre GL (no API token).
      </p>
    </main>
  );
}
