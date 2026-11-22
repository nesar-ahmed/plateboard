"use client";

import { ArrowRight, ChevronDown, MapPin, Receipt, StickyNote, X } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import DishArt from "@/components/dish-art";
import { OrderTimeline, StatusBadge, itemsSummary } from "@/components/order-bits";
import { EmptyState, ErrorBanner, PageHeader, Pager, cx } from "@/components/ui";
import { ordersOf } from "@/lib/admin";
import type { Order, OrderPage, OrderStatus } from "@/lib/api";
import { formatDateTime, formatMinorUnits, orderRef } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const PAGE_SIZE = 15;

const TABS: { key: string; label: string; statuses: OrderStatus[] }[] = [
  { key: "all", label: "All", statuses: [] },
  { key: "open", label: "Open", statuses: ["placed", "accepted", "ready"] },
  { key: "completed", label: "Completed", statuses: ["completed"] },
  { key: "cancelled", label: "Cancelled", statuses: ["cancelled"] },
];

export default function AdminOrdersPage() {
  return (
    <Suspense fallback={null}>
      <AdminOrders />
    </Suspense>
  );
}

/**
 * /admin/orders - every order, newest first (URL: ?tab=&offset= plus
 * ?cook_id=&cook= / ?customer_id=&customer= filters from the other admin
 * pages). Rows expand in place: the list already carries the whole order;
 * `?open=<order id>` (from a notification) starts with that row expanded.
 */
function AdminOrders() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = TABS.find((candidate) => candidate.key === params.get("tab")) ?? TABS[0];
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const cookId = params.get("cook_id");
  const customerId = params.get("customer_id");
  // The expanded row follows ?open= until the admin picks one; the choice is
  // keyed on the URL's value, so following another notification link here
  // expands that order again.
  const openParam = params.get("open");
  const [choice, setChoice] = useState<{ param: string | null; id: string | null } | null>(null);
  const open = choice && choice.param === openParam ? choice.id : openParam;
  const setOpen = (id: string | null) => setChoice({ param: openParam, id });

  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  for (const status of tab.statuses) query.append("status", status);
  if (cookId) query.set("cook_id", cookId);
  if (customerId) query.set("customer_id", customerId);
  const { data: page, error } = useApi<OrderPage>(`/admin/orders?${query.toString()}`);

  const go = (change: Record<string, string | null>) => {
    const next = new URLSearchParams(params.toString());
    next.delete("offset");
    next.delete("open");
    for (const [key, value] of Object.entries(change)) {
      if (value === null || value === "" || (key === "tab" && value === "all")) next.delete(key);
      else next.set(key, value);
    }
    setOpen(null);
    router.push(next.size ? `${pathname}?${next.toString()}` : pathname, { scroll: false });
  };

  type Filter = { key: string; label: string; clear: Record<string, null> };
  const filters: Filter[] = [];
  if (cookId) {
    filters.push({ key: "cook", label: `Kitchen: ${params.get("cook") ?? "one cook"}`, clear: { cook_id: null, cook: null } });
  }
  if (customerId) {
    filters.push({
      key: "customer",
      label: `Customer: ${params.get("customer") ?? "one customer"}`,
      clear: { customer_id: null, customer: null },
    });
  }

  return (
    <div className="space-y-6">
      <PageHeader size="compact" title="Orders" lead="Every order on the platform, newest first. Open a row for the details." />

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div role="tablist" aria-label="Status" className="flex gap-1 rounded-full border border-line bg-surface p-1 sm:w-fit">
          {TABS.map((candidate) => (
            <button
              key={candidate.key}
              role="tab"
              type="button"
              aria-selected={candidate.key === tab.key}
              onClick={() => go({ tab: candidate.key })}
              className={cx(
                "h-9 flex-1 whitespace-nowrap rounded-full px-3 text-sm font-medium transition-colors sm:flex-none sm:px-4",
                candidate.key === tab.key ? "bg-ink text-canvas" : "text-ink-muted hover:text-ink",
              )}
            >
              {candidate.label}
            </button>
          ))}
        </div>
        {filters.length > 0 && (
          <div className="flex flex-wrap gap-2">
            {filters.map((filter) => (
              <button
                key={filter.key}
                type="button"
                onClick={() => go(filter.clear)}
                className="inline-flex h-9 items-center gap-1.5 rounded-full bg-ink px-3.5 text-sm font-medium text-canvas"
                aria-label={`Remove filter ${filter.label}`}
              >
                {filter.label} <X className="h-3.5 w-3.5" aria-hidden="true" />
              </button>
            ))}
          </div>
        )}
      </div>

      <ErrorBanner lines={error ? [error] : []} />

      {!page ? (
        <div className="h-96 animate-pulse rounded-3xl bg-muted" aria-busy="true" />
      ) : page.items.length === 0 ? (
        <EmptyState icon={<Receipt className="h-6 w-6" />} title="No orders here">
          Nothing matches this status{filters.length ? " and filter" : ""}.
        </EmptyState>
      ) : (
        <>
          <p className="text-sm text-ink-muted">
            {page.total} {page.total === 1 ? "order" : "orders"}
          </p>
          <ul className="overflow-hidden rounded-3xl border border-line bg-surface shadow-card">
            {page.items.map((order, index) => (
              <OrderRow
                key={order.id}
                order={order}
                first={index === 0}
                expanded={open === order.id}
                onToggle={() => setOpen(open === order.id ? null : order.id)}
              />
            ))}
          </ul>
          {page.total > PAGE_SIZE && (
            <Pager total={page.total} limit={PAGE_SIZE} offset={offset} onMove={(next) => go({ offset: String(next) })} />
          )}
        </>
      )}
    </div>
  );
}

