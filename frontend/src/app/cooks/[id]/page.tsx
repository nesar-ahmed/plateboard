import { ArrowLeft, BadgeCheck, Banknote, ChefHat, Clock, MapPin, ShieldQuestion, ShoppingBag, UtensilsCrossed } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";

import { AvailabilityPill, NextHours } from "@/components/availability";
import DishCard from "@/components/dish-card";
import { Avatar, Badge, Container, EmptyState, ErrorBanner, Page, cx } from "@/components/ui";
import VerifiedBadge from "@/components/verified-badge";
import { ApiError, type CookProfilePage, type DishPage } from "@/lib/api";
import { formatMinutes } from "@/lib/kitchen";
import { serverGet } from "@/lib/server-api";

/**
 * Public cook profile, rendered on the server: GET /api/cooks/{id} for the
 * person (verification, availability, stats strip), GET /api/dishes?cook_id=
 * for their current (active) menu. Unknown ids render the 404 page. Times are
 * shown in the viewer's own zone by the availability components.
 */
const loadCook = cache(async (id: string): Promise<CookProfilePage | ApiError> => {
  try {
    return await serverGet<CookProfilePage>(`/cooks/${encodeURIComponent(id)}`);
  } catch (cause) {
    if (cause instanceof ApiError && (cause.status === 404 || cause.status === 422)) notFound();
    return cause instanceof ApiError ? cause : new ApiError(503, "unreachable", "Could not reach the API");
  }
});

export async function generateMetadata({ params }: PageProps<"/cooks/[id]">): Promise<Metadata> {
  const cook = await loadCook((await params).id);
  if (cook instanceof ApiError) return { title: "Cook" };
  return {
    title: cook.display_name ?? "Home cook",
    description: `${cook.headline} - ${cook.display_name ?? "a home cook"} on Plateboard.`,
  };
}

/** "Jun 2026" (server-side: a month needs no time zone precision). */
function monthYear(iso: string): string {
  return new Date(iso).toLocaleDateString("en-GB", { month: "short", year: "numeric", timeZone: "UTC" });
}

export default async function CookProfilePage({ params }: PageProps<"/cooks/[id]">) {
  const { id } = await params;
  const cook = await loadCook(id);
  if (cook instanceof ApiError) {
    return (
      <Page>
        <ErrorBanner lines={cook.lines} />
      </Page>
    );
  }
  const menu = await serverGet<DishPage>(`/dishes?cook_id=${cook.user_id}&limit=100`).catch(() => null);
  const dishes = menu?.items ?? [];
  const name = cook.display_name ?? "This cook";
  const first = name.split(" ")[0];

  return (
    <>
      <section className="border-b border-line bg-surface">
        <Container className="py-10 sm:py-14">
          <Link href="/cooks" className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink">
            <ArrowLeft className="h-4 w-4" /> All cooks
          </Link>
          <div className="mt-6 flex flex-col gap-6 sm:flex-row sm:items-center">
            <Avatar name={cook.display_name} size="xl" />
            <div className="min-w-0 max-w-2xl">
              <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
                <h1 className="font-display text-4xl font-semibold tracking-tight text-ink">
                  {cook.display_name ?? "A home cook"}
                </h1>
                {cook.verified && <VerifiedBadge className="px-3 py-1 text-sm" />}
              </div>
              <p className="mt-1 text-lg text-ink-muted">{cook.headline}</p>
              <AvailabilityPill availability={cook.availability} className="mt-3 px-3 py-1 text-sm" />
            </div>
          </div>
          {cook.bio && <p className="mt-6 max-w-2xl leading-relaxed text-ink-muted">{cook.bio}</p>}
          <div className="mt-6 flex flex-wrap items-center gap-2">
            {cook.zone && (
              <Link
                href={`/dishes?zone=${encodeURIComponent(cook.zone.slug)}&max_distance=1`}
                className="inline-flex items-center gap-1.5 rounded-full bg-brand-soft px-3 py-1 text-sm font-medium text-brand hover:underline"
              >
                <MapPin className="h-3.5 w-3.5" /> {cook.zone.name}
              </Link>
            )}
            {cook.area && <span className="rounded-full bg-muted px-3 py-1 text-sm text-ink-muted">{cook.area}</span>}
            {cook.specialties.map((specialty) => (
              <span key={specialty} className="rounded-full border border-line px-3 py-1 text-sm capitalize text-ink-muted">
                {specialty}
              </span>
            ))}
          </div>

          <StatsStrip cook={cook} />
        </Container>
      </section>

      <Container className="pt-10 sm:pt-12">
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.5fr)_minmax(0,1fr)]">
          <section aria-label="Next 24 hours" className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
            <h2 className="flex items-center gap-2 font-display text-lg font-semibold text-ink">
              <Clock className="h-5 w-5 text-ink-soft" aria-hidden="true" /> Taking orders in the next 24 hours
            </h2>
            <div className="mt-5">
              <NextHours availability={cook.availability} />
            </div>
          </section>
          <VerificationCard cook={cook} />
        </div>

        <HowOrderingWorks cook={cook} first={first} />
      </Container>

      <Page>
        <h2 className="mb-6 font-display text-2xl font-semibold tracking-tight text-ink">
          On the menu <span className="font-sans text-base font-normal text-ink-soft">· {dishes.length}</span>
        </h2>
        {dishes.length === 0 ? (
          <EmptyState icon={<UtensilsCrossed className="h-6 w-6" />} title="Nothing on the menu right now">
            Check back soon - {name} adds dishes regularly.
          </EmptyState>
        ) : (
          <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
            {dishes.map((dish) => (
              <li key={dish.id}>
                <DishCard dish={dish} showCook={false} />
              </li>
            ))}
          </ul>
        )}
      </Page>
    </>
  );
}

