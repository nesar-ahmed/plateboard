"use client";

import { useState } from "react";

import { ErrorBanner, Field, ghostButtonClass, inputClass, primaryButtonClass } from "@/components/ui";
import type { Zone } from "@/lib/api";
import { ALLERGENS, type Allergen } from "@/lib/allergens";
import { countActiveFilters, normalizeTags, type DishFilters } from "@/lib/dish-filters";
import { minorUnitsToInput, parseOptionalPriceToMinorUnits, splitList } from "@/lib/format";
import { maxZoneSpan } from "@/lib/use-zones";

const SAME_ZONE = "";

/**
 * Search box + collapsible filter panel for the public menu.
 *
 * Holds *draft* values only; nothing reaches the URL (and so the API) until
 * the form is submitted, which keeps typing cheap and the back button
 * meaningful. The parent remounts this component (`key`) whenever the applied
 * filters change from outside - a removed chip, back/forward - so the draft
 * always starts from what is applied.
 */
export default function DishFiltersPanel({
  value,
  zones,
  zonesError,
  onApply,
  onClear,
}: {
  value: DishFilters;
  zones: Zone[] | null;
  zonesError: string | null;
  onApply: (filters: DishFilters) => void;
  onClear: () => void;
}) {
  const activeCount = countActiveFilters(value);
  const [open, setOpen] = useState(activeCount > 0);
  const [q, setQ] = useState(value.q);
  const [zone, setZone] = useState(value.zone);
  const [distance, setDistance] = useState(value.maxDistance === null ? SAME_ZONE : String(value.maxDistance));
  const [minPrice, setMinPrice] = useState(minorUnitsToInput(value.minPrice));
  const [maxPrice, setMaxPrice] = useState(minorUnitsToInput(value.maxPrice));
  const [tags, setTags] = useState(value.dietaryTags.join(", "));
  const [excluded, setExcluded] = useState<Allergen[]>(value.excludeAllergens);
  const [error, setError] = useState<string | null>(null);

  const span = zones ? maxZoneSpan(zones) : 0;

  const toggleAllergen = (allergen: Allergen) =>
    setExcluded((current) =>
      current.includes(allergen) ? current.filter((held) => held !== allergen) : [...current, allergen],
    );

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    let low: number | null;
    let high: number | null;
    try {
      low = parseOptionalPriceToMinorUnits(minPrice);
      high = parseOptionalPriceToMinorUnits(maxPrice);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : "invalid price");
      return;
    }
    if (low !== null && high !== null && low > high) {
      setError("the minimum price must not be above the maximum price");
      return;
    }
    setError(null);
    onApply({
      q: q.trim(),
      zone,
      maxDistance: zone && distance !== SAME_ZONE ? Number(distance) : null,
      minPrice: low,
      maxPrice: high,
      dietaryTags: normalizeTags(splitList(tags)),
      // Keep the canonical enum order so URLs are stable.
      excludeAllergens: ALLERGENS.filter((allergen) => excluded.includes(allergen)),
    });
  };

  return (
    <form onSubmit={submit} className="space-y-3" aria-label="Search and filter dishes">
      <div className="flex flex-wrap gap-2">
        <input
          value={q}
          onChange={(event) => setQ(event.target.value)}
          placeholder="Search dishes, descriptions, ingredients - e.g. smoky rice"
          aria-label="Search dishes"
          maxLength={120}
          className={`${inputClass} max-w-md flex-1`}
        />
        <button type="submit" className={primaryButtonClass}>
          Search
        </button>
        <button
          type="button"
          onClick={() => setOpen((shown) => !shown)}
          aria-expanded={open}
          aria-controls="dish-filters"
          className={ghostButtonClass}
        >
          Filters{activeCount > 0 ? ` (${activeCount})` : ""}
        </button>
      </div>

      {open && (
        <div
          id="dish-filters"
          className="space-y-4 rounded-2xl border border-zinc-200 bg-white p-5 dark:border-zinc-800 dark:bg-zinc-950"
        >
          <ErrorBanner lines={[...(error ? [error] : []), ...(zonesError ? [`zones: ${zonesError}`] : [])]} />
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            <Field label="Zone" hint="Where the cook's kitchen is.">
              <select
                value={zone}
                onChange={(event) => setZone(event.target.value)}
                disabled={!zones}
                className={inputClass}
              >
                <option value="">Any zone</option>
                {(zones ?? []).map((option) => (
                  <option key={option.slug} value={option.slug}>
                    {option.name}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Distance" hint="Grid steps between zones.">
              <select
                value={distance}
                onChange={(event) => setDistance(event.target.value)}
                disabled={!zone}
                className={inputClass}
              >
                <option value={SAME_ZONE}>Same zone only</option>
                {Array.from({ length: span }, (_, index) => index + 1).map((steps) => (
                  <option key={steps} value={String(steps)}>
                    Within {steps} {steps === 1 ? "step" : "steps"}
                  </option>
                ))}
              </select>
            </Field>
            <Field label="Min price">
              <input
                value={minPrice}
                onChange={(event) => setMinPrice(event.target.value)}
                inputMode="decimal"
                placeholder="0.00"
                className={inputClass}
              />
            </Field>
            <Field label="Max price">
              <input
                value={maxPrice}
                onChange={(event) => setMaxPrice(event.target.value)}
                inputMode="decimal"
                placeholder="any"
                className={inputClass}
              />
            </Field>
          </div>
          <Field label="Dietary tags" hint="Comma separated; dishes must have all of them, e.g. vegan, gluten free.">
            <input
              value={tags}
              onChange={(event) => setTags(event.target.value)}
              placeholder="vegan, halal"
              className={inputClass}
            />
          </Field>
          <fieldset>
            <legend className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
              Exclude allergens
            </legend>
            <div className="grid grid-cols-2 gap-2 sm:grid-cols-4 lg:grid-cols-7">
              {ALLERGENS.map((allergen) => (
                <label key={allergen} className="flex items-center gap-2 text-sm text-zinc-700 dark:text-zinc-300">
                  <input
                    type="checkbox"
                    checked={excluded.includes(allergen)}
                    onChange={() => toggleAllergen(allergen)}
                    className="h-4 w-4 rounded border-zinc-300 accent-emerald-600"
                  />
                  {allergen}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="flex gap-2">
            <button type="submit" className={primaryButtonClass}>
              Apply filters
            </button>
            <button type="button" onClick={onClear} className={ghostButtonClass}>
              Clear all
            </button>
          </div>
        </div>
      )}
    </form>
  );
}
