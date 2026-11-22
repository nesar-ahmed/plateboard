"use client";

import {
  ArrowRight,
  CalendarDays,
  CircleCheck,
  Circle,
  Hourglass,
  Plus,
  ShoppingBag,
  TrendingUp,
  Users,
  UtensilsCrossed,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AvailabilityPill } from "@/components/availability";
import { BarChart, Donut, Meter, StatCard } from "@/components/charts";
import CookOrderActions from "@/components/cook-order-actions";
import DishArt from "@/components/dish-art";
import { OrderCard, STATUS_META } from "@/components/order-bits";
import { Avatar, ButtonLink, ErrorBanner, PageHeader, cx } from "@/components/ui";
import type { AvailabilitySettings, CookDashboard, CookEarnings, OrderStatus } from "@/lib/api";
import { formatMinorUnits, formatRelative } from "@/lib/format";
import {
  CHECKLIST_META,
  formatMinutes,
  formatRate,
  periodLabel,
  periodTitle,
  plural,
  queueMeta,
  utcDaysAgo,
} from "@/lib/kitchen";
import { useKitchen } from "@/lib/kitchen-context";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

/** The queue and the numbers refresh on their own while the page is open. */
const REFRESH_MS = 30_000;
const QUEUE_SHOWN = 3;
const CHART_DAYS = 14;

