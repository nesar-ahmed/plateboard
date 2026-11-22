/**
 * Order presentation shared by the account pages and the cook panel: status
 * vocabulary + colours, the status badge, the progress timeline and a
 * compact order card. Server-safe (no hooks).
 *
 * `perspective` says whose panel renders it: the customer's (default - shows
 * the kitchen, links into /account/orders) or the cook's (shows the
 * customer, links into /cook/orders).
 */

import { ChevronRight, CircleCheck, CircleX } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import DishArt from "@/components/dish-art";
import { Avatar, Badge, cx } from "@/components/ui";
import type { Order, OrderStatus } from "@/lib/api";
import { formatDate, formatDateTime, formatMinorUnits, orderRef } from "@/lib/format";

export const STATUS_META: Record<
  OrderStatus,
  { label: string; tone: "saffron" | "brand" | "herb" | "danger"; color: string; hint: string }
> = {
  placed: { label: "Placed", tone: "saffron", color: "var(--saffron)", hint: "Waiting for the cook" },
  accepted: { label: "Accepted", tone: "brand", color: "var(--brand)", hint: "The cook is on it" },
  ready: { label: "Ready", tone: "brand", color: "#4e8aa1", hint: "Packed and ready for pickup" },
  completed: { label: "Completed", tone: "herb", color: "var(--herb)", hint: "When the customer confirms receipt" },
  cancelled: { label: "Cancelled", tone: "danger", color: "var(--ink-soft)", hint: "This order was cancelled" },
};

export const OPEN_STATUSES: OrderStatus[] = ["placed", "accepted", "ready"];

export function StatusBadge({ status, className }: { status: OrderStatus; className?: string }) {
  const meta = STATUS_META[status];
  return (
    <Badge tone={meta.tone} className={className}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" />
      {meta.label}
    </Badge>
  );
}

/** Whose panel shows the order: the customer's, the cook's or the admin's (both sides). */
export type Perspective = "customer" | "cook" | "admin";

/** "Rejected by you", "Cancelled by the customer", ... */
export function cancelledLabel(order: Order, perspective: Perspective = "customer"): string {
  const byCook = order.cancelled_by === "cook";
  if (perspective === "admin") {
    if (!byCook) return "Cancelled by the customer";
    return order.accepted_at ? "Cancelled by the cook" : "Rejected by the cook";
  }
  if (perspective === "cook") {
    if (!byCook) return "Cancelled by the customer";
    return order.accepted_at ? "Cancelled by you" : "Rejected by you";
  }
  if (!byCook) return "Cancelled by you";
  return order.accepted_at ? "Cancelled by the cook" : "Declined by the cook";
}

const STEPS: { status: OrderStatus; label: string; at: keyof Order }[] = [
  { status: "placed", label: "Placed", at: "created_at" },
  { status: "accepted", label: "Accepted", at: "accepted_at" },
  { status: "ready", label: "Ready", at: "ready_at" },
  { status: "completed", label: "Completed", at: "completed_at" },
];

/** Placed -> accepted -> ready -> completed, or the cancelled state (with the cook's reason). */
export function OrderTimeline({
  order,
  compact = false,
  perspective = "customer",
}: {
  order: Order;
  compact?: boolean;
  perspective?: Perspective;
}) {
  if (order.status === "cancelled") {
    return (
      <div className="flex items-start gap-3 text-sm text-ink">
        <CircleX className="h-5 w-5 shrink-0 text-danger" aria-hidden="true" />
        <div>
          <p>
            {cancelledLabel(order, perspective)} · {formatDateTime(order.cancelled_at)}
          </p>
          {order.cancel_reason && <p className="mt-1 text-ink-muted">“{order.cancel_reason}”</p>}
        </div>
      </div>
    );
  }
  const reached = STEPS.findIndex((step) => step.status === order.status);
  return (
    <ol className={cx("grid gap-4", compact ? "grid-cols-4 gap-1" : "sm:grid-cols-4 sm:gap-2")}>
      {STEPS.map((step, index) => {
        const done = index <= reached;
        const time = order[step.at] as string | null;
        return (
          <li key={step.status} className={cx("relative flex gap-3", compact ? "flex-col gap-1.5" : "sm:flex-col sm:gap-2")}>
            {index < STEPS.length - 1 && (
              <span
                aria-hidden="true"
                className={cx(
                  "absolute",
                  compact
                    ? "left-5 top-[9px] h-0.5 w-[calc(100%-12px)]"
                    : "left-[11px] top-7 h-[calc(100%-4px)] w-0.5 sm:left-7 sm:top-[11px] sm:h-0.5 sm:w-[calc(100%-20px)]",
                  index < reached ? "bg-herb" : "bg-line",
                )}
              />
            )}
            <span
              className={cx(
                "relative z-10 flex shrink-0 items-center justify-center rounded-full border-2",
                compact ? "h-5 w-5" : "h-6 w-6",
                done ? "border-herb bg-herb text-white" : "border-line-strong bg-surface",
                index === reached && "ring-4 ring-herb/20",
              )}
            >
              {done && <CircleCheck className={compact ? "h-3.5 w-3.5" : "h-4 w-4"} aria-hidden="true" />}
            </span>
            <div>
              <p className={cx("font-semibold", compact ? "text-xs" : "text-sm", done ? "text-ink" : "text-ink-soft")}>
                {step.label}
              </p>
              {!compact && (
                <p className="text-xs text-ink-soft">
                  {time
                    ? formatDateTime(time)
                    : step.status === "completed" && perspective === "customer"
                      ? "Once you confirm you have it" // the customer completes it
                      : STATUS_META[step.status].hint}
                </p>
              )}
            </div>
          </li>
        );
      })}
    </ol>
  );
}

