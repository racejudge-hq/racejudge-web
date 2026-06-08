"use client";

import { useEffect, useState } from "react";

const STORAGE_KEY = "rj-cookie-consent";

type Consent = "accepted" | "declined";

export function CookieConsent() {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    try {
      if (!localStorage.getItem(STORAGE_KEY)) {
        setVisible(true);
      }
    } catch {
      // localStorage unavailable (private browsing, iframe) — don't show
    }
  }, []);

  if (!visible) return null;

  const save = (choice: Consent) => {
    try {
      localStorage.setItem(STORAGE_KEY, choice);
    } catch {
      // ignore
    }
    setVisible(false);
  };

  return (
    <div
      role="dialog"
      aria-live="polite"
      aria-label="Cookie consent"
      className="fixed bottom-0 inset-x-0 z-50 p-4 sm:p-6"
    >
      <div className="mx-auto max-w-3xl rounded-xl border border-gray-200 dark:border-gray-800 bg-white dark:bg-gray-950 shadow-xl px-5 py-4 flex flex-col sm:flex-row items-start sm:items-center gap-4">
        <p className="flex-1 text-sm text-gray-600 dark:text-gray-400 leading-relaxed">
          RACEJUDGE uses cookies only for authentication and essential site
          function. No advertising or cross-site tracking. See{" "}
          <a
            href="/legal"
            className="underline underline-offset-2 hover:text-gray-900 dark:hover:text-white transition-colors"
          >
            Legal & Privacy
          </a>
          .
        </p>
        <div className="flex items-center gap-2 shrink-0">
          <button
            type="button"
            onClick={() => save("declined")}
            className="px-4 py-1.5 text-sm rounded border border-gray-200 dark:border-gray-700 text-gray-600 dark:text-gray-400 hover:bg-gray-100 dark:hover:bg-gray-900 transition-colors"
          >
            Decline
          </button>
          <button
            type="button"
            onClick={() => save("accepted")}
            className="px-4 py-1.5 text-sm rounded bg-gray-900 dark:bg-white text-white dark:text-gray-900 hover:bg-gray-700 dark:hover:bg-gray-200 transition-colors font-medium"
          >
            Accept
          </button>
        </div>
      </div>
    </div>
  );
}
