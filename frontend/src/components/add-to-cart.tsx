"use client";

import { useState } from "react";

import QuantityStepper from "@/components/quantity-stepper";
import { primaryButtonClass } from "@/components/ui";
import { useCart, type CartDish } from "@/lib/cart";
import { useSession } from "@/lib/session";

const MAX_QUANTITY = 100;

/** A cook cannot order their own dish (the API would answer 422). */
function useOwnDish(dish: CartDish): boolean {
  const { user } = useSession();
  return user !== null && user.id === dish.cook_id;
}

/** Compact "Add to cart" for dish cards: adds one portion, opens the drawer. */
export function AddToCartButton({ dish }: { dish: CartDish }) {
  const { add, busy } = useCart();
  const own = useOwnDish(dish);
  if (own) {
    return <span className="text-xs text-zinc-400">Your dish</span>;
  }
  return (
    <button
      type="button"
      disabled={busy}
      onClick={() => void add(dish, 1)}
      aria-label={`Add ${dish.name} to cart`}
      className="rounded-full bg-emerald-600 px-3 py-1.5 text-xs font-medium text-white transition-colors hover:bg-emerald-700 disabled:cursor-not-allowed disabled:opacity-50"
    >
      Add to cart
    </button>
  );
}

/** Quantity picker + "Add to cart" for the dish page. */
export function AddToCartWithQuantity({ dish }: { dish: CartDish }) {
  const { add, busy } = useCart();
  const [quantity, setQuantity] = useState(1);
  const own = useOwnDish(dish);
  if (own) {
    return <p className="text-sm text-zinc-500">This is your dish - customers order it from here.</p>;
  }
  return (
    <div className="flex flex-wrap items-center gap-4">
      <QuantityStepper
        value={quantity}
        max={MAX_QUANTITY}
        label={`Quantity of ${dish.name}`}
        onStep={(delta) => setQuantity((current) => current + delta)}
      />
      <button
        type="button"
        disabled={busy}
        onClick={async () => {
          if (await add(dish, quantity)) setQuantity(1);
        }}
        className={primaryButtonClass}
      >
        {busy ? "Adding..." : "Add to cart"}
      </button>
    </div>
  );
}
