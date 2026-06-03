"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";
const WS_BASE  = API_BASE.replace(/^http/, "ws");

interface LiveMessage {
  type: string;
  session_key?: number;
  incident_id?: string;
  drivers?: { code: string; full_name?: string }[];
  infraction?: string;
  message?: string;
  flag?: string;
  timestamp: string;
  detail?: string;
}

interface Session {
  session_key: number;
  session_name: string;
  date_start: string;
  circuit: string;
  country: string;
}

type Transport = "ws" | "sse" | "none";

const FLAG_COLORS: Record<string, string> = {
  RED:    "text-red-500",
  YELLOW: "text-yellow-400",
  GREEN:  "text-green-500",
  BLUE:   "text-blue-400",
  BLACK:  "text-gray-700 dark:text-gray-300",
};

function MessageRow({ msg }: { msg: LiveMessage }) {
  const time = new Date(msg.timestamp).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

  if (msg.type === "ping") {
    return (
      <div className="flex items-center gap-3 py-1 text-xs text-gray-600 dark:text-gray-800 border-b border-gray-100 dark:border-gray-900">
        <span className="font-mono w-20 shrink-0">{time}</span>
        <span>— keepalive —</span>
      </div>
    );
  }

  if (msg.type === "warning" || msg.type === "error") {
    return (
      <div className="flex items-center gap-3 py-2 text-xs text-yellow-600 border-b border-gray-100 dark:border-gray-900">
        <span className="font-mono w-20 shrink-0">{time}</span>
        <span>{msg.detail ?? msg.message}</span>
      </div>
    );
  }

  const drivers = (msg.drivers ?? []).map((d) => d.code).join(" · ");
  const flagColor = msg.flag ? (FLAG_COLORS[msg.flag] ?? "text-gray-600 dark:text-gray-400") : "text-gray-600 dark:text-gray-400";

  return (
    <div className="flex items-start gap-3 py-2 border-b border-gray-100 dark:border-gray-900 hover:bg-white dark:hover:bg-gray-950 transition-colors">
      <span className="font-mono text-xs text-gray-400 dark:text-gray-600 w-20 shrink-0 pt-0.5">{time}</span>
      <div className="min-w-0 space-y-0.5">
        {drivers && <span className="text-xs font-mono text-gray-600 dark:text-gray-400">{drivers}</span>}
        <p className="text-sm text-gray-700 dark:text-gray-200">
          {msg.message ?? msg.infraction ?? msg.type}
        </p>
        {msg.flag && (
          <span className={`text-xs font-bold ${flagColor}`}>{msg.flag} FLAG</span>
        )}
      </div>
    </div>
  );
}

