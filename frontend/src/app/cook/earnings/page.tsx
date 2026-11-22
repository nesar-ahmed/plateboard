"use client";

import { Ban, Banknote, Hourglass, Info, Receipt, TrendingUp, Wallet } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import { BarChart, Meter, StatCard, Trend } from "@/components/charts";
import DishArt from "@/components/dish-art";
import { EmptyState, ErrorBanner, PageHeader, cx } from "@/components/ui";
import type { CookEarnings } from "@/lib/api";
import { formatDate, formatMinorUnits } from "@/lib/format";
import { EARNINGS_RANGES, periodLabel, periodTitle, plural, trendPercent, utcDaysAgo } from "@/lib/kitchen";
import { useApi } from "@/lib/use-api";

const money = (minor: number) => formatMinorUnits(minor);
const short = (minor: number) => formatMinorUnits(minor).replace(/\.00$/, "");

export default function EarningsPage() {
  return (
    <Suspense fallback={null}>
      <Earnings />
    </Suspense>
  );
}

/**
 * /cook/earnings (GET /api/cooks/me/earnings): money from completed orders
 * over a range (URL: ?range=7d|30d|90d|12m), compared with the range before,
 * per day/week/month and per dish, plus what is still on its way.
 */
function Earnings() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const range = EARNINGS_RANGES.find((candidate) => candidate.key === params.get("range")) ?? EARNINGS_RANGES[1];
  // The start date is fixed per range for the life of the page (UTC days).
  const [starts] = useState(() =>
    Object.fromEntries(EARNINGS_RANGES.map((candidate) => [candidate.key, utcDaysAgo(candidate.days - 1)])),
  );
  const { data, error } = useApi<CookEarnings>(`/cooks/me/earnings?start=${starts[range.key]}&group=${range.group}`);

  const pick = (key: string) => {
    const next = new URLSearchParams();
    if (key !== EARNINGS_RANGES[1].key) next.set("range", key);
    router.push(next.size ? `${pathname}?${next.toString()}` : pathname, { scroll: false });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        size="compact"
        title="Earnings"
        lead="Money from orders you handed over. An order counts on the day it's completed."
      />

      <div role="tablist" aria-label="Period" className="flex gap-1 rounded-full border border-line bg-surface p-1 sm:w-fit">
        {EARNINGS_RANGES.map((candidate) => (
          <button
            key={candidate.key}
            role="tab"
            type="button"
            aria-selected={candidate.key === range.key}
            onClick={() => pick(candidate.key)}
            className={cx(
              "h-9 flex-1 whitespace-nowrap rounded-full px-3 text-sm font-medium transition-colors sm:flex-none sm:px-4",
              candidate.key === range.key ? "bg-ink text-canvas" : "text-ink-muted hover:text-ink",
            )}
          >
            {candidate.label}
          </button>
        ))}
      </div>

      <ErrorBanner lines={error ? [error] : []} />

      {!data || data.range.group !== range.group || data.range.start !== starts[range.key] ? (
        <EarningsSkeleton />
      ) : (
        <EarningsReport data={data} compare={range.compare} />
      )}
    </div>
  );
}

