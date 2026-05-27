import Link from "next/link";
import type { Decision } from "@/lib/api";

export function DecisionCard({ d }: { d: Decision }) {
  return (
    <Link
      href={`/decisions/${d.doc_id}`}
      className="block p-4 border border-gray-800 rounded hover:border-gray-500 transition-colors"
    >
      <p className="text-sm text-gray-500 mb-1">
        {d.season} · {d.published_at ?? "date unknown"}
      </p>
      <p className="font-medium leading-snug">{d.title}</p>
      <p className="text-xs text-gray-600 mt-2">{d.char_count.toLocaleString()} chars</p>
    </Link>
  );
}
