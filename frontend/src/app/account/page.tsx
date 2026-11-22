"use client";

import {
  ArrowRight,
  ChefHat,
  Leaf,
  MapPin,
  Receipt,
  ShieldCheck,
  ShoppingBag,
  TrendingUp,
  Wallet,
} from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { BarChart, Donut, StatCard } from "@/components/charts";
import DishArt from "@/components/dish-art";
import { OPEN_STATUSES, OrderCard, OrderTimeline, STATUS_META, StatusBadge } from "@/components/order-bits";
import ReceiveButton from "@/components/receive-button";
import { AllergenTag, Avatar, ButtonLink, EmptyState, ErrorBanner, PageHeader, Tag, cx } from "@/components/ui";
import type { Address, CustomerDashboard, OrderStatus, Preferences } from "@/lib/api";
import { formatMinorUnits, orderRef } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

function greeting(now = new Date()): string {
  const hour = now.getHours();
  return hour < 5 ? "Good evening" : hour < 12 ? "Good morning" : hour < 18 ? "Good afternoon" : "Good evening";
}

function monthLabel(period: string): string {
  const [year, month] = period.split("-").map(Number);
  return new Date(year, month - 1, 1).toLocaleDateString(undefined, { month: "short" });
}

/** /account - the user panel overview (GET /api/me/dashboard + addresses + preferences). */
export default function AccountOverview() {
  const { user } = useSession();
  const dashboard = useApi<CustomerDashboard>("/me/dashboard?months=6");
  const addresses = useApi<Address[]>("/me/addresses");
  const preferences = useApi<Preferences>("/me/preferences");
  const d = dashboard.data;
  const firstName = user?.display_name?.split(" ")[0];

  return (
    <div className="space-y-8">
      <PageHeader
        size="compact"
        title={`${greeting()}${firstName ? `, ${firstName}` : ""}`}
        lead="Your orders, spending and settings in one place."
      />

      <ErrorBanner lines={dashboard.error ? [dashboard.error] : []} />

      {!d ? (
        <OverviewSkeleton />
      ) : (
        <>
          <ActiveOrder dashboard={d} onReceived={() => void dashboard.reload()} />

          {d.cart.lines > 0 && d.cart.cook && (
            <div className="flex flex-col gap-3 rounded-3xl border border-brand/20 bg-brand-soft px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
              <p className="flex items-center gap-3 text-sm text-ink">
                <ShoppingBag className="h-5 w-5 shrink-0 text-brand" aria-hidden="true" />
                <span>
                  <span className="font-semibold">
                    {d.cart.item_count} {d.cart.item_count === 1 ? "portion" : "portions"}
                  </span>{" "}
                  from {d.cart.cook.name ?? "a home cook"} waiting in your bag · {formatMinorUnits(d.cart.total)}
                </span>
              </p>
              <ButtonLink href="/checkout" className="h-10 shrink-0">
                Check out <ArrowRight className="h-4 w-4" />
              </ButtonLink>
            </div>
          )}

          <section aria-label="Your numbers" className="grid grid-cols-2 gap-3 sm:gap-4 xl:grid-cols-4">
            <StatCard
              label="Orders"
              value={d.orders.orders}
              hint={d.orders.open > 0 ? `${d.orders.open} in progress` : "All delivered"}
              icon={<Receipt className="h-[18px] w-[18px]" />}
            />
            <StatCard
              label="Spent"
              value={formatMinorUnits(d.orders.booked_value)}
              hint="Cancelled orders not included"
              icon={<Wallet className="h-[18px] w-[18px]" />}
              tone="brand"
            />
            <StatCard
              label="Average order"
              value={formatMinorUnits(d.orders.average_order_value)}
              icon={<TrendingUp className="h-[18px] w-[18px]" />}
              tone="herb"
            />
            <StatCard
              label="Favourite kitchen"
              value={<span className="block truncate text-2xl">{d.favourite_cooks[0]?.name ?? "—"}</span>}
              hint={d.favourite_cooks[0] ? `${d.favourite_cooks[0].orders} orders` : "Order to find one"}
              icon={<ChefHat className="h-[18px] w-[18px]" />}
              tone="saffron"
            />
          </section>

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <div className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
              <div className="mb-4 flex items-baseline justify-between gap-3">
                <h2 className="font-display text-lg font-semibold text-ink">Spending</h2>
                <p className="text-xs text-ink-soft">Last {d.window.periods} months</p>
              </div>
              <BarChart
                ariaLabel={`Spending per month over the last ${d.window.periods} months`}
                bars={d.spending.map((point) => ({
                  label: monthLabel(point.period),
                  value: point.value,
                  hint: `${point.orders} orders`,
                }))}
                format={(value) => formatMinorUnits(value).replace(/\.00$/, "")}
              />
            </div>
            <div className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
              <h2 className="mb-5 font-display text-lg font-semibold text-ink">Order status</h2>
              <Donut
                ariaLabel="Your orders by status"
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

          <section className="grid grid-cols-1 gap-4 xl:grid-cols-[minmax(0,1.6fr)_minmax(0,1fr)]">
            <div>
              <div className="mb-3 flex items-center justify-between">
                <h2 className="font-display text-lg font-semibold text-ink">Recent orders</h2>
                <Link href="/account/orders" className="text-sm font-semibold text-brand hover:underline">
                  View all
                </Link>
              </div>
              {d.recent_orders.length === 0 ? (
                <EmptyState
                  icon={<Receipt className="h-6 w-6" />}
                  title="No orders yet"
                  action={<ButtonLink href="/dishes">Find something delicious</ButtonLink>}
                >
                  Your orders and their status will show up here.
                </EmptyState>
              ) : (
                <ul className="space-y-3">
                  {d.recent_orders.slice(0, 4).map((order) => (
                    <li key={order.id}>
                      <OrderCard order={order} />
                    </li>
                  ))}
                </ul>
              )}
            </div>
            <div className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
              <div className="flex items-start justify-between gap-3">
                <div>
                  <h2 className="font-display text-lg font-semibold text-ink">Most ordered</h2>
                  <p className="mt-0.5 text-xs text-ink-soft">The dishes you come back to</p>
                </div>
                <Link href="/account/favourites" className="text-sm font-semibold text-brand hover:underline">
                  Saved dishes
                </Link>
              </div>
              {d.favourite_dishes.length === 0 ? (
                <p className="mt-6 text-sm text-ink-muted">Order a few times and your most-ordered dishes appear here.</p>
              ) : (
                <ol className="mt-4 space-y-3">
                  {d.favourite_dishes.map((dish, index) => (
                    <li key={`${dish.dish_id ?? dish.name}`} className="flex items-center gap-3">
                      <span className="w-4 text-center font-display text-sm font-semibold text-ink-soft">{index + 1}</span>
                      <DishArt dish={dish} size="xs" className="h-11 w-11 shrink-0" rounded="rounded-xl" />
                      <div className="min-w-0 flex-1">
                        {dish.dish_id ? (
                          <Link href={`/dishes/${dish.dish_id}`} className="block truncate text-sm font-medium text-ink hover:text-brand">
                            {dish.name}
                          </Link>
                        ) : (
                          <p className="truncate text-sm font-medium text-ink">{dish.name}</p>
                        )}
                        <p className="text-xs text-ink-soft">
                          {dish.quantity} portions · {dish.orders} {dish.orders === 1 ? "order" : "orders"}
                        </p>
                      </div>
                    </li>
                  ))}
                </ol>
              )}
            </div>
          </section>
        </>
      )}

      <section aria-label="Your settings" className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <SettingCard href="/account/addresses" icon={MapPin} title="Delivery address">
          {addresses.data === null ? (
            "…"
          ) : addresses.data.length === 0 ? (
            "No address saved yet"
          ) : (
            <>
              {(() => {
                const main = addresses.data.find((a) => a.is_default) ?? addresses.data[0];
                return `${main.label ?? "Default"} · ${main.line1}, ${main.city}`;
              })()}
              {addresses.data.length > 1 && (
                <span className="block text-ink-soft">+{addresses.data.length - 1} more saved</span>
              )}
            </>
          )}
        </SettingCard>
        <SettingCard href="/account/preferences" icon={Leaf} title="Food preferences">
          {preferences.data === null ? (
            "…"
          ) : preferences.data.excluded_allergens.length + preferences.data.dietary_preferences.length === 0 ? (
            "Tell us what you avoid - we'll help you filter"
          ) : (
            <span className="mt-1 flex flex-wrap gap-1">
              {preferences.data.dietary_preferences.map((diet) => (
                <Tag key={diet} className="capitalize">
                  {diet}
                </Tag>
              ))}
              {preferences.data.excluded_allergens.map((allergen) => (
                <AllergenTag key={allergen}>no {allergen}</AllergenTag>
              ))}
            </span>
          )}
        </SettingCard>
        <SettingCard href="/account/security" icon={ShieldCheck} title="Login & security">
          Password and signed-in devices
        </SettingCard>
      </section>
    </div>
  );
}

