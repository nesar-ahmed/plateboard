"use client";

import { ArrowRight, ShoppingBag, Trash2, TriangleAlert, X } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import DishArt from "@/components/dish-art";
import QuantityStepper from "@/components/quantity-stepper";
import {
  ErrorBanner,
  cx,
  darkButtonClass,
  ghostButtonClass,
  primaryButtonClass,
  quietButtonClass,
  smallButton,
} from "@/components/ui";
import { useCart } from "@/lib/cart";
import { formatMinorUnits } from "@/lib/format";
import { useSession } from "@/lib/session";

const FOCUSABLE = 'a[href], button:not([disabled]), input, select, textarea, [tabindex]:not([tabindex="-1"])';

/**
 * The cart as a slide-over panel (right side, modal).
 *
 * Lines with a quantity stepper, line totals and remove; the order total;
 * checkout. One cook per order: when an add is refused because the cart
 * holds another cook's dishes, the panel asks whether to start a new cart.
 * Guests can shop freely - checkout sends them to log in, and the backend
 * moves this cart to their account at login.
 *
 * Accessibility: role=dialog + aria-modal, Escape closes (or cancels the
 * new-cart question first), focus moves in on open, is kept inside with
 * Tab, and returns to whatever opened the panel; the page behind does not
 * scroll.
 */
