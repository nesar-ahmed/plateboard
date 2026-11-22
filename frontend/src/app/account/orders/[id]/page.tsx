"use client";

import { ArrowLeft, CircleCheck, FileText, MapPin, Package, Phone, StickyNote } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useCallback, useEffect, useState } from "react";

import ConfirmDialog from "@/components/confirm-dialog";
import DishArt from "@/components/dish-art";
import { CookLine, OPEN_STATUSES, OrderTimeline, StatusBadge } from "@/components/order-bits";
import ReceiveButton from "@/components/receive-button";
import ReorderButton from "@/components/reorder-button";
import { ButtonLink, ErrorBanner, PageHeader, Spinner, cx, dangerButtonClass, smallButton } from "@/components/ui";
import { api, ApiError, type Order } from "@/lib/api";
import { formatDateTime, formatMinorUnits, orderRef } from "@/lib/format";
import { useSession } from "@/lib/session";

const REFRESH_MS = 20_000;

export default function OrderPage() {
  return (
    <Suspense fallback={null}>
      <OrderDetail />
    </Suspense>
  );
}

/**
 * /account/orders/{id} (GET /api/me/orders/{id}): status timeline, the
 * address copy (the customer's contact; a pickup order is collected from the
 * kitchen), lines and total; refreshes while the order is open.
 * `?placed=1` (from checkout) shows the confirmation banner. A `ready`
 * order asks the customer to confirm receipt - that is what completes it.
 */
