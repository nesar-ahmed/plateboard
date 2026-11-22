/**
 * Design-system primitives. Server-safe (no hooks, no "use client"), so both
 * Server and Client Components can use them.
 *
 * Colours are the semantic tokens from globals.css (canvas, surface, ink,
 * line, brand, herb, saffron, danger) - never raw palette classes - so dark
 * mode follows automatically.
 */

import { ChevronDown } from "lucide-react";
import Link from "next/link";
import type { ComponentProps, ReactNode } from "react";

import { formatCount } from "@/lib/format";

/** Join class names, skipping falsy entries. */
export function cx(...parts: (string | false | null | undefined)[]): string {
  return parts.filter(Boolean).join(" ");
}

// --- layout -----------------------------------------------------------------------------

/** The page column every non-full-bleed page sits in. */
export function Container({
  children,
  className,
  size = "default",
}: {
  children: ReactNode;
  className?: string;
  size?: "default" | "narrow" | "wide";
}) {
  // default = the header's width, so page edges line up with the logo.
  const width = { narrow: "max-w-3xl", default: "max-w-7xl", wide: "max-w-7xl" }[size];
  return <div className={cx("mx-auto w-full px-4 sm:px-6 lg:px-8", width, className)}>{children}</div>;
}

/** Standard page wrapper: container + vertical rhythm. */
export function Page({
  children,
  size,
  className,
}: {
  children: ReactNode;
  size?: "default" | "narrow" | "wide";
  className?: string;
}) {
  return (
    <Container size={size} className={cx("py-8 sm:py-12", className)}>
      {children}
    </Container>
  );
}

export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cx("text-xs font-semibold uppercase tracking-[0.16em] text-brand", className)}>
      {children}
    </p>
  );
}

/**
 * Page title block: optional eyebrow, display heading, lead text, actions.
 * `compact` is the in-panel size (account, later cook/admin): a smaller
 * heading and no outer margin - the panel page spaces its own sections.
 */
