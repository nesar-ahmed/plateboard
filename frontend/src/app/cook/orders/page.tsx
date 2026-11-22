"use client";

import { CircleCheck, Inbox } from "lucide-react";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import CookOrderActions from "@/components/cook-order-actions";
import { OrderCard, cancelledLabel } from "@/components/order-bits";
import { CountPill, EmptyState, ErrorBanner, PageHeader, Pager, cx } from "@/components/ui";
import type { Order, OrderPage, OrderStatus } from "@/lib/api";
import { formatDateTime } from "@/lib/format";
import { queueMeta } from "@/lib/kitchen";
import { useKitchen } from "@/lib/kitchen-context";
import { useApi } from "@/lib/use-api";

const PAGE_SIZE = 10;
const REFRESH_MS = 30_000;

type Tab = { key: string; label: string; statuses: OrderStatus[]; sort: "newest" | "oldest" };

/** Requests and in-progress orders are a queue: first come, first served. */
const TABS: Tab[] = [
  { key: "requests", label: "Requests", statuses: ["placed"], sort: "oldest" },
  { key: "progress", label: "In progress", statuses: ["accepted", "ready"], sort: "oldest" },
  { key: "completed", label: "Completed", statuses: ["completed"], sort: "newest" },
  { key: "cancelled", label: "Cancelled", statuses: ["cancelled"], sort: "newest" },
  { key: "all", label: "All", statuses: [], sort: "newest" },
];

function ordersPath(tab: Tab, limit: number, offset = 0): string {
  const query = new URLSearchParams({ limit: String(limit), offset: String(offset), sort: tab.sort });
  for (const status of tab.statuses) query.append("status", status);
  return `/cooks/me/orders?${query.toString()}`;
}

export default function CookOrdersPage() {
  return (
    <Suspense fallback={null}>
      <CookOrders />
    </Suspense>
  );
}