/**
 * The order that needs the customer most: a ready one (it waits for their
 * confirmation of receipt), else the newest open one.
 */
function ActiveOrder({ dashboard, onReceived }: { dashboard: CustomerDashboard; onReceived: () => void }) {
  const [error, setError] = useState<string | null>(null);
  const active =
    dashboard.recent_orders.find((order) => order.status === "ready") ??
    dashboard.recent_orders.find((order) => OPEN_STATUSES.includes(order.status));
  if (!active) return null;
  return (
    <section
      aria-label="Order in progress"
      className="rounded-3xl border border-line bg-surface p-5 shadow-lift sm:p-6"
    >
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <Avatar name={active.cook.name} />
          <div>
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-brand">In progress</p>
            <p className="font-display text-lg font-semibold text-ink">
              {active.cook.name ?? "Your cook"} · {orderRef(active.id)}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-3">
          <StatusBadge status={active.status} />
          {active.status === "ready" ? (
            <ReceiveButton order={active} onDone={onReceived} onError={setError} className="h-10" />
          ) : (
            <ButtonLink href={`/account/orders/${active.id}`} variant="dark" className="h-10">
              Track order
            </ButtonLink>
          )}
        </div>
      </div>
      {error && (
        <p role="alert" className="mt-4 rounded-2xl bg-danger-soft px-4 py-3 text-sm text-danger">
          {error}
        </p>
      )}
      <div className="mt-6">
        <OrderTimeline order={active} />
      </div>
    </section>
  );
}

function SettingCard({
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
      <div className="grid grid-cols-2 gap-4 xl:grid-cols-4">
        {[0, 1, 2, 3].map((key) => (
          <div key={key} className={cx("h-32 animate-pulse rounded-3xl bg-muted")} />
        ))}
      </div>
      <div className="h-72 animate-pulse rounded-3xl bg-muted" />
    </div>
  );
}
