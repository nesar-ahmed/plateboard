"use client";

import { ArrowUpRight, FileText } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { StatCard } from "@/components/charts";
import { ButtonLink, EmptyState, ErrorBanner, PageHeader, Pager } from "@/components/ui";
import type { CustomerDashboard, OrderPage } from "@/lib/api";
import { formatDate, formatMinorUnits, invoiceNumber } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const PAGE_SIZE = 10;

/** /account/invoices - one invoice per completed order, newest first. */
export default function InvoicesPage() {
  const [offset, setOffset] = useState(0);
  const { data: page, error } = useApi<OrderPage>(
    `/me/orders?status=completed&limit=${PAGE_SIZE}&offset=${offset}`,
  );
  const { data: summary } = useApi<CustomerDashboard>("/me/dashboard?months=1");

  return (
    <div className="space-y-6">
      <PageHeader
        size="compact"
        title="Invoices"
        lead="An invoice is issued for every completed order - print it or save it as a PDF."
      />

      <div className="grid grid-cols-2 gap-3 sm:max-w-lg sm:gap-4">
        <StatCard label="Invoices" value={summary ? summary.orders.by_status.completed : "…"} />
        <StatCard label="Total invoiced" value={summary ? formatMinorUnits(summary.orders.completed_value) : "…"} />
      </div>

      <ErrorBanner lines={error ? [error] : []} />

      {!page ? (
        <div className="h-64 animate-pulse rounded-3xl bg-muted" aria-busy="true" />
      ) : page.items.length === 0 ? (
        <EmptyState
          icon={<FileText className="h-6 w-6" />}
          title="No invoices yet"
          action={<ButtonLink href="/account/orders">See your orders</ButtonLink>}
        >
          Invoices appear here once your orders are completed.
        </EmptyState>
      ) : (
        <div className="overflow-hidden rounded-3xl border border-line bg-surface shadow-card">
          <div className="hidden grid-cols-[1.2fr_1fr_1.4fr_1fr_auto] gap-4 border-b border-line px-6 py-3 text-xs font-semibold uppercase tracking-[0.1em] text-ink-soft md:grid">
            <span>Invoice</span>
            <span>Issued</span>
            <span>Kitchen</span>
            <span className="text-right">Amount</span>
            <span className="w-16" />
          </div>
          <ul className="divide-y divide-line">
            {page.items.map((order) => (
              <li
                key={order.id}
                className="relative grid grid-cols-[1fr_auto] gap-x-4 gap-y-1 px-5 py-4 hover:bg-canvas md:grid-cols-[1.2fr_1fr_1.4fr_1fr_auto] md:items-center md:px-6"
              >
                <Link
                  href={`/account/orders/${order.id}/invoice`}
                  className="flex items-center gap-3 font-medium tabular-nums text-ink after:absolute after:inset-0 after:content-['']"
                >
                  <span className="hidden h-9 w-9 items-center justify-center rounded-xl bg-muted text-ink-muted sm:flex">
                    <FileText className="h-4 w-4" aria-hidden="true" />
                  </span>
                  {invoiceNumber(order.id)}
                </Link>
                <span className="order-3 text-sm text-ink-muted md:order-none">{formatDate(order.completed_at)}</span>
                <span className="order-4 truncate text-sm text-ink-muted md:order-none">{order.cook.name ?? "Home cook"}</span>
                <span className="text-right font-semibold tabular-nums text-ink md:order-none">
                  {formatMinorUnits(order.total)}
                </span>
                <span className="hidden w-16 justify-end text-sm font-semibold text-brand md:flex">
                  View <ArrowUpRight className="h-4 w-4" aria-hidden="true" />
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
      {page && page.total > PAGE_SIZE && (
        <Pager total={page.total} limit={PAGE_SIZE} offset={offset} onMove={setOffset} />
      )}
    </div>
  );
}
