import { ArrowRight, Banknote, CreditCard, Info, Lock, Smartphone, Wallet } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";

import { Badge, PageHeader, cx, ghostButtonClass } from "@/components/ui";

export const metadata: Metadata = { title: "Payments" };

const WALLETS = [
  { name: "Credit or debit card", icon: CreditCard, detail: "Visa, Mastercard, Amex" },
  { name: "Apple Pay / Google Pay", icon: Smartphone, detail: "Pay with your phone" },
  { name: "PayPal", icon: Wallet, detail: "Pay from your PayPal balance" },
];

/**
 * /account/payments - a static design for now: Plateboard does not take
 * payments online yet (customers pay the cook directly), so saved methods are
 * shown as "coming soon" rather than pretending to work.
 */
export default function PaymentsPage() {
  return (
    <div className="space-y-6">
      <PageHeader size="compact" title="Payments" lead="How you pay for your orders." />

      <p className="flex gap-3 rounded-3xl border border-line bg-surface p-5 text-sm leading-relaxed text-ink-muted shadow-card">
        <Info className="mt-0.5 h-5 w-5 shrink-0 text-ink-soft" aria-hidden="true" />
        <span>
          <span className="font-semibold text-ink">Plateboard doesn&apos;t take payments online yet.</span> You pay your
          cook directly - how (cash, card or transfer) is agreed once they accept your order. Saved payment methods are
          on their way.
        </span>
      </p>

      <section className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
        <h2 className="font-display text-xl font-semibold text-ink">Current method</h2>
        <div className="mt-4 flex items-center gap-4 rounded-2xl border border-ink p-4">
          <span className="flex h-11 w-11 items-center justify-center rounded-xl bg-herb-soft text-herb">
            <Banknote className="h-5 w-5" aria-hidden="true" />
          </span>
          <div className="flex-1">
            <p className="font-medium text-ink">Pay the cook directly</p>
            <p className="text-sm text-ink-muted">Arranged with your cook for every order</p>
          </div>
          <Badge tone="night">Default</Badge>
        </div>
      </section>

      <section className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 className="font-display text-xl font-semibold text-ink">Saved methods</h2>
          <Badge tone="brand">Coming soon</Badge>
        </div>

        <div
          aria-hidden="true"
          className="relative mt-5 aspect-[1.586] w-full max-w-sm overflow-hidden rounded-3xl bg-[linear-gradient(135deg,#2a211c,#4a3328_60%,#c4471b)] p-6 text-white/90 opacity-60 shadow-lift"
        >
          <div className="absolute -right-10 -top-10 h-40 w-40 rounded-full bg-white/10" />
          <p className="font-display text-lg font-semibold">Plateboard</p>
          <p className="absolute bottom-14 left-6 font-mono text-lg tracking-[0.2em]">•••• •••• •••• ••••</p>
          <p className="absolute bottom-6 left-6 text-xs uppercase tracking-[0.2em]">Your card here</p>
        </div>

        <ul className="mt-6 divide-y divide-line">
          {WALLETS.map((wallet) => (
            <li key={wallet.name} className="flex items-center gap-4 py-3">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-muted text-ink-muted">
                <wallet.icon className="h-5 w-5" aria-hidden="true" />
              </span>
              <div className="flex-1">
                <p className="text-sm font-medium text-ink">{wallet.name}</p>
                <p className="text-xs text-ink-soft">{wallet.detail}</p>
              </div>
              <button type="button" disabled className={cx(ghostButtonClass, "h-9 px-4 text-[13px]")}>
                <Lock className="h-3.5 w-3.5" aria-hidden="true" /> Add
              </button>
            </li>
          ))}
        </ul>
      </section>

      <Link
        href="/account/invoices"
        className="group flex items-center justify-between rounded-3xl border border-line bg-surface p-5 transition-shadow hover:shadow-card sm:px-6"
      >
        <span>
          <span className="block font-semibold text-ink">Payment history</span>
          <span className="text-sm text-ink-muted">Every completed order has an invoice.</span>
        </span>
        <ArrowRight className="h-5 w-5 text-ink-soft transition-transform group-hover:translate-x-0.5" />
      </Link>
    </div>
  );
}
