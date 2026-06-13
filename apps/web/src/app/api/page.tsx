"use client";

import { useAuth } from "@clerk/nextjs";
import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

const TIER_LIMITS: Record<string, number> = {
  free: 100,
  pro: 10_000,
  team: 100_000,
};

const TIER_LABELS: Record<string, string> = {
  free:  "Free",
  pro:   "Pro — £29/mo",
  team:  "Team — £499/mo",
};

interface ApiKey {
  key_id:         string;
  key_prefix:     string;
  name:           string | null;
  tier:           string;
  is_active:      boolean;
  requests_today: number;
  requests_total: number;
  last_used_at:   string | null;
  created_at:     string;
  daily_limit:    number;
}

interface SubscriptionStatus {
  tier:                 string;
  status:               string;
  current_period_end:   string | null;
  cancel_at_period_end: boolean;
  stripe_enabled:       boolean;
}

const DEMO_USER = "demo_user_001";

// Same Clerk gate as layout.tsx — hooks may only be used inside ClerkProvider
const CLERK_ENABLED = /^pk_(test|live)_\w{20,}$/.test(
  process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "",
);

type GetToken = () => Promise<string | null>;

function TierBadge({ tier }: { tier: string }) {
  const colors: Record<string, string> = {
    free: "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400",
    pro:  "bg-blue-50 dark:bg-blue-950 text-blue-700 dark:text-blue-300",
    team: "bg-purple-50 dark:bg-purple-950 text-purple-700 dark:text-purple-300",
  };
  return (
    <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${colors[tier] ?? colors.free}`}>
      {tier.toUpperCase()}
    </span>
  );
}

function UsageBar({ used, limit }: { used: number; limit: number }) {
  const pct = Math.min((used / limit) * 100, 100);
  const color = pct > 90 ? "bg-red-500" : pct > 70 ? "bg-yellow-500" : "bg-green-500";
  return (
    <div className="space-y-1">
      <div className="flex justify-between text-xs text-gray-500 dark:text-gray-400">
        <span>{used.toLocaleString()} / {limit.toLocaleString()} today</span>
        <span>{pct.toFixed(1)}%</span>
      </div>
      <div className="h-1.5 w-full bg-gray-200 dark:bg-gray-700 rounded-full overflow-hidden">
        <div className={`h-full ${color} rounded-full transition-all`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function ApiPage() {
  if (CLERK_ENABLED) return <ClerkApiPage />;
  return <ApiPageContent userId={DEMO_USER} getToken={async () => null} />;
}

function ClerkApiPage() {
  const { isLoaded, isSignedIn, userId, getToken } = useAuth();
  if (!isLoaded) return null;
  if (!isSignedIn || !userId) {
    return (
      <main className="max-w-4xl mx-auto px-4 py-10">
        <p className="text-sm text-gray-500">
          <Link href="/sign-in" className="underline hover:text-gray-900 dark:hover:text-white">
            Sign in
          </Link>{" "}
          to manage your API keys.
        </p>
      </main>
    );
  }
  return <ApiPageContent userId={userId} getToken={getToken} />;
}

function ApiPageContent({ userId, getToken }: { userId: string; getToken: GetToken }) {
  const [keys, setKeys]             = useState<ApiKey[]>([]);
  const [sub, setSub]               = useState<SubscriptionStatus | null>(null);
  const [loading, setLoading]       = useState(true);
  const [creating, setCreating]     = useState(false);
  const [newKeyName, setNewKeyName] = useState("");
  const [newKeyFull, setNewKeyFull] = useState<string | null>(null);
  const [copied, setCopied]         = useState(false);
  const [revoking, setRevoking]     = useState<string | null>(null);

  const authHeaders = useCallback(async (): Promise<Record<string, string>> => {
    try {
      const token = await getToken();
      return token ? { Authorization: `Bearer ${token}` } : {};
    } catch {
      return {};
    }
  }, [getToken]);

  const loadData = useCallback(async () => {
    setLoading(true);
    try {
      const headers = await authHeaders();
      const [keysRes, subRes] = await Promise.all([
        fetch(`${API_BASE}/v1/apikeys?user_id=${userId}`, { headers }),
        fetch(`${API_BASE}/v1/billing/subscription?user_id=${userId}`, { headers }),
      ]);
      if (keysRes.ok) setKeys(await keysRes.json());
      if (subRes.ok)  setSub(await subRes.json());
    } catch { /* ignore */ }
    setLoading(false);
  }, [userId, authHeaders]);

  useEffect(() => { loadData(); }, [loadData]);

  const handleCreate = async () => {
    if (creating) return;
    setCreating(true);
    setNewKeyFull(null);
    try {
      const res = await fetch(`${API_BASE}/v1/apikeys`, {
        method:  "POST",
        headers: { "Content-Type": "application/json", ...(await authHeaders()) },
        body:    JSON.stringify({ user_id: userId, name: newKeyName || null }),
      });
      if (res.ok) {
        const data = await res.json();
        setNewKeyFull(data.key);
        setNewKeyName("");
        await loadData();
      }
    } catch { /* ignore */ }
    setCreating(false);
  };

  const handleRevoke = async (keyId: string) => {
    if (!confirm("Revoke this API key? All integrations using it will stop working.")) return;
    setRevoking(keyId);
    try {
      const res = await fetch(
        `${API_BASE}/v1/apikeys/${keyId}?user_id=${userId}`,
        { method: "DELETE", headers: await authHeaders() },
      );
      if (res.ok) await loadData();
    } catch { /* ignore */ }
    setRevoking(null);
  };

  const copyKey = async () => {
    if (!newKeyFull) return;
    await navigator.clipboard.writeText(newKeyFull);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <main className="max-w-4xl mx-auto px-4 py-10 space-y-10">
      <Link href="/" className="text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white">
        ← Home
      </Link>

      {/* Header */}
      <header>
        <h1 className="text-2xl font-bold">
          RACE<span className="rj-brand-red">JUDGE</span>{" "}
          <span className="font-normal text-gray-600 dark:text-gray-400">API</span>
        </h1>
        <p className="text-sm text-gray-500 mt-1">
          Create and manage API keys. Access the RACEJUDGE dataset from any app or AI assistant.
        </p>
      </header>

      {/* Subscription card */}
      {sub && (
        <section className="border border-gray-200 dark:border-gray-800 rounded-lg p-5 space-y-3">
          <div className="flex items-center justify-between">
            <h2 className="font-semibold text-sm text-gray-900 dark:text-white">Your Plan</h2>
            <TierBadge tier={sub.tier} />
          </div>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Status</p>
              <p className="font-medium capitalize text-gray-900 dark:text-white">{sub.status}</p>
            </div>
            <div>
              <p className="text-xs text-gray-500 dark:text-gray-400">Daily request limit</p>
              <p className="font-medium text-gray-900 dark:text-white">
                {(TIER_LIMITS[sub.tier] ?? 100).toLocaleString()} / day
              </p>
            </div>
            {sub.current_period_end && (
              <div>
                <p className="text-xs text-gray-500 dark:text-gray-400">Renews</p>
                <p className="font-medium text-gray-900 dark:text-white">
                  {new Date(sub.current_period_end).toLocaleDateString()}
                </p>
              </div>
            )}
          </div>
          {sub.tier === "free" && sub.stripe_enabled && (
            <p className="text-xs text-gray-500 dark:text-gray-400 pt-1 border-t border-gray-100 dark:border-gray-800">
              Upgrade to Pro (£29/mo) for 10k requests/day, or Team (£499/mo) for 100k/day +
              Right-of-Review Builder.{" "}
              <a href="mailto:maruteymani31@gmail.com" className="text-blue-600 dark:text-blue-400 hover:underline">
                Contact us to upgrade →
              </a>
            </p>
          )}
          {!sub.stripe_enabled && (
            <p className="text-xs text-gray-400 dark:text-gray-600 pt-1 border-t border-gray-100 dark:border-gray-800">
              Billing not yet configured — all accounts on free tier until launch.
            </p>
          )}
        </section>
      )}

      {/* New key shown once */}
      {newKeyFull && (
        <div className="border border-green-400 dark:border-green-700 bg-green-50 dark:bg-green-950/30 rounded-lg p-5 space-y-3">
          <p className="text-sm font-semibold text-green-800 dark:text-green-300">
            Your new API key — copy it now. It will never be shown again.
          </p>
          <div className="flex items-center gap-2">
            <code className="flex-1 font-mono text-sm bg-white dark:bg-gray-900 border border-gray-200 dark:border-gray-700 rounded px-3 py-2 overflow-x-auto text-gray-900 dark:text-white">
              {newKeyFull}
            </code>
            <button
              type="button"
              onClick={copyKey}
              className="px-3 py-2 text-xs font-medium bg-green-600 hover:bg-green-700 text-white rounded transition-colors shrink-0"
            >
              {copied ? "Copied!" : "Copy"}
            </button>
          </div>
          <p className="text-xs text-green-700 dark:text-green-400">
            Use it in the{" "}
            <code className="font-mono">Authorization: Bearer {newKeyFull.slice(0, 16)}…</code>{" "}
            header.
          </p>
        </div>
      )}

      {/* Create key */}
      <section className="border border-gray-200 dark:border-gray-800 rounded-lg p-5 space-y-4">
        <h2 className="font-semibold text-sm text-gray-900 dark:text-white">Create a new API key</h2>
        <div className="flex gap-2">
          <input
            id="api-key-name"
            type="text"
            aria-label="Key name (optional)"
            placeholder="Key name (optional)"
            value={newKeyName}
            onChange={(e) => setNewKeyName(e.target.value)}
            className="flex-1 px-3 py-2 text-sm border border-gray-200 dark:border-gray-700 rounded bg-gray-50 dark:bg-gray-900 text-gray-900 dark:text-white placeholder-gray-400 dark:placeholder-gray-600"
            onKeyDown={(e) => e.key === "Enter" && handleCreate()}
          />
          <button
            type="button"
            onClick={handleCreate}
            disabled={creating}
            className="px-4 py-2 text-sm font-medium bg-gray-900 dark:bg-white text-white dark:text-gray-900 rounded hover:bg-gray-700 dark:hover:bg-gray-200 disabled:opacity-40 transition-colors"
          >
            {creating ? "Creating…" : "Create key"}
          </button>
        </div>
        <p className="text-xs text-gray-400 dark:text-gray-600">
          Keys have the format <code className="font-mono">rj_live_…</code>. The full key is shown once
          and cannot be retrieved later — store it securely.
        </p>
      </section>

      {/* Key list */}
      <section className="space-y-3">
        <h2 className="font-semibold text-sm text-gray-900 dark:text-white">Active keys</h2>
        {loading ? (
          <p role="status" aria-live="polite" className="text-sm text-gray-400 dark:text-gray-600">
            Loading…
          </p>
        ) : keys.length === 0 ? (
          <div className="border border-gray-200 dark:border-gray-800 rounded-lg p-8 text-center text-sm text-gray-400 dark:text-gray-600">
            No API keys yet. Create your first key above.
          </div>
        ) : (
          <div className="space-y-3">
            {keys.map((k) => (
              <div
                key={k.key_id}
                className="border border-gray-200 dark:border-gray-800 rounded-lg p-4 space-y-3"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0 space-y-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <code className="font-mono text-sm text-gray-900 dark:text-white">
                        {k.key_prefix}…
                      </code>
                      <TierBadge tier={k.tier} />
                      {k.name && (
                        <span className="text-xs text-gray-500 dark:text-gray-400">{k.name}</span>
                      )}
                    </div>
                    <p className="text-xs text-gray-400 dark:text-gray-600">
                      Created {new Date(k.created_at).toLocaleDateString()}
                      {k.last_used_at && (
                        <> · Last used {new Date(k.last_used_at).toLocaleDateString()}</>
                      )}
                      {" "}· {k.requests_total.toLocaleString()} total requests
                    </p>
                  </div>
                  <button
                    type="button"
                    onClick={() => handleRevoke(k.key_id)}
                    disabled={revoking === k.key_id}
                    className="text-xs text-red-500 hover:text-red-700 dark:hover:text-red-400 disabled:opacity-40 shrink-0 transition-colors"
                  >
                    {revoking === k.key_id ? "Revoking…" : "Revoke"}
                  </button>
                </div>
                <UsageBar used={k.requests_today} limit={k.daily_limit} />
              </div>
            ))}
          </div>
        )}
      </section>

      {/* API docs + MCP */}
      <section className="grid grid-cols-1 sm:grid-cols-2 gap-4">
        <div className="border border-gray-200 dark:border-gray-800 rounded-lg p-5 space-y-2">
          <h3 className="font-semibold text-sm text-gray-900 dark:text-white">REST API docs</h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Browse all available endpoints, request schemas, and example responses.
          </p>
          <a
            href={`${API_BASE}/docs`}
            target="_blank"
            rel="noreferrer"
            className="inline-block text-xs font-medium text-blue-600 dark:text-blue-400 hover:underline"
          >
            Open Swagger UI →
          </a>
        </div>

        <div className="border border-gray-200 dark:border-gray-800 rounded-lg p-5 space-y-2">
          <h3 className="font-semibold text-sm text-gray-900 dark:text-white">MCP server</h3>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            Connect any MCP-compatible AI assistant (Claude, ChatGPT) to RACEJUDGE.
          </p>
          <code className="block text-xs font-mono bg-gray-100 dark:bg-gray-800 rounded px-2 py-1 text-gray-700 dark:text-gray-300">
            {API_BASE}/mcp/v1/manifest
          </code>
        </div>
      </section>

      {/* Quick-start */}
      <section className="border border-gray-200 dark:border-gray-800 rounded-lg p-5 space-y-3">
        <h2 className="font-semibold text-sm text-gray-900 dark:text-white">Quick start</h2>
        <pre className="text-xs font-mono bg-gray-100 dark:bg-gray-900 rounded p-4 overflow-x-auto text-gray-800 dark:text-gray-300 leading-relaxed">
{`# Search precedents
curl -X POST ${API_BASE}/v1/search \\
  -H "Authorization: Bearer rj_live_YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"q": "forced wide at Turn 1", "limit": 5}'

# Predict penalty
curl -X POST ${API_BASE}/v1/predict \\
  -H "Authorization: Bearer rj_live_YOUR_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{"infraction_type": "forcing_off_track", "session_type": "Race"}'`}
        </pre>
      </section>
    </main>
  );
}
