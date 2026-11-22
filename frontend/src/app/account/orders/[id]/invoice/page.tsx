"use client";

import { ArrowLeft, Printer } from "lucide-react";
import Link from "next/link";
import { useParams } from "next/navigation";

import Logo from "@/components/logo";
import { ButtonLink, ErrorBanner, Spinner, cx, darkButtonClass } from "@/components/ui";
import type { Order } from "@/lib/api";
import { formatDate, formatMinorUnits, invoiceNumber, orderRef } from "@/lib/format";
import { useApi } from "@/lib/use-api";

/**
 * /account/orders/{id}/invoice - a printable invoice for a completed order,
 * built from the order's own snapshot (names, prices, delivery address), so
 * it never changes after the fact. "Print" = the browser's print/PDF; the
 * site chrome is hidden in print.
 */
export default function InvoicePage() {
  const { id } = useParams<{ id: string }>();
  const { data: order, error } = useApi<Order>(`/me/orders/${id}`);

  if (error) return <ErrorBanner lines={[error]} />;
  if (!order) {
    return (
      <div className="flex justify-center py-16 text-ink-muted">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  if (order.status !== "completed") {
    return (
      <div className="space-y-4">
        <p className="rounded-2xl bg-muted px-4 py-3 text-sm text-ink-muted">
          Invoices are issued once an order is completed - this one is {order.status}.
        </p>
        <ButtonLink href={`/account/orders/${order.id}`} variant="ghost">
          Back to the order
        </ButtonLink>
      </div>
    );
  }

  const address = order.delivery_address;
  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center justify-between gap-3 print:hidden">
        <Link
          href={`/account/orders/${order.id}`}
          className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink"
        >
          <ArrowLeft className="h-4 w-4" /> Order {orderRef(order.id)}
        </Link>
        <button type="button" onClick={() => window.print()} className={cx(darkButtonClass, "h-10")}>
          <Printer className="h-4 w-4" /> Print or save as PDF
        </button>
      </div>

      <article
        aria-label={`Invoice ${invoiceNumber(order.id)}`}
        className="rounded-3xl border border-line bg-surface p-6 shadow-card sm:p-10 print:rounded-none print:border-0 print:p-0 print:shadow-none"
      >
        <header className="flex flex-col gap-6 border-b border-line pb-8 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <Logo />
            <p className="mt-3 max-w-xs text-xs leading-relaxed text-ink-soft">
              Home-cooked food from neighbourhood kitchens.
            </p>
          </div>
          <div className="sm:text-right">
            <h1 className="font-display text-3xl font-semibold tracking-tight text-ink">Invoice</h1>
            <dl className="mt-3 grid grid-cols-[auto_auto] gap-x-4 gap-y-1 text-sm sm:justify-end">
              <dt className="text-ink-soft">Invoice no.</dt>
              <dd className="font-medium tabular-nums text-ink">{invoiceNumber(order.id)}</dd>
              <dt className="text-ink-soft">Issued</dt>
              <dd className="text-ink">{formatDate(order.completed_at)}</dd>
              <dt className="text-ink-soft">Order</dt>
              <dd className="text-ink">
                {orderRef(order.id)} · {formatDate(order.created_at)}
              </dd>
            </dl>
          </div>
        </header>

        <section className="grid grid-cols-1 gap-8 border-b border-line py-8 sm:grid-cols-2">
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">From</p>
            <p className="mt-2 font-medium text-ink">{order.cook.name ?? "Home cook"}</p>
            <p className="text-sm text-ink-muted">Home kitchen on Plateboard</p>
          </div>
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">Billed to</p>
            {address ? (
              <div className="mt-2 text-sm leading-relaxed text-ink-muted">
                <p className="font-medium text-ink">{address.recipient}</p>
                <p>
                  {address.line1}
                  {address.line2 && `, ${address.line2}`}
                </p>
                <p>{[address.postal_code, address.city].filter(Boolean).join(" ")}</p>
                <p>{address.phone}</p>
              </div>
            ) : (
              <p className="mt-2 font-medium text-ink">{order.customer.name ?? "Customer"}</p>
            )}
          </div>
        </section>

        <table className="mt-8 w-full text-sm">
          <thead>
            <tr className="border-b border-line text-left text-xs uppercase tracking-[0.1em] text-ink-soft">
              <th scope="col" className="pb-3 font-semibold">Item</th>
              <th scope="col" className="pb-3 text-right font-semibold">Qty</th>
              <th scope="col" className="hidden pb-3 text-right font-semibold sm:table-cell print:table-cell">
                Unit price
              </th>
              <th scope="col" className="pb-3 text-right font-semibold">Amount</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-line">
            {order.items.map((item, index) => (
              <tr key={`${item.name}-${index}`}>
                <td className="py-3 pr-4 text-ink">{item.name}</td>
                <td className="py-3 text-right tabular-nums text-ink-muted">{item.quantity}</td>
                <td className="hidden py-3 text-right tabular-nums text-ink-muted sm:table-cell print:table-cell">
                  {formatMinorUnits(item.unit_price)}
                </td>
                <td className="py-3 text-right tabular-nums text-ink">{formatMinorUnits(item.line_total)}</td>
              </tr>
            ))}
          </tbody>
        </table>

        <dl className="ml-auto mt-6 w-full max-w-xs space-y-2 border-t border-line pt-4 text-sm">
          <div className="flex justify-between text-ink-muted">
            <dt>Subtotal · {order.item_count} portions</dt>
            <dd className="tabular-nums">{formatMinorUnits(order.total)}</dd>
          </div>
          <div className="flex items-baseline justify-between">
            <dt className="font-semibold text-ink">Total</dt>
            <dd className="font-display text-2xl font-semibold tabular-nums text-ink">{formatMinorUnits(order.total)}</dd>
          </div>
        </dl>

        <footer className="mt-10 border-t border-line pt-6 text-xs leading-relaxed text-ink-soft">
          Payment for this order was arranged directly with the cook. Prices are the ones shown when the order
          was placed. Thank you for ordering from a neighbourhood kitchen.
        </footer>
      </article>
    </div>
  );
}
