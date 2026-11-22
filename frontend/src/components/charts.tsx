/**
 * Small, dependency-free charts for the dashboards (account and cook panels,
 * admin later): HTML/CSS bars, an SVG donut, stat cards, trend chips and
 * meters. Server-safe, responsive, coloured through the CSS tokens - so dark
 * mode follows - and described for screen readers.
 */

import { ArrowDownRight, ArrowUpRight } from "lucide-react";

import { cx } from "@/components/ui";

// --- bar chart -----------------------------------------------------------------------

/** `title` (optional) replaces `label` in the tooltip, e.g. a full date. */
export type Bar = { label: string; value: number; hint?: string; title?: string };

/**
 * Columns built from plain HTML/CSS (not an SVG viewBox), so labels keep a
 * real, readable font size on every screen while bars scale to the data.
 * Dense series (a month of days) pass `showValues={false}` - values move to
 * the tooltip - and `labelEvery` to print every n-th axis label only.
 */
export function BarChart({
  bars,
  format = (value) => String(value),
  highlightLast = true,
  height = 180,
  showValues = true,
  labelEvery = 1,
  ariaLabel,
}: {
  bars: Bar[];
  format?: (value: number) => string;
  highlightLast?: boolean;
  height?: number;
  showValues?: boolean;
  labelEvery?: number;
  ariaLabel: string;
}) {
  const max = Math.max(1, ...bars.map((bar) => bar.value));
  return (
    <figure aria-label={ariaLabel} className="w-full">
      <div
        role="img"
        aria-label={`${ariaLabel}: ${bars.map((bar) => `${bar.label} ${format(bar.value)}`).join(", ")}`}
        className={cx(
          "relative flex items-end border-b border-line-strong",
          bars.length > 16 ? "gap-[3px] sm:gap-1" : "gap-2 sm:gap-3",
        )}
        style={{
          height,
          backgroundImage: "linear-gradient(to top, var(--line) 1px, transparent 1px)",
          backgroundSize: `100% ${height / 4}px`,
        }}
      >
        {bars.map((bar, index) => {
          const active = highlightLast && index === bars.length - 1;
          const pct = bar.value > 0 ? Math.max(3, (bar.value / max) * 82) : 0; // headroom for the label
          return (
            <div
              key={`${index}-${bar.label}`}
              title={`${bar.title ?? bar.label}: ${format(bar.value)}${bar.hint ? ` · ${bar.hint}` : ""}`}
              className="flex h-full min-w-0 flex-1 flex-col items-center justify-end"
            >
              {showValues && bar.value > 0 && (
                <span className="mb-1.5 truncate text-[11px] font-medium tabular-nums text-ink-muted sm:text-xs">
                  {format(bar.value)}
                </span>
              )}
              <div
                className={cx(
                  "w-full max-w-14 transition-[height] duration-500",
                  bars.length > 16 ? "rounded-t" : "rounded-t-lg",
                  bar.value === 0 ? "h-[3px] bg-line-strong" : active ? "bg-brand" : "bg-ink/80",
                )}
                style={bar.value > 0 ? { height: `${pct}%` } : undefined}
              />
            </div>
          );
        })}
      </div>
      <div className={cx("mt-2 flex", bars.length > 16 ? "gap-[3px] sm:gap-1" : "gap-2 sm:gap-3")} aria-hidden="true">
        {bars.map((bar, index) => {
          const last = index === bars.length - 1;
          const shown = last || (bars.length - 1 - index) % labelEvery === 0;
          return (
            <span
              key={`${index}-${bar.label}`}
              className={cx(
                "min-w-0 flex-1 text-center text-xs",
                labelEvery > 1 ? "overflow-visible whitespace-nowrap" : "truncate",
                highlightLast && last ? "font-semibold text-ink" : "text-ink-soft",
              )}
            >
              {shown ? bar.label : ""}
            </span>
          );
        })}
      </div>
    </figure>
  );
}

// --- donut -----------------------------------------------------------------------------

export type Slice = { label: string; value: number; color: string };

