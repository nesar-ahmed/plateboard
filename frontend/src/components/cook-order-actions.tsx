"use client";

import { Check, ChefHat, CircleCheck, Hourglass, Package, X } from "lucide-react";
import { useState } from "react";

import ConfirmDialog from "@/components/confirm-dialog";
import {
  Spinner,
  cx,
  darkButtonClass,
  dangerButtonClass,
  quietButtonClass,
  smallButton,
  textareaClass,
} from "@/components/ui";
import { api, ApiError, type Order, type OrderStatus } from "@/lib/api";
import { CANCEL_REASONS, REASON_MAX_LENGTH, REJECT_REASONS } from "@/lib/kitchen";
import { useNotifications } from "@/lib/notifications";

type Move = "accepted" | "ready" | "cancelled";

/**
 * What the next step is called, per current status (the cook's buttons). A
 * `ready` order has none: the *customer* completes it by confirming receipt.
 */
const NEXT: Partial<Record<OrderStatus, { to: Move; label: string; icon: typeof Check }>> = {
  placed: { to: "accepted", label: "Accept", icon: Check },
  accepted: { to: "ready", label: "Mark ready", icon: Package },
};

/** Human text for a refused move (409 `invalid_status_transition`). */
function refusal(cause: unknown): string {
  if (cause instanceof ApiError && cause.code === "invalid_status_transition") {
    const now = (cause.details as { status?: string } | null)?.status;
    return now === "cancelled"
      ? "The customer cancelled this order a moment ago."
      : `This order changed meanwhile${now ? ` - it is ${now} now` : ""}. The list was refreshed.`;
  }
  return cause instanceof ApiError ? cause.message : "Could not reach the API";
}

/**
 * The cook's buttons for one order (PATCH /api/cooks/me/orders/{id}):
 * placed -> Accept | Reject, accepted -> Mark ready | Cancel. A ready order
 * shows who it waits for instead: the customer confirms they have it, which
 * completes it (the cook is notified). Reject/Cancel ask for an optional
 * reason the customer sees. `onChanged` gets the updated order (or null
 * after a refused move, so the caller reloads); `onError` a line to show.
 * A move also refreshes the bell: answering a request resolves its
 * notification.
 */
export default function CookOrderActions({
  order,
  onChanged,
  onError,
  size = "small",
  className,
}: {
  order: Order;
  onChanged: (order: Order | null) => void;
  onError: (message: string | null) => void;
  size?: "small" | "regular";
  className?: string;
}) {
  const notifications = useNotifications();
  const [busy, setBusy] = useState<Move | null>(null);
  const [asking, setAsking] = useState(false);
  const next = NEXT[order.status];
  if (order.status === "ready") {
    return (
      <p className={cx("inline-flex items-center gap-2 text-sm text-ink-muted", className)}>
        <Hourglass className="h-4 w-4 shrink-0 text-brand" aria-hidden="true" />
        Waiting for {order.customer.name ?? "the customer"} to confirm pickup
      </p>
    );
  }
  if (!next) return null;

  const move = async (to: Move, reason?: string) => {
    setBusy(to);
    onError(null);
    try {
      const updated = await api.patch<Order>(`/cooks/me/orders/${order.id}`, {
        status: to,
        ...(reason ? { reason } : {}),
      });
      setAsking(false);
      onChanged(updated);
      void notifications.refresh();
    } catch (cause) {
      setAsking(false);
      onError(refusal(cause));
      if (cause instanceof ApiError && cause.status === 409) onChanged(null);
    } finally {
      setBusy(null);
    }
  };

  const rejecting = order.status === "placed";
  const sizing = size === "small" ? smallButton : "";
  const Icon = next.icon;
  return (
    <div className={cx("flex flex-wrap items-center gap-2", className)}>
      <button
        type="button"
        disabled={busy !== null}
        onClick={() => void move(next.to)}
        className={cx(darkButtonClass, sizing)}
      >
        {busy === next.to ? <Spinner /> : <Icon className="h-4 w-4" aria-hidden="true" />} {next.label}
      </button>
      <button
        type="button"
        disabled={busy !== null}
        onClick={() => setAsking(true)}
        className={cx(rejecting ? dangerButtonClass : quietButtonClass, sizing)}
      >
        <X className="h-4 w-4" aria-hidden="true" /> {rejecting ? "Reject" : "Cancel order"}
      </button>
      {asking && (
        <ReasonDialog
          order={order}
          busy={busy === "cancelled"}
          onCancel={() => setAsking(false)}
          onConfirm={(reason) => void move("cancelled", reason)}
        />
      )}
    </div>
  );
}

function ReasonDialog({
  order,
  busy,
  onConfirm,
  onCancel,
}: {
  order: Order;
  busy: boolean;
  onConfirm: (reason: string) => void;
  onCancel: () => void;
}) {
  const rejecting = order.status === "placed";
  const [reason, setReason] = useState("");
  const customer = order.customer.name ?? "The customer";
  const picks = rejecting ? REJECT_REASONS : CANCEL_REASONS;
  return (
    <ConfirmDialog
      title={rejecting ? "Reject this order?" : "Cancel this order?"}
      confirmLabel={rejecting ? "Reject order" : "Cancel order"}
      tone="danger"
      busy={busy}
      onCancel={onCancel}
      onConfirm={() => onConfirm(reason.trim())}
    >
      <p>
        {rejecting
          ? `${customer} will see that you couldn't take it. A short reason helps them order again.`
          : `You already accepted this order - ${customer} is counting on it. Let them know why.`}
      </p>
      <div className="mt-4 flex flex-wrap gap-2" role="group" aria-label="Quick reasons">
        {picks.map((pick) => (
          <button
            key={pick}
            type="button"
            aria-pressed={reason === pick}
            onClick={() => setReason(pick)}
            className={cx(
              "inline-flex h-8 items-center rounded-full border px-3 text-xs font-medium transition-colors",
              reason === pick
                ? "border-ink bg-ink text-canvas"
                : "border-line-strong bg-surface text-ink-muted hover:text-ink",
            )}
          >
            {pick}
          </button>
        ))}
      </div>
      <label className="mt-4 block">
        <span className="mb-1.5 flex items-baseline justify-between text-xs font-medium text-ink">
          Reason for {customer.split(" ")[0]}
          <span className="font-normal text-ink-soft">
            Optional · {reason.length}/{REASON_MAX_LENGTH}
          </span>
        </span>
        <textarea
          value={reason}
          onChange={(event) => setReason(event.target.value)}
          maxLength={REASON_MAX_LENGTH}
          rows={2}
          placeholder="Sorry - sold out for today"
          className={textareaClass}
        />
      </label>
    </ConfirmDialog>
  );
}

/** Status hint for the cook ("New request", "Cooking", ...). */
export const COOK_STATUS_HINT: Record<OrderStatus, { text: string; icon: typeof Check }> = {
  placed: { text: "New request - accept or reject", icon: ChefHat },
  accepted: { text: "Cooking - mark it ready when packed", icon: ChefHat },
  ready: { text: "Ready - the customer confirms pickup", icon: Package },
  completed: { text: "Received by the customer", icon: CircleCheck },
  cancelled: { text: "Cancelled", icon: X },
};