function greeting(now = new Date()): string {
  const hour = now.getHours();
  return hour < 5 ? "Good evening" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

const money = (minor: number) => formatMinorUnits(minor);
const short = (minor: number) => formatMinorUnits(minor).replace(/\.00$/, "");

/** /cook - the kitchen overview (GET /api/cooks/me/dashboard + a 14-day earnings series). */
export default function KitchenOverview() {
  const { user } = useSession();
  const kitchen = useKitchen();
  const dashboard = useApi<CookDashboard>("/cooks/me/dashboard?days=30");
  const [chartStart] = useState(() => utcDaysAgo(CHART_DAYS - 1));
  const earnings = useApi<CookEarnings>(`/cooks/me/earnings?start=${chartStart}`);
  const hours = useApi<AvailabilitySettings>("/cooks/me/availability");
  const [actionError, setActionError] = useState<string | null>(null);
  const d = dashboard.data;
  const firstName = user?.display_name?.split(" ")[0];

  const { reload: reloadDashboard } = dashboard;
  const { reload: reloadEarnings } = earnings;
  useEffect(() => {
    const timer = window.setInterval(() => void reloadDashboard(), REFRESH_MS);
    return () => window.clearInterval(timer);
  }, [reloadDashboard]);

  const afterMove = () => {
    void reloadDashboard();
    void reloadEarnings();
    void kitchen.refresh();
  };

  return (
    <div className="space-y-8">
      <PageHeader
        size="compact"
        title={`${greeting()}${firstName ? `, ${firstName}` : ""}`}
        lead={d ? headline(d) : "Here's how your kitchen is doing."}
        actions={
          <>
            {hours.data && (
              <Link
                href="/cook/hours"
                title="Hours & availability"
                className="inline-flex h-10 items-center rounded-full border border-line bg-surface px-2 hover:border-line-strong"
              >
                <AvailabilityPill availability={hours.data.availability} />
              </Link>
            )}
            <ButtonLink href="/cook/dishes/new" variant="dark" className="h-10">
              <Plus className="h-4 w-4" /> Add dish
            </ButtonLink>
          </>
        }
      />

      <ErrorBanner lines={[...(dashboard.error ? [dashboard.error] : []), ...(actionError ? [actionError] : [])]} />

      {!d ? (
        <OverviewSkeleton />
      ) : (
        <>
          <Checklist dashboard={d} />

          <Queue dashboard={d} onMoved={afterMove} onError={setActionError} />

          <section aria-label="Your earnings" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <StatCard
              label="Earned today"
              value={money(d.earnings.today.value)}
              hint={`${plural(d.earnings.today.orders, "order")} handed over`}
              icon={<Wallet className="h-[18px] w-[18px]" />}
              tone="brand"
            />
            <StatCard
              label="Last 7 days"
              value={money(d.earnings.last_7_days.value)}
              hint={plural(d.earnings.last_7_days.orders, "order")}
              icon={<TrendingUp className="h-[18px] w-[18px]" />}
              tone="herb"
            />
            <StatCard
              label="This month"
              value={money(d.earnings.this_month.value)}
              hint={`${money(d.earnings.lifetime.value)} since you started`}
              icon={<CalendarDays className="h-[18px] w-[18px]" />}
            />
            <StatCard
              label="In the pipeline"
              value={money(d.earnings.in_progress.value)}
              hint={
                d.earnings.awaiting_acceptance.orders > 0
                  ? `+ ${money(d.earnings.awaiting_acceptance.value)} waiting for your answer`
                  : `${plural(d.earnings.in_progress.orders, "order")} being cooked`
              }
              icon={<Hourglass className="h-[18px] w-[18px]" />}
              tone="saffron"
            />
          </section>

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <div className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
              <div className="mb-4 flex items-baseline justify-between gap-3">
                <h2 className="font-display text-lg font-semibold text-ink">Earnings</h2>
                <Link href="/cook/earnings" className="text-sm font-semibold text-brand hover:underline">
                  Last {CHART_DAYS} days
                </Link>
              </div>
              {earnings.data ? (
                <BarChart
                  ariaLabel={`Earnings per day over the last ${CHART_DAYS} days`}
                  bars={earnings.data.series.map((point) => ({
                    label: periodLabel(point.period, "day", CHART_DAYS),
                    title: periodTitle(point.period, "day"),
                    value: point.earned,
                    hint: plural(point.orders, "order"),
                  }))}
                  format={short}
                  showValues={false}
                />
              ) : (
                <div className="h-[212px] animate-pulse rounded-2xl bg-muted" aria-busy="true" />
              )}
            </div>
            <div className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
              <h2 className="mb-5 font-display text-lg font-semibold text-ink">Orders by status</h2>
              <Donut
                ariaLabel="All your orders by status"
                centerValue={String(d.orders.orders)}
                centerLabel="orders"
                slices={(Object.keys(STATUS_META) as OrderStatus[]).map((status) => ({
                  label: STATUS_META[status].label,
                  value: d.orders.by_status[status],
                  color: STATUS_META[status].color,
                }))}
              />
            </div>
          </section>

          <section className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-3">
            <BestSellers dashboard={d} />
            <TopCustomers dashboard={d} />
            <Performance dashboard={d} />
          </section>

          <section aria-label="Menu and demand" className="grid grid-cols-1 gap-4 md:grid-cols-3">
            <TileLink href="/cook/dishes" icon={UtensilsCrossed} title="Your menu">
              {d.menu.dishes === 0 ? (
                "No dishes yet - add your first one"
              ) : (
                <>
                  {d.menu.active} public · {d.menu.inactive} private
                  {d.menu.price.min !== null && d.menu.price.max !== null && (
                    <span className="block text-ink-soft">
                      {d.menu.price.min === d.menu.price.max
                        ? money(d.menu.price.min)
                        : `${money(d.menu.price.min)} – ${money(d.menu.price.max)}`}
                    </span>
                  )}
                </>
              )}
            </TileLink>
            <Tile icon={ShoppingBag} title="In shoppers' bags">
              {d.demand.portions === 0 ? (
                "Nothing waiting in bags right now"
              ) : (
                <>
                  {plural(d.demand.portions, "portion")} worth {money(d.demand.value)}
                  <span className="block text-ink-soft">in {plural(d.demand.carts, "bag")} - not ordered yet</span>
                </>
              )}
            </Tile>
            <Tile icon={Users} title="Your customers">
              {d.customers.unique === 0 ? (
                "Your first customer is on the way"
              ) : (
                <>
                  {plural(d.customers.unique, "customer")}, {d.customers.repeat} came back
                  <Meter
                    className="mt-2"
                    value={d.customers.repeat / d.customers.unique}
                    display={formatRate(d.customers.repeat / d.customers.unique)}
                    label="Repeat rate"
                  />
                </>
              )}
            </Tile>
          </section>
        </>
      )}
    </div>
  );
}

function headline(d: CookDashboard): string {
  const waiting = d.orders.by_status.placed;
  const cooking = d.orders.by_status.accepted + d.orders.by_status.ready;
  if (waiting === 0 && cooking === 0) return "All caught up - here's how your kitchen is doing.";
  const parts = [];
  if (waiting) parts.push(`${plural(waiting, "request")} waiting for you`);
  if (cooking) parts.push(`${plural(cooking, "order")} in the kitchen`);
  return `${parts.join(" · ")}.`;
}

// --- set-up checklist -------------------------------------------------------------------

function Checklist({ dashboard }: { dashboard: CookDashboard }) {
  const { done, total, steps } = dashboard.checklist;
  if (done >= total) return null;
  return (
    <section
      aria-label="Kitchen set-up"
      className="rounded-3xl border border-brand/20 bg-brand-soft/60 p-5 sm:p-6"
    >
      <div className="flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">Set-up</p>
          <h2 className="font-display text-xl font-semibold text-ink">Finish setting up your kitchen</h2>
          <p className="mt-0.5 text-sm text-ink-muted">Complete kitchens get found - and ordered from - more often.</p>
        </div>
        <Meter
          className="w-full sm:w-56"
          value={done / total}
          label="Progress"
          display={`${done} of ${total}`}
          tone="brand"
        />
      </div>
      <ul className="mt-5 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-3">
        {steps.map((step) => {
          const meta = CHECKLIST_META[step.key];
          return (
            <li key={step.key}>
              <Link
                href={meta.href}
                className={cx(
                  "group flex h-full items-start gap-3 rounded-2xl border p-3.5 transition-colors",
                  step.done ? "border-transparent bg-surface/50" : "border-line bg-surface hover:border-ink-soft",
                )}
              >
                {step.done ? (
                  <CircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-herb" aria-hidden="true" />
                ) : (
                  <Circle className="mt-0.5 h-5 w-5 shrink-0 text-line-strong" aria-hidden="true" />
                )}
                <span className="min-w-0">
                  <span className={cx("block text-sm font-semibold", step.done ? "text-ink-soft line-through" : "text-ink")}>
                    {meta.label}
                  </span>
                  {!step.done && <span className="block text-xs text-ink-muted">{meta.hint}</span>}
                </span>
                <span className="sr-only">{step.done ? "(done)" : "(to do)"}</span>
              </Link>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

// --- queue ----------------------------------------------------------------------------------

function Queue({
  dashboard,
  onMoved,
  onError,
}: {
  dashboard: CookDashboard;
  onMoved: () => void;
  onError: (message: string | null) => void;
}) {
  const counts = dashboard.orders.by_status;
  const open = counts.placed + counts.accepted + counts.ready;
  // Requests first (oldest first), then what's in the kitchen.
  const queue = [...dashboard.queue].sort(
    (a, b) => Number(b.status === "placed") - Number(a.status === "placed"),
  );
  return (
    <section aria-label="Needs your attention">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
        <h2 className="font-display text-lg font-semibold text-ink">Needs your attention</h2>
        {open > 0 && (
          <Link href="/cook/orders" className="text-sm font-semibold text-brand hover:underline">
            All orders
          </Link>
        )}
      </div>
      {open === 0 ? (
        <div className="flex items-center gap-4 rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-herb-soft text-herb">
            <CircleCheck className="h-6 w-6" aria-hidden="true" />
          </span>
          <div>
            <p className="font-semibold text-ink">All caught up</p>
            <p className="text-sm text-ink-muted">New orders show up here - this page checks for them by itself.</p>
          </div>
        </div>
      ) : (
        <>
          <div className="mb-3 flex flex-wrap gap-2 text-xs">
            {(["placed", "accepted", "ready"] as const).map((status) =>
              counts[status] > 0 ? (
                <span
                  key={status}
                  className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface px-3 py-1 font-medium text-ink-muted"
                >
                  <span className="h-1.5 w-1.5 rounded-full" style={{ background: STATUS_META[status].color }} />
                  {counts[status]} {status === "placed" ? "new" : STATUS_META[status].label.toLowerCase()}
                </span>
              ) : null,
            )}
          </div>
          <ul className="space-y-3">
            {queue.slice(0, QUEUE_SHOWN).map((order) => (
              <li key={order.id}>
                <OrderCard
                  order={order}
                  perspective="cook"
                  meta={<span className={order.status === "placed" ? "font-medium text-saffron" : undefined}>{queueMeta(order)}</span>}
                  actions={<CookOrderActions order={order} onChanged={() => onMoved()} onError={onError} />}
                />
              </li>
            ))}
          </ul>
          {open > QUEUE_SHOWN && (
            <Link
              href="/cook/orders"
              className="mt-3 flex items-center justify-center gap-1.5 rounded-2xl border border-dashed border-line-strong py-3 text-sm font-medium text-ink-muted hover:text-ink"
            >
              {open - QUEUE_SHOWN} more open {open - QUEUE_SHOWN === 1 ? "order" : "orders"} <ArrowRight className="h-4 w-4" />
            </Link>
          )}
        </>
      )}
    </section>
  );
}

// --- lists ----------------------------------------------------------------------------------

function Panel({ title, subtitle, children }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
      <h2 className="font-display text-lg font-semibold text-ink">{title}</h2>
      {subtitle && <p className="mt-0.5 text-xs text-ink-soft">{subtitle}</p>}
      {children}
    </div>
  );
}

function BestSellers({ dashboard }: { dashboard: CookDashboard }) {
  return (
    <Panel title="Best sellers" subtitle="Portions sold, all time">
      {dashboard.top_dishes.length === 0 ? (
        <p className="mt-6 text-sm text-ink-muted">Your best sellers appear after your first orders.</p>
      ) : (
        <ol className="mt-4 space-y-3">
          {dashboard.top_dishes.map((dish, index) => (
            <li key={dish.dish_id ?? dish.name} className="flex items-center gap-3">
              <span className="w-4 text-center font-display text-sm font-semibold text-ink-soft">{index + 1}</span>
              <DishArt dish={dish} size="xs" className="h-11 w-11 shrink-0" rounded="rounded-xl" />
              <div className="min-w-0 flex-1">
                {dish.dish_id ? (
                  <Link
                    href={`/cook/dishes/${dish.dish_id}`}
                    className="block truncate text-sm font-medium text-ink hover:text-brand"
                  >
                    {dish.name}
                  </Link>
                ) : (
                  <p className="truncate text-sm font-medium text-ink">{dish.name}</p>
                )}
                <p className="text-xs text-ink-soft">
                  {dish.quantity} portions · {money(dish.value)}
                </p>
              </div>
            </li>
          ))}
        </ol>
      )}
    </Panel>
  );
}

function TopCustomers({ dashboard }: { dashboard: CookDashboard }) {
  return (
    <Panel title="Your regulars" subtitle="Customers with the most orders">
      {dashboard.top_customers.length === 0 ? (
        <p className="mt-6 text-sm text-ink-muted">Customers who order from you show up here.</p>
      ) : (
        <ul className="mt-4 space-y-3">
          {dashboard.top_customers.map((customer) => (
            <li key={customer.customer_id} className="flex items-center gap-3">
              <Avatar name={customer.name} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-ink">{customer.name ?? "A customer"}</p>
                <p className="text-xs text-ink-soft">Last order {formatRelative(customer.last_order_at)}</p>
              </div>
              <div className="text-right">
                <p className="text-sm font-semibold tabular-nums text-ink">{money(customer.value)}</p>
                <p className="text-xs text-ink-soft">{plural(customer.orders, "order")}</p>
              </div>
            </li>
          ))}
        </ul>
      )}
    </Panel>
  );
}

function Performance({ dashboard }: { dashboard: CookDashboard }) {
  const p = dashboard.performance;
  return (
    <Panel title="How you handle orders" subtitle="All time">
      <div className="mt-4 space-y-4">
        <Meter
          label="Requests accepted"
          value={p.acceptance_rate}
          display={formatRate(p.acceptance_rate)}
          tone="herb"
        />
        <Meter
          label="Orders cancelled"
          value={p.cancellation_rate}
          display={formatRate(p.cancellation_rate)}
          tone="saffron"
        />
        <dl className="grid grid-cols-3 gap-2 border-t border-line pt-4 text-center">
          {[
            { label: "to accept", value: formatMinutes(p.average_accept_minutes, true) },
            { label: "to cook", value: formatMinutes(p.average_prep_minutes, true) },
            { label: "in total", value: formatMinutes(dashboard.average_fulfilment_minutes, true) },
          ].map((item) => (
            <div key={item.label} className="flex min-w-0 flex-col-reverse">
              <dt className="text-xs text-ink-soft">{item.label}</dt>
              <dd className="whitespace-nowrap font-display text-lg font-semibold tabular-nums text-ink">{item.value}</dd>
            </div>
          ))}
        </dl>
        <p className="text-xs text-ink-soft">
          {plural(p.rejected, "request")} turned down · {p.cancelled_after_accepting} cancelled after accepting ·{" "}
          {p.cancelled_by_customer} by customers
        </p>
      </div>
    </Panel>
  );
}

// --- tiles ----------------------------------------------------------------------------------

function Tile({
  icon: Icon,
  title,
  children,
}: {
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <div className="flex gap-4 rounded-3xl border border-line bg-surface p-5">
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-muted text-ink">
        <Icon className="h-5 w-5" />
      </span>
      <div className="min-w-0 flex-1 text-sm">
        <p className="font-semibold text-ink">{title}</p>
        <div className="mt-1 text-ink-muted">{children}</div>
      </div>
    </div>
  );
}

function TileLink({
  href,
  icon: Icon,
  title,
  children,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="group flex gap-4 rounded-3xl border border-line bg-surface p-5 transition-shadow hover:shadow-card"
    >
      <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-muted text-ink">
        <Icon className="h-5 w-5" />
      </span>
      <span className="min-w-0 flex-1 text-sm">
        <span className="flex items-center justify-between font-semibold text-ink">
          {title}
          <ArrowRight className="h-4 w-4 text-ink-soft transition-transform group-hover:translate-x-0.5" />
        </span>
        <span className="mt-1 block text-ink-muted">{children}</span>
      </span>
    </Link>
  );
}

function OverviewSkeleton() {
  return (
    <div className="space-y-4" aria-busy="true">
      <div className="h-40 animate-pulse rounded-3xl bg-muted" />
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {[0, 1, 2, 3].map((key) => (
          <div key={key} className="h-32 animate-pulse rounded-3xl bg-muted" />
        ))}
      </div>
      <div className="h-72 animate-pulse rounded-3xl bg-muted" />
    </div>
  );
}