/** /cook/orders - orders placed with me, by tab (URL: ?tab=&offset=), with the cook's actions. */
function CookOrders() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const kitchen = useKitchen();
  const tab = TABS.find((candidate) => candidate.key === params.get("tab")) ?? TABS[0];
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const { data: page, error, reload } = useApi<OrderPage>(ordersPath(tab, PAGE_SIZE, offset));
  const requests = useApi<OrderPage>(ordersPath(TABS[0], 1));
  const progress = useApi<OrderPage>(ordersPath(TABS[1], 1));
  const [actionError, setActionError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const counts: Record<string, number | undefined> = {
    requests: requests.data?.total,
    progress: progress.data?.total,
  };

  const { reload: reloadRequests } = requests;
  const { reload: reloadProgress } = progress;
  useEffect(() => {
    const timer = window.setInterval(() => {
      void reload();
      void reloadRequests();
      void reloadProgress();
    }, REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [reload, reloadRequests, reloadProgress]);

  const go = (nextTab: string, nextOffset = 0) => {
    const next = new URLSearchParams();
    if (nextTab !== TABS[0].key) next.set("tab", nextTab);
    if (nextOffset) next.set("offset", String(nextOffset));
    setNotice(null);
    setActionError(null);
    router.push(next.size ? `${pathname}?${next.toString()}` : pathname, { scroll: false });
  };

  const afterMove = (updated: Order | null) => {
    if (updated) setNotice(noticeFor(updated));
    void reload();
    void reloadRequests();
    void reloadProgress();
    void kitchen.refresh();
  };

  return (
    <div className="space-y-6">
      <PageHeader
        size="compact"
        title="Orders"
        lead="Answer new requests, then move each order along: accepted, ready - the customer confirms pickup."
      />

      <div
        role="tablist"
        aria-label="Filter orders"
        className="-mx-4 flex gap-1 overflow-x-auto px-4 [scrollbar-width:none] sm:mx-0 sm:px-0"
      >
        <div className="flex gap-1 rounded-full border border-line bg-surface p-1">
          {TABS.map((candidate) => {
            const count = counts[candidate.key];
            const selected = candidate.key === tab.key;
            return (
              <button
                key={candidate.key}
                role="tab"
                type="button"
                aria-selected={selected}
                onClick={() => go(candidate.key)}
                className={cx(
                  "inline-flex h-9 shrink-0 items-center gap-2 rounded-full px-4 text-sm font-medium transition-colors",
                  selected ? "bg-ink text-canvas" : "text-ink-muted hover:text-ink",
                )}
              >
                {candidate.label}
                <CountPill count={count} active={selected} tone={candidate.key === "requests" ? "brand" : "quiet"} />
              </button>
            );
          })}
        </div>
      </div>

      {notice && (
        <p role="status" className="animate-rise flex items-center gap-2 rounded-2xl bg-herb-soft px-4 py-3 text-sm text-ink">
          <CircleCheck className="h-4 w-4 shrink-0 text-herb" aria-hidden="true" /> {notice}
        </p>
      )}
      <ErrorBanner lines={[...(error ? [error] : []), ...(actionError ? [actionError] : [])]} />

      {!page ? (
        <div className="space-y-3" aria-busy="true">
          {[0, 1, 2].map((key) => (
            <div key={key} className="h-36 animate-pulse rounded-3xl bg-muted" />
          ))}
        </div>
      ) : page.items.length === 0 ? (
        <EmptyState icon={<Inbox className="h-6 w-6" />} title={emptyTitle(tab)}>
          {tab.key === "requests"
            ? "New orders land here first. This page checks for them every 30 seconds."
            : tab.key === "progress"
              ? "Accepted orders wait here until the customer confirms they have them."
              : "Orders you've handled will show up here."}
        </EmptyState>
      ) : (
        <>
          <ul className="space-y-3">
            {page.items.map((order) => (
              <li key={order.id}>
                <OrderCard
                  order={order}
                  perspective="cook"
                  meta={<OrderMeta order={order} />}
                  actions={
                    ["placed", "accepted", "ready"].includes(order.status) ? (
                      <CookOrderActions order={order} onChanged={afterMove} onError={setActionError} />
                    ) : undefined
                  }
                />
              </li>
            ))}
          </ul>
          {page.total > PAGE_SIZE && (
            <Pager total={page.total} limit={PAGE_SIZE} offset={offset} onMove={(next) => go(tab.key, next)} />
          )}
        </>
      )}
    </div>
  );
}

function emptyTitle(tab: Tab): string {
  if (tab.key === "requests") return "No requests waiting";
  if (tab.key === "progress") return "Nothing in the kitchen";
  if (tab.key === "all") return "No orders yet";
  return `No ${tab.label.toLowerCase()} orders`;
}

function noticeFor(order: Order): string {
  const who = order.customer.name ?? "The customer";
  switch (order.status) {
    case "accepted":
      return `Accepted - ${who} can see you're on it.`;
    case "ready":
      return `Marked ready - ${who} knows it's packed.`;
    case "completed":
      return "Received by the customer - the order counts towards your earnings.";
    case "cancelled":
      return order.accepted_at ? `Order cancelled - ${who} was told.` : `Request rejected - ${who} was told.`;
    default:
      return "Order updated.";
  }
}

function OrderMeta({ order }: { order: Order }) {
  const parts: React.ReactNode[] = [];
  if (["placed", "accepted", "ready"].includes(order.status)) {
    parts.push(
      <span key="queue" className={order.status === "placed" ? "font-medium text-saffron" : undefined}>
        {queueMeta(order)}
      </span>,
    );
  } else if (order.status === "completed") {
    parts.push(<span key="done">Received by the customer {formatDateTime(order.completed_at)}</span>);
  } else if (order.status === "cancelled") {
    parts.push(
      <span key="cancelled">
        {cancelledLabel(order, "cook")}
        {order.cancel_reason && <> · “{order.cancel_reason}”</>}
      </span>,
    );
  }
  const place = order.delivery_address;
  if (place) {
    parts.push(<span key="where">{place.zone?.name ?? place.city}</span>);
  }
  if (order.note) parts.push(<span key="note">Note: “{order.note}”</span>);
  return (
    <span className="flex flex-wrap gap-x-3 gap-y-1">
      {parts.map((part, index) => (
        <span key={index} className="min-w-0">
          {index > 0 && <span className="mr-3 text-line-strong" aria-hidden="true">·</span>}
          {part}
        </span>
      ))}
    </span>
  );
}
