"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";

import { api, type CookProfile, type CookReviewPage, type OrderPage } from "@/lib/api";
import { useNotifications } from "@/lib/notifications";

/** How often the panel re-counts the requests waiting for an answer. */
const REQUESTS_REFRESH_MS = 30_000;

type Kitchen = {
  /** The signed-in cook's profile (GET /api/cooks/me); null while loading. */
  profile: CookProfile | null;
  /** Orders waiting for accept/reject (status placed); null while loading. */
  requests: number | null;
  /** Reviews of my dishes still waiting for a reply; null while loading. */
  unrepliedReviews: number | null;
  /** Re-count requests + unanswered reviews - call after answering either. */
  refresh: () => Promise<void>;
  /** Apply the answer of a PATCH /api/cooks/me. */
  setProfile: (profile: CookProfile) => void;
};

const KitchenContext = createContext<Kitchen | null>(null);

/**
 * State shared by every /cook/* page (rendered by the cook shell, so only
 * for cooks): the cook profile and the live counts of open requests and
 * unanswered reviews that badge the "Orders" and "Reviews" nav items. The
 * counts poll while the panel is open, and re-count at once when the kitchen
 * inbox's unread count rises (a new request or review arrived - the
 * notifications poll noticed it first).
 */
export function KitchenProvider({ children }: { children: ReactNode }) {
  const [profile, setProfile] = useState<CookProfile | null>(null);
  const [requests, setRequests] = useState<number | null>(null);
  const [unrepliedReviews, setUnrepliedReviews] = useState<number | null>(null);

  const refresh = useCallback(async () => {
    // Keep the last known counts on failure; the pages show their own errors.
    await Promise.all([
      api
        .get<OrderPage>("/cooks/me/orders?status=placed&limit=1")
        .then((page) => setRequests(page.total))
        .catch(() => undefined),
      api
        .get<CookReviewPage>("/cooks/me/reviews?replied=false&limit=1")
        .then((page) => setUnrepliedReviews(page.unreplied))
        .catch(() => undefined),
    ]);
  }, []);

  useEffect(() => {
    // Timeout kick-off: no synchronous setState in the effect body
    // (react-hooks/set-state-in-effect).
    const kickOff = window.setTimeout(() => {
      void refresh();
      void api
        .get<CookProfile>("/cooks/me")
        .then(setProfile)
        .catch(() => undefined);
    }, 0);
    const timer = window.setInterval(() => void refresh(), REQUESTS_REFRESH_MS);
    return () => {
      window.clearTimeout(kickOff);
      window.clearInterval(timer);
    };
  }, [refresh]);

  const unread = useNotifications().counts?.cook;
  const lastUnread = useRef<number | undefined>(undefined);
  useEffect(() => {
    const previous = lastUnread.current;
    lastUnread.current = unread;
    if (previous === undefined || unread === undefined || unread <= previous) return;
    const kickOff = window.setTimeout(() => void refresh(), 0);
    return () => window.clearTimeout(kickOff);
  }, [unread, refresh]);

  return (
    <KitchenContext.Provider value={{ profile, requests, unrepliedReviews, refresh, setProfile }}>
      {children}
    </KitchenContext.Provider>
  );
}

export function useKitchen(): Kitchen {
  const kitchen = useContext(KitchenContext);
  if (!kitchen) throw new Error("useKitchen must be used inside <KitchenProvider> (the /cook shell)");
  return kitchen;
}