export default function CartDrawer() {
  const router = useRouter();
  const { user } = useSession();
  const {
    cart,
    busy,
    errors,
    drawerOpen,
    openerRef,
    conflict,
    closeDrawer,
    changeQuantity,
    remove,
    clear,
    startNewCart,
    dismissConflict,
  } = useCart();
  const panel = useRef<HTMLDivElement>(null);
  const closeButton = useRef<HTMLButtonElement>(null);
  const keepCartButton = useRef<HTMLButtonElement>(null);
  // Latest state for the document-level key handler below (registered once
  // per opening, so it must not capture stale values).
  const latest = useRef({ conflict, closeDrawer, dismissConflict });
  useEffect(() => {
    latest.current = { conflict, closeDrawer, dismissConflict };
  });

  // Opening: lock page scroll, move focus in, listen for keys on the whole
  // document - focus can land outside the panel when the focused control
  // disappears (a removed line, the answered new-cart question), and Escape
  // must still work then. Closing: focus goes back to whatever opened the
  // panel (the cart icon or an "Add to cart" button).
  useEffect(() => {
    if (!drawerOpen) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    closeButton.current?.focus();

    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.preventDefault();
        if (latest.current.conflict) latest.current.dismissConflict();
        else latest.current.closeDrawer();
        return;
      }
      if (event.key !== "Tab" || !panel.current) return;
      const focusable = Array.from(panel.current.querySelectorAll<HTMLElement>(FOCUSABLE));
      if (focusable.length === 0) return;
      const first = focusable[0];
      const last = focusable[focusable.length - 1];
      const active = document.activeElement;
      if (!panel.current.contains(active)) {
        event.preventDefault(); // stray focus: bring it back in
        (event.shiftKey ? last : first).focus();
      } else if (event.shiftKey && active === first) {
        event.preventDefault();
        last.focus();
      } else if (!event.shiftKey && active === last) {
        event.preventDefault();
        first.focus();
      }
    };
    document.addEventListener("keydown", onKey);
    const opener = openerRef;
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = overflow;
      opener.current?.focus?.();
    };
  }, [drawerOpen, openerRef]);

  // The new-cart question takes focus on its safe choice; once answered,
  // focus returns to the panel instead of falling to the page behind.
  useEffect(() => {
    if (!drawerOpen) return;
    if (conflict) keepCartButton.current?.focus();
    else if (panel.current && !panel.current.contains(document.activeElement)) closeButton.current?.focus();
  }, [conflict, drawerOpen]);

  if (!drawerOpen) return null;

  const items = cart?.items ?? [];
  const orderable = items.some((item) => item.available);

  const checkout = () => {
    closeDrawer();
    router.push(user ? "/checkout" : "/login?next=/checkout");
  };

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      <div className="animate-fade-in absolute inset-0 bg-night/45 backdrop-blur-[2px]" aria-hidden="true" onClick={closeDrawer} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="cart-title"
        className="animate-slide-in relative flex h-full w-full max-w-[440px] flex-col bg-canvas shadow-pop sm:m-2 sm:h-[calc(100%-1rem)] sm:rounded-[1.75rem] sm:border sm:border-line"
      >
        <header className="flex items-start justify-between gap-4 px-6 pb-4 pt-6">
          <div>
            <h2 id="cart-title" className="font-display text-2xl font-semibold tracking-tight text-ink">
              Your bag
            </h2>
            {cart?.cook ? (
              <p className="mt-1 text-sm text-ink-muted">
                From{" "}
                <Link
                  href={`/cooks/${cart.cook.id}`}
                  onClick={closeDrawer}
                  className="font-medium text-ink underline decoration-line-strong underline-offset-4 hover:decoration-brand"
                >
                  {cart.cook.name ?? "a home cook"}
                </Link>
                &apos;s kitchen
              </p>
            ) : (
              <p className="mt-1 text-sm text-ink-muted">One kitchen per order.</p>
            )}
          </div>
          <button
            ref={closeButton}
            type="button"
            onClick={closeDrawer}
            aria-label="Close cart"
            className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full border border-line bg-surface text-ink-muted hover:text-ink"
          >
            <X className="h-5 w-5" aria-hidden="true" />
          </button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-6 pb-6">
          {conflict && (
            <div
              role="alertdialog"
              aria-labelledby="cart-conflict-title"
              aria-describedby="cart-conflict-text"
              className="animate-rise rounded-2xl border border-saffron/30 bg-saffron-soft p-4"
            >
              <h3 id="cart-conflict-title" className="flex items-center gap-2 text-sm font-semibold text-ink">
                <TriangleAlert className="h-4 w-4 text-saffron" aria-hidden="true" />
                Start a new bag?
              </h3>
              <p id="cart-conflict-text" className="mt-1.5 text-sm leading-relaxed text-ink-muted">
                Your bag holds dishes from {conflict.cartCookName ?? "another cook"}, and an order comes from one
                kitchen. Starting a new bag with <strong className="text-ink">{conflict.dish.name}</strong> removes
                them.
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void startNewCart()}
                  className={cx(darkButtonClass, smallButton)}
                >
                  Start new bag
                </button>
                <button
                  ref={keepCartButton}
                  type="button"
                  onClick={dismissConflict}
                  className={cx(ghostButtonClass, smallButton)}
                >
                  Keep current bag
                </button>
              </div>
            </div>
          )}

          <ErrorBanner lines={errors} />

          {cart === null ? (
            <div className="space-y-3" aria-busy="true">
              {[0, 1].map((row) => (
                <div key={row} className="flex gap-4 rounded-2xl bg-surface p-3">
                  <div className="h-16 w-16 animate-pulse rounded-xl bg-muted" />
                  <div className="flex-1 space-y-2 py-1">
                    <div className="h-4 w-2/3 animate-pulse rounded bg-muted" />
                    <div className="h-3 w-1/3 animate-pulse rounded bg-muted" />
                  </div>
                </div>
              ))}
            </div>
          ) : items.length === 0 ? (
            <div className="flex flex-col items-center px-4 py-16 text-center">
              <span className="flex h-16 w-16 items-center justify-center rounded-full bg-muted text-ink-muted">
                <ShoppingBag className="h-7 w-7" aria-hidden="true" />
              </span>
              <p className="mt-5 font-display text-xl font-semibold text-ink">Your bag is empty</p>
              <p className="mt-1 max-w-xs text-sm text-ink-muted">
                Find something a neighbour is cooking today and tap + to add it.
              </p>
              <Link href="/dishes" onClick={closeDrawer} className={cx(primaryButtonClass, "mt-6")}>
                Browse dishes <ArrowRight className="h-4 w-4" />
              </Link>
            </div>
          ) : (
            <ul className="space-y-3" aria-label="Cart items">
              {items.map((item) => (
                <li
                  key={item.dish_id}
                  className={cx("flex gap-4 rounded-2xl border border-line bg-surface p-3", !item.available && "opacity-70")}
                >
                  <DishArt dish={item} size="xs" className="h-[72px] w-[72px] shrink-0" rounded="rounded-xl" />
                  <div className="flex min-w-0 flex-1 flex-col">
                    <div className="flex items-start justify-between gap-2">
                      <Link
                        href={`/dishes/${item.dish_id}`}
                        onClick={closeDrawer}
                        className="line-clamp-2 font-medium leading-snug text-ink hover:text-brand"
                      >
                        {item.name}
                      </Link>
                      <p className="shrink-0 font-semibold tabular-nums text-ink">
                        {formatMinorUnits(item.line_total)}
                      </p>
                    </div>
                    <p className="text-xs text-ink-soft">{formatMinorUnits(item.price)} each</p>
                    {!item.available && (
                      <p className="mt-1 text-xs font-medium text-saffron">No longer available - remove it to check out</p>
                    )}
                    <div className="mt-auto flex items-center justify-between pt-2">
                      {item.available ? (
                        <QuantityStepper
                          value={item.quantity}
                          max={item.max_quantity}
                          disabled={busy}
                          size="sm"
                          label={`Quantity of ${item.name}`}
                          onStep={(delta) => void changeQuantity(item.dish_id, delta)}
                        />
                      ) : (
                        <span className="text-xs text-ink-soft">Quantity {item.quantity}</span>
                      )}
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => void remove(item.dish_id)}
                        aria-label={`Remove ${item.name} from cart`}
                        className="flex h-8 w-8 items-center justify-center rounded-full text-ink-soft hover:bg-danger-soft hover:text-danger disabled:opacity-50"
                      >
                        <Trash2 className="h-4 w-4" aria-hidden="true" />
                      </button>
                    </div>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {cart && items.length > 0 && (
          <footer className="space-y-4 border-t border-line bg-surface px-6 pb-6 pt-5 sm:rounded-b-[1.75rem]">
            <div className="space-y-1.5 text-sm">
              <div className="flex justify-between text-ink-muted">
                <span>
                  {cart.item_count} {cart.item_count === 1 ? "portion" : "portions"}
                </span>
                <button
                  type="button"
                  disabled={busy}
                  onClick={() => void clear()}
                  className="text-xs font-medium text-ink-soft underline-offset-4 hover:text-danger hover:underline disabled:opacity-50"
                >
                  Clear bag
                </button>
              </div>
              <div className="flex items-baseline justify-between">
                <span className="font-medium text-ink">Subtotal</span>
                <span className="font-display text-2xl font-semibold tabular-nums text-ink">
                  {formatMinorUnits(cart.total)}
                </span>
              </div>
              {cart.unavailable_count > 0 && (
                <p className="text-xs text-saffron">
                  {cart.unavailable_count} unavailable {cart.unavailable_count === 1 ? "dish is" : "dishes are"} not
                  counted.
                </p>
              )}
            </div>
            <button
              type="button"
              disabled={busy || !orderable}
              onClick={checkout}
              className={cx(primaryButtonClass, "h-12 w-full text-[15px]")}
            >
              {user ? "Go to checkout" : "Log in to check out"} <ArrowRight className="h-4 w-4" />
            </button>
            {!user && (
              <p className="text-center text-xs text-ink-soft">Your bag comes with you when you log in.</p>
            )}
            <button type="button" onClick={closeDrawer} className={cx(quietButtonClass, "h-9 w-full")}>
              Keep browsing
            </button>
          </footer>
        )}
      </div>
    </div>
  );
}
