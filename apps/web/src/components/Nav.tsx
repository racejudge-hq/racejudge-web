"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { ThemeToggle } from "@/components/ThemeToggle";

const MAIN_LINKS = [
  { href: "/decisions",   label: "Decisions"   },
  { href: "/precedents",  label: "Precedents"  },
  { href: "/predict",     label: "Predict"     },
  { href: "/consistency", label: "Consistency" },
  { href: "/guidelines",  label: "Guidelines"  },
  { href: "/live",        label: "Live"        },
  { href: "/review",      label: "Review"      },
] as const;

const SECONDARY_LINKS = [
  { href: "/annotate", label: "Annotate" },
  { href: "/api",      label: "API"      },
] as const;

export function Nav() {
  const pathname = usePathname();

  const isCurrent = (href: string) =>
    href === "/" ? pathname === "/" : pathname.startsWith(href);

  return (
    <nav
      aria-label="Main navigation"
      className="border-b border-gray-200 dark:border-gray-900 px-4 py-3 flex items-center gap-5 text-xs text-gray-500 dark:text-gray-600 flex-wrap"
    >
      <Link
        href="/"
        aria-label="RACEJUDGE — home"
        className="font-bold text-gray-900 dark:text-white text-sm tracking-tight shrink-0"
      >
        RACE<span className="rj-brand-red">JUDGE</span>
      </Link>

      {MAIN_LINKS.map(({ href, label }) => (
        <Link
          key={href}
          href={href}
          aria-current={isCurrent(href) ? "page" : undefined}
          className="hover:text-gray-900 dark:hover:text-white transition-colors aria-[current=page]:text-gray-900 dark:aria-[current=page]:text-white"
        >
          {label}
        </Link>
      ))}

      <div className="ml-auto flex items-center gap-3">
        {SECONDARY_LINKS.map(({ href, label }) => (
          <Link
            key={href}
            href={href}
            aria-current={isCurrent(href) ? "page" : undefined}
            className="hover:text-gray-900 dark:hover:text-white transition-colors aria-[current=page]:text-gray-900 dark:aria-[current=page]:text-white"
          >
            {label}
          </Link>
        ))}
        <ThemeToggle />
      </div>
    </nav>
  );
}
