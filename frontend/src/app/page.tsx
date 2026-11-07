"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { AllergenTag, Card, ErrorBanner, Pager, Tag, inputClass } from "@/components/ui";
import { api, ApiError, type DishPage } from "@/lib/api";
import { formatMinorUnits } from "@/lib/format";

const PAGE_SIZE = 12;

/** Public dish list: active dishes only, `?q=` name search, prev/next paging. */
export default function DishDirectory() {
  const [query, setQuery] = useState("");
  const [submittedQuery, setSubmittedQuery] = useState("");
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<DishPage | null>(null);
  const [error, setError] = useState<string[]>([]);

  const load = useCallback(async () => {
    const params = new URLSearchParams({
      limit: String(PAGE_SIZE),
      offset: String(offset),
    });
    if (submittedQuery) params.set("q", submittedQuery);
    try {
      setPage(await api.get<DishPage>(`/dishes?${params.toString()}`));
      setError([]);
    } catch (cause) {
      setPage(null);
      setError(cause instanceof ApiError ? [cause.message] : ["Could not reach the API"]);
    }
  }, [offset, submittedQuery]);

  useEffect(() => {
    // Timeout kick-off so the effect body does not call a setState-transitive
    // function directly (react-hooks/set-state-in-effect).
    const kickOff = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(kickOff);
  }, [load]);

  const search = (event: React.FormEvent) => {
    event.preventDefault();
    setOffset(0);
    setSubmittedQuery(query.trim());
  };

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Dishes from local home cooks
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Only active menu items are listed. Prices are shown per dish.
        </p>
      </header>

      <form onSubmit={search} className="flex max-w-md gap-2">
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="Search by name, e.g. biryani"
          aria-label="Search dishes by name"
          className={inputClass}
        />
        <button
          type="submit"
          className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-700"
        >
          Search
        </button>
      </form>

      <ErrorBanner lines={error} />

      {page && page.items.length === 0 && (
        <p className="text-sm text-zinc-500">
          {submittedQuery ? `Nothing matches "${submittedQuery}".` : "No dishes yet - check back soon."}
        </p>
      )}

      {page && page.items.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {page.items.map((dish) => (
            <li key={dish.id}>
              <Card>
                <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-50">
                  <Link href={`/dishes/${dish.id}`} className="hover:underline">
                    {dish.name}
                  </Link>
                </h2>
                <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
                  by{" "}
                  <Link href={`/cooks/${dish.cook_id}`} className="text-emerald-700 hover:underline dark:text-emerald-400">
                    {dish.cook_name ?? "an anonymous cook"}
                  </Link>
                </p>
                <p className="mt-3 font-mono text-lg text-zinc-900 dark:text-zinc-100">
                  {formatMinorUnits(dish.price)}
                </p>
                <p className="text-xs text-zinc-400">{dish.portions} portions</p>
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
            </li>
          ))}
        </ul>
      )}

      {page && page.total > PAGE_SIZE && (
        <Pager total={page.total} limit={PAGE_SIZE} offset={offset} onMove={setOffset} />
      )}
    </div>
  );
}
