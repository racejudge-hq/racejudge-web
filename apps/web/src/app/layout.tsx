import type { Metadata } from "next";
import Link from "next/link";
import { ThemeProvider } from "@/components/ThemeProvider";
import { ThemeToggle } from "@/components/ThemeToggle";
import "./globals.css";

export const metadata: Metadata = {
  title: "RACEJUDGE — The Stewards' Precedent Engine",
  description:
    "Every F1 stewards' decision, searchable, comparable, and explainable. Precedent search, penalty prediction, and consistency analysis.",
};

const Nav = () => (
  <nav className="border-b border-gray-200 dark:border-gray-900 px-4 py-3 flex items-center gap-5 text-xs text-gray-500 dark:text-gray-600 flex-wrap">
    <Link href="/" className="font-bold text-gray-900 dark:text-white text-sm tracking-tight shrink-0">
      RACE<span className="rj-brand-red">JUDGE</span>
    </Link>
    <Link href="/decisions"   className="hover:text-gray-900 dark:hover:text-white transition-colors">Decisions</Link>
    <Link href="/precedents"  className="hover:text-gray-900 dark:hover:text-white transition-colors">Precedents</Link>
    <Link href="/predict"     className="hover:text-gray-900 dark:hover:text-white transition-colors">Predict</Link>
    <Link href="/consistency" className="hover:text-gray-900 dark:hover:text-white transition-colors">Consistency</Link>
    <Link href="/guidelines"  className="hover:text-gray-900 dark:hover:text-white transition-colors">Guidelines</Link>
    <Link href="/live"        className="hover:text-gray-900 dark:hover:text-white transition-colors">Live</Link>
    <div className="ml-auto flex items-center gap-3">
      <Link href="/annotate" className="hover:text-gray-900 dark:hover:text-white transition-colors">Annotate</Link>
      <ThemeToggle />
    </div>
  </nav>
);

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";
  const hasClerk = /^pk_(test|live)_\w{20,}$/.test(clerkKey);

  if (hasClerk) {
    const { ClerkProvider } = await import("@clerk/nextjs");
    return (
      <ClerkProvider>
        <html lang="en" suppressHydrationWarning>
          <body>
            <ThemeProvider>
              <Nav />
              {children}
            </ThemeProvider>
          </body>
        </html>
      </ClerkProvider>
    );
  }

  return (
    <html lang="en" suppressHydrationWarning>
      <body>
        <ThemeProvider>
          <Nav />
          {children}
        </ThemeProvider>
      </body>
    </html>
  );
}
