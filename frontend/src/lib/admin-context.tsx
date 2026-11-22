"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, type CookApplicationPage } from "@/lib/api";

/** How often the panel re-counts the cook applications waiting for review. */
const PENDING_REFRESH_MS = 30_000;

type AdminPanel = {
  /** Cook applications waiting for a decision; null while loading. */
  pendingApplications: number | null;
  /** Re-count them - call after accepting/rejecting one. */
  refresh: () => Promise<void>;
};

const AdminContext = createContext<AdminPanel | null>(null);

/**
 * State shared by every /admin/* page (rendered by the admin shell, so only
 * for admins): the live count of pending cook applications that badges the
 * "Cook applications" nav item - the admin panel's to-do, twin of the cook
 * panel's open-request count. It polls while the panel is open.
 */
export function AdminProvider({ children }: { children: ReactNode }) {
  const [pendingApplications, setPendingApplications] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    try {
      const page = await api.get<CookApplicationPage>("/admin/cook-applications?status=pending&limit=1");
      setPendingApplications(page.total);
    } catch {
      // Keep the last known count; the pages show their own errors.
    }
  }, []);

  useEffect(() => {
    // Timeout kick-off: no synchronous setState in the effect body
    // (react-hooks/set-state-in-effect).
    const kickOff = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(() => void refresh(), PENDING_REFRESH_MS);
    return () => {
      window.clearTimeout(kickOff);
      window.clearInterval(timer);
    };
  }, [refresh]);

  return <AdminContext.Provider value={{ pendingApplications, refresh }}>{children}</AdminContext.Provider>;
}

export function useAdminPanel(): AdminPanel {
  const panel = useContext(AdminContext);
  if (!panel) throw new Error("useAdminPanel must be used inside <AdminProvider> (the /admin shell)");
  return panel;
}
