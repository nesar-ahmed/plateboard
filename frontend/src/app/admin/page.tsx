"use client";

import { ArrowRight, ChefHat, MapPin, Receipt, ShoppingBag, Store, UserPlus, Users, Wallet } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { BarChart, Donut, Meter, StatCard } from "@/components/charts";
import DishArt from "@/components/dish-art";
import { STATUS_META } from "@/components/order-bits";
import { AllergenTag, Avatar, ErrorBanner, PageHeader, Tag, cx } from "@/components/ui";
import { ordersOf } from "@/lib/admin";
import type { AdminDashboard, OrderStatus, ZoneStats } from "@/lib/api";
import { formatMinorUnits } from "@/lib/format";
import { periodLabel, periodTitle, plural } from "@/lib/kitchen";
import { useApi } from "@/lib/use-api";

const WINDOWS = [
  { days: 7, label: "7 days" },
  { days: 30, label: "30 days" },
  { days: 90, label: "90 days" },
];

const money = (minor: number) => formatMinorUnits(minor);
const short = (minor: number) => formatMinorUnits(minor).replace(/\.00$/, "");

export default function AdminOverviewPage() {
  return (
    <Suspense fallback={null}>
      <AdminOverview />
    </Suspense>
  );
}

/** /admin - the platform at a glance (GET /api/admin/dashboard?days=). */
function AdminOverview() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const days = WINDOWS.find((w) => String(w.days) === params.get("days"))?.days ?? 30;
  const { data: d, error } = useApi<AdminDashboard>(`/admin/dashboard?days=${days}`);
  const current = d && d.window.periods === days ? d : null;

  const pick = (next: number) =>
    router.push(next === 30 ? pathname : `${pathname}?days=${next}`, { scroll: false });

  return (
    <div className="space-y-8">
      <PageHeader
        size="compact"
        title="Platform overview"
        lead="Plateboard at a glance - people, orders and where the food comes from."
        actions={
          <div role="tablist" aria-label="Period" className="flex gap-1 rounded-full border border-line bg-surface p-1">
            {WINDOWS.map((window) => (
              <button
                key={window.days}
                role="tab"
                type="button"
                aria-selected={window.days === days}
                onClick={() => pick(window.days)}
                className={cx(
                  "h-9 whitespace-nowrap rounded-full px-3 text-sm font-medium transition-colors sm:px-4",
                  window.days === days ? "bg-ink text-canvas" : "text-ink-muted hover:text-ink",
                )}
              >
                {window.label}
              </button>
            ))}
          </div>
        }
      />

      <ErrorBanner lines={error ? [error] : []} />

      {!!d?.users.pending_cook_applications && (
        <Link
          href="/admin/applications"
          className="animate-rise group flex items-center gap-4 rounded-3xl border border-saffron/30 bg-saffron-soft p-4 transition-shadow hover:shadow-card sm:p-5"
        >
          <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-surface text-saffron">
            <Store className="h-5 w-5" aria-hidden="true" />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-semibold text-ink">
              {d.users.pending_cook_applications} cook{" "}
              {d.users.pending_cook_applications === 1 ? "application is" : "applications are"} waiting for review
            </span>
            <span className="block text-sm text-ink-muted">Accept to open the kitchen, or tell the applicant why not.</span>
          </span>
          <ArrowRight
            className="h-5 w-5 shrink-0 text-ink-soft transition-transform group-hover:translate-x-0.5"
            aria-hidden="true"
          />
        </Link>
      )}

      {!current ? (
        <Skeleton />
      ) : (
        <>
          <section aria-label="Key numbers" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <StatCard
              label="People"
              value={current.users.total}
              hint={`+${current.users.new_in_window} in the last ${days} days`}
              icon={<Users className="h-[18px] w-[18px]" />}
            />
            <StatCard
              label="Kitchens"
              value={current.users.cooks}
              hint={`${plural(current.menu.active, "dish", "dishes")} on the menu`}
              icon={<ChefHat className="h-[18px] w-[18px]" />}
              tone="saffron"
            />
            <StatCard
              label="Orders"
              value={current.orders.orders}
              hint={`${current.orders.open} open right now`}
              icon={<Receipt className="h-[18px] w-[18px]" />}
              tone="herb"
            />
            <StatCard
              label="Order value"
              value={money(current.orders.booked_value)}
              hint={`Average order ${money(current.orders.average_order_value)}`}
              icon={<Wallet className="h-[18px] w-[18px]" />}
              tone="brand"
            />
          </section>

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Panel title="Orders per day" aside={`Last ${days} days · by day placed`}>
              <BarChart
                ariaLabel={`Order value per day over the last ${days} days`}
                bars={current.order_series.map((point) => ({
                  label: periodLabel(point.period, "day", days),
                  title: periodTitle(point.period, "day"),
                  value: point.value,
                  hint: `${plural(point.orders, "order")}${point.cancelled ? ` · ${point.cancelled} cancelled` : ""}`,
                }))}
                format={short}
                showValues={days <= 7}
                labelEvery={days <= 7 ? 1 : days <= 30 ? 5 : 15}
              />
            </Panel>
            <Panel title="Orders by status" aside="All time">
              <Donut
                ariaLabel="All orders by status"
                centerValue={String(current.orders.orders)}
                centerLabel="orders"
                slices={(Object.keys(STATUS_META) as OrderStatus[]).map((status) => ({
                  label: STATUS_META[status].label,
                  value: current.orders.by_status[status],
                  color: STATUS_META[status].color,
                }))}
              />
            </Panel>
          </section>

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <Panel title="New accounts per day" aside={`${current.users.new_in_window} in the last ${days} days`}>
              <BarChart
                ariaLabel={`New accounts per day over the last ${days} days`}
                bars={current.signups.map((point) => ({
                  label: periodLabel(point.period, "day", days),
                  title: periodTitle(point.period, "day"),
                  value: point.count,
                }))}
                showValues={days <= 7}
                labelEvery={days <= 7 ? 1 : days <= 30 ? 5 : 15}
                height={140}
              />
            </Panel>
            <Panel title="Who's on Plateboard">
              <div className="space-y-4">
                {[
                  { label: "Customers", value: current.users.customers, tone: "herb" as const },
                  { label: "Cooks", value: current.users.cooks, tone: "saffron" as const },
                  { label: "Admins", value: current.users.admins, tone: "ink" as const },
                ].map((row) => (
                  <Meter
                    key={row.label}
                    label={row.label}
                    value={current.users.total ? row.value / current.users.total : 0}
                    display={String(row.value)}
                    tone={row.tone}
                  />
                ))}
                <p className="text-xs text-ink-soft">Cooks can order too, so most of them are customers as well.</p>
                <p className="flex items-center gap-2 border-t border-line pt-4 text-sm text-ink-muted">
                  <UserPlus className="h-4 w-4 text-ink-soft" aria-hidden="true" />
                  {plural(current.users.active_sessions, "active session")} right now
                </p>
              </div>
            </Panel>
          </section>

          <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Panel title="Top kitchens" aside="By order value, all time">
              {current.top_cooks.length === 0 ? (
                <p className="text-sm text-ink-muted">No orders yet.</p>
              ) : (
                <ol className="space-y-3">
                  {current.top_cooks.map((cook, index) => (
                    <li key={cook.cook_id} className="flex items-center gap-3">
                      <span className="w-4 text-center font-display text-sm font-semibold text-ink-soft">{index + 1}</span>
                      <Avatar name={cook.name} size="sm" />
                      <div className="min-w-0 flex-1">
                        <Link
                          href={ordersOf("cook", cook.cook_id, cook.name)}
                          className="block truncate text-sm font-medium text-ink hover:text-brand"
                        >
                          {cook.name ?? "A home cook"}
                        </Link>
                        <p className="text-xs text-ink-soft">{plural(cook.orders, "order")}</p>
                      </div>
                      <p className="text-sm font-semibold tabular-nums text-ink">{money(cook.value)}</p>
                    </li>
                  ))}
                </ol>
              )}
            </Panel>
            <Panel title="Top dishes" aside="By portions, all time">
              {current.top_dishes.length === 0 ? (
                <p className="text-sm text-ink-muted">No orders yet.</p>
              ) : (
                <ol className="space-y-3">
                  {current.top_dishes.map((dish, index) => (
                    <li key={dish.dish_id ?? dish.name} className="flex items-center gap-3">
                      <span className="w-4 text-center font-display text-sm font-semibold text-ink-soft">{index + 1}</span>
                      <DishArt dish={dish} size="xs" className="h-10 w-10 shrink-0" rounded="rounded-xl" />
                      <div className="min-w-0 flex-1">
                        {dish.dish_id ? (
                          <Link href={`/dishes/${dish.dish_id}`} className="block truncate text-sm font-medium text-ink hover:text-brand">
                            {dish.name}
                          </Link>
                        ) : (
                          <p className="truncate text-sm font-medium text-ink">{dish.name}</p>
                        )}
                        <p className="text-xs text-ink-soft">
                          {dish.quantity} portions · {plural(dish.orders, "order")}
                        </p>
                      </div>
                      <p className="text-sm font-semibold tabular-nums text-ink">{money(dish.value)}</p>
                    </li>
                  ))}
                </ol>
              )}
            </Panel>
          </section>

          <ZoneMap zones={current.zones} />

          <section className="grid grid-cols-1 gap-4 md:grid-cols-2">
            <Panel title="The menu" aside={`${current.menu.active} public · ${current.menu.inactive} private`}>
              <p className="text-sm text-ink-muted">
                {current.menu.price.min !== null && current.menu.price.max !== null
                  ? `Prices from ${money(current.menu.price.min)} to ${money(current.menu.price.max)}, ${money(current.menu.price.avg ?? 0)} on average.`
                  : "No public dishes yet."}
              </p>
              {current.menu.dietary_tags.length > 0 && (
                <>
                  <p className="mt-4 text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">Diets</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {current.menu.dietary_tags.slice(0, 8).map((tag) => (
                      <Tag key={tag.name} className="capitalize">
                        {tag.name} · {tag.count}
                      </Tag>
                    ))}
                  </div>
                </>
              )}
              {current.menu.allergens.length > 0 && (
                <>
                  <p className="mt-4 text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">Allergens declared</p>
                  <div className="mt-2 flex flex-wrap gap-1.5">
                    {current.menu.allergens.map((allergen) => (
                      <AllergenTag key={allergen.name} className="capitalize">
                        {allergen.name} · {allergen.count}
                      </AllergenTag>
                    ))}
                  </div>
                </>
              )}
            </Panel>
            <Panel title="Open bags" aside="Not ordered yet">
              <div className="flex items-center gap-4">
                <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-brand-soft text-brand">
                  <ShoppingBag className="h-5 w-5" aria-hidden="true" />
                </span>
                <div>
                  <p className="font-display text-2xl font-semibold tabular-nums text-ink">{money(current.carts.value)}</p>
                  <p className="text-sm text-ink-muted">
                    {plural(current.carts.portions, "portion")} in {plural(current.carts.carts, "bag")}
                  </p>
                </div>
              </div>
              <div className="mt-5 space-y-3">
                <Meter
                  label="Signed-in shoppers"
                  value={current.carts.carts ? current.carts.account_carts / current.carts.carts : 0}
                  display={String(current.carts.account_carts)}
                  tone="herb"
                />
                <Meter
                  label="Guests"
                  value={current.carts.carts ? current.carts.guest_carts / current.carts.carts : 0}
                  display={String(current.carts.guest_carts)}
                  tone="saffron"
                />
              </div>
            </Panel>
          </section>
        </>
      )}
    </div>
  );
}

