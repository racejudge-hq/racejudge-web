import type { Metadata } from "next";
import Link from "next/link";
import { ClerkProvider } from "@clerk/nextjs";
import "./globals.css";

export const metadata: Metadata = {
  title: "RACEJUDGE — The Stewards' Precedent Engine",
  description:
    "Every F1 stewards' decision, searchable, comparable, and explainable. Precedent search, penalty prediction, and consistency analysis.",
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ClerkProvider>
      <html lang="en">
        <body>
          <nav className="border-b border-gray-900 px-4 py-3 flex items-center gap-6 text-xs text-gray-600">
            <Link href="/" className="font-bold text-white text-sm tracking-tight">
              RACE<span className="rj-brand-red">JUDGE</span>
            </Link>
            <Link href="/decisions" className="hover:text-white transition-colors">
              Decisions
            </Link>
            <Link href="/search" className="hover:text-white transition-colors">
              Search
            </Link>
            <Link href="/predict" className="hover:text-white transition-colors">
              Predict
            </Link>
            <Link href="/annotate" className="hover:text-white transition-colors ml-auto">
              Annotate
            </Link>
          </nav>
          {children}
        </body>
      </html>
    </ClerkProvider>
  );
}
