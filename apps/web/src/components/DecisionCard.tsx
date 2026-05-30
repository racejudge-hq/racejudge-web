import Link from "next/link";
import type { Decision } from "@/lib/api";

const INFRACTION_COLORS: Record<string, string> = {
  "causing a collision":    "text-red-500",
  "track limits":           "text-yellow-500",
  "unsafe release":         "text-orange-500",
  "pit lane speeding":      "text-orange-400",
  "impeding":               "text-blue-400",
  "ignoring blue flags":    "text-blue-500",
  "safety car violation":   "text-purple-400",
  "VSC infringement":       "text-purple-400",
  "yellow flag violation":  "text-yellow-400",
  "disqualification":       "text-red-600",
};

function infractionColor(infraction?: string | null): string {
  if (!infraction) return "text-gray-600";
  return INFRACTION_COLORS[infraction.toLowerCase()] ?? "text-gray-500";
}

export function DecisionCard({ d }: { d: Decision }) {
  return (
    <Link
      href={`/decisions/${d.doc_id}`}
      className="block p-4 border border-gray-800 rounded hover:border-gray-500 transition-colors"
    >
      <div className="flex items-start justify-between gap-3">
        <p className="font-medium leading-snug flex-1">{d.title}</p>
        <span className="text-xs text-gray-600 shrink-0 font-mono pt-0.5">{d.season}</span>
      </div>

      <div className="flex items-center gap-3 mt-2 text-xs">
        <span className="text-gray-600">{d.published_at ?? "date unknown"}</span>
        <span className="text-gray-700">{d.char_count.toLocaleString()} chars</span>
        {d.needs_ocr && (
          <span className="text-yellow-700">OCR needed</span>
        )}
      </div>
    </Link>
  );
}