export function Donut({
  slices,
  centerValue,
  centerLabel,
  size = 160,
  ariaLabel,
}: {
  slices: Slice[];
  centerValue: string;
  centerLabel: string;
  size?: number;
  ariaLabel: string;
}) {
  const radius = 42;
  const circumference = 2 * Math.PI * radius;
  const total = slices.reduce((sum, slice) => sum + slice.value, 0);
  const visible = slices.filter((slice) => slice.value > 0);
  const gap = visible.length > 1 ? 2.5 : 0;
  let offset = 0;

  return (
    <div className="flex flex-col items-center gap-5 sm:flex-row sm:items-center">
      <svg
        viewBox="0 0 100 100"
        width={size}
        height={size}
        role="img"
        aria-label={ariaLabel}
        className="shrink-0 -rotate-90"
      >
        <title>{ariaLabel}</title>
        <circle cx="50" cy="50" r={radius} fill="none" stroke="var(--muted)" strokeWidth="11" />
        {total > 0 &&
          visible.map((slice) => {
            const length = (slice.value / total) * circumference;
            const dash = Math.max(0.001, length - gap);
            const element = (
              <circle
                key={slice.label}
                cx="50"
                cy="50"
                r={radius}
                fill="none"
                stroke={slice.color}
                strokeWidth="11"
                strokeDasharray={`${dash} ${circumference - dash}`}
                strokeDashoffset={-offset}
                strokeLinecap="butt"
              >
                <title>{`${slice.label}: ${slice.value}`}</title>
              </circle>
            );
            offset += length;
            return element;
          })}
        <g className="rotate-90" style={{ transformOrigin: "50px 50px" }}>
          <text x="50" y="49" textAnchor="middle" className="fill-ink font-display text-[20px] font-semibold">
            {centerValue}
          </text>
          <text x="50" y="62" textAnchor="middle" className="fill-ink-soft text-[8px]">
            {centerLabel}
          </text>
        </g>
      </svg>
      <ul className="grid w-full grid-cols-2 gap-x-4 gap-y-2 text-sm sm:grid-cols-1">
        {slices.map((slice) => (
          <li key={slice.label} className="flex items-center justify-between gap-3">
            <span className="flex items-center gap-2 text-ink-muted">
              <span className="h-2.5 w-2.5 rounded-full" style={{ background: slice.color }} aria-hidden="true" />
              {slice.label}
            </span>
            <span className="font-semibold tabular-nums text-ink">{slice.value}</span>
          </li>
        ))}
      </ul>
    </div>
  );
}

// --- stat card -----------------------------------------------------------------------

export function StatCard({
  label,
  value,
  hint,
  icon,
  tone = "neutral",
}: {
  label: string;
  value: React.ReactNode;
  hint?: React.ReactNode;
  icon?: React.ReactNode;
  tone?: "neutral" | "brand" | "herb" | "saffron";
}) {
  const tones = {
    neutral: "bg-muted text-ink-muted",
    brand: "bg-brand-soft text-brand",
    herb: "bg-herb-soft text-herb",
    saffron: "bg-saffron-soft text-saffron",
  }[tone];
  return (
    <div className="rounded-3xl border border-line bg-surface p-5 shadow-card">
      <div className="flex items-center justify-between gap-3">
        <p className="text-sm text-ink-muted">{label}</p>
        {icon && <span className={cx("flex h-9 w-9 items-center justify-center rounded-xl", tones)}>{icon}</span>}
      </div>
      <p className="mt-3 font-display text-3xl font-semibold tabular-nums tracking-tight text-ink">{value}</p>
      {hint && <p className="mt-1 text-xs text-ink-soft">{hint}</p>}
    </div>
  );
}

// --- trend + meter -------------------------------------------------------------------

/**
 * "+12% vs previous 30 days" chip. `percent` null = nothing to compare with
 * (the previous period was empty). `inverse` for numbers where up is bad.
 */
export function Trend({
  percent,
  label,
  inverse = false,
}: {
  percent: number | null;
  label: string;
  inverse?: boolean;
}) {
  if (percent === null) return <span className="text-ink-soft">No earlier data to compare</span>;
  const up = percent > 0;
  const good = percent === 0 ? null : up !== inverse;
  const Icon = up ? ArrowUpRight : ArrowDownRight;
  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <span
        className={cx(
          "inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 text-[11px] font-semibold tabular-nums",
          good === null ? "bg-muted text-ink-muted" : good ? "bg-herb-soft text-herb" : "bg-danger-soft text-danger",
        )}
      >
        {percent !== 0 && <Icon className="h-3 w-3" aria-hidden="true" />}
        {percent > 0 ? "+" : ""}
        {percent}%
      </span>
      <span className="text-ink-soft">vs {label}</span>
    </span>
  );
}

/** A labelled 0..1 bar (acceptance rate, share of earnings, set-up progress). */
export function Meter({
  value,
  label,
  display,
  tone = "herb",
  className,
}: {
  value: number | null;
  label?: string;
  display?: string;
  tone?: "herb" | "brand" | "saffron" | "ink";
  className?: string;
}) {
  const pct = value === null ? 0 : Math.min(100, Math.max(0, value * 100));
  const fill = { herb: "bg-herb", brand: "bg-brand", saffron: "bg-saffron", ink: "bg-ink" }[tone];
  return (
    <div className={className}>
      {(label || display) && (
        <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
          {label && <span className="text-ink-muted">{label}</span>}
          {display && <span className="font-semibold tabular-nums text-ink">{display}</span>}
        </div>
      )}
      <div
        role="meter"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={Math.round(pct)}
        className="h-2 overflow-hidden rounded-full bg-muted"
      >
        <div className={cx("h-full rounded-full transition-[width] duration-500", fill)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}
