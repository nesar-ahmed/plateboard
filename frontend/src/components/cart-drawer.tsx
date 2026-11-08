"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import QuantityStepper from "@/components/quantity-stepper";
import { ErrorBanner, ghostButtonClass, primaryButtonClass } from "@/components/ui";
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
      <div className="absolute inset-0 bg-zinc-950/40" aria-hidden="true" onClick={closeDrawer} />
      <div
        ref={panel}
        role="dialog"
        aria-modal="true"
        aria-labelledby="cart-title"
        className="relative flex h-full w-full max-w-md flex-col bg-white shadow-2xl dark:bg-zinc-950"
      >
        <header className="flex items-start justify-between gap-4 border-b border-zinc-200 px-5 py-4 dark:border-zinc-800">
          <div>
            <h2 id="cart-title" className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              Your cart
            </h2>
            {cart?.cook && (
              <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
                Order from{" "}
                <Link
                  href={`/cooks/${cart.cook.id}`}
                  onClick={closeDrawer}
                  className="text-emerald-700 hover:underline dark:text-emerald-400"
                >
                  {cart.cook.name ?? "a home cook"}
                </Link>
              </p>
            )}
          </div>
          <button
            ref={closeButton}
            type="button"
            onClick={closeDrawer}
            aria-label="Close cart"
            className="rounded-full p-1.5 text-zinc-500 hover:bg-zinc-100 hover:text-zinc-900 dark:hover:bg-zinc-800 dark:hover:text-zinc-50"
          >
            <svg aria-hidden="true" viewBox="0 0 24 24" className="h-5 w-5" fill="none" stroke="currentColor" strokeWidth={2} strokeLinecap="round">
              <path d="M6 6l12 12M18 6L6 18" />
            </svg>
          </button>
        </header>

        <div className="flex-1 space-y-4 overflow-y-auto px-5 py-4">
          {conflict && (
            <div
              role="alertdialog"
              aria-labelledby="cart-conflict-title"
              aria-describedby="cart-conflict-text"
              className="rounded-xl border border-amber-300 bg-amber-50 p-4 dark:border-amber-900 dark:bg-amber-950"
            >
              <h3 id="cart-conflict-title" className="text-sm font-semibold text-amber-900 dark:text-amber-200">
                Start a new cart?
              </h3>
              <p id="cart-conflict-text" className="mt-1 text-sm text-amber-900 dark:text-amber-200">
                Your cart holds dishes from {conflict.cartCookName ?? "another cook"}, and an order comes from
                one cook. Starting a new cart with <strong>{conflict.dish.name}</strong> removes them.
              </p>
              <div className="mt-3 flex gap-2">
                <button type="button" disabled={busy} onClick={() => void startNewCart()} className={primaryButtonClass}>
                  Start new cart
                </button>
                <button ref={keepCartButton} type="button" onClick={dismissConflict} className={ghostButtonClass}>
                  Keep current cart
                </button>
              </div>
            </div>
          )}

          <ErrorBanner lines={errors} />

          {cart === null ? (
            <p className="text-sm text-zinc-500">Loading...</p>
          ) : items.length === 0 ? (
            <div className="py-10 text-center">
              <p className="text-sm text-zinc-500">Your cart is empty.</p>
              <Link
                href="/"
                onClick={closeDrawer}
                className="mt-2 inline-block text-sm text-emerald-700 hover:underline dark:text-emerald-400"
              >
                Browse dishes
              </Link>
            </div>
          ) : (
            <ul className="divide-y divide-zinc-100 dark:divide-zinc-800" aria-label="Cart items">
              {items.map((item) => (
                <li key={item.dish_id} className={`py-4 ${item.available ? "" : "opacity-60"}`}>
                  <div className="flex items-start justify-between gap-3">
                    <div className="min-w-0">
                      <Link
                        href={`/dishes/${item.dish_id}`}
                        onClick={closeDrawer}
                        className="block truncate font-medium text-zinc-900 hover:underline dark:text-zinc-50"
                      >
                        {item.name}
                      </Link>
                      <p className="text-xs text-zinc-500 dark:text-zinc-400">
                        {formatMinorUnits(item.price)} each
                      </p>
                      {!item.available && (
                        <p className="mt-1 text-xs font-medium text-amber-700 dark:text-amber-400">
                          No longer available - remove it to check out
                        </p>
                      )}
                    </div>
                    <p className="font-mono text-sm text-zinc-900 dark:text-zinc-100">
                      {formatMinorUnits(item.line_total)}
                    </p>
                  </div>
                  <div className="mt-2 flex items-center justify-between">
                    {item.available ? (
                      <QuantityStepper
                        value={item.quantity}
                        max={item.max_quantity}
                        disabled={busy}
                        label={`Quantity of ${item.name}`}
                        onStep={(delta) => void changeQuantity(item.dish_id, delta)}
                      />
                    ) : (
                      <span className="text-xs text-zinc-400">Quantity {item.quantity}</span>
                    )}
                    <button
                      type="button"
                      disabled={busy}
                      onClick={() => void remove(item.dish_id)}
                      aria-label={`Remove ${item.name} from cart`}
                      className="text-xs font-medium text-red-700 hover:underline disabled:opacity-50 dark:text-red-400"
                    >
                      Remove
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        {cart && items.length > 0 && (
          <footer className="space-y-3 border-t border-zinc-200 px-5 py-4 dark:border-zinc-800">
            <div className="flex items-baseline justify-between">
              <span className="text-sm text-zinc-500 dark:text-zinc-400">
                Total · {cart.item_count} {cart.item_count === 1 ? "portion" : "portions"}
              </span>
              <span className="font-mono text-lg font-semibold text-zinc-900 dark:text-zinc-50">
                {formatMinorUnits(cart.total)}
              </span>
            </div>
            {cart.unavailable_count > 0 && (
              <p className="text-xs text-amber-700 dark:text-amber-400">
                {cart.unavailable_count} unavailable {cart.unavailable_count === 1 ? "dish is" : "dishes are"} not
                counted.
              </p>
            )}
            {!user && (
              <p className="text-xs text-zinc-500 dark:text-zinc-400">
                You will log in at checkout - this cart comes with you.
              </p>
            )}
            <div className="flex gap-2">
              <button
                type="button"
                disabled={busy || !orderable}
                onClick={checkout}
                className={`${primaryButtonClass} flex-1`}
              >
                Checkout
              </button>
              <button type="button" disabled={busy} onClick={() => void clear()} className={ghostButtonClass}>
                Clear cart
              </button>
            </div>
          </footer>
        )}
      </div>
    </div>
  );
}
