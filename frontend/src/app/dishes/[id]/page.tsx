import { ArrowRight, ChevronRight, CircleCheck, Leaf, MapPin, ShieldCheck, Store } from "lucide-react";
import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { cache } from "react";

import { AddToCartWithQuantity } from "@/components/add-to-cart";
import { AvailabilityPill } from "@/components/availability";
import DishArt from "@/components/dish-art";
import DishCard from "@/components/dish-card";
import DishReviews from "@/components/dish-reviews";
import FavouriteButton from "@/components/favourite-button";
import {
  AllergenTag,
  Avatar,
  Container,
  ErrorBanner,
  SectionHeading,
  Tag,
  cx,
  railItemClass,
  railListClass,
} from "@/components/ui";
import Stars from "@/components/stars";
import VerifiedBadge from "@/components/verified-badge";
import { ApiError, type CookProfilePage, type Dish, type DishPage, type ReviewPage } from "@/lib/api";
import { formatMinorUnits } from "@/lib/format";
import { REVIEWS_PAGE_SIZE, formatAverage, reviewCount } from "@/lib/reviews";
import { serverGet } from "@/lib/server-api";

/**
 * One dish, rendered on the server (GET /api/dishes/{id}). Unknown or
 * deactivated dishes - and ids that are not UUIDs at all - render the 404
 * page. `cache` dedupes the fetch between the metadata and the page.
 */
const loadDish = cache(async (id: string): Promise<Dish | ApiError> => {
  try {
    return await serverGet<Dish>(`/dishes/${encodeURIComponent(id)}`);
  } catch (cause) {
    if (cause instanceof ApiError && (cause.status === 404 || cause.status === 422)) notFound();
    return cause instanceof ApiError ? cause : new ApiError(503, "unreachable", "Could not reach the API");
  }
});

export async function generateMetadata({ params }: PageProps<"/dishes/[id]">): Promise<Metadata> {
  const dish = await loadDish((await params).id);
  if (dish instanceof ApiError) return { title: "Dish" };
  return {
    title: dish.name,
    description: dish.description ?? `${dish.name} by ${dish.cook_name ?? "a home cook"} on Plateboard.`,
  };
}

