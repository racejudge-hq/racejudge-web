import Link from "next/link";

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6">
      <div className="max-w-2xl w-full text-center space-y-8">
        <div className="space-y-4">
          <h1 className="text-5xl font-bold tracking-tight">
            RACE<span className="rj-brand-red">JUDGE</span>
          </h1>
          <p className="text-xl text-gray-400">
            Every F1 stewards&apos; decision — searchable, comparable, explainable.
          </p>
        </div>

        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-left">
          <Link
            href="/decisions"
            className="border border-gray-800 rounded-lg p-5 hover:border-gray-600 transition-colors"
          >
            <p className="font-semibold">Decisions</p>
            <p className="text-sm text-gray-500 mt-1">
              Browse 1,000+ FIA stewards&apos; decisions from 2019–2025
            </p>
          </Link>

          <Link
            href="/decisions?q=collision"
            className="border border-gray-800 rounded-lg p-5 hover:border-gray-600 transition-colors"
          >
            <p className="font-semibold">Search</p>
            <p className="text-sm text-gray-500 mt-1">
              BM25 full-text search · hybrid semantic search coming in Phase 4
            </p>
          </Link>

          <Link
            href="/predict"
            className="border border-gray-800 rounded-lg p-5 hover:border-gray-600 transition-colors"
          >
            <p className="font-semibold">
              Predictor{" "}
              <span className="text-xs text-yellow-600 font-normal">Phase 5</span>
            </p>
            <p className="text-sm text-gray-500 mt-1">
              AI penalty prediction — XGBoost + LLM ensemble
            </p>
          </Link>

          <div className="border border-gray-900 rounded-lg p-5 opacity-40">
            <p className="font-semibold">
              Precedents{" "}
              <span className="text-xs text-gray-600 font-normal">Phase 4</span>
            </p>
            <p className="text-sm text-gray-500 mt-1">
              Semantic precedent search via BGE-M3 + pgvector HNSW
            </p>
          </div>
        </div>

        <p className="text-xs text-gray-700 uppercase tracking-widest">
          Private beta · May 2026
        </p>
      </div>
    </main>
  );
}
