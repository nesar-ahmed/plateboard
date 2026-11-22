"use client";

import { RotateCcw } from "lucide-react";
import { useState } from "react";

import ConfirmDialog from "@/components/confirm-dialog";
import { Spinner, cx, ghostButtonClass, smallButton } from "@/components/ui";
import type { Order } from "@/lib/api";
import { ApiError } from "@/lib/api";
import { useReorder } from "@/lib/reorder";

/**
 * "Order again" with its own confirmation (when it would replace another
 * kitchen's bag) and a one-line report (`onDone`) of what was added/skipped.
 */
export default function ReorderButton({
  order,
  onDone,
  className,
}: {
  order: Order;
  onDone: (message: string) => void;
  className?: string;
}) {
  const { reorder, wouldReplace, busy } = useReorder();
  const [confirming, setConfirming] = useState(false);

  const run = async () => {
    setConfirming(false);
    try {
      const { added, skipped } = await reorder(order);
      const parts = [];
      if (added) parts.push(`Added ${added} ${added === 1 ? "dish" : "dishes"} to your bag.`);
      if (skipped.length) parts.push(`No longer on the menu: ${skipped.join(", ")}.`);
      onDone(parts.join(" ") || "Nothing from this order can be ordered right now.");
    } catch (cause) {
      onDone(cause instanceof ApiError ? cause.message : "Could not reach the API");
    }
  };

  return (
    <>
      <button
        type="button"
        disabled={busy}
        onClick={() => (wouldReplace(order) ? setConfirming(true) : void run())}
        className={cx(ghostButtonClass, smallButton, className)}
      >
        {busy ? <Spinner /> : <RotateCcw className="h-3.5 w-3.5" aria-hidden="true" />} Order again
      </button>
      {confirming && (
        <ConfirmDialog
          title="Start a new bag?"
          confirmLabel="Replace my bag"
          onConfirm={() => void run()}
          onCancel={() => setConfirming(false)}
        >
          Your bag holds dishes from another kitchen, and an order comes from one cook. Ordering again from{" "}
          {order.cook.name ?? "this cook"} replaces them.
        </ConfirmDialog>
      )}
    </>
  );
}
