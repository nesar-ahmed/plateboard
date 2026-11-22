"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";

import { api, ApiError, type Cart, type DifferentCookDetails } from "@/lib/api";
import { useSession } from "@/lib/session";

/** What an "Add to cart" button knows about the dish it adds. */
export type CartDish = { id: string; name: string; cook_id: string; cook_name?: string | null };

/**
 * Where an add comes from: the menu (`POST /api/cart/items`) or the
 * customer's favourites (`POST /api/me/favourites/{id}/cart` - only for a
 * saved dish, 409 `dish_unavailable` while its cook hides it). Both answer
 * with the whole cart and share every cart rule, so the drawer treats them
 * alike.
 */
export type AddSource = "menu" | "favourites";

/** A refused add: the cart holds another cook's dishes (409 `different_cook`). */
export type CookConflict = {
  dish: CartDish;
  quantity: number;
  cartCookName: string | null;
  /** Retried the same way when the user starts a new cart. */
  source: AddSource;
};

type CartState = {
  /** Null until the first GET /api/cart answered. */
  cart: Cart | null;
  /** A cart request is in flight - controls disable themselves meanwhile. */
  busy: boolean;
  /** Lines of the last failed action (shown in the drawer). */
  errors: string[];
  drawerOpen: boolean;
  /** The element that opened the drawer - focus returns there on close. */
  openerRef: RefObject<HTMLElement | null>;
  /** Set when an add needs the user's OK to start a new cart. */
  conflict: CookConflict | null;
  openDrawer: () => void;
  closeDrawer: () => void;
  /** Add `quantity` portions; opens the drawer. Resolves false on failure or a conflict. */
  add: (dish: CartDish, quantity?: number, source?: AddSource) => Promise<boolean>;
  /** Confirm the pending conflict: empty the cart and start it with that dish. */
  startNewCart: () => Promise<boolean>;
  dismissConflict: () => void;
  setQuantity: (dishId: string, quantity: number) => Promise<boolean>;
  changeQuantity: (dishId: string, delta: number) => Promise<boolean>;
  remove: (dishId: string) => Promise<boolean>;
  clear: () => Promise<boolean>;
  /** Re-read the cart from the server (e.g. after an order emptied it). */
  reload: () => Promise<void>;
};

const CartContext = createContext<CartState | null>(null);

function errorLines(cause: unknown): string[] {
  return cause instanceof ApiError ? cause.lines : ["Could not reach the API"];
}

/** The add request for `source` (see `AddSource`). */
function addRequest(dish: CartDish, quantity: number, replaceCart: boolean, source: AddSource): Promise<Cart> {
  const replace = replaceCart ? { replace_cart: true } : {};
  return source === "favourites"
    ? api.post<Cart>(`/me/favourites/${dish.id}/cart`, { quantity, ...replace })
    : api.post<Cart>("/cart/items", { dish_id: dish.id, quantity, ...replace });
}

/**
 * The cart for the whole app (guest or account - the backend decides by
 * cookie). Every mutation answers with the complete cart, which simply
 * replaces local state: no optimistic guessing, so the UI always shows what
 * the server stored. The cart reloads whenever the signed-in user changes:
 * logging in returns the merged account cart, logging out the guest one.
 */
export function CartProvider({ children }: { children: ReactNode }) {
  const { user, checked } = useSession();
  const userId = user?.id ?? null;
  const [cart, setCart] = useState<Cart | null>(null);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [conflict, setConflict] = useState<CookConflict | null>(null);
  const openerRef = useRef<HTMLElement | null>(null);

  /** Remember who opened the drawer *now*, at the click - before the
   * clicked button is disabled for the request (which would drop focus). */
  const rememberOpener = useCallback(() => {
    if (!drawerOpen && document.activeElement instanceof HTMLElement) {
      openerRef.current = document.activeElement;
    }
  }, [drawerOpen]);

  useEffect(() => {
    if (!checked) return; // wait for the session, or a guest cart would flash first
    let active = true;
    const load = async () => {
      try {
        const next = await api.get<Cart>("/cart");
        if (active) setCart(next);
      } catch (cause) {
        if (active) setErrors(errorLines(cause));
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [checked, userId]);

  const reload = useCallback(async () => {
    try {
      setCart(await api.get<Cart>("/cart"));
    } catch (cause) {
      setErrors(errorLines(cause));
    }
  }, []);

  /** Run one cart request; its answer (the whole cart) becomes the state. */
  const run = useCallback(async (request: () => Promise<Cart>): Promise<boolean> => {
    setBusy(true);
    setErrors([]);
    try {
      setCart(await request());
      return true;
    } catch (cause) {
      setErrors(errorLines(cause));
      return false;
    } finally {
      setBusy(false);
    }
  }, []);

  const add = useCallback(
    async (dish: CartDish, quantity = 1, replaceCart = false, source: AddSource = "menu"): Promise<boolean> => {
      rememberOpener();
      setBusy(true);
      setErrors([]);
      setConflict(null);
      try {
        setCart(await addRequest(dish, quantity, replaceCart, source));
        setDrawerOpen(true);
        return true;
      } catch (cause) {
        if (cause instanceof ApiError && cause.code === "different_cook") {
          const details = cause.details as DifferentCookDetails | null;
          setConflict({ dish, quantity, cartCookName: details?.cart_cook_name ?? null, source });
        } else {
          setErrors(errorLines(cause));
        }
        setDrawerOpen(true); // the drawer shows the question or the error
        return false;
      } finally {
        setBusy(false);
      }
    },
    [rememberOpener],
  );

  const value: CartState = {
    cart,
    busy,
    errors,
    drawerOpen,
    openerRef,
    conflict,
    openDrawer: () => {
      rememberOpener();
      setDrawerOpen(true);
    },
    closeDrawer: () => {
      setDrawerOpen(false);
      setConflict(null);
    },
    add: (dish, quantity = 1, source = "menu") => add(dish, quantity, false, source),
    startNewCart: () =>
      conflict ? add(conflict.dish, conflict.quantity, true, conflict.source) : Promise.resolve(false),
    dismissConflict: () => setConflict(null),
    setQuantity: (dishId, quantity) =>
      run(() => api.patch<Cart>(`/cart/items/${dishId}`, { quantity })),
    changeQuantity: (dishId, delta) =>
      run(() => api.patch<Cart>(`/cart/items/${dishId}`, { delta })),
    remove: (dishId) => run(() => api.delete<Cart>(`/cart/items/${dishId}`)),
    clear: () => run(() => api.delete<Cart>("/cart")),
    reload,
  };

  return <CartContext.Provider value={value}>{children}</CartContext.Provider>;
}

export function useCart(): CartState {
  const cart = useContext(CartContext);
  if (!cart) throw new Error("useCart must be used inside <CartProvider>");
  return cart;
}
