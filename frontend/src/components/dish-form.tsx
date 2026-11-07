"use client";

import { useState } from "react";

import { ErrorBanner, Field, inputClass, primaryButtonClass, ghostButtonClass } from "@/components/ui";
import type { Dish, DishInput } from "@/lib/api";
import { ALLERGENS } from "@/lib/allergens";
import { parsePriceToMinorUnits, splitList } from "@/lib/format";

/**
 * Create/edit form for dishes. Holds its own raw strings; converts to the
 * API payload (minor-unit price, trimmed lists, allergen subset) on submit.
 * Server 422 details are rendered through `errors` owned by the parent.
 */
export default function DishForm({
  dish,
  submitLabel,
  busy = false,
  errors,
  onSubmit,
  onCancel,
}: {
  dish?: Dish | null;
  submitLabel: string;
  busy?: boolean;
  errors: string[];
  onSubmit: (values: DishInput) => Promise<void>;
  onCancel?: () => void;
}) {
  const [name, setName] = useState(dish?.name ?? "");
  const [description, setDescription] = useState(dish?.description ?? "");
  const [price, setPrice] = useState(dish ? String(dish.price / 100) : "");
  const [portions, setPortions] = useState(dish ? String(dish.portions) : "");
  const [ingredients, setIngredients] = useState((dish?.ingredients ?? []).join(", "));
  const [tags, setTags] = useState((dish?.dietary_tags ?? []).join(", "));
  const [allergens, setAllergens] = useState<string[]>(dish?.allergens ?? []);
  const [localError, setLocalError] = useState<string | null>(null);

  const toggleAllergen = (allergen: string) => {
    setAllergens((current) =>
      current.includes(allergen)
        ? current.filter((held) => held !== allergen)
        : [...current, allergen],
    );
  };

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setLocalError(null);
    let priceMinor: number;
    let portionsCount: number;
    try {
      priceMinor = parsePriceToMinorUnits(price);
      portionsCount = Number(portions.trim());
      if (!Number.isInteger(portionsCount) || portionsCount < 1) {
        throw new Error("portions must be a whole number of 1 or more");
      }
    } catch (cause) {
      setLocalError(cause instanceof Error ? cause.message : "invalid numbers");
      return;
    }
    await onSubmit({
      name: name.trim(),
      description: description.trim() || null,
      price: priceMinor,
      portions: portionsCount,
      ingredients: splitList(ingredients),
      allergens,
      dietary_tags: splitList(tags),
    });
    // Successful submit: reset the transient fields for "create" forms only.
    if (!dish) {
      setPrice("");
      setPortions("");
      setDescription("");
      setIngredients("");
      setTags("");
      setAllergens([]);
    }
  };

  const shown = localError ? [...errors, localError] : errors;

  return (
    <form onSubmit={submit} className="space-y-4">
      <ErrorBanner lines={shown} />
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Name">
          <input
            value={name}
            onChange={(event) => setName(event.target.value)}
            placeholder="Hyderabadi chicken biryani"
            required
            className={inputClass}
          />
        </Field>
        <Field label="Portions offered" hint="Whole number, 1 or more.">
          <input
            value={portions}
            onChange={(event) => setPortions(event.target.value)}
            inputMode="numeric"
            placeholder="12"
            required
            className={inputClass}
          />
        </Field>
      </div>
      <Field label="Description" hint="Optional - what makes this dish yours.">
        <textarea
          value={description}
          onChange={(event) => setDescription(event.target.value)}
          rows={2}
          className={inputClass}
        />
      </Field>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Price" hint="Entered in major units; stored as integer minor units (8.90 -> 890).">
          <input
            value={price}
            onChange={(event) => setPrice(event.target.value)}
            inputMode="decimal"
            placeholder="8.90"
            required
            className={inputClass}
          />
        </Field>
        <Field label="Ingredients" hint="Comma separated.">
          <input
            value={ingredients}
            onChange={(event) => setIngredients(event.target.value)}
            placeholder="basmati rice, chicken, yogurt"
            className={inputClass}
          />
        </Field>
      </div>
      <Field label="Dietary tags" hint="Comma separated, e.g. vegan, gluten free.">
        <input
          value={tags}
          onChange={(event) => setTags(event.target.value)}
          placeholder="halal, spicy"
          className={inputClass}
        />
      </Field>
      <fieldset>
        <legend className="mb-2 text-sm font-medium text-zinc-700 dark:text-zinc-300">
          Allergens (fixed vocabulary - only these are accepted)
        </legend>
        <div className="flex flex-wrap gap-x-4 gap-y-2">
          {ALLERGENS.map((allergen) => (
            <label key={allergen} className="flex items-center gap-1.5 text-sm text-zinc-600 dark:text-zinc-400">
              <input
                type="checkbox"
                checked={allergens.includes(allergen)}
                onChange={() => toggleAllergen(allergen)}
                className="h-4 w-4 rounded border-zinc-300 accent-emerald-600"
              />
              {allergen}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="flex gap-2">
        <button type="submit" disabled={busy} className={primaryButtonClass}>
          {busy ? "Saving..." : submitLabel}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className={ghostButtonClass}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
