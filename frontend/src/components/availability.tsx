"use client";

import { cx } from "@/components/ui";
import type { Availability } from "@/lib/api";
import { AVAILABILITY_TONE, availabilityText, clock, when } from "@/lib/availability";

const DOT = { herb: "bg-herb", saffron: "bg-saffron", neutral: "bg-ink-soft" } as const;
const PILL = {
  herb: "bg-herb-soft text-herb",
  saffron: "bg-saffron-soft text-saffron",
  neutral: "bg-muted text-ink-muted",
} as const;

/**
 * The kitchen's status in one pill: "Open now · until 21:30". Times are the
 * viewer's own (formatted in the browser; the server's guess is replaced on
 * hydration - hence `suppressHydrationWarning` on the text).
 */
export function AvailabilityPill({
  availability,
  className,
}: {
  availability: Availability;
  className?: string;
}) {
  const tone = AVAILABILITY_TONE[availability.status];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1.5 rounded-full px-2.5 py-0.5 text-xs font-semibold",
        PILL[tone],
        className,
      )}
    >
      <span className={cx("h-1.5 w-1.5 shrink-0 rounded-full", DOT[tone])} aria-hidden="true" />
      <time suppressHydrationWarning dateTime={availability.closes_at ?? availability.opens_at ?? undefined}>
        {availabilityText(availability)}
      </time>
    </span>
  );
}

const HOUR = 3_600_000;

/**
 * The next 24 hours as a bar: taking-orders windows in herb, the rest muted,
 * "now" plus whole-hour ticks every 6 hours, and the windows spelled out
 * below. Positions come from `as_of` (and UTC hour boundaries), so server and
 * browser draw the same bar; only the tick *labels* are the viewer's time.
 */
export function NextHours({ availability }: { availability: Availability }) {
  const start = new Date(availability.as_of).getTime();
  const end = start + 24 * HOUR;
  const pct = (iso: string) => Math.min(100, Math.max(0, ((new Date(iso).getTime() - start) / (end - start)) * 100));
  const firstHour = Math.ceil(start / HOUR) * HOUR;
  const ticks = [0, 6, 12, 18]
    .map((hours) => firstHour + hours * HOUR)
    .filter((tick) => tick - start >= 2 * HOUR && end - tick >= HOUR) // keep clear of "Now"
    .map((tick) => new Date(tick).toISOString());
  const windows = availability.next_24h;
  /** The window runs past the 24 h view: its end there is not a closing time. */
  const continues = (iso: string) => new Date(iso).getTime() >= end - 60_000;
  const everything = availability.status === "anytime";

  return (
    <div>
      <div
        role="img"
        aria-label={
          windows.length === 0
            ? "Not taking orders in the next 24 hours"
            : `Taking orders ${windows.map((w) => `from ${when(w.starts_at)} to ${when(w.ends_at)}`).join(", ")}`
        }
        className="relative h-3 overflow-hidden rounded-full bg-muted"
      >
        {windows.map((window) => (
          <span
            key={window.starts_at}
            className="absolute inset-y-0 rounded-full bg-herb"
            style={{ left: `${pct(window.starts_at)}%`, width: `${pct(window.ends_at) - pct(window.starts_at)}%` }}
          />
        ))}
      </div>
      <div className="relative mt-1.5 h-4 text-[11px] tabular-nums text-ink-soft" aria-hidden="true">
        <span className="absolute left-0">Now</span>
        {ticks.map((tick) => (
          <time
            key={tick}
            suppressHydrationWarning
            dateTime={tick}
            className="absolute -translate-x-1/2 whitespace-nowrap"
            style={{ left: `${pct(tick)}%` }}
          >
            {clock(tick)}
          </time>
        ))}
      </div>
      <p className="mt-3 text-sm text-ink-muted">
        {everything ? (
          "No fixed hours - order whenever you like; the cook confirms each order."
        ) : availability.status === "paused" ? (
          "The cook has paused new orders for now."
        ) : windows.length === 0 ? (
          <>
            Not taking orders in the next 24 hours
            {availability.opens_at && (
              <>
                {" "}
                · next opening{" "}
                <time suppressHydrationWarning dateTime={availability.opens_at} className="font-medium text-ink">
                  {when(availability.opens_at)}
                </time>
              </>
            )}
          </>
        ) : (
          <>
            Taking orders{" "}
            {windows.map((window, index) => (
              <span key={window.starts_at}>
                {index > 0 && (index === windows.length - 1 ? " and " : ", ")}
                <time suppressHydrationWarning dateTime={window.starts_at} className="font-medium text-ink">
                  {window.starts_at === availability.as_of
                    ? continues(window.ends_at)
                      ? "all day"
                      : `now–${clock(window.ends_at)}`
                    : continues(window.ends_at)
                      ? `from ${when(window.starts_at)}`
                      : `${when(window.starts_at)}–${clock(window.ends_at)}`}
                </time>
              </span>
            ))}
          </>
        )}
      </p>
    </div>
  );
}
