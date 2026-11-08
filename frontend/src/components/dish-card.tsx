"use client";

import Link from "next/link";

import { AddToCartButton } from "@/components/add-to-cart";
import { AllergenTag, Card, Tag } from "@/components/ui";
import type { Dish } from "@/lib/api";
import { formatDistance, formatMinorUnits } from "@/lib/format";

/**
 * One public-menu dish: name, cook, price, the kitchen's zone (plus the grid
 * distance when the list was filtered by zone), dietary tags and allergens.
 * Used by the dish directory and the cook profile page.
 */
export default function DishCard({ dish, showCook = true }: { dish: Dish; showCook?: boolean }) {
  return (
    <Card>
      <h3 className="text-base font-semibold text-zinc-900 dark:text-zinc-50">
        <Link href={`/dishes/${dish.id}`} className="hover:underline">
          {dish.name}
        </Link>
      </h3>
      {showCook && (
        <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
          by{" "}
          <Link href={`/cooks/${dish.cook_id}`} className="text-emerald-700 hover:underline dark:text-emerald-400">
            {dish.cook_name ?? "an anonymous cook"}
          </Link>
        </p>
      )}
      <div className="mt-3 flex items-end justify-between gap-2">
        <div>
          <p className="font-mono text-lg text-zinc-900 dark:text-zinc-100">{formatMinorUnits(dish.price)}</p>
          <p className="text-xs text-zinc-400">{dish.portions} portions</p>
        </div>
        <AddToCartButton dish={dish} />
      </div>
      {dish.zone && (
        <p className="mt-2 flex flex-wrap items-center gap-1.5 text-xs text-zinc-500 dark:text-zinc-400">
          <span>{dish.zone.name}</span>
          {dish.distance != null && (
            <span className="rounded-full bg-emerald-50 px-2 py-0.5 font-medium text-emerald-700 dark:bg-emerald-950 dark:text-emerald-400">
              {formatDistance(dish.distance)}
            </span>
          )}
        </p>
      )}
      {dish.dietary_tags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {dish.dietary_tags.map((tag) => (
            <Tag key={tag}>{tag}</Tag>
          ))}
        </div>
      )}
      {dish.allergens.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {dish.allergens.map((allergen) => (
            <AllergenTag key={allergen}>{allergen}</AllergenTag>
          ))}
        </div>
      )}
    </Card>
  );
}