export function PageHeader({
  eyebrow,
  title,
  lead,
  actions,
  size = "default",
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  lead?: ReactNode;
  actions?: ReactNode;
  size?: "default" | "compact";
}) {
  const compact = size === "compact";
  return (
    <header
      className={cx(
        "flex flex-col gap-4 sm:flex-row sm:items-end sm:justify-between",
        !compact && "mb-8 sm:mb-10",
      )}
    >
      <div className="max-w-2xl">
        {eyebrow && <Eyebrow className="mb-2">{eyebrow}</Eyebrow>}
        <h1
          className={cx(
            "font-display text-3xl font-semibold tracking-tight text-ink",
            !compact && "sm:text-4xl",
          )}
        >
          {title}
        </h1>
        {lead && <p className={cx("text-base text-ink-muted", compact ? "mt-1" : "mt-2")}>{lead}</p>}
      </div>
      {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
    </header>
  );
}

export function SectionHeading({
  eyebrow,
  title,
  lead,
  action,
}: {
  eyebrow?: ReactNode;
  title: ReactNode;
  lead?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
      <div className="max-w-2xl">
        {eyebrow && <Eyebrow className="mb-2">{eyebrow}</Eyebrow>}
        <h2 className="font-display text-2xl font-semibold tracking-tight text-ink sm:text-3xl">{title}</h2>
        {lead && <p className="mt-2 text-ink-muted">{lead}</p>}
      </div>
      {action}
    </div>
  );
}

// --- surfaces ---------------------------------------------------------------------------

export function Card({
  title,
  aside,
  children,
  className,
  padded = true,
}: {
  title?: ReactNode;
  aside?: ReactNode;
  children: ReactNode;
  className?: string;
  padded?: boolean;
}) {
  return (
    <section
      className={cx(
        "rounded-3xl border border-line bg-surface shadow-card",
        padded && "p-5 sm:p-6",
        className,
      )}
    >
      {(title || aside) && (
        <header className="mb-4 flex items-center justify-between gap-4">
          {title && <h2 className="font-display text-lg font-semibold tracking-tight text-ink">{title}</h2>}
          {aside}
        </header>
      )}
      {children}
    </section>
  );
}

export function EmptyState({
  icon,
  title,
  children,
  action,
}: {
  icon?: ReactNode;
  title: ReactNode;
  children?: ReactNode;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center rounded-3xl border border-dashed border-line-strong px-6 py-14 text-center">
      {icon && (
        <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-full bg-muted text-ink-muted">
          {icon}
        </div>
      )}
      <p className="font-display text-lg font-semibold text-ink">{title}</p>
      {children && <div className="mt-1 max-w-sm text-sm text-ink-muted">{children}</div>}
      {action && <div className="mt-5">{action}</div>}
    </div>
  );
}

// --- forms ------------------------------------------------------------------------------

export function Field({
  label,
  hint,
  error,
  optional,
  children,
}: {
  label: string;
  hint?: string;
  error?: string | null;
  optional?: boolean;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1.5 flex items-baseline justify-between gap-2 text-sm font-medium text-ink">
        {label}
        {optional && <span className="text-xs font-normal text-ink-soft">Optional</span>}
      </span>
      {children}
      {error ? (
        <span className="mt-1.5 block text-xs font-medium text-danger">{error}</span>
      ) : (
        hint && <span className="mt-1.5 block text-xs text-ink-soft">{hint}</span>
      )}
    </label>
  );
}

export const inputClass =
  "h-11 w-full rounded-xl border border-line-strong bg-surface px-3.5 text-[15px] text-ink shadow-xs " +
  "placeholder:text-ink-soft transition-colors hover:border-ink-soft " +
  "focus:border-brand focus:outline-none focus:ring-4 focus:ring-brand/15 " +
  "disabled:cursor-not-allowed disabled:opacity-60";

export const textareaClass = inputClass.replace("h-11", "min-h-24 py-2.5");

export const selectClass = `${inputClass} appearance-none pr-10`;

/** Native <select> (keeps mobile pickers + a11y) with a consistent chevron. */
export function Select({ className, children, ...props }: ComponentProps<"select">) {
  return (
    <div className="relative">
      <select className={cx(selectClass, className)} {...props}>
        {children}
      </select>
      <ChevronDown
        aria-hidden="true"
        className="pointer-events-none absolute right-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-soft"
      />
    </div>
  );
}

// --- buttons ----------------------------------------------------------------------------

export const buttonClass =
  "inline-flex items-center justify-center gap-2 rounded-full px-5 h-11 text-sm font-semibold " +
  "transition-all duration-150 active:scale-[0.98] disabled:pointer-events-none disabled:opacity-50 whitespace-nowrap";

export const primaryButtonClass = `${buttonClass} bg-brand text-on-brand shadow-sm hover:bg-brand-strong`;

export const darkButtonClass = `${buttonClass} bg-ink text-canvas hover:bg-ink/85`;

export const ghostButtonClass = `${buttonClass} border border-line-strong bg-surface text-ink hover:border-ink-soft hover:bg-muted`;

export const quietButtonClass = `${buttonClass} text-ink-muted hover:bg-muted hover:text-ink`;

export const dangerButtonClass = `${buttonClass} border border-danger/30 text-danger hover:bg-danger-soft`;

export const smallButton = "h-9 px-4 text-[13px]";

/** A link styled as a button (same variants). */
export function ButtonLink({
  variant = "primary",
  className,
  ...props
}: ComponentProps<typeof Link> & { variant?: "primary" | "dark" | "ghost" | "quiet" }) {
  const base = {
    primary: primaryButtonClass,
    dark: darkButtonClass,
    ghost: ghostButtonClass,
    quiet: quietButtonClass,
  }[variant];
  return <Link className={cx(base, className)} {...props} />;
}

// --- feedback ---------------------------------------------------------------------------

export function ErrorBanner({ lines }: { lines: string[] }) {
  if (lines.length === 0) return null;
  return (
    <div
      role="alert"
      className="rounded-2xl border border-danger/25 bg-danger-soft px-4 py-3 text-sm text-danger"
    >
      {lines.length === 1 ? (
        <p>{lines[0]}</p>
      ) : (
        <ul className="list-inside list-disc space-y-1">
          {lines.map((line) => (
            <li key={line}>{line}</li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function Spinner({ className }: { className?: string }) {
  return (
    <span
      aria-hidden="true"
      className={cx("inline-block h-4 w-4 animate-spin rounded-full border-2 border-current border-r-transparent", className)}
    />
  );
}

export function Pager({
  total,
  limit,
  offset,
  onMove,
}: {
  total: number;
  limit: number;
  offset: number;
  onMove: (nextOffset: number) => void;
}) {
  const from = total === 0 ? 0 : offset + 1;
  const to = Math.min(offset + limit, total);
  const page = Math.floor(offset / limit) + 1;
  const pages = Math.max(1, Math.ceil(total / limit));
  return (
    <nav
      aria-label="Pagination"
      className="mt-10 flex flex-col items-center justify-between gap-4 border-t border-line pt-6 text-sm text-ink-muted sm:flex-row"
    >
      <span>
        Showing <span className="font-medium text-ink">{from}&ndash;{to}</span> of{" "}
        <span className="font-medium text-ink">{total}</span>
      </span>
      <div className="flex items-center gap-2">
        <button
          type="button"
          className={cx(ghostButtonClass, smallButton)}
          disabled={offset <= 0}
          onClick={() => onMove(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <span className="px-2 tabular-nums">
          {page} / {pages}
        </span>
        <button
          type="button"
          className={cx(ghostButtonClass, smallButton)}
          disabled={offset + limit >= total}
          onClick={() => onMove(offset + limit)}
        >
          Next
        </button>
      </div>
    </nav>
  );
}

// --- chips + badges ---------------------------------------------------------------------

export function Tag({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full bg-herb-soft px-2.5 py-0.5 text-xs font-medium text-herb",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function AllergenTag({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <span
      className={cx(
        "inline-flex items-center rounded-full bg-saffron-soft px-2.5 py-0.5 text-xs font-medium text-saffron",
        className,
      )}
    >
      {children}
    </span>
  );
}

export function Badge({
  children,
  tone = "neutral",
  className,
}: {
  children: ReactNode;
  tone?: "neutral" | "brand" | "herb" | "saffron" | "danger" | "night";
  className?: string;
}) {
  const tones = {
    neutral: "bg-muted text-ink-muted",
    brand: "bg-brand-soft text-brand",
    herb: "bg-herb-soft text-herb",
    saffron: "bg-saffron-soft text-saffron",
    danger: "bg-danger-soft text-danger",
    night: "bg-ink text-canvas",
  }[tone];
  return (
    <span
      className={cx(
        "inline-flex items-center gap-1 rounded-full px-2.5 py-0.5 text-xs font-semibold",
        tones,
        className,
      )}
    >
      {children}
    </span>
  );
}

/**
 * A live count on a nav item or tab ("3", "99+" - nothing at all at 0):
 * `brand` for what needs attention (requests, unread, pending), `quiet`
 * otherwise; inverted on the active / selected item. `label` is the
 * accessible text when the number alone would be unclear ("3 unread").
 */
export function CountPill({
  count,
  active = false,
  tone = "brand",
  size = "md",
  label,
  className,
}: {
  count: number | null | undefined;
  active?: boolean;
  tone?: "brand" | "quiet";
  size?: "sm" | "md";
  label?: string;
  className?: string;
}) {
  if (!count) return null;
  return (
    <span
      aria-label={label}
      className={cx(
        "rounded-full text-center font-bold tabular-nums",
        size === "sm" ? "min-w-4 px-1 text-[10px] leading-4" : "min-w-5 px-1.5 text-[11px] leading-5",
        active ? "bg-canvas text-ink" : tone === "brand" ? "bg-brand text-on-brand" : "bg-muted text-ink",
        className,
      )}
    >
      {formatCount(count)}
    </span>
  );
}

/** Initials avatar with a warm, name-derived tint (no photos in the data yet). */
export function Avatar({
  name,
  size = "md",
  className,
}: {
  name: string | null | undefined;
  size?: "sm" | "md" | "lg" | "xl";
  className?: string;
}) {
  const label = (name ?? "?").trim() || "?";
  const initials = label
    .split(/\s+/)
    .slice(0, 2)
    .map((part) => part[0]?.toUpperCase() ?? "")
    .join("");
  const tints = [
    "bg-[#f3d9c8] text-[#8a3412]",
    "bg-[#dfe9d5] text-[#3f6b3a]",
    "bg-[#f6e6c2] text-[#7a4b06]",
    "bg-[#e6dcef] text-[#5b3d7a]",
    "bg-[#d8e6ea] text-[#2f5f6e]",
    "bg-[#f2d6d6] text-[#8b2f2f]",
  ];
  let hash = 0;
  for (const ch of label) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0;
  const sizes = { sm: "h-8 w-8 text-xs", md: "h-10 w-10 text-sm", lg: "h-14 w-14 text-lg", xl: "h-20 w-20 text-2xl" }[
    size
  ];
  return (
    <span
      aria-hidden="true"
      className={cx(
        "inline-flex shrink-0 items-center justify-center rounded-full font-display font-semibold",
        tints[hash % tints.length],
        sizes,
        className,
      )}
    >
      {initials}
    </span>
  );
}

/**
 * A row that is a swipeable, snapping carousel on phones and a normal grid
 * from `sm` up - long lists of cards stay one thumb-swipe tall on mobile.
 * Pass the grid columns for larger screens via `className`.
 */
export const railListClass =
  "-mx-4 flex snap-x snap-mandatory gap-4 overflow-x-auto px-4 pb-3 [scrollbar-width:none] " +
  "sm:mx-0 sm:grid sm:gap-5 sm:overflow-visible sm:px-0 sm:pb-0";
export const railItemClass = "w-[80%] shrink-0 snap-start sm:w-auto";
