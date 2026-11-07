/**
 * Typed access to the FastAPI backend.
 *
 * Everything goes through the relative `/api` path: `next dev` and the
 * standalone server rewrite it to `API_ORIGIN`, and behind nginx the same
 * URL works unchanged. Auth is the HTTP-only session cookie, which same-origin
 * `fetch` sends automatically - we never touch it here.
 */

export class ApiError extends Error {
  readonly status: number;
  readonly code: string;
  readonly fieldErrors: { field: string; type: string; message: string }[];

  constructor(
    status: number,
    code: string,
    message: string,
    fieldErrors: ApiError["fieldErrors"] = [],
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
  }

  /** Human-readable lines for form error banners (server-side validation). */
  get lines(): string[] {
    if (this.fieldErrors.length > 0) {
      return this.fieldErrors.map((e) => `${e.field}: ${e.message}`);
    }
    return [this.message];
  }
}

// --- backend schema mirrors ---------------------------------------------------

export type User = {
  id: string;
  email: string;
  display_name: string | null;
  bio: string | null;
  area: string | null;
  roles: string[];
  created_at: string;
  updated_at: string;
};

export type Dish = {
  id: string;
  cook_id: string;
  name: string;
  description: string | null;
  price: number; // integer minor units
  portions: number;
  ingredients: string[];
  allergens: string[];
  dietary_tags: string[];
  active: boolean;
  created_at: string;
  updated_at: string;
  cook_name?: string | null; // present on the public endpoints
};

export type DishPage = { items: Dish[]; total: number; limit: number; offset: number };

export type CookPublic = {
  user_id: string;
  display_name: string | null;
  bio: string | null;
  area: string | null;
  headline: string;
  specialties: string[];
  created_at: string;
};

export type CookPage = { items: CookPublic[]; total: number; limit: number; offset: number };

/** Body for POST /api/me/dishes (price already in minor units). */
export type DishInput = {
  name: string;
  description: string | null;
  price: number;
  portions: number;
  ingredients: string[];
  allergens: string[];
  dietary_tags: string[];
};

// --- fetch plumbing -------------------------------------------------------------

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`/api${path}`, { cache: "no-store", ...init });
  if (response.status === 204) {
    return undefined as T;
  }
  const body = (await response.json().catch(() => null)) as
    | { error?: { code?: string; message?: string; details?: unknown } }
    | null;
  if (!response.ok) {
    const error = body?.error ?? {};
    const details = Array.isArray(error.details)
      ? (error.details as ApiError["fieldErrors"])
      : [];
    throw new ApiError(
      response.status,
      error.code ?? "error",
      error.message ?? `Request failed (${response.status})`,
      details,
    );
  }
  return body as T;
}

export const api = {
  get: <T>(path: string) => call<T>(path),
  post: <T>(path: string, json: unknown) =>
    call<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(json) }),
  patch: <T>(path: string, json: unknown) =>
    call<T>(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(json) }),
  delete: <T>(path: string) => call<T>(path, { method: "DELETE" }),
};
