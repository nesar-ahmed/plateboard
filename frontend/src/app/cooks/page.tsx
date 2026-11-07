"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";

import { Card, ErrorBanner, Pager, Tag } from "@/components/ui";
import { api, ApiError, type CookPage } from "@/lib/api";

const PAGE_SIZE = 12;

/** Public directory of cooks: GET /api/cooks (paginated). */
export default function CookDirectory() {
  const [offset, setOffset] = useState(0);
  const [page, setPage] = useState<CookPage | null>(null);
  const [errors, setErrors] = useState<string[]>([]);

  const load = useCallback(async () => {
    try {
      setPage(
        await api.get<CookPage>(`/cooks?limit=${PAGE_SIZE}&offset=${offset}`),
      );
      setErrors([]);
    } catch (cause) {
      setPage(null);
      setErrors(cause instanceof ApiError ? [cause.message] : ["Could not reach the API"]);
    }
  }, [offset]);

  useEffect(() => {
    // Timeout kick-off: the effect body must not directly call a
    // setState-transitive function (react-hooks/set-state-in-effect).
    const kickOff = window.setTimeout(() => void load(), 0);
    return () => window.clearTimeout(kickOff);
  }, [load]);

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Meet the cooks
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Home cooks with a public Plateboard profile.
        </p>
      </header>

      <ErrorBanner lines={errors} />

      {page && page.items.length === 0 && (
        <p className="text-sm text-zinc-500">No cooks yet - the first one is a register away.</p>
      )}

      {page && page.items.length > 0 && (
        <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {page.items.map((cook) => (
            <li key={cook.user_id}>
              <Card>
                <h2 className="text-base font-semibold text-zinc-900 dark:text-zinc-50">
                  <Link href={`/cooks/${cook.user_id}`} className="hover:underline">
                    {cook.display_name ?? "A home cook"}
                  </Link>
                </h2>
                <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">{cook.headline}</p>
                {cook.area && <p className="mt-2 text-xs text-zinc-400">{cook.area}</p>}
                {cook.specialties.length > 0 && (
                  <div className="mt-3 flex flex-wrap gap-1.5">
                    {cook.specialties.map((specialty) => (
                      <Tag key={specialty}>{specialty}</Tag>
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
