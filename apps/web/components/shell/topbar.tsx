"use client";

import { useRouter } from "next/navigation";
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
  review_operator: "Оператор · только чтение",
};

export function Topbar({ user }: { user: CurrentUser }) {
  const router = useRouter();

  async function handleLogout() {
    try {
      await logout();
    } finally {
      router.replace("/login");
    }
  }

  return (
    <div className="sticky top-0 z-10 flex items-center gap-4 border-b border-border bg-bg/90 px-8 py-4 backdrop-blur">
      <div className="font-mono text-xs uppercase tracking-widest text-text-faint">
        сеть / <span className="text-accent">панель управления</span>
      </div>
      <div className="ml-auto flex items-center gap-3">
        <div className="flex items-center gap-2.5 rounded-lg bg-surface-2 px-3 py-1.5">
          <div className="flex h-8 w-8 items-center justify-center rounded-full bg-gradient-to-br from-accent to-[#7a9020] text-[13px] font-bold text-bg">
            {initials(user.name)}
          </div>
          <div className="min-w-0">
            <div className="text-[13px] font-semibold leading-tight">{user.name}</div>
            <div className="text-[11px] text-text-faint">{ROLE_LABEL[user.role] ?? user.role}</div>
          </div>
        </div>
        <button
          type="button"
          onClick={handleLogout}
          className="rounded-lg border border-border bg-surface-2 px-3.5 py-2 text-[13px] font-medium text-text hover:bg-surface-3"
        >
          Выйти
        </button>
      </div>
    </div>
  );
}
