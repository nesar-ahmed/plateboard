"use client";

import { usePathname, useRouter } from "next/navigation";
import { useTransition } from "react";

import DishCard from "@/components/dish-card";
import DishFiltersPanel from "@/components/dish-filters";
import { ErrorBanner, Pager } from "@/components/ui";
import type { DishPage, Zone } from "@/lib/api";
import { EMPTY_FILTERS, dishFiltersToParams, type DishFilters } from "@/lib/dish-filters";
import { formatMinorUnits } from "@/lib/format";

/**
 * The interactive half of the dish list (the page itself is a Server
 * Component that already fetched `page` and `zones` - see app/page.tsx).
 *
 * Applying a filter or turning a page only changes the URL: Next re-renders
 * the server page for the new query and streams the result back, so there
 * is no client-side fetching here. The navigation runs in a transition, which
 * keeps the current results on screen (dimmed) until the new ones arrive.
 */
export default function DishDirectory({
  filters,
  offset,
  pageSize,
  page,
  errors,
  zones,
  zonesError,
}: {
  filters: DishFilters;
  offset: number;
  pageSize: number;
  page: DishPage | null;
  errors: string[];
  zones: Zone[] | null;
  zonesError: string | null;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const [pending, startTransition] = useTransition();

  const filtersKey = dishFiltersToParams(filters).toString();
  const filtered = filtersKey !== "";

  const navigate = (next: DishFilters, nextOffset = 0) => {
    const query = dishFiltersToParams(next, nextOffset).toString();
    startTransition(() => {
      router.push(query ? `${pathname}?${query}` : pathname, { scroll: false });
    });
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Dishes from local home cooks
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Only active menu items are listed, newest first. Search matches dish names, descriptions and ingredients.
        </p>
      </header>

      <DishFiltersPanel
        key={filtersKey}
        value={filters}
        zones={zones}
        zonesError={zonesError}
        onApply={(next) => navigate(next)}
        onClear={() => navigate(EMPTY_FILTERS)}
      />

      <ActiveFilters filters={filters} zones={zones} onChange={(next) => navigate(next)} />

      <ErrorBanner lines={errors} />

      <div className={pending ? "opacity-60 transition-opacity" : undefined} aria-busy={pending}>
        {page && (
          <p className="mb-3 text-sm text-zinc-500 dark:text-zinc-400" aria-live="polite">
            {page.total === 0
              ? "No dishes match."
              : `${page.total} ${page.total === 1 ? "dish" : "dishes"}${filtered ? " match" : ""} · newest first`}
          </p>
        )}

        {page && page.items.length === 0 && (
          <p className="text-sm text-zinc-500">
            {filtered ? (
              <>
                Nothing matches these filters.{" "}
                <button
                  type="button"
                  onClick={() => navigate(EMPTY_FILTERS)}
                  className="text-emerald-700 hover:underline dark:text-emerald-400"
                >
                  Clear all filters
                </button>
              </>
            ) : (
              "No dishes yet - check back soon."
            )}
          </p>
        )}

        {page && page.items.length > 0 && (
          <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
            {page.items.map((dish) => (
              <li key={dish.id}>
                <DishCard dish={dish} />
              </li>
            ))}
          </ul>
        )}

        {page && page.total > pageSize && (
          <Pager
            total={page.total}
            limit={pageSize}
            offset={offset}
            onMove={(nextOffset) => navigate(filters, nextOffset)}
          />
        )}
      </div>
    </div>
  );
}

/** Removable chips for every applied filter (search text included). */
function ActiveFilters({
  filters,
  zones,
  onChange,
}: {
  filters: DishFilters;
  zones: Zone[] | null;
  onChange: (next: DishFilters) => void;
}) {
  const chips: { key: string; label: string; next: DishFilters }[] = [];
  if (filters.q) chips.push({ key: "q", label: `"${filters.q}"`, next: { ...filters, q: "" } });
  if (filters.zone) {
    const name = zones?.find((zone) => zone.slug === filters.zone)?.name ?? filters.zone;
    const reach =
      filters.maxDistance === null
        ? ""
        : ` · within ${filters.maxDistance} ${filters.maxDistance === 1 ? "step" : "steps"}`;
    chips.push({
      key: "zone",
      label: `${name}${reach}`,
      next: { ...filters, zone: "", maxDistance: null },
    });
  }
  if (filters.minPrice !== null || filters.maxPrice !== null) {
    const low = filters.minPrice !== null ? formatMinorUnits(filters.minPrice) : null;
    const high = filters.maxPrice !== null ? formatMinorUnits(filters.maxPrice) : null;
    const label = low && high ? `${low} - ${high}` : low ? `from ${low}` : `up to ${high}`;
    chips.push({ key: "price", label, next: { ...filters, minPrice: null, maxPrice: null } });
  }
  for (const tag of filters.dietaryTags) {
    chips.push({
      key: `tag:${tag}`,
      label: tag,
      next: { ...filters, dietaryTags: filters.dietaryTags.filter((held) => held !== tag) },
    });
  }
  for (const allergen of filters.excludeAllergens) {
    chips.push({
      key: `no:${allergen}`,
      label: `no ${allergen}`,
      next: {
        ...filters,
        excludeAllergens: filters.excludeAllergens.filter((held) => held !== allergen),
      },
    });
  }
  if (chips.length === 0) return null;

  return (
    <ul className="flex flex-wrap gap-2" aria-label="Applied filters">
      {chips.map((chip) => (
        <li key={chip.key}>
          <button
            type="button"
            onClick={() => onChange(chip.next)}
            aria-label={`Remove filter ${chip.label}`}
            className="inline-flex items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1 text-xs font-medium text-emerald-800 hover:bg-emerald-100 dark:border-emerald-900 dark:bg-emerald-950 dark:text-emerald-300"
          >
            {chip.label}
            <span aria-hidden="true">×</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
