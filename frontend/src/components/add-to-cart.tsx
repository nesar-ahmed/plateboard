"use client";

import { Plus, ShoppingBag } from "lucide-react";
import { useState } from "react";

import QuantityStepper from "@/components/quantity-stepper";
import { Badge, Spinner, cx, primaryButtonClass } from "@/components/ui";
import { useCart, type AddSource, type CartDish } from "@/lib/cart";
import { formatMinorUnits } from "@/lib/format";
import { useSession } from "@/lib/session";

const MAX_QUANTITY = 100;

/** A cook cannot order their own dish (the API would answer 422). */
function useOwnDish(dish: CartDish): boolean {
  const { user } = useSession();
  return user !== null && user.id === dish.cook_id;
}

/**
 * Round "+ Add" for dish cards: adds one portion and opens the cart.
 * `source="favourites"` adds through the favourites list (a saved dish);
 * `onDone` hears whether it went in (false: refused - the drawer says why).
 */
export function AddToCartButton({
  dish,
  source = "menu",
  onDone,
}: {
  dish: CartDish;
  source?: AddSource;
  onDone?: (added: boolean) => void;
}) {
  const { add, busy } = useCart();
  const own = useOwnDish(dish);
  const [pending, setPending] = useState(false);
  if (own) {
    return <Badge tone="night">Your dish</Badge>;
  }
  return (
    <button
      type="button"
      disabled={busy}
      onClick={async () => {
        setPending(true);
        try {
          onDone?.(await add(dish, 1, source));
        } finally {
          setPending(false);
        }
      }}
      aria-label={`Add ${dish.name} to cart`}
      className={cx(
        "inline-flex h-10 items-center gap-1.5 rounded-full bg-surface pl-3 pr-4 text-sm font-semibold text-ink shadow-lift",
        "ring-1 ring-black/5 transition-all hover:bg-ink hover:text-canvas active:scale-95 disabled:opacity-60",
      )}
    >
      {pending ? <Spinner /> : <Plus className="h-4 w-4" strokeWidth={2.5} aria-hidden="true" />}
      Add
    </button>
  );
}

/** Quantity picker + "Add to cart" for the dish page. */
export function AddToCartWithQuantity({ dish, price }: { dish: CartDish; price: number }) {
  const { add, busy } = useCart();
  const [quantity, setQuantity] = useState(1);
  const own = useOwnDish(dish);
  if (own) {
    return (
      <p className="rounded-2xl bg-muted px-4 py-3 text-sm text-ink-muted">
        This is your dish - customers order it from this page.
      </p>
    );
  }
  return (
    <div className="flex flex-wrap items-center gap-3">
      <QuantityStepper
        value={quantity}
        max={MAX_QUANTITY}
        size="lg"
        label={`Quantity of ${dish.name}`}
        onStep={(delta) => setQuantity((current) => current + delta)}
      />
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          if (await add(dish, quantity)) setQuantity(1);
        }}
        className={cx(primaryButtonClass, "h-12 flex-1 px-6 text-[15px] sm:flex-none")}
      >
        {busy ? <Spinner /> : <ShoppingBag className="h-4 w-4" aria-hidden="true" />}
        Add to cart · {formatMinorUnits(price * quantity)}
      </button>
    </div>
  );
}