function Panel({ title, aside, children }: { title: string; aside?: string; children: React.ReactNode }) {
  return (
    <div className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="font-display text-lg font-semibold text-ink">{title}</h2>
        {aside && <p className="text-xs text-ink-soft">{aside}</p>}
      </div>
      {children}
    </div>
  );
}

/** The service grid as a heat map: one tile per zone, tinted by order value. */
function ZoneMap({ zones }: { zones: ZoneStats[] }) {
  if (zones.length === 0) return null;
  const columns = Math.max(...zones.map((zone) => zone.x)) + 1;
  const top = Math.max(1, ...zones.map((zone) => zone.value));
  return (
    <section aria-label="Zones" className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 className="font-display text-lg font-semibold text-ink">Where the food comes from</h2>
        <p className="text-xs text-ink-soft">Order value by the kitchen&apos;s zone, all time</p>
      </div>
      <ol
        className="grid gap-2 sm:gap-3"
        style={{ gridTemplateColumns: `repeat(${columns}, minmax(0, 1fr))` }}
      >
        {zones.map((zone) => {
          const heat = zone.value / top;
          return (
            <li
              key={zone.slug}
              style={{
                gridColumn: zone.x + 1,
                gridRow: zone.y + 1,
                background: `color-mix(in srgb, var(--brand) ${Math.round(6 + heat * 40)}%, var(--surface))`,
              }}
              className="min-w-0 rounded-2xl border border-line p-3 sm:p-4"
            >
              <p className="flex items-center gap-1 truncate text-xs font-semibold text-ink sm:text-sm">
                <MapPin className="hidden h-3.5 w-3.5 shrink-0 sm:block" aria-hidden="true" /> {zone.name}
              </p>
              <p className="mt-1 truncate font-display text-lg font-semibold tabular-nums text-ink sm:text-xl">{money(zone.value)}</p>
              <p className="truncate text-[11px] text-ink-muted sm:text-xs">
                {plural(zone.orders, "order")}
                <span className="hidden sm:inline">
                  {" "}
                  · {plural(zone.cooks, "cook")} · {plural(zone.active_dishes, "dish", "dishes")}
                </span>
              </p>
            </li>
          );
        })}
      </ol>
    </section>
  );
}

function Skeleton() {
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
