"use client";

import { Check, Info, Leaf, ShieldAlert } from "lucide-react";
import { useEffect, useState } from "react";

import { ErrorBanner, PageHeader, Spinner, cx, darkButtonClass, inputClass } from "@/components/ui";
import { api, ApiError, type DishPage, type Preferences } from "@/lib/api";
import { ALLERGENS } from "@/lib/allergens";
import { normalizeTags } from "@/lib/dish-filters";
import { splitList } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const COMMON_DIETS = ["vegetarian", "vegan", "gluten free", "halal", "dairy free", "low carb"];

/**
 * /account/preferences - the food profile (GET/PUT /api/me/preferences).
 * Nothing is hidden from the menu behind the user's back: the dish list
 * offers "apply my preferences" as one tap. The preview counts today's
 * matching dishes with the same filters the menu would use.
 */
export default function PreferencesPage() {
  const { data, error } = useApi<Preferences>("/me/preferences");
  if (error) return <ErrorBanner lines={[error]} />;
  if (!data) {
    return (
      <div className="flex justify-center py-16 text-ink-muted">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  return <PreferencesForm initial={data} />;
}

function PreferencesForm({ initial }: { initial: Preferences }) {
  const [allergens, setAllergens] = useState<string[]>(initial.excluded_allergens);
  const [diets, setDiets] = useState<string[]>(initial.dietary_preferences.filter((d) => COMMON_DIETS.includes(d)));
  const [otherDiets, setOtherDiets] = useState(
    initial.dietary_preferences.filter((d) => !COMMON_DIETS.includes(d)).join(", "),
  );
  const [saved, setSaved] = useState<Preferences>(initial);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [preview, setPreview] = useState<{ fit: number; all: number } | null>(null);

  const allDiets = normalizeTags([...diets, ...splitList(otherDiets)]);
  const orderedAllergens = ALLERGENS.filter((a) => allergens.includes(a));
  const dirty =
    JSON.stringify(orderedAllergens) !== JSON.stringify(ALLERGENS.filter((a) => saved.excluded_allergens.includes(a))) ||
    JSON.stringify(allDiets) !== JSON.stringify(saved.dietary_preferences);

  // Live preview (debounced): how much of today's menu fits this profile.
  const previewKey = JSON.stringify([orderedAllergens, allDiets]);
  useEffect(() => {
    const timer = window.setTimeout(async () => {
      const query = new URLSearchParams({ limit: "1" });
      orderedAllergens.forEach((a) => query.append("exclude_allergen", a));
      allDiets.forEach((d) => query.append("dietary_tag", d));
      try {
        const [fit, all] = await Promise.all([
          api.get<DishPage>(`/dishes?${query.toString()}`),
          api.get<DishPage>("/dishes?limit=1"),
        ]);
        setPreview({ fit: fit.total, all: all.total });
      } catch {
        setPreview(null);
      }
    }, 300);
    return () => window.clearTimeout(timer);
    // previewKey captures both lists by value
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewKey]);

  const toggle = (list: string[], item: string) =>
    list.includes(item) ? list.filter((held) => held !== item) : [...list, item];

  const save = async () => {
    setBusy(true);
    setErrors([]);
    try {
      setSaved(
        await api.put<Preferences>("/me/preferences", {
          excluded_allergens: orderedAllergens,
          dietary_preferences: allDiets,
        }),
      );
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        size="compact"
        title="Food preferences"
        lead="Tell us what you avoid and how you eat. When you browse, one tap applies it to the menu."
      />

      <ErrorBanner lines={errors} />

      <section className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
        <h2 className="flex items-center gap-2 font-display text-xl font-semibold text-ink">
          <ShieldAlert className="h-5 w-5 text-saffron" aria-hidden="true" /> Allergens to avoid
        </h2>
        <p className="mt-1 text-sm text-ink-muted">
          Dishes declaring any of these are left out when you apply your preferences.
        </p>
        <div className="mt-5 grid grid-cols-2 gap-2 sm:grid-cols-3 xl:grid-cols-4">
          {ALLERGENS.map((allergen) => {
            const on = allergens.includes(allergen);
            return (
              <button
                key={allergen}
                type="button"
                aria-pressed={on}
                onClick={() => setAllergens((held) => toggle(held, allergen))}
                className={cx(
                  "flex h-12 items-center justify-between rounded-2xl border px-4 text-sm font-medium capitalize transition-colors",
                  on ? "border-saffron bg-saffron-soft text-saffron" : "border-line-strong text-ink-muted hover:border-ink-soft hover:text-ink",
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
      </section>

      <section className="rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
        <h2 className="flex items-center gap-2 font-display text-xl font-semibold text-ink">
          <Leaf className="h-5 w-5 text-herb" aria-hidden="true" /> Diets you follow
        </h2>
        <p className="mt-1 text-sm text-ink-muted">Dishes must carry every diet you pick.</p>
        <div className="mt-5 flex flex-wrap gap-2">
          {COMMON_DIETS.map((diet) => {
            const on = diets.includes(diet);
            return (
              <button
                key={diet}
                type="button"
                aria-pressed={on}
                onClick={() => setDiets((held) => toggle(held, diet))}
                className={cx(
                  "inline-flex h-10 items-center gap-1.5 rounded-full border px-4 text-sm font-medium capitalize transition-colors",
                  on ? "border-herb bg-herb-soft text-herb" : "border-line-strong text-ink-muted hover:text-ink",
                )}
              >
                {on && <Check className="h-4 w-4" aria-hidden="true" />} {diet}
              </button>
            );
          })}
        </div>
        <input
          value={otherDiets}
          onChange={(event) => setOtherDiets(event.target.value)}
          placeholder="Something else? e.g. kosher, pescatarian"
          aria-label="Other diets, comma separated"
          className={cx(inputClass, "mt-4")}
        />
      </section>

      <div className="sticky bottom-4 z-10 flex flex-col gap-3 rounded-3xl border border-line bg-surface/95 p-4 shadow-lift backdrop-blur sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p className="flex items-center gap-2 text-sm text-ink-muted" aria-live="polite">
          <Info className="h-4 w-4 shrink-0" aria-hidden="true" />
          {preview ? (
            <span>
              <span className="font-semibold text-ink">
                {preview.fit} of {preview.all}
              </span>{" "}
              dishes on today&apos;s menu fit this profile.
            </span>
          ) : (
            "Checking today's menu…"
          )}
        </p>
        <button type="button" disabled={busy || !dirty} onClick={() => void save()} className={darkButtonClass}>
          {busy ? <Spinner /> : null} {dirty ? "Save preferences" : "Saved"}
        </button>
      </div>
    </div>
  );
}
