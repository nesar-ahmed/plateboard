"use client";

import { Leaf, Search, SlidersHorizontal, UtensilsCrossed, X } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useState, useTransition } from "react";

import DishCard from "@/components/dish-card";
import DishFiltersPanel from "@/components/dish-filters";
import { EmptyState, ErrorBanner, Pager, cx, ghostButtonClass, primaryButtonClass } from "@/components/ui";
import type { DishPage, Preferences, Zone } from "@/lib/api";
import { ALLERGENS, type Allergen } from "@/lib/allergens";
import { EMPTY_FILTERS, countActiveFilters, dishFiltersToParams, type DishFilters } from "@/lib/dish-filters";
import { formatMinorUnits } from "@/lib/format";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

/**
 * The interactive half of the dish list (the page itself is a Server
 * Component that already fetched `page` and `zones` - see app/dishes/page.tsx).
 *
 * Searching, filtering or paging only changes the URL: Next re-renders the
 * server page for the new query and streams the result back, so there is no
 * client-side fetching here. Navigation runs in a transition, which keeps the
 * current results on screen (dimmed) until the new ones arrive.
 *
 * Layout: search bar on top; filters in a sticky sidebar from `lg`, in a
 * bottom sheet below that.
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
  const [sheetOpen, setSheetOpen] = useState(false);

  const filtersKey = dishFiltersToParams(filters).toString();
  const activeCount = countActiveFilters(filters);
  const filtered = filtersKey !== "";

  const navigate = (next: DishFilters, nextOffset = 0) => {
    setSheetOpen(false);
    const query = dishFiltersToParams(next, nextOffset).toString();
    startTransition(() => {
      router.push(query ? `${pathname}?${query}` : pathname, { scroll: nextOffset !== offset });
    });
  };

  const panel = (
    <DishFiltersPanel
      key={filtersKey}
      value={filters}
      zones={zones}
      zonesError={zonesError}
      onApply={(next) => navigate(next)}
      onClear={() => navigate({ ...EMPTY_FILTERS, q: filters.q })}
    />
  );

  return (
    <div>
      <div className="flex gap-2">
        <SearchBar key={filters.q} initial={filters.q} onSearch={(q) => navigate({ ...filters, q })} />
        <button
          type="button"
          onClick={() => setSheetOpen(true)}
          className={cx(ghostButtonClass, "h-12 shrink-0 lg:hidden")}
          aria-haspopup="dialog"
        >
          <SlidersHorizontal className="h-4 w-4" aria-hidden="true" />
          <span className="hidden sm:inline">Filters</span>
          {activeCount > 0 && (
            <span className="flex h-5 min-w-5 items-center justify-center rounded-full bg-brand px-1 text-[11px] text-on-brand">
              {activeCount}
            </span>
          )}
        </button>
      </div>

      <div className="mt-8 grid grid-cols-1 gap-10 lg:grid-cols-[272px_minmax(0,1fr)]">
        <aside aria-label="Filters" className="hidden lg:block">
          <div className="sticky top-24 max-h-[calc(100vh-7rem)] overflow-y-auto rounded-3xl border border-line bg-surface px-5 pt-5 shadow-card">
            {panel}
          </div>
        </aside>

        <div className={cx("min-w-0 transition-opacity", pending && "opacity-50")} aria-busy={pending}>
          <div className="mb-5 flex flex-wrap items-center justify-between gap-3">
            <p className="text-sm text-ink-muted" aria-live="polite">
              {page
                ? page.total === 0
                  ? "No dishes match"
                  : `${page.total} ${page.total === 1 ? "dish" : "dishes"}${filtered ? " match" : ""} · newest first`
                : " "}
            </p>
          </div>

          <PreferencesSuggestion filters={filters} onApply={(next) => navigate(next)} />
          <ActiveFilters filters={filters} zones={zones} onChange={(next) => navigate(next)} />
          <ErrorBanner lines={errors} />

          {page && page.items.length === 0 && (
            <EmptyState
              icon={<UtensilsCrossed className="h-6 w-6" />}
              title={filtered ? "Nothing matches these filters" : "No dishes yet"}
              action={
                filtered && (
                  <button type="button" onClick={() => navigate(EMPTY_FILTERS)} className={primaryButtonClass}>
                    Clear all filters
                  </button>
                )
              }
            >
              {filtered
                ? "Try a wider neighbourhood, fewer tags or a different search."
                : "Home cooks are adding their menus - check back soon."}
            </EmptyState>
          )}

          {page && page.items.length > 0 && (
            <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3">
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

      {sheetOpen && <FilterSheet onClose={() => setSheetOpen(false)}>{panel}</FilterSheet>}
    </div>
  );
}

function SearchBar({ initial, onSearch }: { initial: string; onSearch: (q: string) => void }) {
  const [q, setQ] = useState(initial);
  return (
    <form
      role="search"
      className="relative flex-1"
      onSubmit={(event) => {
        event.preventDefault();
        onSearch(q.trim());
      }}
    >
      <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-soft" />
      <input
        type="search"
        value={q}
        onChange={(event) => setQ(event.target.value)}
        placeholder="Search dishes, descriptions, ingredients…"
        aria-label="Search dishes"
        maxLength={120}
        className="h-12 w-full rounded-full border border-line-strong bg-surface pl-12 pr-28 text-[15px] text-ink shadow-card placeholder:text-ink-soft focus:border-brand focus:outline-none focus:ring-4 focus:ring-brand/15"
      />
      <button
        type="submit"
        className="absolute right-1.5 top-1/2 h-9 -translate-y-1/2 rounded-full bg-ink px-4 text-sm font-semibold text-canvas hover:bg-ink/85"
      >
        Search
      </button>
    </form>
  );
}

/** Bottom sheet (mobile/tablet) holding the same filter panel. */
function FilterSheet({ onClose, children }: { onClose: () => void; children: React.ReactNode }) {
  useEffect(() => {
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => {
      document.body.style.overflow = overflow;
      document.removeEventListener("keydown", onKey);
    };
  }, [onClose]);

  return (
    <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true" aria-label="Filters">
      <div className="animate-fade-in absolute inset-0 bg-night/50" onClick={onClose} aria-hidden="true" />
      <div className="animate-rise absolute inset-x-0 bottom-0 max-h-[88vh] overflow-y-auto rounded-t-[2rem] bg-surface px-5 pt-3 shadow-pop">
        <div className="mx-auto mb-3 h-1.5 w-10 rounded-full bg-line-strong" aria-hidden="true" />
        <div className="mb-5 flex items-center justify-between">
          <p className="font-display text-xl font-semibold text-ink">Filters</p>
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 items-center justify-center rounded-full hover:bg-muted"
            aria-label="Close filters"
          >
            <X className="h-5 w-5" />
          </button>
        </div>
        {children}
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
  if (filters.q) chips.push({ key: "q", label: `“${filters.q}”`, next: { ...filters, q: "" } });
  if (filters.zone) {
    const name = zones?.find((zone) => zone.slug === filters.zone)?.name ?? filters.zone;
    const reach =
      filters.maxDistance === null
        ? ""
        : ` · within ${filters.maxDistance} ${filters.maxDistance === 1 ? "step" : "steps"}`;
    chips.push({ key: "zone", label: `${name}${reach}`, next: { ...filters, zone: "", maxDistance: null } });
  }
  if (filters.minPrice !== null || filters.maxPrice !== null) {
    const low = filters.minPrice !== null ? formatMinorUnits(filters.minPrice) : null;
    const high = filters.maxPrice !== null ? formatMinorUnits(filters.maxPrice) : null;
    const label = low && high ? `${low} – ${high}` : low ? `From ${low}` : `Up to ${high}`;
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
      label: `No ${allergen}`,
      next: { ...filters, excludeAllergens: filters.excludeAllergens.filter((held) => held !== allergen) },
    });
  }
  if (chips.length === 0) return null;

  return (
    <ul className="mb-6 flex flex-wrap items-center gap-2" aria-label="Applied filters">
      {chips.map((chip) => (
        <li key={chip.key}>
          <button
            type="button"
            onClick={() => onChange(chip.next)}
            aria-label={`Remove filter ${chip.label}`}
            className="inline-flex h-8 items-center gap-1.5 rounded-full bg-ink pl-3 pr-2 text-xs font-medium capitalize text-canvas hover:bg-ink/85"
          >
            {chip.label}
            <X className="h-3.5 w-3.5" aria-hidden="true" />
          </button>
        </li>
      ))}
      {chips.length > 1 && (
        <li>
          <button
            type="button"
            onClick={() => onChange(EMPTY_FILTERS)}
            className="h-8 px-2 text-xs font-semibold text-brand hover:underline"
          >
            Clear all
          </button>
        </li>
      )}
    </ul>
  );
}

