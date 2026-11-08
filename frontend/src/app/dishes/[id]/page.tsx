"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { AddToCartWithQuantity } from "@/components/add-to-cart";
import { AllergenTag, Card, ErrorBanner, Tag } from "@/components/ui";
import { api, ApiError, type Dish } from "@/lib/api";
import { formatMinorUnits, joinListOrDash } from "@/lib/format";

/** Public dish detail: GET /api/dishes/{id} (404 for unknown or deactivated). */
export default function DishDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [dish, setDish] = useState<Dish | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [checked, setChecked] = useState(false);

  const load = useCallback(async () => {
    try {
      setDish(await api.get<Dish>(`/dishes/${id}`));
      setErrors([]);
    } catch (cause) {
      setDish(null);
      setErrors(cause instanceof ApiError ? [cause.message] : ["Could not reach the API"]);
    } finally {
      setChecked(true);
    }
  }, [id]);

  useEffect(() => {
    // Timeout kick-off: the effect body must not directly call a
    // setState-transitive function (react-hooks/set-state-in-effect).
    const kickOff = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(kickOff);
  }, [load]);

  if (!checked) return <p className="text-sm text-zinc-500">Loading...</p>;
  if (!dish) {
    return (
      <div className="space-y-4">
        <ErrorBanner lines={errors} />
        <Link href="/" className="text-sm text-emerald-700 hover:underline dark:text-emerald-400">
          &larr; Back to all dishes
        </Link>
      </div>
    );
  }

  return (
    <div className="mx-auto w-full max-w-2xl space-y-4">
      <Card>
        <p className="text-xs uppercase tracking-wide text-zinc-400">Dish</p>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          {dish.name}
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          by{" "}
          <Link href={`/cooks/${dish.cook_id}`} className="text-emerald-700 hover:underline dark:text-emerald-400">
            {dish.cook_name ?? "an anonymous cook"}
          </Link>
        </p>

        {dish.description && (
          <p className="mt-4 text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
            {dish.description}
          </p>
        )}

        <div className="mt-6 flex items-end gap-8">
          <div>
            <p className="text-xs uppercase tracking-wide text-zinc-400">Price</p>
            <p className="font-mono text-2xl text-zinc-900 dark:text-zinc-100">
              {formatMinorUnits(dish.price)}
            </p>
          </div>
          <div>
            <p className="text-xs uppercase tracking-wide text-zinc-400">Portions</p>
            <p className="font-mono text-2xl text-zinc-900 dark:text-zinc-100">{dish.portions}</p>
          </div>
        </div>

        <div className="mt-6">
          <AddToCartWithQuantity dish={dish} />
        </div>

        <dl className="mt-6 space-y-3 text-sm">
          <div>
            <dt className="font-medium text-zinc-500 dark:text-zinc-400">Ingredients</dt>
            <dd className="mt-0.5 text-zinc-800 dark:text-zinc-200">{joinListOrDash(dish.ingredients)}</dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-500 dark:text-zinc-400">Allergens</dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {dish.allergens.length === 0 ? (
                <span className="text-zinc-400">None declared</span>
              ) : (
                dish.allergens.map((allergen) => <AllergenTag key={allergen}>{allergen}</AllergenTag>)
              )}
            </dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-500 dark:text-zinc-400">Kitchen zone</dt>
            <dd className="mt-0.5 text-zinc-800 dark:text-zinc-200">
              {dish.zone ? (
                <>
                  {dish.zone.name}{" "}
                  <span className="text-zinc-400">
                    (grid {dish.zone.x}, {dish.zone.y})
                  </span>{" "}
                  <Link
                    href={`/?zone=${encodeURIComponent(dish.zone.slug)}&max_distance=1`}
                    className="text-emerald-700 hover:underline dark:text-emerald-400"
                  >
                    More dishes near {dish.zone.name}
                  </Link>
                </>
              ) : (
                <span className="text-zinc-400">Not set</span>
              )}
            </dd>
          </div>
          <div>
            <dt className="font-medium text-zinc-500 dark:text-zinc-400">Dietary tags</dt>
            <dd className="mt-1 flex flex-wrap gap-1.5">
              {dish.dietary_tags.length === 0 ? (
                <span className="text-zinc-400">None</span>
              ) : (
                dish.dietary_tags.map((tag) => <Tag key={tag}>{tag}</Tag>)
              )}
            </dd>
          </div>
        </dl>
      </Card>
      <Link href="/" className="text-sm text-emerald-700 hover:underline dark:text-emerald-400">
        &larr; Back to all dishes
      </Link>
    </div>
  );
}
