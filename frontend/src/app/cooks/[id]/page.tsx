"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import DishCard from "@/components/dish-card";
import { Card, ErrorBanner, Tag } from "@/components/ui";
import { api, ApiError, type CookPublic, type Dish, type DishPage } from "@/lib/api";

/**
 * Public cook profile: GET /api/cooks/{id} for the person, then
 * GET /api/dishes?cook_id= for their current menu (active only, by design).
 */
export default function CookProfilePage() {
  const { id } = useParams<{ id: string }>();
  const [cook, setCook] = useState<CookPublic | null>(null);
  const [dishes, setDishes] = useState<Dish[]>([]);
  const [errors, setErrors] = useState<string[]>([]);
  const [checked, setChecked] = useState(false);

  const load = useCallback(async () => {
    try {
      const [profile, menu] = await Promise.all([
        api.get<CookPublic>(`/cooks/${id}`),
        api.get<DishPage>(`/dishes?cook_id=${id}&limit=100`),
      ]);
      setCook(profile);
      setDishes(menu.items);
      setErrors([]);
    } catch (cause) {
      setCook(null);
      setDishes([]);
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
  if (!cook) {
    return (
      <div className="space-y-4">
        <ErrorBanner lines={errors} />
        <Link href="/cooks" className="text-sm text-emerald-700 hover:underline dark:text-emerald-400">
          &larr; Back to all cooks
        </Link>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          {cook.display_name ?? "A home cook"}
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">{cook.headline}</p>
        {cook.bio && (
          <p className="mt-4 max-w-2xl text-sm leading-relaxed text-zinc-700 dark:text-zinc-300">
            {cook.bio}
          </p>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-3 text-sm text-zinc-500 dark:text-zinc-400">
          {cook.area && <span>{cook.area}</span>}
          {cook.zone && (
            <Link
              href={`/?zone=${encodeURIComponent(cook.zone.slug)}`}
              className="text-emerald-700 hover:underline dark:text-emerald-400"
            >
              Zone: {cook.zone.name}
            </Link>
          )}
          {cook.specialties.map((specialty) => (
            <Tag key={specialty}>{specialty}</Tag>
          ))}
        </div>
      </Card>

      <section>
        <h2 className="mb-3 text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          On the menu right now
        </h2>
        {dishes.length === 0 && (
          <p className="text-sm text-zinc-500">Nothing listed at the moment - check back soon.</p>
        )}
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {dishes.map((dish) => (
            <li key={dish.id}>
              <DishCard dish={dish} showCook={false} />
            </li>
          ))}
        </ul>
      </section>

      <Link href="/cooks" className="text-sm text-emerald-700 hover:underline dark:text-emerald-400">
        &larr; Back to all cooks
      </Link>
    </div>
  );
}