function OrderDetail() {
  const { id } = useParams<{ id: string }>();
  const placed = useSearchParams().get("placed") === "1";
  const router = useRouter();
  const { user } = useSession();
  const [order, setOrder] = useState<Order | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [confirmCancel, setConfirmCancel] = useState(false);
  const [cancelling, setCancelling] = useState(false);

  const load = useCallback(async () => {
    try {
      setOrder(await api.get<Order>(`/me/orders/${id}`));
      setErrors([]);
    } catch (cause) {
      if (cause instanceof ApiError && cause.status === 401) router.replace(`/login?next=/account/orders/${id}`);
      else setErrors(cause instanceof ApiError ? [cause.message] : ["Could not reach the API"]);
    }
  }, [id, router]);

  const open = order !== null && OPEN_STATUSES.includes(order.status);
  useEffect(() => {
    const kickOff = window.setTimeout(() => void load(), 0);
    const timer = open ? window.setInterval(() => void load(), REFRESH_MS) : undefined;
    return () => {
      window.clearTimeout(kickOff);
      if (timer) window.clearInterval(timer);
    };
  }, [load, open]);

  const cancel = async () => {
    setCancelling(true);
    try {
      setOrder(await api.post<Order>(`/me/orders/${id}/cancel`, {}));
      setConfirmCancel(false);
    } catch (cause) {
      setErrors(cause instanceof ApiError ? [cause.message] : ["Could not reach the API"]);
      setConfirmCancel(false);
      void load();
    } finally {
      setCancelling(false);
    }
  };

  if (!order) {
    return errors.length ? (
      <div className="space-y-4">
        <ErrorBanner lines={errors} />
        <ButtonLink href="/account/orders" variant="ghost">
          Back to orders
        </ButtonLink>
      </div>
    ) : (
      <div className="flex justify-center py-16 text-ink-muted">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  const address = order.delivery_address;
  return (
    <div className="space-y-6">
      <Link href="/account/orders" className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> All orders
      </Link>

      {placed && order.status !== "cancelled" && (
        <div className="animate-rise flex items-start gap-4 rounded-3xl bg-herb-soft p-5 sm:p-6">
          <CircleCheck className="mt-0.5 h-7 w-7 shrink-0 text-herb" aria-hidden="true" />
          <div>
            <p className="font-display text-xl font-semibold text-ink">
              Thank you{user?.display_name ? `, ${user.display_name.split(" ")[0]}` : ""}! Your order is in.
            </p>
            <p className="mt-1 text-sm text-ink-muted">
              It&apos;s now in {order.cook.name ?? "your cook"}&apos;s order list. This page updates as the order
              moves along.
            </p>
          </div>
        </div>
      )}

      <PageHeader
        size="compact"
        eyebrow={`Order ${orderRef(order.id)}`}
        title={`From ${order.cook.name ?? "a home cook"}`}
        lead={`Placed ${formatDateTime(order.created_at)}`}
        actions={<StatusBadge status={order.status} className="px-3 py-1 text-sm" />}
      />

      {notice && (
        <p role="status" className="rounded-2xl bg-herb-soft px-4 py-3 text-sm text-ink">
          {notice}
        </p>
      )}
      <ErrorBanner lines={errors} />

      {order.status === "ready" && (
        <section
          aria-label="Ready for pickup"
          className="animate-rise flex flex-col gap-4 rounded-3xl border border-brand/25 bg-brand-soft p-5 sm:flex-row sm:items-center sm:p-6"
        >
          <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-surface text-brand">
            <Package className="h-6 w-6" aria-hidden="true" />
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-display text-xl font-semibold text-ink">
              {order.fulfilment === "delivery" ? "Your order is on its way" : "Your order is ready for pickup"}
            </p>
            <p className="mt-1 text-sm text-ink-muted">
              {order.fulfilment === "delivery"
                ? "Once it arrives, let us know - that completes the order."
                : `Collect it from ${order.cook.name ?? "the kitchen"}, then let us know you have it - that completes the order.`}
            </p>
          </div>
          <ReceiveButton
            order={order}
            size="large"
            className="shrink-0"
            onDone={(completed) => {
              setOrder(completed);
              setErrors([]);
              setNotice("Enjoy your meal! The order is complete - your invoice is ready below.");
            }}
            onError={(message) => {
              setErrors([message]);
              void load();
            }}
          />
        </section>
      )}

      <section aria-label="Order progress" className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
        <OrderTimeline order={order} />
      </section>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <section
          aria-label={order.fulfilment === "delivery" ? "Delivery" : "Pickup"}
          className="rounded-3xl border border-line bg-surface p-5 sm:p-6"
        >
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
            <MapPin className="h-4 w-4 text-ink-soft" aria-hidden="true" />
            {order.fulfilment === "delivery" ? "Delivering to" : "Pickup · your contact for the cook"}
          </h2>
          {address ? (
            <div className="mt-3 text-sm leading-relaxed text-ink-muted">
              <p className="font-medium text-ink">
                {address.recipient}
                {address.label && <span className="ml-2 text-xs font-normal text-ink-soft">{address.label}</span>}
              </p>
              <p>
                {address.line1}
                {address.line2 && `, ${address.line2}`}
              </p>
              <p>{[address.postal_code, address.city].filter(Boolean).join(" ")}</p>
              <p className="mt-2 flex items-center gap-1.5 text-xs">
                <Phone className="h-3 w-3" aria-hidden="true" /> {address.phone}
              </p>
              {address.instructions && <p className="mt-2 text-xs italic">“{address.instructions}”</p>}
            </div>
          ) : (
            <p className="mt-3 text-sm text-ink-soft">No address on this order.</p>
          )}
        </section>
        <section aria-label="Kitchen" className="rounded-3xl border border-line bg-surface p-5 sm:p-6">
          <h2 className="text-sm font-semibold text-ink">From the kitchen of</h2>
          <div className="mt-3">
            <CookLine order={order} />
          </div>
          {order.note && (
            <p className="mt-4 flex gap-2 rounded-2xl bg-muted p-3 text-sm text-ink-muted">
              <StickyNote className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" /> {order.note}
            </p>
          )}
        </section>
      </div>

      <section aria-label="Items" className="rounded-3xl border border-line bg-surface p-5 sm:p-6">
        <h2 className="text-sm font-semibold text-ink">
          {order.item_count} {order.item_count === 1 ? "portion" : "portions"}
        </h2>
        <ul className="mt-3 divide-y divide-line">
          {order.items.map((item, index) => (
            <li key={`${item.dish_id ?? item.name}-${index}`} className="flex items-center gap-4 py-3">
              <DishArt dish={item} size="xs" className="h-12 w-12 shrink-0" rounded="rounded-xl" />
              <div className="min-w-0 flex-1">
                {item.dish_id ? (
                  <Link href={`/dishes/${item.dish_id}`} className="font-medium text-ink hover:text-brand">
                    {item.name}
                  </Link>
                ) : (
                  <p className="font-medium text-ink">{item.name}</p>
                )}
                <p className="text-sm text-ink-muted">
                  {item.quantity} × {formatMinorUnits(item.unit_price)}
                </p>
              </div>
              <p className="font-semibold tabular-nums text-ink">{formatMinorUnits(item.line_total)}</p>
            </li>
          ))}
        </ul>
        <div className="mt-2 flex items-baseline justify-between border-t border-line pt-4">
          <span className="font-medium text-ink">Total</span>
          <span className="font-display text-2xl font-semibold tabular-nums text-ink">
            {formatMinorUnits(order.total)}
          </span>
        </div>
      </section>

      <div className="flex flex-wrap items-center gap-2">
        {order.status === "completed" && (
          <ButtonLink href={`/account/orders/${order.id}/invoice`} variant="ghost" className={smallButton}>
            <FileText className="h-3.5 w-3.5" /> Invoice
          </ButtonLink>
        )}
        {(order.status === "completed" || order.status === "cancelled") && (
          <ReorderButton order={order} onDone={setNotice} />
        )}
        {order.status === "placed" && (
          <button
            type="button"
            onClick={() => setConfirmCancel(true)}
            className={cx(dangerButtonClass, smallButton, "ml-auto")}
          >
            Cancel order
          </button>
        )}
      </div>

      {confirmCancel && (
        <ConfirmDialog
          title="Cancel this order?"
          confirmLabel="Cancel order"
          tone="danger"
          busy={cancelling}
          onConfirm={() => void cancel()}
          onCancel={() => setConfirmCancel(false)}
        >
          {order.cook.name ?? "The cook"} hasn&apos;t accepted it yet, so you can still cancel. This can&apos;t be
          undone.
        </ConfirmDialog>
      )}
    </div>
  );
}