/** "Veg curry ×2, Tart ×1 +2 more" */
export function itemsSummary(order: Order, shown = 2): string {
  const names = order.items.slice(0, shown).map((item) => `${item.name} ×${item.quantity}`);
  const more = order.items.length - shown;
  return more > 0 ? `${names.join(", ")} +${more} more` : names.join(", ");
}

/**
 * A row/card for order lists: the other party (kitchen or customer), ref,
 * date, items, total, status, optional `meta` line and actions.
 */
export function OrderCard({
  order,
  actions,
  meta,
  perspective = "customer",
}: {
  order: Order;
  actions?: ReactNode;
  meta?: ReactNode;
  perspective?: Exclude<Perspective, "admin">;
}) {
  const cookSide = perspective === "cook";
  const href = cookSide ? `/cook/orders/${order.id}` : `/account/orders/${order.id}`;
  const party = cookSide ? (order.customer.name ?? "A customer") : (order.cook.name ?? "A home cook");
  return (
    <article className="group relative rounded-3xl border border-line bg-surface p-4 shadow-card transition-shadow hover:shadow-lift sm:p-5">
      <div className="flex items-start gap-4">
        <div className="relative hidden shrink-0 sm:block">
          <DishArt dish={order.items[0] ?? { name: "Order" }} size="xs" className="h-16 w-16" rounded="rounded-2xl" />
          {order.items.length > 1 && (
            <span className="absolute -bottom-1.5 -right-1.5 rounded-full border-2 border-surface bg-ink px-1.5 text-[10px] font-bold text-canvas">
              +{order.items.length - 1}
            </span>
          )}
        </div>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
            <h3 className="font-semibold text-ink">
              <Link href={href} className="after:absolute after:inset-0 after:content-[''] focus-visible:outline-none">
                {party}
              </Link>
            </h3>
            <StatusBadge status={order.status} />
          </div>
          <p className="mt-0.5 text-xs text-ink-soft">
            {orderRef(order.id)} · {formatDate(order.created_at)} · {order.item_count}{" "}
            {order.item_count === 1 ? "portion" : "portions"}
          </p>
          <p className="mt-2 line-clamp-1 text-sm text-ink-muted">{itemsSummary(order)}</p>
          {meta && <div className="mt-2 text-xs text-ink-soft">{meta}</div>}
        </div>
        <div className="flex shrink-0 flex-col items-end gap-2">
          <p className="font-display text-lg font-semibold tabular-nums text-ink">{formatMinorUnits(order.total)}</p>
          <ChevronRight className="h-4 w-4 text-ink-soft transition-transform group-hover:translate-x-0.5" aria-hidden="true" />
        </div>
      </div>
      {actions && <div className="relative z-10 mt-4 flex flex-wrap gap-2 border-t border-line pt-4">{actions}</div>}
    </article>
  );
}

export function CookLine({ order }: { order: Order }) {
  return (
    <Link href={`/cooks/${order.cook.id}`} className="flex items-center gap-3 hover:text-brand">
      <Avatar name={order.cook.name} />
      <span className="font-medium text-ink">{order.cook.name ?? "A home cook"}</span>
    </Link>
  );
}
