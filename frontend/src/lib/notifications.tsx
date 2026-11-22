"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, type AppNotification, type NotificationAudience, type UnreadCounts } from "@/lib/api";
import { useSession } from "@/lib/session";

/** How often the unread counts are re-read while the tab is visible. */
const UNREAD_REFRESH_MS = 30_000;

type NotificationsState = {
  /** Unread per panel inbox; null while signed out or before the first answer. */
  counts: UnreadCounts | null;
  /** Re-read the counts now (after an action that may have notified the user). */
  refresh: () => Promise<void>;
  /** Mark one notification read / unread again; answers the updated notification. */
  setRead: (id: string, read: boolean) => Promise<AppNotification>;
  /**
   * Mark every unread notification of `audience` read - only those created at
   * or before `before` (the newest one the user saw), so one that arrives
   * meanwhile stays unread. Answers how many changed.
   */
  markAllRead: (audience: NotificationAudience, before?: string) => Promise<number>;
  /** Dismiss one notification for good. */
  dismiss: (id: string) => Promise<void>;
};

const NotificationsContext = createContext<NotificationsState | null>(null);

/**
 * The signed-in user's unread notification counts, for every badge (the
 * header bell, the panel nav), plus the inbox actions that change them - so
 * after any action every badge shows the server's new count.
 *
 * Counts poll every 30 s while the tab is visible, and refresh when the tab
 * comes back into view; the inbox pages read their own lists. The counts are
 * stored with the user they belong to, so a sign-out (or switching accounts)
 * never shows the previous user's numbers - not even for one render.
 */
export function NotificationsProvider({ children }: { children: ReactNode }) {
  const { user } = useSession();
  const userId = user?.id ?? null;
  const [state, setState] = useState<{ userId: string; counts: UnreadCounts } | null>(null);

  const refresh = useCallback(async () => {
    if (!userId) return;
    try {
      const counts = await api.get<UnreadCounts>("/me/notifications/unread-count");
      setState({ userId, counts });
    } catch {
      // Keep the last known counts; the inbox pages show their own errors.
    }
  }, [userId]);

  useEffect(() => {
    if (!userId) return;
    const whenVisible = () => {
      if (document.visibilityState === "visible") void refresh();
    };
    // Timeout kick-off: no synchronous setState in the effect body
    // (react-hooks/set-state-in-effect).
    const kickOff = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(whenVisible, UNREAD_REFRESH_MS);
    document.addEventListener("visibilitychange", whenVisible);
    window.addEventListener("focus", whenVisible);
    return () => {
      window.clearTimeout(kickOff);
      window.clearInterval(timer);
      document.removeEventListener("visibilitychange", whenVisible);
      window.removeEventListener("focus", whenVisible);
    };
  }, [userId, refresh]);

  const setRead = useCallback(
    async (id: string, read: boolean) => {
      const updated = await api.patch<AppNotification>(`/me/notifications/${id}`, { read });
      void refresh();
      return updated;
    },
    [refresh],
  );

  const markAllRead = useCallback(
    async (audience: NotificationAudience, before?: string) => {
      const { marked } = await api.post<{ marked: number }>("/me/notifications/read-all", {
        audience,
        ...(before ? { before } : {}),
      });
      void refresh();
      return marked;
    },
    [refresh],
  );

  const dismiss = useCallback(
    async (id: string) => {
      await api.delete<void>(`/me/notifications/${id}`);
      void refresh();
    },
    [refresh],
  );

  const counts = state && state.userId === userId ? state.counts : null;
  return (
    <NotificationsContext.Provider value={{ counts, refresh, setRead, markAllRead, dismiss }}>
      {children}
    </NotificationsContext.Provider>
  );
}

export function useNotifications(): NotificationsState {
  const state = useContext(NotificationsContext);
  if (!state) throw new Error("useNotifications must be used inside <NotificationsProvider>");
  return state;
}
