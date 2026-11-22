"use client";

import { ShoppingBag } from "lucide-react";

import { cx } from "@/components/ui";
import { useCart } from "@/lib/cart";
import { formatCount } from "@/lib/format";

/**
 * Header cart button: the bag icon with a count badge in its corner - the
 * number of portions in the bag. No badge while the bag is empty; the badge
 * pops when the count changes (re-keyed on the count).
 */
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
      className="relative flex h-10 w-10 items-center justify-center rounded-full text-ink transition-colors hover:bg-muted"
    >
      <ShoppingBag className="h-[22px] w-[22px]" strokeWidth={1.9} aria-hidden="true" />
      {count > 0 && (
        <span
          key={count}
          aria-hidden="true"
          className={cx(
            // Anchored left of centre so longer counts ("99+") grow to the right.
            "animate-pop absolute left-[55%] top-0 flex h-5 min-w-5 items-center justify-center rounded-full",
            "bg-brand px-1 text-[11px] font-bold leading-none tabular-nums text-on-brand ring-2 ring-canvas",
          )}
        >
          {formatCount(count)}
        </span>
      )}
    </button>
  );
}
