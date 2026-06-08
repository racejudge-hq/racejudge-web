import Link from "next/link";
import type { Metadata } from "next";

export const metadata: Metadata = { title: "404 — Page not found" };

export default function NotFound() {
  return (
    <div className="min-h-screen flex flex-col items-center justify-center gap-6 px-4 text-center">
      <p className="text-7xl font-bold text-red-600 tabular-nums" aria-hidden="true">
        404
      </p>
      <h1 className="text-2xl font-semibold text-gray-900 dark:text-white">
        Page not found
      </h1>
      <p className="text-gray-500 dark:text-gray-400 max-w-sm">
        The stewards have reviewed this request and deemed the URL did not
        exist. No further action.
      </p>
      <Link
        href="/"
        className="mt-2 px-5 py-2 rounded bg-red-600 text-white text-sm font-medium hover:bg-red-700 transition-colors"
      >
        Return to home
      </Link>
    </div>
  );
}
