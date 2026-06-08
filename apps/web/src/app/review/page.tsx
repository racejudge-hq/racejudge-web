"use client";

import Link from "next/link";
import { useCallback, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const DEMO_USER = "demo_user_001";

interface ReviewResult {
  incident_id:     string;
  driver_code:     string;
  document:        string;
  precedents_used: number;
  rag_used:        boolean;
  generated_at:    string;
}

function Field({
  label,
  htmlFor,
  required,
  children,
}: {
  label: string;
  htmlFor?: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <div className="space-y-1.5">
      <label
        htmlFor={htmlFor}
        className="block text-xs font-medium text-gray-700 dark:text-gray-300"
      >
        {label}
        {required && <span className="text-red-500 ml-0.5" aria-hidden="true">*</span>}
        {required && <span className="sr-only">(required)</span>}
      </label>
      {children}
    </div>
  );
}

export default function ReviewPage() {
  const [incidentId,  setIncidentId]  = useState("");
  const [driverCode,  setDriverCode]  = useState("");
  const [teamName,    setTeamName]    = useState("");
  const [newEvidence, setNewEvidence] = useState("");
  const [notes,       setNotes]       = useState("");

  const [loading,  setLoading]  = useState(false);
  const [result,   setResult]   = useState<ReviewResult | null>(null);
  const [error,    setError]    = useState<string | null>(null);
  const [copied,   setCopied]   = useState(false);

  const handleGenerate = useCallback(async () => {
    if (!incidentId || !driverCode || !teamName || !newEvidence) return;
    setLoading(true);
    setError(null);
    setResult(null);

    try {
      const res = await fetch(`${API_BASE}/v1/review/generate`, {
        method:  "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          incident_id:  incidentId.trim(),
          driver_code:  driverCode.trim().toUpperCase(),
          team_name:    teamName.trim(),
          new_evidence: newEvidence.trim(),
          notes:        notes.trim(),
        }),
      });
      if (!res.ok) {
        const data = await res.json().catch(() => ({}));
        setError(data.detail ?? `Error ${res.status}`);
      } else {
        setResult(await res.json());
      }
    } catch (e) {
      setError(String(e));
    }
    setLoading(false);
  }, [incidentId, driverCode, teamName, newEvidence, notes]);

  const handleCopy = async () => {
    if (!result) return;
    await navigator.clipboard.writeText(result.document);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const handleDownload = () => {
    if (!result) return;
    const blob = new Blob([result.document], { type: "text/plain" });
    const url  = URL.createObjectURL(blob);
    const a    = document.createElement("a");
    a.href     = url;
    a.download = `ror_${result.driver_code}_${result.incident_id.slice(0, 8)}.txt`;
    a.click();
    URL.revokeObjectURL(url);
  };

  const isValid = incidentId && driverCode && teamName && newEvidence.length >= 20;

  return (
    <main className="max-w-4xl mx-auto px-4 py-10 space-y-8">
      <Link href="/" className="text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white">
        ← Home
      </Link>

      <header>
        <h1 className="text-2xl font-bold">
          RACE<span className="rj-brand-red">JUDGE</span>{" "}
          <span className="font-normal text-gray-600 dark:text-gray-400">Right-of-Review Builder</span>
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Generate a formal FIA Right-of-Review request document (Art. 14.1.1 ISC) with
          precedent analysis and a RAG-drafted legal argument.
        </p>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-8">
        {/* Form */}
        <section className="space-y-5">
          <Field label="Incident ID" htmlFor="rr-incident-id" required>
            <input
              id="rr-incident-id"
              type="text"
              value={incidentId}
              onChange={(e) => setIncidentId(e.target.value)}
              placeholder="xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx"
              className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600"
            />
            <p className="text-xs text-gray-400 dark:text-gray-600">
              Find the UUID on the{" "}
              <Link href="/incidents" className="text-blue-600 dark:text-blue-400 hover:underline">
                incident detail page
              </Link>
              .
            </p>
          </Field>

          <div className="grid grid-cols-2 gap-4">
            <Field label="Driver code" htmlFor="rr-driver-code" required>
              <input
                id="rr-driver-code"
                type="text"
                value={driverCode}
                onChange={(e) => setDriverCode(e.target.value.toUpperCase().slice(0, 3))}
                placeholder="VER"
                maxLength={3}
                className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 uppercase font-mono"
              />
            </Field>
            <Field label="Team name" htmlFor="rr-team-name" required>
              <input
                id="rr-team-name"
                type="text"
                value={teamName}
                onChange={(e) => setTeamName(e.target.value)}
                placeholder="Red Bull Racing"
                className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600"
              />
            </Field>
          </div>

          <Field label="New significant evidence" htmlFor="rr-new-evidence" required>
            <textarea
              id="rr-new-evidence"
              value={newEvidence}
              onChange={(e) => setNewEvidence(e.target.value)}
              placeholder="Describe the new evidence that was not available to the Stewards at the time of the original decision (e.g. onboard camera footage showing X, telemetry data proving Y, witness statement from Z…)"
              rows={5}
              className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 resize-none"
            />
            <p className="text-xs text-gray-400 dark:text-gray-600">
              Must be evidence that genuinely was not available at the time of the hearing.
            </p>
          </Field>

          <Field label="Additional notes (optional)" htmlFor="rr-notes">
            <textarea
              id="rr-notes"
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              placeholder="Any additional context, procedural notes, or supporting arguments to include at the end of the document."
              rows={3}
              className="w-full px-3 py-2 text-sm bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600 resize-none"
            />
          </Field>

          <button
            type="button"
            onClick={handleGenerate}
            disabled={!isValid || loading}
            className="w-full py-2.5 text-sm font-semibold bg-gray-900 dark:bg-white text-white dark:text-gray-900 rounded hover:bg-gray-700 dark:hover:bg-gray-200 disabled:opacity-40 transition-colors"
          >
            {loading ? "Generating document…" : "Generate Right-of-Review"}
          </button>

          {error && (
            <div className="rounded border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-950/30 px-4 py-3 text-sm text-red-700 dark:text-red-400">
              {error}
            </div>
          )}

          {/* Info box */}
          <div className="rounded border border-gray-200 dark:border-gray-800 bg-gray-50 dark:bg-gray-900/50 px-4 py-3 space-y-1 text-xs text-gray-500 dark:text-gray-400">
            <p className="font-medium text-gray-700 dark:text-gray-300">How this works</p>
            <ul className="space-y-0.5 list-disc list-inside">
              <li>Fetches the original incident + stewards' reasoning from the database</li>
              <li>Finds similar incidents where a more lenient penalty was given</li>
              <li>Drafts the legal argument using RAG (requires ANTHROPIC_API_KEY)</li>
              <li>Formats a complete Art. 14.1.1 ISC review request document</li>
            </ul>
          </div>
        </section>

        {/* Document preview */}
        <section className="space-y-4">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-gray-900 dark:text-white">
              Generated document
            </h2>
            {result && (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-400 dark:text-gray-600">
                  {result.precedents_used} precedent{result.precedents_used !== 1 ? "s" : ""} found
                  {result.rag_used ? " · RAG" : " · template"}
                </span>
                <button
                  type="button"
                  onClick={handleCopy}
                  className="text-xs px-2 py-1 border border-gray-200 dark:border-gray-700 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                >
                  {copied ? "Copied!" : "Copy"}
                </button>
                <button
                  type="button"
                  onClick={handleDownload}
                  className="text-xs px-2 py-1 border border-gray-200 dark:border-gray-700 rounded hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                >
                  Download .txt
                </button>
              </div>
            )}
          </div>

          <div className="border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden min-h-[500px]">
            {loading ? (
              <div className="h-full flex items-center justify-center p-12 text-sm text-gray-400 dark:text-gray-600">
                <span role="status" aria-live="polite" className="animate-pulse">
                  Fetching incident, searching precedents, drafting…
                </span>
              </div>
            ) : result ? (
              <pre className="p-5 text-xs font-mono leading-relaxed text-gray-800 dark:text-gray-200 overflow-auto max-h-[700px] whitespace-pre-wrap">
                {result.document}
              </pre>
            ) : (
              <div className="h-full flex items-center justify-center p-12 text-center text-sm text-gray-400 dark:text-gray-600 space-y-2">
                <div>
                  <p>Fill in the form and click "Generate" to produce</p>
                  <p>a complete FIA Right-of-Review request document.</p>
                </div>
              </div>
            )}
          </div>

          {result && (
            <p className="text-xs text-gray-400 dark:text-gray-600">
              Generated {new Date(result.generated_at).toLocaleString()}.
              This is a draft document — review carefully before submission.
              RACEJUDGE is not a law firm and this does not constitute legal advice.
            </p>
          )}
        </section>
      </div>
    </main>
  );
}
