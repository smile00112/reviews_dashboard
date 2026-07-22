"use client";

import { createContext, useContext } from "react";
import type { CurrentUser, PermissionKey } from "@/lib/types";

export const UserContext = createContext<CurrentUser | null>(null);

export function useCurrentUser(): CurrentUser | null {
  return useContext(UserContext);
}

export function useIsAdmin(): boolean {
  return useCurrentUser()?.role?.slug === "admin";
}

/** True if the current user holds `permission` (mirrors the backend; UX only). */
export function useCan(permission: PermissionKey): boolean {
  const user = useCurrentUser();
  return Boolean(user?.permissions?.includes(permission));
}

/** True if the current user may access the page identified by `name` (e.g. "reviews"). */
export function useCanPage(name: string): boolean {
  return useCan(`page:${name}`);
}
