import type { Metadata } from "next";
import { CookieConsent } from "@/components/CookieConsent";
import { Nav } from "@/components/Nav";
import { ThemeProvider } from "@/components/ThemeProvider";
import "./globals.css";
import { Geist } from "next/font/google";
import { cn } from "@/lib/utils";

const geist = Geist({subsets:['latin'],variable:'--font-sans'});

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://racejudge.com";

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: "RACEJUDGE — The Stewards' Precedent Engine",
    template: "%s | RACEJUDGE",
  },
  description:
    "Every F1 stewards' decision, searchable, comparable, and explainable. Precedent search, penalty prediction, and consistency analysis.",
  openGraph: {
    type:        "website",
    siteName:    "RACEJUDGE",
    title:       "RACEJUDGE — The Stewards' Precedent Engine",
    description: "Every F1 stewards' decision, searchable, comparable, and explainable.",
    url:         SITE_URL,
    // OG image is generated dynamically by app/opengraph-image.tsx (1200×630)
  },
  twitter: {
    card:        "summary_large_image",
    title:       "RACEJUDGE — The Stewards' Precedent Engine",
    description: "Every F1 stewards' decision, searchable, comparable, and explainable.",
  },
};

export default async function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const clerkKey = process.env.NEXT_PUBLIC_CLERK_PUBLISHABLE_KEY ?? "";
  const hasClerk = /^pk_(test|live)_\w{20,}$/.test(clerkKey);

  const body = (
    <html lang="en" suppressHydrationWarning className={cn("font-sans", geist.variable)}>
      <body>
        <a
          href="#main-content"
          className="sr-only focus:not-sr-only focus:absolute focus:z-50 focus:top-2 focus:left-2 focus:px-4 focus:py-2 focus:bg-red-600 focus:text-white focus:rounded"
        >
          Skip to content
        </a>
        <ThemeProvider>
          <Nav />
          <main id="main-content" tabIndex={-1}>
            {children}
          </main>
          <CookieConsent />
        </ThemeProvider>
      </body>
    </html>
  );

  if (hasClerk) {
    const { ClerkProvider } = await import("@clerk/nextjs");
    return <ClerkProvider>{body}</ClerkProvider>;
  }

  return body;
}