function OrderRow({
  order,
  first,
  expanded,
  onToggle,
}: {
  order: Order;
  first: boolean;
  expanded: boolean;
  onToggle: () => void;
}) {
  const panelId = `order-${order.id}`;
  const address = order.delivery_address;
  return (
    <li className={cx(!first && "border-t border-line")}>
      <button
        type="button"
        aria-expanded={expanded}
        aria-controls={panelId}
        onClick={onToggle}
        className={cx(
          "grid w-full grid-cols-[minmax(0,1fr)_auto] items-center gap-x-4 gap-y-1 px-5 py-4 text-left transition-colors hover:bg-canvas sm:px-6",
          // Fixed tracks after the text columns: every row lines up with the others.
          "md:grid-cols-[minmax(0,0.9fr)_minmax(0,1.6fr)_7rem_6rem_1rem]",
          expanded && "bg-canvas",
        )}
      >
        <span className="min-w-0">
          <span className="block text-sm font-semibold tabular-nums text-ink">{orderRef(order.id)}</span>
          <span className="block text-xs text-ink-soft">{formatDateTime(order.created_at)}</span>
        </span>
        <span className="col-span-2 row-start-2 min-w-0 md:col-span-1 md:row-start-auto">
          <span className="flex min-w-0 items-center gap-1.5 text-sm text-ink">
            <span className="truncate">{order.customer.name ?? "A customer"}</span>
            <ArrowRight className="h-3.5 w-3.5 shrink-0 text-ink-soft" aria-label="ordered from" />
            <span className="truncate font-medium">{order.cook.name ?? "A home cook"}</span>
          </span>
          <span className="block truncate text-xs text-ink-soft">{itemsSummary(order)}</span>
        </span>
        <span className="hidden justify-self-start md:block">
          <StatusBadge status={order.status} />
        </span>
        <span className="text-right font-display text-base font-semibold tabular-nums text-ink">
          {formatMinorUnits(order.total)}
        </span>
        <ChevronDown
          aria-hidden="true"
          className={cx("hidden h-4 w-4 text-ink-soft transition-transform md:block", expanded && "rotate-180")}
        />
        <span className="md:hidden">
          <StatusBadge status={order.status} />
        </span>
      </button>

      {expanded && (
        <div id={panelId} className="animate-rise space-y-5 border-t border-line bg-canvas px-5 pb-6 pt-5 sm:px-6">
          <OrderTimeline order={order} perspective="admin" />
          <div className="grid grid-cols-1 gap-4 md:grid-cols-[minmax(0,1.3fr)_minmax(0,1fr)]">
            <ul className="divide-y divide-line rounded-2xl border border-line bg-surface px-4">
              {order.items.map((item, index) => (
                <li key={`${item.dish_id ?? item.name}-${index}`} className="flex items-center gap-3 py-3">
                  <DishArt dish={item} size="xs" className="h-9 w-9 shrink-0" rounded="rounded-lg" />
                  <span className="min-w-0 flex-1 truncate text-sm text-ink">
                    {item.name} <span className="text-ink-soft">× {item.quantity}</span>
                  </span>
                  <span className="text-sm tabular-nums text-ink">{formatMinorUnits(item.line_total)}</span>
                </li>
              ))}
              <li className="flex justify-between py-3 text-sm font-semibold text-ink">
                <span>Total · {order.item_count} portions</span>
                <span className="tabular-nums">{formatMinorUnits(order.total)}</span>
              </li>
            </ul>
            <div className="space-y-3 text-sm">
              {address && (
                <p className="flex gap-2 text-ink-muted">
                  <MapPin className="mt-0.5 h-4 w-4 shrink-0 text-ink-soft" aria-hidden="true" />
                  <span>
                    {address.recipient} · {address.line1}, {address.city}
                    {address.zone && <span className="block text-xs text-ink-soft">{address.zone.name}</span>}
                  </span>
                </p>
              )}
              {order.note && (
                <p className="flex gap-2 rounded-2xl bg-surface p-3 text-ink-muted">
                  <StickyNote className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" /> {order.note}
                </p>
              )}
              <div className="flex flex-wrap gap-x-4 gap-y-1 pt-1">
                <Link href={ordersOf("cook", order.cook.id, order.cook.name)} className="font-semibold text-brand hover:underline">
                  All orders of this kitchen
                </Link>
                <Link
                  href={ordersOf("customer", order.customer.id, order.customer.name)}
                  className="font-semibold text-brand hover:underline"
                >
                  All orders of this customer
                </Link>
              </div>
            </div>
          </div>
        </div>
      )}
    </li>
  );
}