function EarningsReport({ data, compare }: { data: CookEarnings; compare: string }) {
  const { summary, previous, range } = data;
  const best = data.series.reduce((top, point) => (point.earned > top.earned ? point : top), data.series[0]);
  const labelEvery = data.series.length > 16 ? 5 : 1;
  return (
    <>
      <p className="text-sm text-ink-muted">
        {formatDate(`${range.start}T00:00:00Z`)} – {formatDate(`${range.end}T00:00:00Z`)}
      </p>

      <section aria-label="Summary" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
        <StatCard
          label="Earned"
          value={money(summary.earned)}
          hint={<Trend percent={trendPercent(summary.earned, previous.earned)} label={compare} />}
          icon={<Wallet className="h-[18px] w-[18px]" />}
          tone="brand"
        />
        <StatCard
          label="Orders handed over"
          value={summary.orders}
          hint={<Trend percent={trendPercent(summary.orders, previous.orders)} label={compare} />}
          icon={<Receipt className="h-[18px] w-[18px]" />}
          tone="herb"
        />
        <StatCard
          label="Average order"
          value={money(summary.average_order_value)}
          hint={`${plural(summary.portions, "portion")} in total`}
          icon={<TrendingUp className="h-[18px] w-[18px]" />}
        />
        <StatCard
          label="Lost to cancellations"
          value={money(summary.cancelled_value)}
          hint={
            summary.cancelled_orders === 0
              ? "Nothing cancelled - nice"
              : `${plural(summary.cancelled_orders, "order")} · ${summary.rejected_orders} rejected by you`
          }
          icon={<Ban className="h-[18px] w-[18px]" />}
          tone="saffron"
        />
      </section>

      <section className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
        <div className="mb-4 flex flex-wrap items-baseline justify-between gap-3">
          <h2 className="font-display text-lg font-semibold text-ink">
            Earnings per {range.group === "day" ? "day" : range.group === "week" ? "week" : "month"}
          </h2>
          {best && best.earned > 0 && (
            <p className="text-xs text-ink-soft">
              Best: <span className="font-semibold text-ink">{periodTitle(best.period, range.group)}</span> ·{" "}
              {money(best.earned)}
            </p>
          )}
        </div>
        <BarChart
          ariaLabel={`Earnings per ${range.group}`}
          bars={data.series.map((point) => ({
            label: periodLabel(point.period, range.group, range.days),
            title: periodTitle(point.period, range.group),
            value: point.earned,
            hint: plural(point.orders, "order"),
          }))}
          format={short}
          showValues={data.series.length <= 16}
          labelEvery={labelEvery}
          height={200}
        />
      </section>

      <section className="grid grid-cols-1 items-start gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
        <div className="rounded-3xl border border-line bg-surface shadow-card">
          <div className="flex items-baseline justify-between gap-3 border-b border-line px-5 py-4 sm:px-6">
            <h2 className="font-display text-lg font-semibold text-ink">By dish</h2>
            <p className="text-xs text-ink-soft">{plural(data.dishes.length, "dish", "dishes")} sold</p>
          </div>
          {data.dishes.length === 0 ? (
            <div className="p-5">
              <EmptyState icon={<Wallet className="h-6 w-6" />} title="No sales in this period">
                Completed orders in this period will be broken down by dish here.
              </EmptyState>
            </div>
          ) : (
            <ul className="divide-y divide-line">
              {data.dishes.map((dish) => (
                <li key={dish.dish_id ?? dish.name} className="flex items-center gap-4 px-5 py-4 sm:px-6">
                  <DishArt dish={dish} size="xs" className="h-11 w-11 shrink-0" rounded="rounded-xl" />
                  <div className="min-w-0 flex-1">
                    <div className="flex items-baseline justify-between gap-3">
                      {dish.dish_id ? (
                        <Link
                          href={`/cook/dishes/${dish.dish_id}`}
                          className="truncate text-sm font-medium text-ink hover:text-brand"
                        >
                          {dish.name}
                        </Link>
                      ) : (
                        <p className="truncate text-sm font-medium text-ink">{dish.name}</p>
                      )}
                      <p className="shrink-0 text-sm font-semibold tabular-nums text-ink">{money(dish.value)}</p>
                    </div>
                    <Meter
                      className="mt-2"
                      value={summary.earned ? dish.value / summary.earned : 0}
                      tone="ink"
                    />
                    <p className="mt-1 text-xs text-ink-soft">
                      {plural(dish.quantity, "portion")} · {plural(dish.orders, "order")} ·{" "}
                      {summary.earned ? Math.round((dish.value / summary.earned) * 100) : 0}% of earnings
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-4">
          <div className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
            <h2 className="flex items-center gap-2 font-display text-lg font-semibold text-ink">
              <Hourglass className="h-5 w-5 text-saffron" aria-hidden="true" /> On its way
            </h2>
            <p className="mt-0.5 text-xs text-ink-soft">Open orders - earned once the customer confirms pickup</p>
            <dl className="mt-4 space-y-3 text-sm">
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-ink-muted">Being cooked · {plural(data.in_progress.orders, "order")}</dt>
                <dd className="font-semibold tabular-nums text-ink">{money(data.in_progress.value)}</dd>
              </div>
              <div className="flex items-baseline justify-between gap-3">
                <dt className="text-ink-muted">
                  Waiting for your answer · {plural(data.awaiting_acceptance.orders, "request")}
                </dt>
                <dd className="font-semibold tabular-nums text-ink">{money(data.awaiting_acceptance.value)}</dd>
              </div>
            </dl>
            {data.awaiting_acceptance.orders > 0 && (
              <Link href="/cook/orders" className="mt-4 inline-block text-sm font-semibold text-brand hover:underline">
                Answer requests
              </Link>
            )}
          </div>
          <div className="rounded-3xl bg-night p-5 text-on-night sm:p-6">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">Since you started</p>
            <p className="mt-2 font-display text-3xl font-semibold tabular-nums">{money(data.lifetime.value)}</p>
            <p className="mt-1 text-sm text-on-night/70">from {plural(data.lifetime.orders, "completed order")}</p>
          </div>
          <p className="flex gap-3 rounded-3xl border border-line bg-surface p-5 text-sm leading-relaxed text-ink-muted">
            <Banknote className="mt-0.5 h-5 w-5 shrink-0 text-herb" aria-hidden="true" />
            <span>
              <span className="font-semibold text-ink">You&apos;re paid directly.</span> Customers pay you at handover -
              Plateboard doesn&apos;t process payments online yet, so there are no payouts to wait for.
            </span>
          </p>
        </div>
      </section>

      <p className="flex items-center gap-2 text-xs text-ink-soft">
        <Info className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
        Days follow UTC. Cancellations count on the day they were cancelled.
      </p>
    </>
  );
}

function EarningsSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true">
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {[0, 1, 2, 3].map((key) => (
          <div key={key} className="h-32 animate-pulse rounded-3xl bg-muted" />
        ))}
      </div>
      <div className="h-72 animate-pulse rounded-3xl bg-muted" />
    </div>
  );
}