/** Counts that build trust - never money. Rates wait until the kitchen has a track record. */
function StatsStrip({ cook }: { cook: CookProfilePage }) {
  const { stats } = cook;
  const items = [
    { value: String(stats.orders_completed), label: `${stats.orders_completed === 1 ? "order" : "orders"} handed over` },
    {
      value: stats.customers ? `${stats.returning_customers} of ${stats.customers}` : "—",
      label: "customers came back",
    },
    stats.acceptance_rate !== null
      ? { value: `${Math.round(stats.acceptance_rate * 100)}%`, label: "of orders accepted" }
      : { value: "New", label: "kitchen - rates after a few orders" },
    {
      value: stats.average_ready_minutes !== null ? `~${formatMinutes(stats.average_ready_minutes, true)}` : "—",
      label: "usually ready after ordering",
    },
    { value: monthYear(cook.created_at), label: "cooking on Plateboard since" },
  ];
  return (
    // gap-px over a hairline background: clean dividers at any column count.
    <dl
      aria-label="Kitchen stats"
      className="mt-8 grid grid-cols-2 gap-px overflow-hidden rounded-3xl border border-line bg-line sm:grid-cols-3 lg:grid-cols-5"
    >
      {items.map((item, index) => (
        <div
          key={item.label}
          className={cx(
            "flex flex-col-reverse gap-0.5 bg-canvas p-4 sm:p-5",
            index === items.length - 1 && "col-span-2 lg:col-span-1",
          )}
        >
          <dt className="text-xs text-ink-muted">{item.label}</dt>
          <dd className="font-display text-2xl font-semibold tabular-nums tracking-tight text-ink">{item.value}</dd>
        </div>
      ))}
    </dl>
  );
}

function VerificationCard({ cook }: { cook: CookProfilePage }) {
  if (cook.verified) {
    return (
      <section aria-label="Verification" className="rounded-3xl border border-herb/25 bg-herb-soft p-5 sm:p-6">
        <h2 className="flex items-center gap-2 font-display text-lg font-semibold text-ink">
          <BadgeCheck className="h-5 w-5 text-herb" aria-hidden="true" /> Verified kitchen
        </h2>
        <p className="mt-2 text-sm leading-relaxed text-ink-muted">
          The Plateboard team checked this kitchen
          {cook.verified_at ? ` in ${monthYear(cook.verified_at)}` : ""}. Every dish still declares its allergens, and
          you can always see what&apos;s in it before you order.
        </p>
      </section>
    );
  }
  return (
    <section aria-label="Verification" className="rounded-3xl border border-line bg-surface p-5 sm:p-6">
      <h2 className="flex items-center gap-2 font-display text-lg font-semibold text-ink">
        <ShieldQuestion className="h-5 w-5 text-ink-soft" aria-hidden="true" /> Not verified yet
      </h2>
      <p className="mt-2 text-sm leading-relaxed text-ink-muted">
        The Plateboard team hasn&apos;t checked this kitchen yet. Its dishes still declare every allergen - read them
        before you order.
      </p>
    </section>
  );
}

function HowOrderingWorks({ cook, first }: { cook: CookProfilePage; first: string }) {
  const ready = cook.stats.average_ready_minutes;
  const steps = [
    {
      icon: ShoppingBag,
      title: "Fill your bag",
      text: `Add dishes from ${first}'s menu. One kitchen per order, so everything arrives together.`,
    },
    {
      icon: ChefHat,
      title: `${first} confirms`,
      text:
        cook.availability.status === "anytime"
          ? "Order whenever you like - the cook accepts or declines each order, and you see it in your account."
          : "Orders are taken during opening hours. The cook accepts or declines each one - you see it in your account.",
    },
    {
      icon: Clock,
      title: "Cooked fresh",
      text: ready !== null
        ? `Usually ready about ${formatMinutes(ready)} after you order - you're told the moment it is.`
        : "Cooked to order - you're told the moment it's ready.",
    },
    {
      icon: Banknote,
      title: "Pay at handover",
      text: `Pay ${first} directly when you get your food. Cancel for free until the order is accepted.`,
    },
  ];
  return (
    <section aria-labelledby="how-ordering-works" className="mt-10 sm:mt-12">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="how-ordering-works" className="font-display text-2xl font-semibold tracking-tight text-ink">
          How ordering works
        </h2>
        {!cook.availability.accepting_orders && (
          <Badge tone="saffron">Not taking orders right now - you can still fill your bag</Badge>
        )}
      </div>
      <ol className="mt-6 grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {steps.map((step, index) => (
          <li key={step.title} className="rounded-3xl border border-line bg-surface p-5 shadow-card">
            <div className="flex items-center justify-between">
              <span className="flex h-10 w-10 items-center justify-center rounded-xl bg-brand-soft text-brand">
                <step.icon className="h-5 w-5" aria-hidden="true" />
              </span>
              <span className="font-display text-2xl font-semibold text-line-strong" aria-hidden="true">
                {index + 1}
              </span>
            </div>
            <h3 className="mt-4 font-semibold text-ink">{step.title}</h3>
            <p className="mt-1 text-sm leading-relaxed text-ink-muted">{step.text}</p>
          </li>
        ))}
      </ol>
    </section>
  );
}
