import Link from "next/link";

export default function PredictPage() {
  return (
    <main className="max-w-3xl mx-auto px-4 py-10 space-y-8">
      <Link href="/" className="text-sm text-gray-500 hover:text-white">
        ← Home
      </Link>

      <header className="space-y-2">
        <h1 className="text-3xl font-bold">
          RACE<span className="rj-brand-red">JUDGE</span>{" "}
          <span className="text-gray-400 font-normal">Predictor</span>
        </h1>
        <p className="text-gray-400 text-sm">
          AI-powered penalty prediction engine — Phase 5 (coming soon)
        </p>
      </header>

      {/* Coming soon banner */}
      <div className="border border-yellow-800 rounded-lg p-6 bg-yellow-950/20">
        <p className="text-yellow-500 font-semibold text-sm uppercase tracking-wider mb-2">
          Training in progress
        </p>
        <p className="text-gray-300 text-sm leading-relaxed">
          The penalty prediction model is being trained on 2018–2023 stewards&apos;
          decisions. It will be available once the model passes the calibration gate
          (ECE &lt; 0.05, Macro-F1 ≥ 0.65).
        </p>
      </div>

      {/* Architecture preview */}
      <section className="space-y-4">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
          Model Architecture
        </h2>
        <div className="grid gap-3">
          {[
            {
              layer: "Layer A",
              name: "XGBoost (tabular)",
              desc: "Article cited, lap phase, speed delta, tyre compound, SC status, driver penalty history",
              status: "training",
            },
            {
              layer: "Layer B",
              name: "Llama-3-8B-Instruct + LoRA",
              desc: "Free-text incident reasoning fine-tuned on stewards' written decisions",
              status: "planned",
            },
            {
              layer: "Meta",
              name: "Stacked logistic regression + Platt calibration",
              desc: "Combines Layer A + B outputs into final probability distribution",
              status: "planned",
            },
          ].map(({ layer, name, desc, status }) => (
            <div key={layer} className="border border-gray-800 rounded p-4 space-y-1">
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-600 font-mono">{layer}</span>
                <span className="font-medium text-sm">{name}</span>
                <span
                  className={`ml-auto text-xs px-2 py-0.5 rounded-full ${
                    status === "training"
                      ? "bg-yellow-900 text-yellow-400"
                      : "bg-gray-800 text-gray-500"
                  }`}
                >
                  {status}
                </span>
              </div>
              <p className="text-xs text-gray-500">{desc}</p>
            </div>
          ))}
        </div>
      </section>

      {/* Output classes */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
          Prediction Output — 7 Classes
        </h2>
        <div className="flex flex-wrap gap-2">
          {["NFA", "REP", "5s", "10s", "DT", "GRID", "DSQ"].map((cls) => (
            <span
              key={cls}
              className="px-3 py-1 border border-gray-700 rounded text-xs font-mono"
            >
              {cls}
            </span>
          ))}
        </div>
        <p className="text-xs text-gray-600">
          NFA = No Further Action · REP = Reprimand · DT = Drive-Through · DSQ = Disqualification
        </p>
      </section>

      {/* Gates */}
      <section className="space-y-3">
        <h2 className="text-sm font-semibold text-gray-500 uppercase tracking-wider">
          Ship Gate
        </h2>
        <div className="grid grid-cols-2 gap-3">
          <div className="border border-gray-800 rounded p-3">
            <p className="text-xs text-gray-500">Target Macro-F1</p>
            <p className="text-lg font-mono font-bold">≥ 0.65</p>
          </div>
          <div className="border border-gray-800 rounded p-3">
            <p className="text-xs text-gray-500">Target ECE</p>
            <p className="text-lg font-mono font-bold">&lt; 0.05</p>
          </div>
        </div>
        <p className="text-xs text-gray-600">
          Expected Calibration Error (ECE) measures how well predicted probabilities
          reflect true outcome frequencies. Model will not ship publicly until both
          gates pass on the 2025 held-out test set.
        </p>
      </section>

      <footer className="pt-6 border-t border-gray-800">
        <p className="text-xs text-gray-700">
          Predictions are for research purposes only and do not represent official
          FIA determinations. Train/val/test split: 2018–2023 / 2024 / 2025.
        </p>
      </footer>
    </main>
  );
}
