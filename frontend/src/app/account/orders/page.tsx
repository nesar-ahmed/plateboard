"use client";

import { FileText, Receipt } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { OrderCard } from "@/components/order-bits";
import ReceiveButton from "@/components/receive-button";
import ReorderButton from "@/components/reorder-button";
import {
  ButtonLink,
  EmptyState,
  ErrorBanner,
  PageHeader,
  Pager,
  cx,
  darkButtonClass,
  quietButtonClass,
  smallButton,
} from "@/components/ui";
import type { Order, OrderPage, OrderStatus } from "@/lib/api";
import { orderRef } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const PAGE_SIZE = 10;

const TABS: { key: string; label: string; statuses: OrderStatus[] }[] = [
  { key: "all", label: "All", statuses: [] },
  { key: "active", label: "Active", statuses: ["placed", "accepted", "ready"] },
  { key: "completed", label: "Completed", statuses: ["completed"] },
  { key: "cancelled", label: "Cancelled", statuses: ["cancelled"] },
];

export default function OrdersPage() {
  return (
    <Suspense fallback={null}>
      <Orders />
    </Suspense>
  );
}

/** /account/orders - every order, by status tab (URL: ?tab=&offset=). */
function Orders() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const tab = TABS.find((candidate) => candidate.key === params.get("tab")) ?? TABS[0];
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  for (const status of tab.statuses) query.append("status", status);
  const { data: page, error, setData } = useApi<OrderPage>(`/me/orders?${query.toString()}`);
  const [notice, setNotice] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  /** A ready order the customer just confirmed: swap in the completed one. */
  const received = (completed: Order) => {
    setData((current) => current && { ...current, items: current.items.map((o) => (o.id === completed.id ? completed : o)) });
    setActionError(null);
    setNotice(`Enjoy your meal! Order ${orderRef(completed.id)} is complete.`);
  };

  const go = (nextTab: string, nextOffset = 0) => {
    const next = new URLSearchParams();
    if (nextTab !== "all") next.set("tab", nextTab);
    if (nextOffset) next.set("offset", String(nextOffset));
    router.push(next.size ? `${pathname}?${next.toString()}` : pathname, { scroll: false });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        size="compact"
        title="Orders"
        lead="Track what's cooking, download invoices and order your favourites again."
      />

      <div role="tablist" aria-label="Filter orders" className="flex gap-1 rounded-full border border-line bg-surface p-1 sm:w-fit">
        {TABS.map((candidate) => (
          <button
            key={candidate.key}
            role="tab"
            type="button"
            aria-selected={candidate.key === tab.key}
            onClick={() => go(candidate.key)}
            className={cx(
              "h-9 flex-1 rounded-full px-4 text-sm font-medium transition-colors sm:flex-none",
              candidate.key === tab.key ? "bg-ink text-canvas" : "text-ink-muted hover:text-ink",
            )}
          >
            {candidate.label}
          </button>
        ))}
      </div>

      {notice && (
        <p role="status" className="animate-rise rounded-2xl bg-herb-soft px-4 py-3 text-sm text-ink">
          {notice}
        </p>
      )}
      <ErrorBanner lines={error ? [error] : actionError ? [actionError] : []} />

      {!page ? (
        <div className="space-y-3" aria-busy="true">
          {[0, 1, 2].map((key) => (
            <div key={key} className="h-28 animate-pulse rounded-3xl bg-muted" />
          ))}
        </div>
      ) : page.items.length === 0 ? (
        <EmptyState
          icon={<Receipt className="h-6 w-6" />}
          title={tab.key === "all" ? "No orders yet" : `No ${tab.label.toLowerCase()} orders`}
          action={<ButtonLink href="/dishes">Browse dishes</ButtonLink>}
        >
          {tab.key === "active" ? "Nothing is cooking for you right now." : "Your orders will appear here."}
        </EmptyState>
      ) : (
        <>
          <ul className="space-y-3">
            {page.items.map((order) => (
              <li key={order.id}>
                <OrderCard
                  order={order}
                  actions={
                    <>
                      {order.status === "ready" && (
                        <ReceiveButton order={order} onDone={received} onError={setActionError} />
                      )}
                      {["placed", "accepted", "ready"].includes(order.status) && (
                        <Link
                          href={`/account/orders/${order.id}`}
                          className={cx(order.status === "ready" ? quietButtonClass : darkButtonClass, smallButton)}
                        >
                          Track order
                        </Link>
                      )}
                      {order.status === "completed" && (
                        <Link
                          href={`/account/orders/${order.id}/invoice`}
                          className={cx(quietButtonClass, smallButton)}
                        >
                          <FileText className="h-3.5 w-3.5" aria-hidden="true" /> Invoice
                        </Link>
                      )}
                      {(order.status === "completed" || order.status === "cancelled") && (
                        <ReorderButton order={order} onDone={setNotice} className="ml-auto" />
                      )}
                    </>
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
