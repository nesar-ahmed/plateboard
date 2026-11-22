"use client";

import { createContext, useCallback, useContext, useEffect, useState, type ReactNode } from "react";

import { api, ApiError, type Favourite, type FavouritePage } from "@/lib/api";
import { useSession } from "@/lib/session";

/**
 * One request loads the whole list: the backend keeps at most
 * `max_favourites` (50) per account, below its page-size cap of 100.
 */
const LIST_PATH = "/me/favourites?limit=100";

type Loaded = {
  /** Whose list this is - a sign-out or account switch never shows another's. */
  userId: string;
  items: Favourite[];
  max: number;
};

type FavouritesState = {
  /**
   * Only signed-in customers keep favourites (a cook is a customer too; an
   * admin-only account is not). Guests see the heart too - it asks them to
   * log in.
   */
  enabled: boolean;
  /** The saved dishes, newest first; null while loading (and when not `enabled`). */
  items: Favourite[] | null;
  /** How many dishes the list may hold (from the API). */
  max: number | null;
  /** The last load failed (the list page shows it). */
  error: string | null;
  isSaved: (dishId: string) => boolean;
  /** Save / remove one dish; both throw `ApiError` (the caller shows it). */
  save: (dishId: string) => Promise<void>;
  remove: (dishId: string) => Promise<void>;
  /**
   * The available dish removed last, for "Undo" - a hidden one cannot be
   * saved again, so removing it is final (the list page asks first).
   */
  lastRemoved: Favourite | null;
  undoRemove: () => Promise<void>;
  clearLastRemoved: () => void;
  /** Re-read the list (after the cook may have hidden or published a dish). */
  reload: () => Promise<void>;
};

const FavouritesContext = createContext<FavouritesState | null>(null);

/**
 * The signed-in customer's favourite dishes for the whole app: every heart
 * (dish cards, the dish page) and the /account/favourites list read this one
 * copy, so saving anywhere shows everywhere at once. Mutations apply the
 * API's answer - no optimistic guessing, like the cart: `PUT` answers the
 * saved favourite, `DELETE` a 204. Loaded when the signed-in user changes;
 * the list page reloads it on every visit.
 */
export function FavouritesProvider({ children }: { children: ReactNode }) {
  const { user } = useSession();
  const userId = user?.id ?? null;
  const enabled = !!user && user.roles.includes("customer");
  const [state, setState] = useState<Loaded | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [lastRemoved, setLastRemoved] = useState<{ userId: string; favourite: Favourite } | null>(null);

  const reload = useCallback(async () => {
    if (!enabled || !userId) return;
    try {
      const page = await api.get<FavouritePage>(LIST_PATH);
      setState({ userId, items: page.items, max: page.max_favourites });
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not reach the API");
    }
  }, [enabled, userId]);

  useEffect(() => {
    // Timeout kick-off: no synchronous setState in the effect body
    // (react-hooks/set-state-in-effect).
    const kickOff = window.setTimeout(() => void reload(), 0);
    return () => window.clearTimeout(kickOff);
  }, [reload]);

  const current = enabled && state && state.userId === userId ? state : null;

  const save = useCallback(
    async (dishId: string) => {
      if (!userId) return;
      const saved = await api.put<Favourite>(`/me/favourites/${dishId}`, {});
      setState((previous) => {
        if (!previous || previous.userId !== userId) return previous;
        // Newly saved goes first (newest first); already saved keeps its place.
        const known = previous.items.some((item) => item.dish.id === dishId);
        const items = known
          ? previous.items.map((item) => (item.dish.id === dishId ? saved : item))
          : [saved, ...previous.items];
        return { ...previous, items };
      });
    },
    [userId],
  );

  const remove = useCallback(
    async (dishId: string) => {
      if (!userId) return;
      const removed = current?.items.find((item) => item.dish.id === dishId) ?? null;
      await api.delete<void>(`/me/favourites/${dishId}`);
      setState((previous) =>
        previous && previous.userId === userId
          ? { ...previous, items: previous.items.filter((item) => item.dish.id !== dishId) }
          : previous,
      );
      setLastRemoved(removed?.available ? { userId, favourite: removed } : null);
    },
    [current, userId],
  );

  const clearLastRemoved = useCallback(() => setLastRemoved(null), []);

  const undone = lastRemoved && lastRemoved.userId === userId ? lastRemoved.favourite : null;

  const value: FavouritesState = {
    enabled,
    items: current?.items ?? null,
    max: current?.max ?? null,
    error: enabled ? error : null,
    isSaved: (dishId) => !!current?.items.some((item) => item.dish.id === dishId),
    save,
    remove,
    lastRemoved: undone,
    undoRemove: async () => {
      if (!undone) return;
      await save(undone.dish.id);
      setLastRemoved(null);
    },
    clearLastRemoved,
    reload,
  };

  return <FavouritesContext.Provider value={value}>{children}</FavouritesContext.Provider>;
}

export function useFavourites(): FavouritesState {
  const favourites = useContext(FavouritesContext);
  if (!favourites) throw new Error("useFavourites must be used inside <FavouritesProvider>");
  return favourites;
}
