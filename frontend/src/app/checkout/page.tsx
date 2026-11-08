"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { Card, ghostButtonClass, primaryButtonClass } from "@/components/ui";
import { useCart } from "@/lib/cart";
import { formatMinorUnits } from "@/lib/format";
import { useSession } from "@/lib/session";

/**
 * Checkout - signed-in users only. Guests are sent to log in first
 * (`/login?next=/checkout`); the backend moves their guest cart to the
 * account at that login, so the same dishes are waiting here.
 *
 * Placing the order is the next backend step (orders API); until then this
 * page is the reviewed summary with the button disabled.
 */
export default function CheckoutPage() {
  const router = useRouter();
  const { user, checked } = useSession();
  const { cart, openDrawer } = useCart();
  // Only a visitor who *arrives* signed out is sent to log in. Someone who
  // logs out while on this page is on their way home (the nav navigates);
  // redirecting them to the login form would race with that.
  const sawUser = useRef(false);

  useEffect(() => {
    if (user) sawUser.current = true;
    else if (checked && !sawUser.current) router.replace("/login?next=/checkout");
  }, [checked, user, router]);

  if (!checked || !user) {
    return <p className="text-sm text-zinc-500">{checked ? "Redirecting to login..." : "Loading..."}</p>;
  }
  if (cart === null) return <p className="text-sm text-zinc-500">Loading your cart...</p>;

  const available = cart.items.filter((item) => item.available);

  return (
    <div className="mx-auto w-full max-w-2xl space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">Checkout</h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">Ordering as {user.email}</p>
      </header>

      {cart.items.length === 0 ? (
        <Card>
          <p className="text-sm text-zinc-500">Your cart is empty.</p>
          <Link href="/" className="mt-2 inline-block text-sm text-emerald-700 hover:underline dark:text-emerald-400">
            Browse dishes
          </Link>
        </Card>
      ) : (
        <Card
          title="Order summary"
          aside={
            <button type="button" onClick={openDrawer} className={ghostButtonClass}>
              Edit cart
            </button>
          }
        >
          {cart.cook && (
            <p className="-mt-2 mb-4 text-sm text-zinc-500 dark:text-zinc-400">
              From{" "}
              <Link href={`/cooks/${cart.cook.id}`} className="text-emerald-700 hover:underline dark:text-emerald-400">
                {cart.cook.name ?? "a home cook"}
              </Link>
            </p>
          )}
          <ul className="divide-y divide-zinc-100 dark:divide-zinc-800" aria-label="Order items">
            {cart.items.map((item) => (
              <li key={item.dish_id} className="flex items-center justify-between gap-4 py-3 text-sm">
                <span className={item.available ? "text-zinc-900 dark:text-zinc-100" : "text-zinc-400 line-through"}>
                  {item.quantity} × {item.name}
                  {!item.available && <span className="ml-2 text-xs no-underline">(unavailable)</span>}
                </span>
                <span className="font-mono text-zinc-900 dark:text-zinc-100">
                  {item.available ? formatMinorUnits(item.line_total) : "—"}
                </span>
              </li>
            ))}
          </ul>
          <div className="mt-4 flex items-baseline justify-between border-t border-zinc-200 pt-4 dark:border-zinc-800">
            <span className="text-sm text-zinc-500 dark:text-zinc-400">Total</span>
            <span className="font-mono text-xl font-semibold text-zinc-900 dark:text-zinc-50">
              {formatMinorUnits(cart.total)}
            </span>
          </div>
          {cart.unavailable_count > 0 && (
            <p className="mt-3 text-sm text-amber-700 dark:text-amber-400">
              Remove the unavailable {cart.unavailable_count === 1 ? "dish" : "dishes"} before ordering.
            </p>
          )}
          <div className="mt-6 space-y-2">
            <button type="button" disabled className={`${primaryButtonClass} w-full`}>
              Place order
            </button>
            <p className="text-center text-xs text-zinc-400">
              {available.length > 0
                ? "Order placement is the next step on the roadmap - nothing is ordered or charged yet."
                : "Nothing orderable in the cart."}
            </p>
          </div>
        </Card>
      )}
    </div>
  );
}
