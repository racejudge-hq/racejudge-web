"use client";

import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";

const API_BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

type Status = "idle" | "unsupported" | "subscribed" | "denied" | "working";

function urlBase64ToUint8Array(base64String: string): BufferSource {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  const buffer = new ArrayBuffer(raw.length);
  const arr = new Uint8Array(buffer);
  for (let i = 0; i < raw.length; i++) arr[i] = raw.charCodeAt(i);
  return arr;
}

export default function NotificationOptIn() {
  const [status, setStatus] = useState<Status>("idle");

  useEffect(() => {
    if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
      setStatus("unsupported");
      return;
    }
    if (Notification.permission === "denied") setStatus("denied");
    navigator.serviceWorker.getRegistration().then(async (reg) => {
      const sub = await reg?.pushManager.getSubscription();
      if (sub) setStatus("subscribed");
    });
  }, []);

  async function subscribe() {
    try {
      setStatus("working");
      const reg = await navigator.serviceWorker.register("/sw.js");
      await navigator.serviceWorker.ready;

      const permission = await Notification.requestPermission();
      if (permission !== "granted") {
        setStatus("denied");
        return;
      }

      const res = await fetch(`${API_BASE}/v1/push/vapid-public-key`);
      if (!res.ok) throw new Error("vapid key unavailable");
      const { publicKey } = await res.json();

      const sub = await reg.pushManager.subscribe({
        userVisibleOnly: true,
        applicationServerKey: urlBase64ToUint8Array(publicKey),
      });

      await fetch(`${API_BASE}/v1/push/subscribe`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(sub),
      });
      setStatus("subscribed");
    } catch {
      setStatus("idle");
    }
  }

  if (status === "unsupported") return null;
  if (status === "subscribed") {
    return (
      <p className="text-xs text-gray-500 dark:text-gray-400">
        🔔 You&apos;ll be notified of new decisions.
      </p>
    );
  }

  return (
    <Button variant="outline" size="sm" onClick={subscribe} disabled={status === "working"}>
      {status === "working"
        ? "Enabling…"
        : status === "denied"
          ? "Notifications blocked in browser"
          : "🔔 Notify me of new decisions"}
    </Button>
  );
}
