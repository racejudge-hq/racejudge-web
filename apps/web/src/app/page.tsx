import Link from "next/link";

const NAV_CARDS = [
  {
    href:    "/decisions",
    title:   "Decisions",
    desc:    "Browse 1,000+ FIA stewards’ decisions from 2018–2025",
    badge:   null,
    active:  true,
  },
  {
    href:    "/precedents",
    title:   "Precedents",
    desc:    "Hybrid semantic + BM25 precedent search via BGE-M3 + pgvector HNSW",
    badge:   null,
    active:  true,
  },
  {
    href:    "/predict",
    title:   "Predictor",
    desc:    "XGBoost + LLM ensemble — 7-class penalty prediction with RAG explanation",
    badge:   null,
    active:  true,
  },
  {
    href:    "/consistency",
    title:   "Consistency",
    desc:    "Penalty outcome heat-maps by infraction type across seasons",
    badge:   null,
    active:  true,
  },
  {
    href:    "/guidelines",
    title:   "Guidelines",
    desc:    "FIA sporting regulations and stewards’ recommended penalty table",
    badge:   null,
    active:  true,
  },
  {
    href:    "/live",
    title:   "Live",
    desc:    "Real-time incident stream via WebSocket + Redis Pub/Sub",
    badge:   null,
    active:  true,
  },
] as const;

export default function Home() {
  return (
    <main className="min-h-screen flex flex-col items-center justify-center px-6 py-16">
      <div className="max-w-2xl w-full space-y-10">
        {/* Hero */}
        <div className="text-center space-y-4">
          <h1 className="text-5xl font-bold tracking-tight">
            RACE<span className="rj-brand-red">JUDGE</span>
          </h1>
          <p className="text-xl text-gray-600 dark:text-gray-400">
            Every F1 stewards&apos; decision — searchable, comparable, explainable.
          </p>
        </div>

        {/* Quick search */}
        <form method="get" action="/search" className="flex gap-2">
          <input
            name="q"
            placeholder="Search decisions…  e.g. causing a collision at Turn 1"
            className="flex-1 px-4 py-3 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded-lg text-sm focus:outline-none focus:border-gray-300 dark:focus:border-gray-600"
          />
          <button
            type="submit"
            className="px-5 py-3 bg-white text-black rounded-lg text-sm font-medium hover:bg-gray-200 transition-colors"
          >
            Search
          </button>
        </form>

        {/* Nav cards */}
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-left">
          {NAV_CARDS.map(({ href, title, desc, badge, active }) =>
            active ? (
              <Link
                key={href}
                href={href}
                className="border border-gray-200 dark:border-gray-800 rounded-lg p-5 hover:border-gray-300 dark:hover:border-gray-600 transition-colors space-y-1"
              >
                <p className="font-semibold">
                  {title}
                  {badge && (
                    <span className="ml-2 text-xs text-yellow-600 font-normal">{badge}</span>
                  )}
                </p>
                <p className="text-sm text-gray-500">{desc}</p>
              </Link>
            ) : (
              <div
                key={href}
                className="border border-gray-100 dark:border-gray-900 rounded-lg p-5 opacity-40 space-y-1"
              >
                <p className="font-semibold">
                  {title}
                  {badge && (
                    <span className="ml-2 text-xs text-gray-400 dark:text-gray-600 font-normal">{badge}</span>
                  )}
                </p>
                <p className="text-sm text-gray-500">{desc}</p>
              </div>
            )
          )}
        </div>

        <p className="text-center text-xs text-gray-500 dark:text-gray-700 uppercase tracking-widest">
          Private beta · June 2026
        </p>
      </div>
    </main>
  );
}
