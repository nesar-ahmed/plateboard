import { MapPin } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

import { AddToCartButton } from "@/components/add-to-cart";
import DishArt from "@/components/dish-art";
import FavouriteButton from "@/components/favourite-button";
import { Avatar, cx } from "@/components/ui";
import type { Dish } from "@/lib/api";
import { formatDistance, formatMinorUnits } from "@/lib/format";

/**
 * One public-menu dish. The whole card opens the dish (stretched title
 * link); the cook link, the heart (save to favourites) and the add button
 * sit above that layer. Server-safe: only the heart and the add button are
 * Client Components.
 *
 * `preview` renders the same card inert - no links, no heart, no add button
 * - for the cook's dish editor ("this is how customers will see it").
 * `action` replaces the "+ Add" button (the favourites list adds through
 * its own endpoint).
 */
export default function DishCard({
  dish,
  showCook = true,
  preview = false,
  action,
  className,
}: {
  dish: Dish;
  showCook?: boolean;
  preview?: boolean;
  action?: ReactNode;
  className?: string;
}) {
  const lead = dish.dietary_tags[0];
  return (
    <article
      className={cx(
        "group relative flex h-full flex-col overflow-hidden rounded-3xl border border-line bg-surface shadow-card",
        "transition-all duration-200 hover:-translate-y-0.5 hover:shadow-lift",
        className,
      )}
    >
      <div className="relative">
        <DishArt
          dish={dish}
          rounded="rounded-none"
          className="aspect-[4/3] transition-transform duration-500 group-hover:scale-[1.03]"
        />
        <div className="absolute left-3 right-16 top-3 flex flex-wrap gap-1.5">
          {dish.distance != null && (
            <span className="rounded-full bg-surface/90 px-2.5 py-1 text-[11px] font-semibold text-ink shadow-sm backdrop-blur">
              {formatDistance(dish.distance)}
            </span>
          )}
          {lead && (
            <span className="rounded-full bg-black/55 px-2.5 py-1 text-[11px] font-semibold capitalize text-white backdrop-blur">
              {lead}
            </span>
          )}
        </div>
        {!preview && (
          <>
            <div className="absolute right-3 top-3 z-10">
              <FavouriteButton dish={dish} />
            </div>
            <div className="absolute bottom-3 right-3 z-10">{action ?? <AddToCartButton dish={dish} />}</div>
          </>
        )}
      </div>

      <div className="flex flex-1 flex-col p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-display text-lg font-semibold leading-snug tracking-tight text-ink">
            {preview ? (
              dish.name
            ) : (
              <Link
                href={`/dishes/${dish.id}`}
                className="after:absolute after:inset-0 after:content-[''] focus-visible:outline-none"
              >
                {dish.name}
              </Link>
            )}
          </h3>
          <p className="shrink-0 font-display text-lg font-semibold tabular-nums text-ink">
            {formatMinorUnits(dish.price)}
          </p>
        </div>

        {dish.description && (
          <p className="mt-1.5 line-clamp-2 text-sm leading-relaxed text-ink-muted">{dish.description}</p>
        )}

        <div className="mt-auto pt-4">
          {dish.allergens.length > 0 ? (
            <p className="mb-3 text-xs text-saffron">
              <span className="font-semibold">Contains:</span> {dish.allergens.join(", ")}
            </p>
          ) : (
            <p className="mb-3 text-xs text-herb">No declared allergens</p>
          )}
          <div className="flex items-center justify-between gap-3 border-t border-line pt-3 text-xs text-ink-muted">
            {showCook && preview ? (
              <span className="flex min-w-0 items-center gap-2 font-medium text-ink">
                <Avatar name={dish.cook_name} size="sm" className="h-6 w-6 text-[10px]" />
                <span className="truncate">{dish.cook_name ?? "Home cook"}</span>
              </span>
            ) : showCook ? (
              <Link
                href={`/cooks/${dish.cook_id}`}
                className="relative z-10 flex min-w-0 items-center gap-2 font-medium text-ink hover:text-brand"
              >
                <Avatar name={dish.cook_name} size="sm" className="h-6 w-6 text-[10px]" />
                <span className="truncate">{dish.cook_name ?? "Home cook"}</span>
              </Link>
            ) : (
              <span>{dish.portions} portions</span>
            )}
            {dish.zone && (
              <span className="flex shrink-0 items-center gap-1">
                <MapPin className="h-3.5 w-3.5" aria-hidden="true" />
                {dish.zone.name}
              </span>
            )}
          </div>
        </div>
      </div>
    </article>
  );
}
