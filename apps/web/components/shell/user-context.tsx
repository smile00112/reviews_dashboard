"use client";

import { createContext, useContext } from "react";
import type { CurrentUser } from "@/lib/types";

export const UserContext = createContext<CurrentUser | null>(null);

export function useCurrentUser(): CurrentUser | null {
  return useContext(UserContext);
}

export function useIsAdmin(): boolean {
  return useCurrentUser()?.role === "admin";
}
