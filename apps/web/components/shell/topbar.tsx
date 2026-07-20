"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const PAGE_LABEL: { prefix: string; label: string }[] = [
  { prefix: "/ratings", label: "рейтинги" },
  { prefix: "/companies", label: "организации" },
  { prefix: "/organizations", label: "все филиалы" },
  { prefix: "/reviews", label: "отзывы" },
  { prefix: "/scrape-runs", label: "история сборов" },
  { prefix: "/jobs", label: "фоновые задачи" },
  { prefix: "/attention-rules", label: "правила внимания" },
  { prefix: "/http-scraper", label: "http-парсер" },
  { prefix: "/settings", label: "настройки" },
];

function currentPageLabel(pathname: string): string | null {
  if (pathname === "/overview") return null;
  const match = PAGE_LABEL.find((p) => pathname === p.prefix || pathname.startsWith(p.prefix + "/"));
  return match?.label ?? null;
}

export function Topbar() {
  const pathname = usePathname();
  const pageLabel = currentPageLabel(pathname);

  return (
    <div className="sticky top-0 z-10 flex items-center gap-4 border-b border-border bg-bg/90 px-8 py-4 backdrop-blur">
      <div className="font-mono text-xs uppercase tracking-widest text-text-faint">
        <Link href="/overview" className={pageLabel ? "hover:text-accent" : "text-accent"}>
          сеть
        </Link>
        {pageLabel ? (
          <>
            {" "}
            / <span className="text-accent">{pageLabel}</span>
          </>
        ) : null}
      </div>
    </div>
  );
}