export default async function DishDetailPage({ params }: PageProps<"/dishes/[id]">) {
  const dish = await loadDish((await params).id);
  if (dish instanceof ApiError) {
    return (
      <Container className="py-16">
        <ErrorBanner lines={dish.lines} />
      </Container>
    );
  }
  const [more, cook, reviews] = await Promise.all([
    serverGet<DishPage>(`/dishes?cook_id=${dish.cook_id}&limit=5`).catch(() => null),
    serverGet<CookProfilePage>(`/cooks/${dish.cook_id}`).catch(() => null),
    serverGet<ReviewPage>(`/dishes/${dish.id}/reviews?limit=${REVIEWS_PAGE_SIZE}`).catch(() => null),
  ]);
  const rating = dish.rating ?? { average: null, count: 0 };
  const others = (more?.items ?? []).filter((other) => other.id !== dish.id).slice(0, 4);

  return (
    <>
      <Container size="wide" className="pb-6 pt-6 sm:pt-8">
        <nav aria-label="Breadcrumb" className="mb-6 flex items-center gap-1.5 text-sm text-ink-muted">
          <Link href="/dishes" className="hover:text-ink">
            Dishes
          </Link>
          <ChevronRight className="h-3.5 w-3.5" aria-hidden="true" />
          <span className="truncate text-ink">{dish.name}</span>
        </nav>

        <div className="grid grid-cols-1 gap-8 lg:grid-cols-2 lg:gap-14">
          <div className="lg:sticky lg:top-24 lg:self-start">
            <DishArt dish={dish} size="lg" className="aspect-square w-full shadow-lift" rounded="rounded-[2rem]" />
          </div>

          <div className="flex flex-col">
            <div className="flex items-start justify-between gap-3">
              <Link
                href={`/cooks/${dish.cook_id}`}
                className="group inline-flex w-fit min-w-0 items-center gap-2.5 rounded-full border border-line bg-surface py-1 pl-1 pr-4 text-sm font-medium text-ink hover:border-line-strong"
              >
                <Avatar name={dish.cook_name} size="sm" />
                <span className="truncate">{dish.cook_name ?? "A home cook"}</span>
                {cook?.verified && <VerifiedBadge compact className="-ml-1" />}
                <ArrowRight className="h-3.5 w-3.5 shrink-0 text-ink-soft transition-transform group-hover:translate-x-0.5" />
              </Link>
              <FavouriteButton dish={dish} variant="pill" className="shrink-0" />
            </div>

            <h1 className="mt-5 font-display text-4xl font-semibold leading-tight tracking-tight text-ink sm:text-5xl">
              {dish.name}
            </h1>

            <a
              href="#reviews"
              className="mt-3 inline-flex w-fit items-center gap-2 text-sm text-ink-muted hover:text-ink"
            >
              {rating.count > 0 ? (
                <>
                  <Stars value={rating.average ?? 0} />
                  <span className="font-semibold text-ink">{formatAverage(rating.average)}</span>
                  <span className="underline decoration-line-strong underline-offset-4">{reviewCount(rating.count)}</span>
                </>
              ) : (
                <span className="underline decoration-line-strong underline-offset-4">No reviews yet</span>
              )}
            </a>

            {dish.dietary_tags.length > 0 && (
              <div className="mt-4 flex flex-wrap gap-1.5">
                {dish.dietary_tags.map((tag) => (
                  <Tag key={tag} className="capitalize">
                    <Leaf className="mr-1 h-3 w-3" aria-hidden="true" />
                    {tag}
                  </Tag>
                ))}
              </div>
            )}

            {dish.description && (
              <p className="mt-5 text-lg leading-relaxed text-ink-muted">{dish.description}</p>
            )}

            <div className="mt-8 flex items-end gap-4">
              <p className="font-display text-4xl font-semibold tabular-nums text-ink">
                {formatMinorUnits(dish.price)}
              </p>
              <p className="pb-1.5 text-sm text-ink-muted">per portion · {dish.portions} portions offered</p>
            </div>

            <div className="mt-6">
              <AddToCartWithQuantity dish={dish} price={dish.price} />
            </div>
            {cook && (
              <p className="mt-3 flex flex-wrap items-center gap-2 text-sm text-ink-muted">
                <AvailabilityPill availability={cook.availability} />
                {!cook.availability.accepting_orders && "You can fill your bag now and order once the kitchen opens."}
              </p>
            )}

            <ul className="mt-6 grid grid-cols-1 gap-2 text-sm text-ink-muted sm:grid-cols-2">
              <li className="flex items-center gap-2">
                <Store className="h-4 w-4 text-ink-soft" aria-hidden="true" /> One kitchen per order
              </li>
              <li className="flex items-center gap-2">
                <ShieldCheck className="h-4 w-4 text-ink-soft" aria-hidden="true" /> Allergens declared by the cook
              </li>
            </ul>

            <div className="mt-10 divide-y divide-line rounded-3xl border border-line bg-surface">
              <section className="p-5 sm:p-6">
                <h2 className="text-sm font-semibold text-ink">Ingredients</h2>
                <p className="mt-2 leading-relaxed text-ink-muted">
                  {dish.ingredients.length > 0 ? dish.ingredients.join(", ") : "Not listed yet."}
                </p>
              </section>
              <section className="p-5 sm:p-6">
                <h2 className="text-sm font-semibold text-ink">Allergens</h2>
                {dish.allergens.length > 0 ? (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {dish.allergens.map((allergen) => (
                      <AllergenTag key={allergen} className="capitalize">
                        {allergen}
                      </AllergenTag>
                    ))}
                  </div>
                ) : (
                  <p className="mt-2 flex items-center gap-1.5 text-herb">
                    <CircleCheck className="h-4 w-4" aria-hidden="true" /> No allergens declared
                  </p>
                )}
              </section>
              <section className="p-5 sm:p-6">
                <h2 className="text-sm font-semibold text-ink">Kitchen</h2>
                {dish.zone ? (
                  <div className="mt-2 flex flex-wrap items-center justify-between gap-3">
                    <p className="flex items-center gap-1.5 text-ink-muted">
                      <MapPin className="h-4 w-4" aria-hidden="true" /> {dish.zone.name}
                    </p>
                    <Link
                      href={`/dishes?zone=${encodeURIComponent(dish.zone.slug)}&max_distance=1`}
                      className="text-sm font-semibold text-brand hover:underline"
                    >
                      More dishes near {dish.zone.name}
                    </Link>
                  </div>
                ) : (
                  <p className="mt-2 text-ink-muted">The cook hasn&apos;t set a neighbourhood yet.</p>
                )}
              </section>
            </div>
          </div>
        </div>
      </Container>

      <Container size="wide" className={cx("pt-14", others.length === 0 && "pb-14")}>
        <section id="reviews" aria-label="Reviews" className="scroll-mt-24">
          <SectionHeading
            eyebrow="Reviews"
            title={`What people say about ${dish.name}`}
            lead="Ratings and words from customers who received it, with the cook's replies."
          />
          <DishReviews dishId={dish.id} cookId={dish.cook_id} cookName={dish.cook_name} initial={reviews} />
        </section>
      </Container>

      {others.length > 0 && (
        <Container size="wide" className="py-14">
          <SectionHeading
            eyebrow="From the same kitchen"
            title={`More from ${dish.cook_name ?? "this cook"}`}
            lead="Same kitchen, same order - add them to one bag."
          />
          <ul className={cx(railListClass, "sm:grid-cols-2 lg:grid-cols-4")}>
            {others.map((other) => (
              <li key={other.id} className={railItemClass}>
                <DishCard dish={other} showCook={false} />
              </li>
            ))}
          </ul>
        </Container>
      )}
    </>
  );
}
