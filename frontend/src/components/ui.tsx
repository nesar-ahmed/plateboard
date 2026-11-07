"use client";

/** Small shared building blocks so the pages stay presentational. */

import type { ReactNode } from "react";

export function Card({
  title,
  aside,
  children,
}: {
  title?: string;
  aside?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="rounded-2xl border border-zinc-200 bg-white p-6 shadow-sm dark:border-zinc-800 dark:bg-zinc-950">
      {(title || aside) && (
        <header className="mb-4 flex items-center justify-between gap-4">
          {title && (
            <h2 className="text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
              {title}
            </h2>
          )}
          {aside}
        </header>
      )}
      {children}
    </section>
  );
}

export function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-sm font-medium text-zinc-700 dark:text-zinc-300">
        {label}
      </span>
      {children}
      {hint && <span className="mt-1 block text-xs text-zinc-400">{hint}</span>}
    </label>
  );
}

export const inputClass =
  "w-full rounded-lg border border-zinc-300 bg-white px-3 py-2 text-sm text-zinc-900 " +
  "placeholder:text-zinc-400 focus:border-emerald-500 focus:outline-none " +
  "dark:border-zinc-700 dark:bg-zinc-900 dark:text-zinc-100";

export const buttonClass =
  "rounded-full px-4 py-2 text-sm font-medium transition-colors disabled:cursor-not-allowed disabled:opacity-50";

export const primaryButtonClass =
  `${buttonClass} bg-emerald-600 text-white hover:bg-emerald-700`;

export const ghostButtonClass =
  `${buttonClass} border border-zinc-300 text-zinc-700 hover:bg-zinc-100 ` +
  "dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800";

export const dangerButtonClass =
  `${buttonClass} border border-red-300 text-red-700 hover:bg-red-50 ` +
  "dark:border-red-900 dark:text-red-400 dark:hover:bg-red-950";

export function ErrorBanner({ lines }: { lines: string[] }) {
  if (lines.length === 0) return null;
  return (
    <div
      role="alert"
      className="rounded-lg border border-red-300 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900 dark:bg-red-950 dark:text-red-300"
    >
      <ul className="list-inside list-disc space-y-1">
        {lines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </div>
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
  return (
    <div className="mt-6 flex items-center justify-between text-sm text-zinc-500 dark:text-zinc-400">
      <span>
        Showing {from}&ndash;{to} of {total}
      </span>
      <div className="flex gap-2">
        <button
          type="button"
          className={ghostButtonClass}
          disabled={offset <= 0}
          onClick={() => onMove(Math.max(0, offset - limit))}
        >
          Previous
        </button>
        <button
          type="button"
          className={ghostButtonClass}
          disabled={offset + limit >= total}
          onClick={() => onMove(offset + limit)}
        >
          Next
        </button>
      </div>
    </div>
  );
}

export function Tag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex rounded-full bg-zinc-100 px-2.5 py-0.5 text-xs font-medium text-zinc-600 dark:bg-zinc-800 dark:text-zinc-300">
      {children}
    </span>
  );
}

export function AllergenTag({ children }: { children: ReactNode }) {
  return (
    <span className="inline-flex rounded-full bg-amber-100 px-2.5 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-950 dark:text-amber-300">
      {children}
    </span>
  );
}
