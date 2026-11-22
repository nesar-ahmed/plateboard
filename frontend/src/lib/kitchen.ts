/**
 * Cook-panel vocabulary and pure helpers (no React): the set-up checklist's
 * copy, quick reasons for turning an order down, the earnings ranges and
 * the small number/date formatting the kitchen pages share.
 *
 * Dates: the backend buckets by UTC day (see the root README's "Cook
 * dashboard & earnings"), so ranges are computed in UTC here too.
 */

import type { ChecklistKey, EarningsGroup, Order } from "@/lib/api";
import { formatRelative } from "@/lib/format";

/** Set-up steps (GET /api/cooks/me/dashboard `checklist`): copy + where to fix them. */
export const CHECKLIST_META: Record<ChecklistKey, { label: string; hint: string; href: string }> = {
  display_name: { label: "Add your name", hint: "Customers order from people, not accounts.", href: "/cook/profile" },
  bio: { label: "Tell your story", hint: "A few lines about you and your cooking.", href: "/cook/profile" },
  specialties: { label: "Pick your specialties", hint: "Tags like biryani or vegan baking.", href: "/cook/profile" },
  zone: { label: "Place your kitchen", hint: "Neighbours filter the menu by distance.", href: "/cook/profile" },
  public_dish: { label: "Publish a dish", hint: "Your first public dish opens your kitchen.", href: "/cook/dishes/new" },
  dish_descriptions: {
    label: "Describe every public dish",
    hint: "Dishes with a description sell better.",
    href: "/cook/dishes",
  },
};

/** One-tap reasons offered when rejecting a request (free text is allowed too). */
export const REJECT_REASONS = [
  "Sold out for today",
  "Kitchen closed right now",
  "Too many orders right now",
  "Can't deliver to your area",
];

/** ...and when cancelling an order that was already accepted. */
export const CANCEL_REASONS = ["Ran out of an ingredient", "Something came up in the kitchen"];

/** Limit of `reason` on PATCH /api/cooks/me/orders/{id}. */
export const REASON_MAX_LENGTH = 200;

// --- dates (UTC) ---------------------------------------------------------------------

/** "2026-11-08" for a Date, in UTC. */
export function isoDay(date: Date): string {
  return date.toISOString().slice(0, 10);
}

/** The UTC date `days` before today ("2026-10-10" for 29 days before 11-08). */
export function utcDaysAgo(days: number, now: Date = new Date()): string {
  const date = new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate()));
  date.setUTCDate(date.getUTCDate() - days);
  return isoDay(date);
}

/** Earnings ranges offered on /cook/earnings: length in days + chart grouping. */
export const EARNINGS_RANGES: { key: string; label: string; days: number; group: EarningsGroup; compare: string }[] = [
  { key: "7d", label: "7 days", days: 7, group: "day", compare: "previous 7 days" },
  { key: "30d", label: "30 days", days: 30, group: "day", compare: "previous 30 days" },
  { key: "90d", label: "3 months", days: 91, group: "week", compare: "previous 3 months" },
  { key: "12m", label: "12 months", days: 365, group: "month", compare: "previous 12 months" },
];

/** Short chart label for an earnings period ("8", "Mon 3", "3 Nov", "Nov"). */
export function periodLabel(period: string, group: EarningsGroup, days: number): string {
  if (group === "month") {
    const [year, month] = period.split("-").map(Number);
    return new Date(Date.UTC(year, month - 1, 1)).toLocaleDateString(undefined, { month: "short", timeZone: "UTC" });
  }
  const date = new Date(`${period}T00:00:00Z`);
  if (group === "day" && days <= 7) {
    return date.toLocaleDateString(undefined, { weekday: "short", timeZone: "UTC" });
  }
  if (group === "day") return String(date.getUTCDate());
  return date.toLocaleDateString(undefined, { day: "numeric", month: "short", timeZone: "UTC" });
}

/** Long label for tooltips ("Sat, 8 Nov", "Week of 3 Nov", "November 2026"). */
export function periodTitle(period: string, group: EarningsGroup): string {
  if (group === "month") {
    const [year, month] = period.split("-").map(Number);
    return new Date(Date.UTC(year, month - 1, 1)).toLocaleDateString(undefined, {
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    });
  }
  const date = new Date(`${period}T00:00:00Z`);
  const day = date.toLocaleDateString(undefined, { weekday: "short", day: "numeric", month: "short", timeZone: "UTC" });
  return group === "week" ? `Week of ${day}` : day;
}

// --- numbers ---------------------------------------------------------------------------

/** Change between two periods: +12 / -40 (percent, rounded), or null without a base. */
export function trendPercent(current: number, previous: number): number | null {
  if (previous === 0) return null;
  return Math.round(((current - previous) / previous) * 100);
}

/** 0.985 -> "99%", null -> "—". */
export function formatRate(rate: number | null): string {
  return rate === null ? "—" : `${Math.round(rate * 100)}%`;
}

/** 15.2 -> "15 min", 95 -> "1 h 35 min" (`compact`: "1h 35m"), null -> "—". */
export function formatMinutes(minutes: number | null, compact = false): string {
  if (minutes === null) return "—";
  const rounded = Math.round(minutes);
  if (rounded < 60) return `${rounded} min`;
  const hours = Math.floor(rounded / 60);
  const rest = rounded % 60;
  if (compact) return rest ? `${hours}h ${rest}m` : `${hours}h`;
  return rest ? `${hours} h ${rest} min` : `${hours} h`;
}

/** Minutes since an ISO timestamp (for "waiting 12 min"). */
export function minutesSince(iso: string, now: number = Date.now()): number {
  return Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
}

export function plural(count: number, one: string, many = `${one}s`): string {
  return `${count} ${count === 1 ? one : many}`;
}

/** The cook's one-line status of an open order ("Waiting 12 min for your answer"). */
export function queueMeta(order: Order, now: number = Date.now()): string {
  if (order.status === "placed") {
    const waited = minutesSince(order.created_at, now);
    return waited < 1 ? "Just came in" : `Waiting ${formatMinutes(waited)} for your answer`;
  }
  if (order.status === "accepted") return `Accepted ${formatRelative(order.accepted_at ?? order.created_at, now)}`;
  if (order.status === "ready") return `Ready ${formatRelative(order.ready_at ?? order.created_at, now)} - waiting for pickup`;
  return "";
}