export default function LivePage() {
  const [sessions, setSessions]     = useState<Session[]>([]);
  const [sessionKey, setSessionKey] = useState<string>("");
  const [messages, setMessages]     = useState<LiveMessage[]>([]);
  const [connected, setConnected]   = useState(false);
  const [connecting, setConnecting] = useState(false);
  const [transport, setTransport]   = useState<Transport>("none");

  const wsRef  = useRef<WebSocket | null>(null);
  const esRef  = useRef<EventSource | null>(null);
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch(`${API_BASE}/v1/live/sessions`)
      .then((r) => r.ok ? r.json() : [])
      .then(setSessions)
      .catch(() => {});
  }, []);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const pushMsg = useCallback((data: LiveMessage) => {
    setMessages((prev) => [...prev.slice(-200), data]);
  }, []);

  const _connectSSE = useCallback((sk: string) => {
    const url = sk
      ? `${API_BASE}/v1/live/stream?session_key=${sk}`
      : `${API_BASE}/v1/live/stream`;

    const es = new EventSource(url);
    esRef.current = es;

    es.onopen = () => { setConnected(true); setConnecting(false); setTransport("sse"); };
    es.onerror = () => { setConnected(false); setConnecting(false); setTransport("none"); };
    es.onmessage = (evt) => {
      try {
        pushMsg(JSON.parse(evt.data) as LiveMessage);
      } catch { /* ignore */ }
    };
  }, [pushMsg]);

  const connect = useCallback(() => {
    // Close any existing connection
    wsRef.current?.close();
    esRef.current?.close();
    wsRef.current  = null;
    esRef.current  = null;

    setMessages([]);
    setConnecting(true);
    setTransport("none");

    const wsUrl = sessionKey
      ? `${WS_BASE}/v1/live?session_key=${sessionKey}`
      : `${WS_BASE}/v1/live`;

    const ws = new WebSocket(wsUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      setConnected(true);
      setConnecting(false);
      setTransport("ws");
    };

    ws.onerror = () => {
      // WS failed — fall back to SSE automatically
      ws.close();
      wsRef.current = null;
      pushMsg({
        type: "warning",
        detail: "WebSocket unavailable — falling back to SSE",
        timestamp: new Date().toISOString(),
      });
      _connectSSE(sessionKey);
    };

    ws.onclose = () => {
      if (transport === "ws") {
        setConnected(false);
        setConnecting(false);
        setTransport("none");
      }
    };

    ws.onmessage = (evt) => {
      try {
        pushMsg(JSON.parse(evt.data) as LiveMessage);
      } catch { /* ignore */ }
    };
  }, [sessionKey, transport, pushMsg, _connectSSE]);

  const disconnect = useCallback(() => {
    wsRef.current?.close();
    esRef.current?.close();
    wsRef.current  = null;
    esRef.current  = null;
    setConnected(false);
    setTransport("none");
  }, []);

  useEffect(() => () => {
    wsRef.current?.close();
    esRef.current?.close();
  }, []);

  const incidents = messages.filter(
    (m) => m.type === "incident_alert" || m.type === "race_control"
  );

  return (
    <main className="max-w-4xl mx-auto px-4 py-10 space-y-6">
      <Link href="/" className="text-sm text-gray-500 hover:text-gray-900 dark:hover:text-white">
        ← Home
      </Link>

      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold">
            RACE<span className="rj-brand-red">JUDGE</span>{" "}
            <span className="font-normal text-gray-600 dark:text-gray-400">Live</span>
          </h1>
          <p className="text-sm text-gray-500">
            Real-time incident stream — WebSocket with SSE fallback
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${
              connected
                ? "bg-green-500 animate-pulse"
                : connecting
                ? "bg-yellow-500 animate-pulse"
                : "bg-gray-700"
            }`}
          />
          <span className="text-xs text-gray-500">
            {connected
              ? `connected · ${transport.toUpperCase()}`
              : connecting
              ? "connecting…"
              : "disconnected"}
          </span>
        </div>
      </header>

      {/* Session selector + connect */}
      <div className="flex gap-2">
        <select
          aria-label="Session"
          value={sessionKey}
          onChange={(e) => setSessionKey(e.target.value)}
          className="flex-1 px-3 py-2 bg-gray-50 dark:bg-gray-900 border border-gray-200 dark:border-gray-800 rounded text-sm"
        >
          <option value="">All sessions</option>
          {sessions.map((s) => (
            <option key={s.session_key} value={s.session_key}>
              {s.circuit} — {s.session_name} ({s.date_start?.slice(0, 10)})
            </option>
          ))}
        </select>
        {connected ? (
          <button
            type="button"
            onClick={disconnect}
            className="px-4 py-2 border border-gray-300 dark:border-gray-700 rounded text-sm hover:border-red-700 text-red-400 transition-colors"
          >
            Disconnect
          </button>
        ) : (
          <button
            type="button"
            onClick={connect}
            disabled={connecting}
            className="px-4 py-2 bg-white text-black rounded text-sm font-medium hover:bg-gray-200 disabled:opacity-40"
          >
            {connecting ? "Connecting…" : "Connect"}
          </button>
        )}
      </div>

      {/* Stats */}
      {connected && (
        <div className="grid grid-cols-3 gap-3 text-center">
          {[
            { label: "Total messages", value: messages.length },
            { label: "Incidents",      value: incidents.length },
            { label: "Session",        value: sessionKey || "All" },
          ].map(({ label, value }) => (
            <div key={label} className="border border-gray-200 dark:border-gray-800 rounded p-3">
              <div className="text-lg font-mono font-bold">{value}</div>
              <div className="text-xs text-gray-400 dark:text-gray-600">{label}</div>
            </div>
          ))}
        </div>
      )}

      {/* Feed */}
      <div className="space-y-1">
        <div className="flex items-center justify-between text-xs text-gray-400 dark:text-gray-600 mb-2">
          <span>Live feed</span>
          {messages.length > 0 && (
            <button type="button" onClick={() => setMessages([])} className="hover:text-gray-900 dark:hover:text-white transition-colors">
              Clear
            </button>
          )}
        </div>
        <div className="border border-gray-200 dark:border-gray-800 rounded-lg overflow-hidden">
          {messages.length === 0 ? (
            <div className="p-8 text-center text-gray-400 dark:text-gray-600 text-sm">
              {connected
                ? "Waiting for messages…"
                : "Connect to a session to see live incident data."}
            </div>
          ) : (
            <div className="max-h-[500px] overflow-y-auto divide-y divide-gray-100 dark:divide-gray-900 px-4">
              {messages.map((m, i) => (
                <MessageRow key={i} msg={m} />
              ))}
              <div ref={bottomRef} />
            </div>
          )}
        </div>
      </div>

      <p className="text-xs text-gray-500 dark:text-gray-700">
        Connects via WebSocket first. Falls back to Server-Sent Events automatically if WebSocket
        is blocked. Both modes degrade to OpenF1 polling when Redis is unavailable.
      </p>
    </main>
  );
}
