"use client";

import { useState } from "react";

import { api, ApiError, type Cart, type Order } from "@/lib/api";
import { useCart } from "@/lib/cart";

export type ReorderResult = { added: number; skipped: string[] };

/**
 * "Order again": put a past order's dishes back in the bag, at today's
 * prices. Dishes that are gone or deactivated are skipped (and reported). If
 * the bag holds another kitchen's dishes, the caller must confirm first -
 * the first add then starts a new bag (`replace_cart`), one cook per order.
 */
export function useReorder() {
  const { cart, reload, openDrawer } = useCart();
  const [busy, setBusy] = useState(false);

  /** True when re-ordering would replace another kitchen's bag. */
  const wouldReplace = (order: Order) =>
    !!cart?.cook && cart.items.length > 0 && cart.cook.id !== order.cook.id;

  const reorder = async (order: Order): Promise<ReorderResult> => {
    setBusy(true);
    const result: ReorderResult = { added: 0, skipped: [] };
    let first = true;
    try {
      for (const item of order.items) {
        if (!item.dish_id) {
          result.skipped.push(item.name);
          continue;
        }
        try {
          await api.post<Cart>("/cart/items", {
            dish_id: item.dish_id,
            quantity: item.quantity,
            ...(first ? { replace_cart: true } : {}),
          });
          first = false;
          result.added += 1;
        } catch (cause) {
          if (cause instanceof ApiError && (cause.status === 404 || cause.status === 422)) {
            result.skipped.push(item.name); // off the menu, or over a quantity limit
          } else {
            throw cause;
          }
        }
      }
      await reload();
      if (result.added > 0) openDrawer();
      return result;
    } finally {
      setBusy(false);
    }
  };

  return { reorder, wouldReplace, busy };
}
