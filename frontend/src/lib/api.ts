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
  /** The envelope's raw `details` (a field-error list, or an object such as
   * the cart's `different_cook` payload). */
  readonly details: unknown;

  constructor(
    status: number,
    code: string,
    message: string,
    fieldErrors: ApiError["fieldErrors"] = [],
    details: unknown = null,
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.code = code;
    this.fieldErrors = fieldErrors;
    this.details = details;
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

/** A cell on the service grid (GET /api/zones); distances are grid steps. */
export type Zone = {
  slug: string;
  name: string;
  x: number;
  y: number;
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
  zone?: Zone | null; // public endpoints: the cook's kitchen zone
  distance?: number | null; // public list with ?zone=: grid steps from it
};

export type DishPage = { items: Dish[]; total: number; limit: number; offset: number };

export type CookPublic = {
  user_id: string;
  display_name: string | null;
  bio: string | null;
  area: string | null;
  headline: string;
  specialties: string[];
  zone: Zone | null;
  created_at: string;
};

/** The signed-in cook's own profile (GET/PATCH /api/cooks/me). */
export type CookProfile = {
  user_id: string;
  headline: string;
  specialties: string[];
  zone: Zone | null;
  created_at: string;
  updated_at: string;
};

export type CookPage = { items: CookPublic[]; total: number; limit: number; offset: number };

/** One line of the cart (GET/POST/PATCH/DELETE /api/cart...). */
export type CartItem = {
  dish_id: string;
  name: string;
  price: number; // current unit price, minor units
  quantity: number;
  line_total: number; // minor units
  available: boolean; // false once the dish is deactivated: not in totals, remove-only
  max_quantity: number; // 100
  added_at: string;
};

/**
 * The caller's cart - a guest's (HTTP-only cookie) or the account's. Every
 * cart endpoint answers with the whole cart. One cook per cart.
 */
export type Cart = {
  owner: "guest" | "user";
  cook: { id: string; name: string | null } | null; // null while empty
  items: CartItem[]; // newest additions first
  item_count: number; // portions across available lines
  total: number; // minor units, available lines only
  unavailable_count: number;
};

/** `details` of a 409 `different_cook` from POST /api/cart/items. */
export type DifferentCookDetails = {
  cart_cook_id: string;
  cart_cook_name: string | null;
  dish_cook_id: string;
};

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

/**
 * Body of an API response, or an ApiError built from the project's error
 * envelope. Shared by the browser client below and lib/server-api.ts.
 */
export async function readResponse<T>(response: Response): Promise<T> {
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
      error.details ?? null,
    );
  }
  return body as T;
}

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  return readResponse<T>(await fetch(`/api${path}`, { cache: "no-store", ...init }));
}

export const api = {
  get: <T>(path: string) => call<T>(path),
  post: <T>(path: string, json: unknown) =>
    call<T>(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(json) }),
  patch: <T>(path: string, json: unknown) =>
    call<T>(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(json) }),
  delete: <T>(path: string) => call<T>(path, { method: "DELETE" }),
};
