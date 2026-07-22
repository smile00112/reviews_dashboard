"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { logout } from "@/lib/api";
import type { CurrentUser } from "@/lib/types";

function initials(name: string): string {
  return name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((p) => p[0]?.toUpperCase() ?? "")
    .join("");
}

const ROLE_LABEL: Record<string, string> = {
  admin: "Админ · полный доступ",
  call_center: "Колл-центр",
  manager: "Менеджер",
};

type NavItem = { href: string; label: string; icon: string; page: string };

const NAV: { group: string; items: NavItem[] }[] = [
  {
    group: "Обзор",
    items: [
      { href: "/overview", label: "Обзор сети", icon: "⚡", page: "overview" },
      { href: "/ratings", label: "Рейтинги", icon: "⭐", page: "ratings" },
    ],
  },
  {
    group: "Управление",
    items: [
      { href: "/companies", label: "Организации", icon: "🏢", page: "companies" },
      { href: "/organizations", label: "Все филиалы", icon: "📍", page: "organizations" },
    ],
  },
  {
    group: "Аналитика",
    items: [
      { href: "/reviews", label: "Отзывы", icon: "💬", page: "reviews" },
      { href: "/scrape-runs", label: "История сборов", icon: "🗂", page: "scrape_runs" },
      { href: "/jobs", label: "Фоновые задачи", icon: "⏱", page: "jobs" },
      { href: "/attention-rules", label: "Правила внимания", icon: "⚡", page: "attention_rules" },
      { href: "/http-scraper", label: "HTTP-парсер", icon: "🔧", page: "http_scraper" },
    ],
  },
  {
    group: "Система",
    items: [
      { href: "/settings", label: "Настройки", icon: "⚙", page: "settings" },
      { href: "/settings/roles", label: "Роли и доступ", icon: "🔑", page: "roles" },
    ],
  },
];

export function Sidebar({ user }: { user: CurrentUser }) {
  const pathname = usePathname();
  const router = useRouter();

  async function handleLogout() {
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

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
        {NAV.map((group) => {
          const items = group.items.filter((item) =>
            user.permissions.includes(`page:${item.page}`),
          );
          if (items.length === 0) return null;
          return (
          <div key={group.group} className="mb-6">
            <div className="mb-2 px-3 text-[10px] font-semibold uppercase tracking-widest text-text-faint">
              {group.group}
            </div>
            {items.map((item) => {
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
          );
        })}
      </nav>
      <div className="mt-auto border-t border-border px-3 pt-4">
        <div className="mb-2 flex items-center gap-2.5 rounded-lg bg-surface-2 px-3 py-1.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-accent to-[#7a9020] text-[13px] font-bold text-bg">
            {initials(user.name)}
          </div>
          <div className="min-w-0">
            <div className="truncate text-[13px] font-semibold leading-tight">{user.name}</div>
            <div className="text-[11px] text-text-faint">{ROLE_LABEL[user.role.slug] ?? user.role.name}</div>
          </div>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="w-full rounded-lg border border-border bg-surface-2 px-3.5 py-2 text-[13px] font-medium text-text hover:bg-surface-3"
        >
          Выйти
        </button>
      </div>
    </aside>
  );
}
