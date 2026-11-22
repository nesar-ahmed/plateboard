"use client";

import { PackageCheck } from "lucide-react";
import { useState } from "react";

import ConfirmDialog from "@/components/confirm-dialog";
import { Spinner, cx, primaryButtonClass, smallButton } from "@/components/ui";
import { api, ApiError, type Order } from "@/lib/api";
import { useNotifications } from "@/lib/notifications";

/**
 * "I've received my order" - the customer's confirmation that completes a
 * `ready` order (POST /api/me/orders/{id}/receive). Only the customer can
 * complete an order, so it asks first: confirming before the food is in
 * hand would tell the kitchen it was handed over.
 *
 * `onDone` gets the completed order; `onError` the message of a refusal
 * (e.g. the order moved meanwhile). The bell follows right away: the
 * "ready for pickup" notification is resolved by the backend.
 */
export default function ReceiveButton({
  order,
  onDone,
  onError,
  size = "small",
  className,
}: {
  order: Order;
  onDone: (order: Order) => void;
  onError: (message: string) => void;
  size?: "small" | "large";
  className?: string;
}) {
  const { refresh } = useNotifications();
  const [confirming, setConfirming] = useState(false);
  const [busy, setBusy] = useState(false);

  const receive = async () => {
    setBusy(true);
    try {
      const completed = await api.post<Order>(`/me/orders/${order.id}/receive`, {});
      setConfirming(false);
      onDone(completed);
      void refresh();
    } catch (cause) {
      setConfirming(false);
      onError(cause instanceof ApiError ? cause.message : "Could not reach the API");
    } finally {
      setBusy(false);
    }
  };

  const cook = order.cook.name ?? "the cook";
  return (
    <>
      <button
        type="button"
        disabled={busy}
        onClick={() => setConfirming(true)}
        className={cx(primaryButtonClass, size === "small" && smallButton, className)}
      >
        {busy ? <Spinner /> : <PackageCheck className="h-4 w-4" aria-hidden="true" />} I&apos;ve received my order
      </button>
      {confirming && (
        <ConfirmDialog
          title="Got your food?"
          confirmLabel="Yes, I have it"
          busy={busy}
          onConfirm={() => void receive()}
          onCancel={() => setConfirming(false)}
        >
          Confirm only once the order is in your hands: it completes the order and tells {cook} it was handed over.
        </ConfirmDialog>
      )}
    </>
  );
}