/**
 * Signed-in shoppers with a food profile (/account/preferences) get a
 * one-tap suggestion to apply it - never applied silently. Hidden once the
 * current filters already include everything in the profile.
 */
function PreferencesSuggestion({
  filters,
  onApply,
}: {
  filters: DishFilters;
  onApply: (next: DishFilters) => void;
}) {
  const { user } = useSession();
  const { data } = useApi<Preferences>(user ? "/me/preferences" : null);
  if (!data) return null;
  const allergens = data.excluded_allergens.filter((a) => !filters.excludeAllergens.includes(a as Allergen));
  const diets = data.dietary_preferences.filter((d) => !filters.dietaryTags.includes(d));
  if (allergens.length === 0 && diets.length === 0) return null;

  const summary = [
    ...diets,
    ...(allergens.length ? [`no ${allergens.join(", ")}`] : []),
  ].join(" · ");
  return (
    <div className="animate-rise mb-5 flex flex-col gap-3 rounded-2xl border border-herb/25 bg-herb-soft px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
      <p className="flex items-center gap-2.5 text-sm text-ink">
        <Leaf className="h-4 w-4 shrink-0 text-herb" aria-hidden="true" />
        <span>
          Apply your food preferences? <span className="text-ink-muted">{summary}</span>
        </span>
      </p>
      <button
        type="button"
        onClick={() =>
          onApply({
            ...filters,
            dietaryTags: [...filters.dietaryTags, ...diets],
            excludeAllergens: ALLERGENS.filter(
              (a) => filters.excludeAllergens.includes(a) || allergens.includes(a),
            ),
          })
        }
        className="h-9 shrink-0 rounded-full bg-herb px-4 text-sm font-semibold text-surface hover:opacity-90"
      >
        Apply
      </button>
    </div>
  );
}
