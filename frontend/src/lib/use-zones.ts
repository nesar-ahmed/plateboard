"use client";

import { useEffect, useState } from "react";

import { api, ApiError, type Zone } from "@/lib/api";

/**
 * The service-grid zones (GET /api/zones), loaded once per mounting
 * component. `zones` is null while loading or after a failure (see `error`).
 */
export function useZones(): { zones: Zone[] | null; error: string | null } {
  const [state, setState] = useState<{ zones: Zone[] | null; error: string | null }>({
    zones: null,
    error: null,
  });

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const zones = await api.get<Zone[]>("/zones");
        if (active) setState({ zones, error: null });
      } catch (cause) {
        if (active) {
          setState({
            zones: null,
            error: cause instanceof ApiError ? cause.message : "Could not load zones",
          });
        }
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, []);

  return state;
}

/** Largest possible grid distance between two of `zones` (for distance pickers). */
export function maxZoneSpan(zones: Zone[]): number {
  if (zones.length === 0) return 0;
  const xs = zones.map((zone) => zone.x);
  const ys = zones.map((zone) => zone.y);
  return Math.max(...xs) - Math.min(...xs) + (Math.max(...ys) - Math.min(...ys));
}
