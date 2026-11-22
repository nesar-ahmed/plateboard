"use client";

import { Check } from "lucide-react";
import { useState } from "react";

import {
  ErrorBanner,
  Field,
  Select,
  cx,
  darkButtonClass,
  inputClass,
  quietButtonClass,
} from "@/components/ui";
import type { Zone } from "@/lib/api";
import { ALLERGENS, type Allergen } from "@/lib/allergens";
import { normalizeTags, type DishFilters } from "@/lib/dish-filters";
import { minorUnitsToInput, parseOptionalPriceToMinorUnits, splitList } from "@/lib/format";
import { maxZoneSpan } from "@/lib/use-zones";

const SAME_ZONE = "";

/** Tags offered as one-tap chips; anything else goes in "Other tags". */
export const COMMON_TAGS = ["vegetarian", "vegan", "gluten free", "halal", "spicy", "sweet"];

/**
 * The filter form (zone + distance, price range, dietary tags, excluded
 * allergens) - used in the desktop sidebar and the mobile sheet.
 *
 * Holds *draft* values only; nothing reaches the URL (and so the API) until
 * "Show results", which keeps the back button meaningful. The parent
 * remounts it (`key`) whenever the applied filters change from outside - a
 * removed chip, back/forward - so the draft always starts from what is
 * applied. The text search lives in the page's search bar, not here.
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
  const [zone, setZone] = useState(value.zone);
  const [distance, setDistance] = useState(value.maxDistance === null ? SAME_ZONE : String(value.maxDistance));
  const [minPrice, setMinPrice] = useState(minorUnitsToInput(value.minPrice));
  const [maxPrice, setMaxPrice] = useState(minorUnitsToInput(value.maxPrice));
  const [tags, setTags] = useState<string[]>(value.dietaryTags.filter((tag) => COMMON_TAGS.includes(tag)));
  const [otherTags, setOtherTags] = useState(
    value.dietaryTags.filter((tag) => !COMMON_TAGS.includes(tag)).join(", "),
  );
  const [excluded, setExcluded] = useState<Allergen[]>(value.excludeAllergens);
  const [error, setError] = useState<string | null>(null);

  const span = zones ? maxZoneSpan(zones) : 0;

  const toggle = <T,>(list: T[], item: T) =>
    list.includes(item) ? list.filter((held) => held !== item) : [...list, item];

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
      setError("The minimum price must not be above the maximum price.");
      return;
    }
    setError(null);
    onApply({
      q: value.q, // the search bar owns the text query
      zone,
      maxDistance: zone && distance !== SAME_ZONE ? Number(distance) : null,
      minPrice: low,
      maxPrice: high,
      dietaryTags: normalizeTags([...tags, ...splitList(otherTags)]),
      // Keep the canonical enum order so URLs are stable.
      excludeAllergens: ALLERGENS.filter((allergen) => excluded.includes(allergen)),
    });
  };

  return (
    <form onSubmit={submit} aria-label="Filter dishes" className="space-y-7">
      <ErrorBanner lines={[...(error ? [error] : []), ...(zonesError ? [`Zones: ${zonesError}`] : [])]} />

      <FilterGroup title="Location">
        <div className="space-y-3">
          <Field label="Neighbourhood">
            <Select value={zone} onChange={(event) => setZone(event.target.value)} disabled={!zones}>
              <option value="">Anywhere</option>
              {(zones ?? []).map((option) => (
                <option key={option.slug} value={option.slug}>
                  {option.name}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Distance" hint="In grid steps between neighbourhoods.">
            <Select value={distance} onChange={(event) => setDistance(event.target.value)} disabled={!zone}>
              <option value={SAME_ZONE}>Same neighbourhood</option>
              {Array.from({ length: span }, (_, index) => index + 1).map((steps) => (
                <option key={steps} value={String(steps)}>
                  Within {steps} {steps === 1 ? "step" : "steps"}
                </option>
              ))}
            </Select>
          </Field>
        </div>
      </FilterGroup>

      <FilterGroup title="Price per portion">
        <div className="grid grid-cols-2 gap-2">
          <input
            value={minPrice}
            onChange={(event) => setMinPrice(event.target.value)}
            inputMode="decimal"
            placeholder="Min"
            aria-label="Minimum price"
            className={inputClass}
          />
          <input
            value={maxPrice}
            onChange={(event) => setMaxPrice(event.target.value)}
            inputMode="decimal"
            placeholder="Max"
            aria-label="Maximum price"
            className={inputClass}
          />
        </div>
      </FilterGroup>

      <FilterGroup title="Diet" hint="Dishes must match every tag you pick.">
        <div className="flex flex-wrap gap-2">
          {COMMON_TAGS.map((tag) => (
            <Chip key={tag} active={tags.includes(tag)} onClick={() => setTags((held) => toggle(held, tag))}>
              {tag}
            </Chip>
          ))}
        </div>
        <input
          value={otherTags}
          onChange={(event) => setOtherTags(event.target.value)}
          placeholder="Other tags, comma separated"
          aria-label="Other dietary tags"
          className={cx(inputClass, "mt-3")}
        />
      </FilterGroup>

      <FilterGroup title="Leave out allergens" hint="Hides dishes that declare any of these.">
        <div className="flex flex-wrap gap-2">
          {ALLERGENS.map((allergen) => (
            <Chip
              key={allergen}
              tone="saffron"
              active={excluded.includes(allergen)}
              onClick={() => setExcluded((held) => toggle(held, allergen))}
            >
              {allergen}
            </Chip>
          ))}
        </div>
      </FilterGroup>

      {/* Sticky: "Show results" stays in reach in the sheet and the sidebar. */}
      <div className="sticky bottom-0 -mx-5 flex gap-2 border-t border-line bg-surface px-5 py-4">
        <button type="submit" className={cx(darkButtonClass, "flex-1")}>
          Show results
        </button>
        <button type="button" onClick={onClear} className={quietButtonClass}>
          Clear all
        </button>
      </div>
    </form>
  );
}

function FilterGroup({ title, hint, children }: { title: string; hint?: string; children: React.ReactNode }) {
  return (
    <fieldset>
      <legend className="text-sm font-semibold text-ink">{title}</legend>
      {hint && <p className="mt-0.5 text-xs text-ink-soft">{hint}</p>}
      <div className="mt-3">{children}</div>
    </fieldset>
  );
}

function Chip({
  active,
  tone = "herb",
  onClick,
  children,
}: {
  active: boolean;
  tone?: "herb" | "saffron";
  onClick: () => void;
  children: React.ReactNode;
}) {
  const on = tone === "herb" ? "border-herb bg-herb-soft text-herb" : "border-saffron bg-saffron-soft text-saffron";
  return (
    <button
      type="button"
      aria-pressed={active}
      onClick={onClick}
      className={cx(
        "inline-flex h-8 items-center gap-1 rounded-full border px-3 text-[13px] font-medium capitalize transition-colors",
        active ? on : "border-line-strong bg-surface text-ink-muted hover:border-ink-soft hover:text-ink",
      )}
    >
      {active && <Check className="h-3.5 w-3.5" aria-hidden="true" />}
      {children}
    </button>
  );
}
