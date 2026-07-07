"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useRouter } from "next/navigation";
import { getMe } from "@/lib/api";
import type { CurrentUser } from "@/lib/types";
import { UserContext } from "./user-context";
import { Sidebar } from "./sidebar";
import { Topbar } from "./topbar";

/**
 * Client shell that enforces authentication for every dashboard page:
 * calls GET /api/auth/me on mount and redirects to /login on 401.
 * Middleware provides the fast cookie-presence redirect; this is the
 * authoritative check and also supplies the current user (role) to children.
 */
export function DashboardShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [user, setUser] = useState<CurrentUser | null>(null);
  const [state, setState] = useState<"loading" | "ready" | "denied">("loading");

  useEffect(() => {
    let cancelled = false;
    getMe()
      .then((u) => {
        if (cancelled) return;
        setUser(u);
        setState("ready");
      })
      .catch(() => {
        if (cancelled) return;
        setState("denied");
        router.replace("/login");
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (state !== "ready" || !user) {
    return (
      <div className="flex min-h-screen items-center justify-center text-text-faint">
        {state === "denied" ? "Перенаправление…" : "Загрузка…"}
      </div>
    );
  }

  return (
    <UserContext.Provider value={user}>
      <div className="grid min-h-screen grid-cols-[240px_1fr]">
        <Sidebar />
        <main className="min-w-0">
          <Topbar user={user} />
          <div className="px-8 py-7">{children}</div>
        </main>
      </div>
    </UserContext.Provider>
  );
}
