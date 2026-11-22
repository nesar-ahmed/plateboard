"use client";

import { Check, Eye, EyeOff, Leaf, ShieldAlert, UtensilsCrossed } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import DishCard from "@/components/dish-card";
import {
  ErrorBanner,
  Field,
  Spinner,
  cx,
  darkButtonClass,
  inputClass,
  primaryButtonClass,
  quietButtonClass,
  textareaClass,
} from "@/components/ui";
import { ApiError, type Dish, type DishInput, type Zone } from "@/lib/api";
import { ALLERGENS } from "@/lib/allergens";
import { normalizeTags } from "@/lib/dish-filters";
import { minorUnitsToInput, parsePriceToMinorUnits, splitList } from "@/lib/format";

/** Tags offered as one tap; anything else goes in the free-text field. */
const SUGGESTED_TAGS = ["vegetarian", "vegan", "gluten free", "halal", "dairy free", "spicy", "mild"];

const NAME_MAX = 120;
const DESCRIPTION_MAX = 1000;
const PORTIONS_MAX = 999;

type Props = {
  /** Edit this dish; without it the form creates one. */
  dish?: Dish;
  /** Shown in the live preview. */
  cookName: string | null;
  zone: Zone | null;
  /** Save (POST or PATCH); throw the ApiError to have it shown on the fields. */
  onSubmit: (values: DishInput) => Promise<void>;
  cancelHref: string;
};

/**
 * Create/edit a dish: basics, price + portions, ingredients + diet tags,
 * allergens (the fixed vocabulary) and visibility (public/private), with a
 * live preview of the menu card. Prices are typed in major units and sent
 * as minor units; server 422s land on the field they name.
 */
