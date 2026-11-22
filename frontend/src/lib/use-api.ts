"use client";

import { useCallback, useEffect, useState } from "react";

import { api, ApiError } from "@/lib/api";

/**
 * GET `path` (relative to /api) once on mount and whenever it changes.
 * `data` is null while loading or after an error; `reload()` refetches;
 * `setData` lets a page apply the answer of its own PUT/PATCH directly.
 * Pass `null` as the path to skip fetching (e.g. until a prerequisite exists).
 */
export function useApi<T>(path: string | null) {
  const [data, setData] = useState<T | null>(null);
  const [error, setError] = useState<string | null>(null);

  const reload = useCallback(async () => {
    if (path === null) return;
    try {
      setData(await api.get<T>(path));
      setError(null);
    } catch (cause) {
      setError(cause instanceof ApiError ? cause.message : "Could not reach the API");
    }
  }, [path]);

  useEffect(() => {
    // Timeout kick-off: the effect body must not call a setState-transitive
    // function directly (react-hooks/set-state-in-effect).
    const kickOff = window.setTimeout(() => void reload(), 0);
    return () => window.clearTimeout(kickOff);
  }, [reload]);

  return { data, error, reload, setData };
}
