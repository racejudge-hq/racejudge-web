import Link from "next/link";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

interface Guideline {
  article_id: string;
  document_name: string;
  section: string | null;
  article_number: string;
  article_text: string;
  recommended_penalty: string | null;
  effective_date: string | null;
}

async function fetchGuidelines(): Promise<Guideline[]> {
  try {
    const res = await fetch(`${API_BASE}/v1/guidelines`, {
      next: { revalidate: 3600 },
    });
    if (res.ok) return res.json();
  } catch {
    // fall through
  }
  return [];
}

function PenaltyChip({ penalty }: { penalty: string }) {
  const color =
    penalty.includes("DSQ") ? "text-red-500 border-red-900"
    : penalty.includes("DT") || penalty.includes("GRID") ? "text-orange-500 border-orange-900"
    : penalty.includes("10s") || penalty.includes("5s") ? "text-yellow-500 border-yellow-900"
    : "text-gray-400 border-gray-700";
  return (
    <span className={`text-xs font-mono border rounded px-2 py-0.5 ${color}`}>
      {penalty}
    </span>
  );
}

export default async function GuidelinesPage() {
  const guidelines = await fetchGuidelines();

  const byDocument: Record<string, Guideline[]> = {};
  for (const g of guidelines) {
    (byDocument[g.document_name] ??= []).push(g);
  }

  const hasData = guidelines.length > 0;

  return (
    <main className="max-w-3xl mx-auto px-4 py-10 space-y-8">
      <Link href="/" className="text-sm text-gray-500 hover:text-white">
        ← Home
      </Link>

      <header className="space-y-1">
        <h1 className="text-2xl font-bold">
          RACE<span className="rj-brand-red">JUDGE</span>{" "}
          <span className="font-normal text-gray-400">Guidelines</span>
        </h1>
        <p className="text-sm text-gray-500">
          FIA Sporting Regulations and stewards&apos; guidelines — penalty recommendations by article
        </p>
      </header>

      {!hasData && (
        <div className="border border-gray-800 rounded-lg p-8 text-center space-y-2">
          <p className="text-gray-500 text-sm">No guidelines loaded yet.</p>
          <p className="text-xs text-gray-700">
            Populate the <span className="font-mono">guidelines</span> table via the ingest pipeline
            or the annotate interface to see article-by-article penalty recommendations here.
          </p>
        </div>
      )}

      {Object.entries(byDocument).map(([docName, articles]) => (
        <section key={docName} className="space-y-3">
          <h2 className="text-sm font-semibold text-gray-300 border-b border-gray-800 pb-2">
            {docName}
          </h2>

          <div className="space-y-2">
            {articles
              .sort((a, b) => a.article_number.localeCompare(b.article_number, undefined, { numeric: true }))
              .map((g) => (
                <div
                  key={g.article_id}
                  className="border border-gray-800 rounded p-4 space-y-2 hover:border-gray-700 transition-colors"
                >
                  <div className="flex items-start justify-between gap-3">
                    <div className="flex items-baseline gap-2">
                      <span className="text-xs font-mono text-gray-500 shrink-0">
                        Art. {g.article_number}
                      </span>
                      {g.section && (
                        <span className="text-xs text-gray-600">{g.section}</span>
                      )}
                    </div>
                    {g.recommended_penalty && (
                      <PenaltyChip penalty={g.recommended_penalty} />
                    )}
                  </div>

                  <p className="text-sm text-gray-300 leading-relaxed">
                    {g.article_text}
                  </p>

                  {g.effective_date && (
                    <p className="text-xs text-gray-700">
                      Effective: {g.effective_date}
                    </p>
                  )}
                </div>
              ))}
          </div>
        </section>
      ))}
    </main>
  );
}