export default function DishForm({ dish, cookName, zone, onSubmit, cancelHref }: Props) {
  const [name, setName] = useState(dish?.name ?? "");
  const [description, setDescription] = useState(dish?.description ?? "");
  const [price, setPrice] = useState(dish ? minorUnitsToInput(dish.price) : "");
  const [portions, setPortions] = useState(dish ? String(dish.portions) : "");
  const [ingredients, setIngredients] = useState((dish?.ingredients ?? []).join(", "));
  const [tags, setTags] = useState<string[]>((dish?.dietary_tags ?? []).filter((tag) => SUGGESTED_TAGS.includes(tag)));
  const [otherTags, setOtherTags] = useState(
    (dish?.dietary_tags ?? []).filter((tag) => !SUGGESTED_TAGS.includes(tag)).join(", "),
  );
  const [allergens, setAllergens] = useState<string[]>(dish?.allergens ?? []);
  const [active, setActive] = useState(dish?.active ?? true);
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<string[]>([]);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const toggle = (list: string[], item: string) =>
    list.includes(item) ? list.filter((held) => held !== item) : [...list, item];
  const allTags = normalizeTags([...tags, ...splitList(otherTags)]);
  const previewPrice = (() => {
    try {
      return parsePriceToMinorUnits(price);
    } catch {
      return 0;
    }
  })();

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBanner([]);
    const local: Record<string, string> = {};
    let priceMinor = 0;
    try {
      priceMinor = parsePriceToMinorUnits(price);
    } catch (cause) {
      local.price = cause instanceof Error ? cause.message : "enter a price";
    }
    const portionsCount = Number(portions.trim());
    if (!Number.isInteger(portionsCount) || portionsCount < 1 || portionsCount > PORTIONS_MAX) {
      local.portions = `a whole number from 1 to ${PORTIONS_MAX}`;
    }
    setFieldErrors(local);
    if (Object.keys(local).length > 0) {
      setBanner(["Please check the highlighted fields."]);
      return;
    }
    setBusy(true);
    try {
      await onSubmit({
        name: name.trim(),
        description: description.trim() || null,
        price: priceMinor,
        portions: portionsCount,
        ingredients: splitList(ingredients).map((item) => item.toLowerCase()),
        allergens: ALLERGENS.filter((allergen) => allergens.includes(allergen)),
        dietary_tags: allTags,
        active,
      });
    } catch (cause) {
      if (cause instanceof ApiError && cause.fieldErrors.length > 0) {
        setFieldErrors(
          Object.fromEntries(cause.fieldErrors.map((error) => [error.field.split(".")[0], error.message])),
        );
        setBanner(["Please check the highlighted fields."]);
      } else {
        setBanner(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
      }
      setBusy(false);
    }
  };

  const invalid = (key: string) => ({
    "aria-invalid": fieldErrors[key] ? true : undefined,
    className: cx(inputClass, fieldErrors[key] && "border-danger"),
  });

  const preview: Dish = {
    id: dish?.id ?? "preview",
    cook_id: dish?.cook_id ?? "preview",
    name: name.trim() || "Your dish",
    description: description.trim() || null,
    price: previewPrice,
    portions: Number(portions) || 0,
    ingredients: splitList(ingredients),
    allergens: ALLERGENS.filter((allergen) => allergens.includes(allergen)),
    dietary_tags: allTags,
    active,
    created_at: dish?.created_at ?? "",
    updated_at: dish?.updated_at ?? "",
    cook_name: cookName,
    zone,
  };

  const submitLabel = dish ? "Save changes" : active ? "Publish dish" : "Save private draft";
  return (
    <form onSubmit={submit} aria-label={dish ? "Edit dish" : "New dish"} className="space-y-6">
      <ErrorBanner lines={banner} />
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-6">
          <section className="space-y-5 rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
            <h2 className="flex items-center gap-2 font-display text-xl font-semibold text-ink">
              <UtensilsCrossed className="h-5 w-5 text-brand" aria-hidden="true" /> The dish
            </h2>
            <Field label="Name" error={fieldErrors.name}>
              <input
                value={name}
                onChange={(event) => setName(event.target.value)}
                placeholder="Hyderabadi chicken biryani"
                required
                maxLength={NAME_MAX}
                {...invalid("name")}
              />
            </Field>
            <Field
              label="Description"
              optional
              hint={`What makes it yours - ${description.length}/${DESCRIPTION_MAX}`}
              error={fieldErrors.description}
            >
              <textarea
                value={description}
                onChange={(event) => setDescription(event.target.value)}
                maxLength={DESCRIPTION_MAX}
                rows={3}
                placeholder="Dum-cooked basmati with saffron and yoghurt-marinated chicken."
                className={cx(textareaClass, fieldErrors.description && "border-danger")}
              />
            </Field>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
              <Field label="Price per portion" hint="e.g. 8.90" error={fieldErrors.price}>
                <input
                  value={price}
                  onChange={(event) => setPrice(event.target.value)}
                  inputMode="decimal"
                  placeholder="8.90"
                  required
                  {...invalid("price")}
                />
              </Field>
              <Field label="Portions you can make" hint="Per batch, 1 to 999." error={fieldErrors.portions}>
                <input
                  value={portions}
                  onChange={(event) => setPortions(event.target.value)}
                  inputMode="numeric"
                  placeholder="12"
                  required
                  {...invalid("portions")}
                />
              </Field>
            </div>
            <Field
              label="Ingredients"
              optional
              hint="Comma separated - customers can search by them."
              error={fieldErrors.ingredients}
            >
              <input
                value={ingredients}
                onChange={(event) => setIngredients(event.target.value)}
                placeholder="basmati rice, chicken, yoghurt, saffron"
                {...invalid("ingredients")}
              />
            </Field>
          </section>

          <section className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
            <h2 className="flex items-center gap-2 font-display text-xl font-semibold text-ink">
              <Leaf className="h-5 w-5 text-herb" aria-hidden="true" /> Diet & style
            </h2>
            <p className="mt-1 text-sm text-ink-muted">Customers filter the menu by these tags.</p>
            <div className="mt-4 flex flex-wrap gap-2">
              {SUGGESTED_TAGS.map((tag) => {
                const on = tags.includes(tag);
                return (
                  <button
                    key={tag}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setTags((held) => toggle(held, tag))}
                    className={cx(
                      "inline-flex h-10 items-center gap-1.5 rounded-full border px-4 text-sm font-medium capitalize transition-colors",
                      on ? "border-herb bg-herb-soft text-herb" : "border-line-strong text-ink-muted hover:text-ink",
                    )}
                  >
                    {on && <Check className="h-4 w-4" aria-hidden="true" />} {tag}
                  </button>
                );
              })}
            </div>
            <input
              value={otherTags}
              onChange={(event) => setOtherTags(event.target.value)}
              placeholder="Other tags, e.g. winter special, kids' favourite"
              aria-label="Other tags, comma separated"
              className={cx(inputClass, "mt-4", fieldErrors.dietary_tags && "border-danger")}
            />
            {fieldErrors.dietary_tags && (
              <p className="mt-1.5 text-xs font-medium text-danger">{fieldErrors.dietary_tags}</p>
            )}
          </section>

          <section className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
            <h2 className="flex items-center gap-2 font-display text-xl font-semibold text-ink">
              <ShieldAlert className="h-5 w-5 text-saffron" aria-hidden="true" /> Allergens
            </h2>
            <p className="mt-1 text-sm text-ink-muted">
              Declare every allergen the dish contains - customers with allergies rely on it.
            </p>
            <div className="mt-4 grid grid-cols-2 gap-2 sm:grid-cols-3 2xl:grid-cols-4">
              {ALLERGENS.map((allergen) => {
                const on = allergens.includes(allergen);
                return (
                  <button
                    key={allergen}
                    type="button"
                    aria-pressed={on}
                    onClick={() => setAllergens((held) => toggle(held, allergen))}
                    className={cx(
                      "flex h-11 items-center justify-between rounded-2xl border px-3.5 text-sm font-medium capitalize transition-colors",
                      on
                        ? "border-saffron bg-saffron-soft text-saffron"
                        : "border-line-strong text-ink-muted hover:border-ink-soft hover:text-ink",
                    )}
                  >
                    {allergen}
                    <span
                      className={cx(
                        "flex h-5 w-5 items-center justify-center rounded-full border",
                        on ? "border-saffron bg-saffron text-surface" : "border-line-strong",
                      )}
                    >
                      {on && <Check className="h-3 w-3" strokeWidth={3} aria-hidden="true" />}
                    </span>
                  </button>
                );
              })}
            </div>
            {allergens.length === 0 && (
              <p className="mt-3 text-xs text-herb">No allergens selected - the menu will say “No declared allergens”.</p>
            )}
          </section>

          <section className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
            <h2 className="font-display text-xl font-semibold text-ink">Visibility</h2>
            <div role="radiogroup" aria-label="Visibility" className="mt-4 grid grid-cols-1 gap-3 sm:grid-cols-2">
              {[
                { value: true, icon: Eye, title: "Public", text: "On the menu - neighbours can find and order it." },
                { value: false, icon: EyeOff, title: "Private", text: "Only you see it. Publish whenever you're ready." },
              ].map((option) => {
                const on = active === option.value;
                return (
                  <button
                    key={option.title}
                    type="button"
                    role="radio"
                    aria-checked={on}
                    onClick={() => setActive(option.value)}
                    className={cx(
                      "flex items-start gap-3 rounded-2xl border p-4 text-left transition-colors",
                      on ? "border-ink bg-muted" : "border-line-strong hover:border-ink-soft",
                    )}
                  >
                    <span
                      className={cx(
                        "flex h-9 w-9 shrink-0 items-center justify-center rounded-xl",
                        on ? "bg-ink text-canvas" : "bg-muted text-ink-muted",
                      )}
                    >
                      <option.icon className="h-4 w-4" aria-hidden="true" />
                    </span>
                    <span>
                      <span className="block text-sm font-semibold text-ink">{option.title}</span>
                      <span className="block text-xs leading-relaxed text-ink-muted">{option.text}</span>
                    </span>
                  </button>
                );
              })}
            </div>
          </section>
        </div>

        <aside aria-label="Preview" className="min-w-0">
          <div className="space-y-3 xl:sticky xl:top-24">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">
              {active ? "How customers will see it" : "Preview - hidden from the menu"}
            </p>
            <div className={cx("mx-auto max-w-sm transition-opacity", !active && "opacity-60")}>
              <DishCard dish={preview} preview />
            </div>
          </div>
        </aside>
      </div>

      <div className="sticky bottom-4 z-10 flex flex-col gap-3 rounded-3xl border border-line bg-surface/95 p-4 shadow-lift backdrop-blur sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p className="flex items-center gap-2 text-sm text-ink-muted">
          {active ? <Eye className="h-4 w-4 text-herb" aria-hidden="true" /> : <EyeOff className="h-4 w-4" aria-hidden="true" />}
          {active ? "Public - listed on the menu" : "Private - only you can see it"}
        </p>
        <div className="flex gap-2">
          <Link href={cancelHref} className={quietButtonClass}>
            Cancel
          </Link>
          <button type="submit" disabled={busy} className={active && !dish ? primaryButtonClass : darkButtonClass}>
            {busy && <Spinner />} {submitLabel}
          </button>
        </div>
      </div>
    </form>
  );
}
