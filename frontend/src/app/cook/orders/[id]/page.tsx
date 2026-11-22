"use client";

import { ArrowLeft, MapPin, Phone, StickyNote } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import CookOrderActions, { COOK_STATUS_HINT } from "@/components/cook-order-actions";
import DishArt from "@/components/dish-art";
import { OPEN_STATUSES, OrderTimeline, StatusBadge } from "@/components/order-bits";
import { Avatar, ButtonLink, ErrorBanner, PageHeader, Spinner } from "@/components/ui";
import { api, ApiError, type Order } from "@/lib/api";
import { formatDateTime, formatMinorUnits, orderRef } from "@/lib/format";
import { queueMeta } from "@/lib/kitchen";
import { useKitchen } from "@/lib/kitchen-context";

const REFRESH_MS = 20_000;

/**
 * /cook/orders/{id} (GET /api/cooks/me/orders/{id}): the cook's view of one
 * order - next action on top, timeline, who and where, the lines. Refreshes
 * while the order is open (the customer may cancel a request meanwhile).
 */
export default function CookOrderPage() {
  const { id } = useParams<{ id: string }>();
  const kitchen = useKitchen();
  const [order, setOrder] = useState<Order | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [actionError, setActionError] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      setOrder(await api.get<Order>(`/cooks/me/orders/${id}`));
      setErrors([]);
    } catch (cause) {
      setErrors(cause instanceof ApiError ? [cause.message] : ["Could not reach the API"]);
    }
  }, [id]);

  const open = order !== null && OPEN_STATUSES.includes(order.status);
  useEffect(() => {
    const kickOff = window.setTimeout(() => void load(), 0);
    const timer = open ? window.setInterval(() => void load(), REFRESH_MS) : undefined;
    return () => {
      window.clearTimeout(kickOff);
      if (timer) window.clearInterval(timer);
    };
  }, [load, open]);

  if (!order) {
    return errors.length ? (
      <div className="space-y-4">
        <ErrorBanner lines={errors} />
        <ButtonLink href="/cook/orders" variant="ghost">
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
  const hint = COOK_STATUS_HINT[order.status];
  return (
    <div className="space-y-6">
      <Link href="/cook/orders" className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> All orders
      </Link>

      <PageHeader
        size="compact"
        eyebrow={`Order ${orderRef(order.id)}`}
        title={`For ${order.customer.name ?? "a customer"}`}
        lead={`Placed ${formatDateTime(order.created_at)}`}
        actions={<StatusBadge status={order.status} className="px-3 py-1 text-sm" />}
      />

      <ErrorBanner lines={[...errors, ...(actionError ? [actionError] : [])]} />

      {open && (
        <section
          aria-label="Next step"
          className="flex flex-col gap-4 rounded-3xl border border-line bg-surface p-5 shadow-lift sm:flex-row sm:items-center sm:justify-between sm:p-6"
        >
          <div className="flex items-center gap-3">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-brand-soft text-brand">
              <hint.icon className="h-5 w-5" aria-hidden="true" />
            </span>
            <div>
              <p className="font-semibold text-ink">{hint.text}</p>
              <p className="text-sm text-ink-muted">{queueMeta(order)}</p>
            </div>
          </div>
          <CookOrderActions
            order={order}
            size="regular"
            onError={setActionError}
            onChanged={(updated) => {
              if (updated) setOrder(updated);
              else void load();
              void kitchen.refresh();
            }}
          />
        </section>
      )}

      <section aria-label="Order progress" className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
        <OrderTimeline order={order} perspective="cook" />
      </section>

      <div className="grid grid-cols-1 gap-4 md:grid-cols-2">
        <section
          aria-label={order.fulfilment === "delivery" ? "Delivery" : "Pickup"}
          className="rounded-3xl border border-line bg-surface p-5 sm:p-6"
        >
          <h2 className="flex items-center gap-2 text-sm font-semibold text-ink">
            <MapPin className="h-4 w-4 text-ink-soft" aria-hidden="true" />
            {order.fulfilment === "delivery" ? "Deliver to" : "Pickup · the customer's contact"}
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
              {address.zone && <p className="text-xs text-ink-soft">{address.zone.name}</p>}
              <a
                href={`tel:${address.phone.replace(/[^\d+]/g, "")}`}
                className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-brand hover:underline"
              >
                <Phone className="h-3 w-3" aria-hidden="true" /> {address.phone}
              </a>
              {address.instructions && <p className="mt-2 text-xs italic">“{address.instructions}”</p>}
            </div>
          ) : (
            <p className="mt-3 text-sm text-ink-soft">No address on this order.</p>
          )}
        </section>
        <section aria-label="Customer" className="rounded-3xl border border-line bg-surface p-5 sm:p-6">
          <h2 className="text-sm font-semibold text-ink">Ordered by</h2>
          <div className="mt-3 flex items-center gap-3">
            <Avatar name={order.customer.name} />
            <span className="font-medium text-ink">{order.customer.name ?? "A customer"}</span>
          </div>
          {order.note ? (
            <p className="mt-4 flex gap-2 rounded-2xl bg-saffron-soft p-3 text-sm text-ink">
              <StickyNote className="mt-0.5 h-4 w-4 shrink-0 text-saffron" aria-hidden="true" /> {order.note}
            </p>
          ) : (
            <p className="mt-4 text-xs text-ink-soft">No note for the kitchen.</p>
          )}
        </section>
      </div>

      <section aria-label="Items" className="rounded-3xl border border-line bg-surface p-5 sm:p-6">
        <h2 className="text-sm font-semibold text-ink">
          {order.item_count} {order.item_count === 1 ? "portion" : "portions"} to cook
        </h2>
        <ul className="mt-3 divide-y divide-line">
          {order.items.map((item, index) => (
            <li key={`${item.dish_id ?? item.name}-${index}`} className="flex items-center gap-4 py-3">
              <DishArt dish={item} size="xs" className="h-12 w-12 shrink-0" rounded="rounded-xl" />
              <div className="min-w-0 flex-1">
                {item.dish_id ? (
                  <Link href={`/cook/dishes/${item.dish_id}`} className="font-medium text-ink hover:text-brand">
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
          <span className="font-medium text-ink">{order.status === "completed" ? "Earned" : "Total"}</span>
          <span className="font-display text-2xl font-semibold tabular-nums text-ink">
            {formatMinorUnits(order.total)}
          </span>
        </div>
        <p className="mt-2 text-xs text-ink-soft">The customer pays you directly at handover.</p>
      </section>
    </div>
  );
}
