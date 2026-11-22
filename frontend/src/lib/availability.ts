/**
 * Kitchen availability for people (no React): status copy and tones, and
 * the short clock/day labels. The API sends UTC instants; these helpers
 * format them in the *viewer's* time zone - run them in the browser (the
 * components wrap the output in `<time suppressHydrationWarning>`).
 */

import type { Availability } from "@/lib/api";

export const AVAILABILITY_TONE: Record<Availability["status"], "herb" | "saffron" | "neutral"> = {
  open: "herb",
  anytime: "herb",
  closed: "saffron",
  paused: "neutral",
};

/** "21:30" in the viewer's time. */
export function clock(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

function startOfDay(date: Date): number {
  return new Date(date.getFullYear(), date.getMonth(), date.getDate()).getTime();
}

/** "today" / "tomorrow" / "Mon" for an instant, relative to `now` (viewer's days). */
export function dayLabel(iso: string, now: Date = new Date()): string {
  const days = Math.round((startOfDay(new Date(iso)) - startOfDay(now)) / 86_400_000);
  if (days === 0) return "today";
  if (days === 1) return "tomorrow";
  return new Date(iso).toLocaleDateString(undefined, { weekday: "short" });
}

/** "21:30" today, "tomorrow 09:00", "Mon 09:00". */
export function when(iso: string, now: Date = new Date()): string {
  const day = dayLabel(iso, now);
  return day === "today" ? clock(iso) : `${day} ${clock(iso)}`;
}

/** The one-line status: "Open now · until 21:30", "Closed · opens tomorrow 09:00", ... */
export function availabilityText(availability: Availability, now: Date = new Date()): string {
  switch (availability.status) {
    case "open":
      return availability.closes_at ? `Open now · until ${when(availability.closes_at, now)}` : "Open now";
    case "closed":
      return availability.opens_at ? `Closed · opens ${when(availability.opens_at, now)}` : "Closed this week";
    case "paused":
      return "Not taking orders right now";
    case "anytime":
      return "Takes orders any time";
  }
}
