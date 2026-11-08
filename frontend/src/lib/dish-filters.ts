/**
 * Public-menu filter state <-> URL query string.
 *
 * The page URL is the single source of truth for the dish list: filters are
 * shareable, bookmarkable and survive reloads / the back button. The URL uses
 * exactly the parameter names of `GET /api/dishes` (prices in minor units),
 * so the same string is forwarded to the API - no second mapping to drift.
 *
 * Pure functions only (no React), so they are trivially unit-testable.
 */

import { ALLERGENS, type Allergen } from "@/lib/allergens";

export type DishFilters = {
  /** Text search: every word must appear in name, description or ingredients. */
  q: string;
  /** Origin zone slug; "" = any zone. */
  zone: string;
  /** Grid steps from `zone`; null = same zone only. Ignored without a zone. */
  maxDistance: number | null;
  /** Inclusive bounds in minor units. */
  minPrice: number | null;
  maxPrice: number | null;
  /** The dish must carry every tag (lowercase). */
  dietaryTags: string[];
  /** Dishes declaring any of these are hidden. */
  excludeAllergens: Allergen[];
};

export const EMPTY_FILTERS: DishFilters = {
  q: "",
  zone: "",
  maxDistance: null,
  minPrice: null,
  maxPrice: null,
  dietaryTags: [],
  excludeAllergens: [],
};

const ALLERGEN_SET: ReadonlySet<string> = new Set(ALLERGENS);

/** A non-negative integer from the URL, or null for anything else. */
function wholeNumber(raw: string | null): number | null {
  if (raw === null || raw.trim() === "") return null;
  const value = Number(raw);
  return Number.isInteger(value) && value >= 0 ? value : null;
}

/** Trim, lowercase, drop blanks and duplicates - same rules as the API. */
export function normalizeTags(tags: string[]): string[] {
  return [...new Set(tags.map((tag) => tag.trim().toLowerCase()).filter(Boolean))];
}

/** Read filters from a URL. Malformed values are dropped, never thrown. */
export function parseDishFilters(params: URLSearchParams): DishFilters {
  const zone = (params.get("zone") ?? "").trim().toLowerCase();
  return {
    q: (params.get("q") ?? "").trim(),
    zone,
    maxDistance: zone ? wholeNumber(params.get("max_distance")) : null,
    minPrice: wholeNumber(params.get("min_price")),
    maxPrice: wholeNumber(params.get("max_price")),
    dietaryTags: normalizeTags(params.getAll("dietary_tag")),
    excludeAllergens: [
      ...new Set(
        params.getAll("exclude_allergen").filter((a): a is Allergen => ALLERGEN_SET.has(a)),
      ),
    ],
  };
}

/** The page offset from the URL (0 when absent or malformed). */
export function parseOffset(params: URLSearchParams): number {
  return wholeNumber(params.get("offset")) ?? 0;
}

/**
 * Filters (+ optional offset) -> query string in the API's vocabulary. Only
 * set values are written, so an unfiltered first page is just "".
 */
export function dishFiltersToParams(filters: DishFilters, offset = 0): URLSearchParams {
  const params = new URLSearchParams();
  if (filters.q.trim()) params.set("q", filters.q.trim());
  if (filters.zone) {
    params.set("zone", filters.zone);
    if (filters.maxDistance !== null) params.set("max_distance", String(filters.maxDistance));
  }
  if (filters.minPrice !== null) params.set("min_price", String(filters.minPrice));
  if (filters.maxPrice !== null) params.set("max_price", String(filters.maxPrice));
  for (const tag of normalizeTags(filters.dietaryTags)) params.append("dietary_tag", tag);
  for (const allergen of filters.excludeAllergens) params.append("exclude_allergen", allergen);
  if (offset > 0) params.set("offset", String(offset));
  return params;
}

/** Number of active filters, text search excluded (for the "Filters (n)" badge). */
export function countActiveFilters(filters: DishFilters): number {
  return (
    (filters.zone ? 1 : 0) +
    (filters.minPrice !== null || filters.maxPrice !== null ? 1 : 0) +
    filters.dietaryTags.length +
    filters.excludeAllergens.length
  );
}

/** A Next.js `searchParams` object -> URLSearchParams (repeated keys kept). */
export function toSearchParams(
  record: Record<string, string | string[] | undefined>,
): URLSearchParams {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(record)) {
    for (const item of Array.isArray(value) ? value : value === undefined ? [] : [value]) {
      params.append(key, item);
    }
  }
  return params;
}
