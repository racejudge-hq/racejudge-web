import Link from "next/link";
import { getAnnotationStats } from "@/lib/api";

export default async function AnnotatePage() {
  const stats = await getAnnotationStats().catch(() => null);

  const progress = stats?.progress_pct ?? 0;
  const triplets = stats?.triplet_pairs ?? 0;
  const target = stats?.target_pairs ?? 500;

  return (
    <main className="max-w-3xl mx-auto px-4 py-10 space-y-8">
      <Link href="/" className="text-sm text-gray-500 hover:text-white">
        ← Home
      </Link>

      <header className="space-y-2">
        <h1 className="text-2xl font-bold">
          RACE<span className="rj-brand-red">JUDGE</span> Annotation
        </h1>
        <p className="text-gray-400 text-sm">
          Label incident pairs for BGE-M3 fine-tuning — target: 500 pairs
        </p>
      </header>

      {/* Progress */}
      <section className="border border-gray-800 rounded-lg p-5 space-y-3">
        <div className="flex items-baseline justify-between">
          <span className="text-sm font-medium">Triplet pairs labelled</span>
          <span className="font-mono text-lg">
            {triplets} / {target}
          </span>
        </div>
        <div className="h-2 bg-gray-800 rounded-full overflow-hidden">
          <div
            className="h-full bg-white rounded-full transition-all"
            style={{ width: `${Math.min(progress, 100)}%` }}
          />
        </div>
        <p className="text-xs text-gray-600">{progress.toFixed(1)}% of target</p>
      </section>

      {/* Stats by annotator */}
      {stats?.by_annotator && Object.keys(stats.by_annotator).length > 0 && (
        <section className="space-y-3">
          <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
            By Annotator
          </h2>
          <div className="space-y-1">
            {Object.entries(stats.by_annotator)
              .sort((a, b) => b[1] - a[1])
              .map(([annotator, count]) => (
                <div key={annotator} className="flex justify-between text-sm">
                  <span className="text-gray-400 font-mono">{annotator}</span>
                  <span className="text-gray-600">{count} labels</span>
                </div>
              ))}
          </div>
        </section>
      )}

      {/* Instructions */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
          How to Annotate
        </h2>
        <div className="space-y-2 text-sm text-gray-400">
          <p>
            A <strong className="text-white">triplet</strong> is (anchor, positive, negative):
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-500 ml-2">
            <li>
              <strong className="text-gray-300">Positive</strong>: a decision that should be
              treated as a precedent for the anchor (similar infraction type, similar context)
            </li>
            <li>
              <strong className="text-gray-300">Negative</strong>: a decision that looks
              superficially similar but led to a different outcome (optional)
            </li>
          </ul>
          <p className="text-gray-500 text-xs mt-3">
            Use the API directly:{" "}
            <code className="bg-gray-900 px-1 rounded">
              POST /v1/annotations
            </code>{" "}
            with{" "}
            <code className="bg-gray-900 px-1 rounded">
              doc_id, positive_doc_id, annotator
            </code>
          </p>
        </div>
      </section>

      {/* API example */}
      <section className="space-y-2">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
          Quick API Reference
        </h2>
        <pre className="bg-gray-900 rounded p-4 text-xs text-gray-400 overflow-x-auto">{`# Submit a triplet label
curl -X POST /v1/annotations \\
  -H "Content-Type: application/json" \\
  -d '{
    "doc_id": "anchor-doc-id",
    "positive_doc_id": "similar-doc-id",
    "negative_doc_id": "dissimilar-doc-id",
    "annotator": "your-name",
    "infraction_type": "causing a collision",
    "penalty_class": "5s"
  }'

# Export all triplets for fine-tuning
curl /v1/annotations/export/triplets`}</pre>
      </section>
    </main>
  );
}
