import "server-only";

import { readResponse } from "@/lib/api";

/**
 * Backend access for Server Components (server-side rendering).
 *
 * The browser talks to the relative `/api/*` path (rewritten or proxied to
 * the backend); the Next server has no such origin of its own, so it calls
 * the backend directly at API_ORIGIN - the same variable next.config.ts uses
 * for the rewrite, read here at runtime. Responses are never cached: the
 * menu must always be current.
 */
const API_ORIGIN = (process.env.API_ORIGIN ?? "http://127.0.0.1:8000").replace(/\/+$/, "");

export async function serverGet<T>(path: string): Promise<T> {
  return readResponse<T>(await fetch(`${API_ORIGIN}/api${path}`, { cache: "no-store" }));
}
