"use client";

import { useCart } from "@/lib/cart";

/** Navbar cart icon with the number of portions in the cart; opens the drawer. */
export default function CartButton() {
  const { cart, openDrawer } = useCart();
  const count = cart?.item_count ?? 0;
  return (
    <button
      type="button"
      onClick={openDrawer}
      aria-label={`Open cart, ${count} ${count === 1 ? "item" : "items"}`}
      aria-haspopup="dialog"
      data-cart-button
      className="relative rounded-full p-2 text-zinc-600 hover:bg-zinc-100 hover:text-zinc-900 dark:text-zinc-300 dark:hover:bg-zinc-800 dark:hover:text-zinc-50"
    >
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth={1.8}
        strokeLinecap="round"
        strokeLinejoin="round"
        className="h-6 w-6"
      >
        <path d="M3 4h2l2.4 10.2a1.5 1.5 0 0 0 1.5 1.1h8.6a1.5 1.5 0 0 0 1.5-1.1L21 7H6.2" />
        <circle cx="9.5" cy="19.5" r="1.3" />
        <circle cx="17" cy="19.5" r="1.3" />
      </svg>
      {count > 0 && (
        <span
          aria-hidden="true"
          className="absolute -right-0.5 -top-0.5 flex h-5 min-w-5 items-center justify-center rounded-full bg-emerald-600 px-1 text-[11px] font-semibold leading-none text-white"
        >
          {count > 99 ? "99+" : count}
        </span>
      )}
    </button>
  );
}
