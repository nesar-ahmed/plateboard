import { CircleCheck } from "lucide-react";
import type { ReactNode } from "react";

import DishArt from "@/components/dish-art";

/** Invented dish names - only their deterministic plate art is shown. */
const MOSAIC = [
  "Chilli Garlic Noodles",
  "Custard Tart",
  "Garden Salad",
  "Lamb Korma",
  "Prawn Dumplings",
  "Mushroom Risotto",
];

const PROMISES = [
  "Cooked today by someone in your neighbourhood",
  "Every ingredient listed, every allergen declared",
  "Cancel any time until your cook accepts",
];

/**
 * Split layout for login + registration: a brand panel (always dark) on the
 * left from `lg`, the form on the right. Below `lg` only the form shows.
 */
export default function AuthShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: ReactNode;
  children: ReactNode;
}) {
  return (
    <div className="grid grid-cols-1 min-h-[calc(100vh-4rem)] lg:grid-cols-2">
      <aside className="grain relative hidden overflow-hidden bg-night text-on-night lg:flex lg:flex-col lg:justify-between lg:p-12 xl:p-16">
        <div
          aria-hidden="true"
          className="absolute -left-32 top-1/3 h-96 w-96 rounded-full bg-[radial-gradient(circle,var(--brand)_0%,transparent_70%)] opacity-30"
        />
        <div className="relative">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand">Plateboard</p>
          <p className="mt-4 max-w-md font-display text-4xl font-semibold leading-tight tracking-tight xl:text-5xl">
            Good food has a name <span className="italic text-brand">and an address.</span>
          </p>
        </div>

        <div aria-hidden="true" className="relative my-10 grid max-w-md grid-cols-3 gap-3">
          {MOSAIC.map((name, index) => (
            <DishArt
              key={name}
              dish={{ name }}
              size="sm"
              className={index % 2 ? "aspect-square translate-y-6" : "aspect-square"}
              rounded="rounded-2xl"
            />
          ))}
        </div>

        <ul className="relative space-y-3 text-sm text-on-night/80">
          {PROMISES.map((promise) => (
            <li key={promise} className="flex items-center gap-3">
              <CircleCheck className="h-5 w-5 shrink-0 text-brand" aria-hidden="true" />
              {promise}
            </li>
          ))}
        </ul>
      </aside>

      <section className="flex items-start justify-center px-4 py-12 sm:items-center sm:px-6 lg:px-12">
        <div className="w-full max-w-[420px]">
          <h1 className="font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">{title}</h1>
          {subtitle && <p className="mt-2 text-ink-muted">{subtitle}</p>}
          <div className="mt-8">{children}</div>
        </div>
      </section>
    </div>
  );
}
