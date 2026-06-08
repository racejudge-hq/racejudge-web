"use client";

import { useEffect } from "react";

interface ErrorBoundaryProps {
  error: Error & { digest?: string };
  reset: () => void;
}

export default function ErrorBoundary({ error, reset }: ErrorBoundaryProps) {
  useEffect(() => {
    // Forward to Sentry if the client SDK is configured
    if (typeof window !== "undefined" && (window as { Sentry?: { captureException: (e: unknown) => void } }).Sentry) {
      (window as { Sentry?: { captureException: (e: unknown) => void } }).Sentry!.captureException(error);
    }
  }, [error]);

  return (
    <div
      role="alert"
      className="min-h-screen flex flex-col items-center justify-center gap-6 px-4 text-center"
    >
      <p className="text-7xl font-bold text-red-600" aria-hidden="true">!</p>
      <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
        Something went wrong
      </h1>
      <p className="text-gray-500 dark:text-gray-400 max-w-sm">
        An unexpected error occurred. The incident has been logged.
        {error.digest && (
          <span className="block mt-1 font-mono text-xs">
            Ref: {error.digest}
          </span>
        )}
      </p>
      <button
        onClick={reset}
        className="mt-2 px-5 py-2 rounded bg-red-600 text-white text-sm font-medium hover:bg-red-700 transition-colors"
      >
        Try again
      </button>
    </div>
  );
}
