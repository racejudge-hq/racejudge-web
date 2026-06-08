import type { Metadata } from "next";
import { Nav } from "@/components/Nav";
import { ThemeProvider } from "@/components/ThemeProvider";
import "./globals.css";

const SITE_URL = process.env.NEXT_PUBLIC_SITE_URL ?? "https://racejudge.com";
const OG_IMAGE  = `${SITE_URL}/og.png`;

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
    images: [
      {
        url:    OG_IMAGE,
        width:  1200,
        height: 630,
        alt:    "RACEJUDGE — F1 stewards' precedent engine",
      },
    ],
  },
  twitter: {
    card:        "summary_large_image",
    title:       "RACEJUDGE — The Stewards' Precedent Engine",
    description: "Every F1 stewards' decision, searchable, comparable, and explainable.",
    images:      [OG_IMAGE],
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
    <html lang="en" suppressHydrationWarning>
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
