"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, type User } from "@/lib/api";

type Session = {
  /** The signed-in user, or null for guests (and while `checked` is false). */
  user: User | null;
  /** False until the first GET /api/me has answered. */
  checked: boolean;
  /** Re-read GET /api/me - call after login/logout. */
  refresh: () => Promise<User | null>;
};

const SessionContext = createContext<Session | null>(null);

/**
 * Who is signed in, shared by the nav, the cart and the pages that care.
 * Any failure of GET /api/me (401, backend down) simply means "guest".
 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [checked, setChecked] = useState(false);

  const refresh = useCallback(async () => {
    let next: User | null = null;
    try {
      next = await api.get<User>("/me");
    } catch {
      next = null;
    }
    setUser(next);
    setChecked(true);
    return next;
  }, []);

  useEffect(() => {
    const load = async () => {
      await refresh();
    };
    void load();
  }, [refresh]);

  return <SessionContext.Provider value={{ user, checked, refresh }}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (!session) throw new Error("useSession must be used inside <SessionProvider>");
  return session;
}

/**
 * A post-login destination from `?next=`, accepted only if it is a path on
 * this site ("/checkout"), never an absolute or protocol-relative URL
 * ("https://evil.example", "//evil.example") - no open redirects.
 */
export function safeNextPath(next: string | null, fallback = "/dashboard"): string {
  if (!next || !next.startsWith("/") || next.startsWith("//") || next.startsWith("/\\")) {
    return fallback;
  }
  return next;
}
