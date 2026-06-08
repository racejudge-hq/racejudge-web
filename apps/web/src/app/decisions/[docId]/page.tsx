import type { Metadata } from "next";
import Link from "next/link";
import { getDecision } from "@/lib/api";
import { notFound } from "next/navigation";

interface Props {
  params: Promise<{ docId: string }>;
}

export async function generateMetadata({ params }: Props): Promise<Metadata> {
  const { docId } = await params;
  try {
    const d = await getDecision(docId);
    return {
      title: d.title,
      description: `FIA stewards' decision — Season ${d.season}. ${d.title}.`,
      openGraph: { title: d.title, description: `Season ${d.season} · FIA stewards' decision` },
    };
  } catch {
    return { title: "Decision not found" };
  }
}

export default async function DecisionDetailPage({ params }: Props) {
  const { docId } = await params;

  let decision;
  try {
    decision = await getDecision(docId);
  } catch {
    notFound();
  }

  return (
    <main className="max-w-3xl mx-auto px-4 py-10 space-y-6">
      <Link href="/decisions" className="text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white">
        ← All decisions
      </Link>

      <header className="space-y-2">
        <p className="text-xs text-gray-400 dark:text-gray-600 uppercase tracking-widest">
          Season {decision.season} · {decision.published_at ?? "date unknown"}
        </p>
        <h1 className="text-2xl font-bold leading-tight">{decision.title}</h1>
      </header>

      <div className="flex gap-3 flex-wrap text-xs">
        <a
          href={decision.pdf_url}
          target="_blank"
          rel="noopener noreferrer"
          className="px-3 py-1 border border-gray-300 dark:border-gray-700 rounded hover:border-gray-400"
        >
          View PDF ↗
        </a>
        <span className="px-3 py-1 border border-gray-200 dark:border-gray-800 rounded text-gray-400 dark:text-gray-600">
          {decision.char_count.toLocaleString()} chars
        </span>
        {decision.needs_ocr && (
          <span className="px-3 py-1 border border-yellow-800 rounded text-yellow-600">
            OCR needed
          </span>
        )}
      </div>

      <section>
        <h2 className="text-sm font-semibold text-gray-500 mb-3 uppercase tracking-wider">
          Extracted Text
        </h2>
        <pre className="whitespace-pre-wrap text-sm text-gray-700 dark:text-gray-300 leading-relaxed bg-gray-50 dark:bg-gray-900 p-4 rounded overflow-auto max-h-[60vh]">
          {decision.raw_text || "(no text extracted)"}
        </pre>
      </section>

      <footer className="text-xs text-gray-500 dark:text-gray-700 pt-4 border-t border-gray-200 dark:border-gray-800">
        doc_id: {decision.doc_id} · parsed {decision.parsed_at.slice(0, 10)}
      </footer>
    </main>
  );
}
