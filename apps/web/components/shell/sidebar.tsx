"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const NAV: { group: string; items: { href: string; label: string; icon: string }[] }[] = [
  {
    group: "Обзор",
    items: [{ href: "/overview", label: "Обзор сети", icon: "⚡" }],
  },
  {
    group: "Управление",
    items: [
      { href: "/companies", label: "Организации", icon: "🏢" },
      { href: "/organizations", label: "Все филиалы", icon: "📍" },
    ],
  },
  {
    group: "Аналитика",
    items: [
      { href: "/reviews", label: "Отзывы", icon: "💬" },
      { href: "/scrape-runs", label: "История сборов", icon: "🗂" },
      { href: "/http-scraper", label: "HTTP-парсер", icon: "🔧" },
    ],
  },
];

export function Sidebar() {
  const pathname = usePathname();
  return (
    <aside className="sticky top-0 flex h-screen w-60 flex-col border-r border-border bg-surface py-6">
      <div className="border-b border-border px-6 pb-6">
        <div className="flex items-center gap-2 font-display text-xl font-semibold tracking-tight">
          <span className="h-2 w-2 rounded-full bg-accent shadow-[0_0_12px_#d4ff3a]" />
          SERM Dashboard
        </div>
        <div className="mt-1 font-mono text-[11px] uppercase tracking-widest text-text-faint">
          Digital Marketing By SM
        </div>
      </div>
      <nav className="flex-1 px-3 pt-5">
        {NAV.map((group) => (
          <div key={group.group} className="mb-6">
            <div className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-widest text-text-faint">
              {group.group}
            </div>
            {group.items.map((item) => {
              const active = pathname === item.href || pathname.startsWith(item.href + "/");
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`mb-0.5 flex items-center gap-2.5 rounded-lg px-3 py-2.5 text-[13.5px] font-medium transition-colors ${
                    active
                      ? "bg-surface-2 text-accent"
                      : "text-text-dim hover:bg-surface-2 hover:text-text"
                  }`}
                >
                  <span className="inline-flex h-[18px] w-[18px] items-center justify-center">{item.icon}</span>
                  {item.label}
                </Link>
              );
            })}
          </div>
        ))}
      </nav>
    </aside>
  );
}
