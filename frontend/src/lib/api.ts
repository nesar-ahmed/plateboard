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
  rating?: Rating; // public endpoints: average stars + review count
};

export type DishPage = { items: Dish[]; total: number; limit: number; offset: number };

/** A dish's or a kitchen's rating: `average` is null until the first review. */
export type Rating = { average: number | null; count: number };

/** Rating + how many reviews gave each star, 5 down to 1. */
export type RatingSummary = Rating & { distribution: { rating: number; count: number }[] };

/**
 * A review as anyone may read it (GET /api/dishes/{id}/reviews): the author
 * only as "First L.", never their id or order. Only customers who received
 * the dish (an order accepted, made ready and confirmed received) can write one.
 */
export type Review = {
  id: string;
  rating: number; // 1..5
  comment: string | null;
  author_name: string | null; // null: no display name
  dish_id: string | null; // null once the cook deleted the dish
  dish_name: string;
  cook_id: string;
  created_at: string;
  edited_at: string | null;
  reply: { body: string; replied_at: string } | null; // the cook's answer
};

/** A page of public reviews; `summary` covers every review, whatever the filter. */
export type ReviewPage = {
  items: Review[];
  total: number;
  limit: number;
  offset: number;
  summary: RatingSummary;
};

/** One of the signed-in customer's own reviews (GET /api/me/reviews). */
export type MyReview = Review & { order_id: string | null; cook_name: string | null };
export type MyReviewPage = { items: MyReview[]; total: number; limit: number; offset: number };

/** A dish the customer received and has not reviewed yet (GET /api/me/reviews/pending). */
export type PendingReview = {
  dish_id: string;
  dish_name: string;
  dish_available: boolean;
  cook_id: string;
  cook_name: string | null;
  order_id: string; // the order to review it from
  completed_at: string;
};
export type PendingReviewPage = { items: PendingReview[]; total: number; limit: number; offset: number };

/** A review of one of my dishes, as the cook sees it (GET /api/cooks/me/reviews). */
export type CookReview = Review & { order_id: string | null; customer_name: string | null };

/** The kitchen's reviews + its rating summary and how many still wait for a reply. */
export type CookReviewPage = {
  items: CookReview[];
  total: number;
  limit: number;
  offset: number;
  summary: RatingSummary;
  unreplied: number;
};

/**
 * One saved dish (GET /api/me/favourites): the dish as the public menu shows
 * it, and whether it can be ordered now - `available` is false while its
 * cook hides it (the dish stays on the list, and can't go to the cart).
 */
export type Favourite = { dish: Dish; available: boolean; added_at: string };

/** The signed-in customer's favourites, newest first (max `max_favourites`). */
export type FavouritePage = {
  items: Favourite[];
  total: number; // every saved dish, hidden ones included
  unavailable: number; // ...of which hidden by their cook
  max_favourites: number;
  limit: number;
  offset: number;
};

/**
 * Whether a kitchen takes orders now, and when over the next 24 hours.
 * `open`/`closed` follow weekly hours, `paused` = switched off by the cook,
 * `anytime` = no fixed hours. Instants are UTC; show them in the viewer's time.
 */
export type Availability = {
  status: "open" | "closed" | "paused" | "anytime";
  accepting_orders: boolean;
  opens_at: string | null; // closed: the next opening (within a week)
  closes_at: string | null; // open: the end of this window
  next_24h: { starts_at: string; ends_at: string }[]; // clipped to [as_of, as_of + 24h]
  timezone: string; // the kitchen's IANA zone
  as_of: string; // the instant this was computed for
};

export type CookPublic = {
  user_id: string;
  display_name: string | null;
  bio: string | null;
  area: string | null;
  headline: string;
  specialties: string[];
  zone: Zone | null;
  verified: boolean; // checked by the Plateboard team
  verified_at: string | null;
  availability: Availability;
  created_at: string; // when the kitchen opened on Plateboard
};

/** The stats strip of a public profile - counts, never money. */
export type CookPublicStats = {
  orders_completed: number;
  customers: number;
  returning_customers: number;
  acceptance_rate: number | null; // 0..1, null for new kitchens
  average_ready_minutes: number | null; // placed -> ready, null for new kitchens
  new_kitchen: boolean;
};

/** GET /api/cooks/{id} - the card plus the stats strip. */
export type CookProfilePage = CookPublic & { stats: CookPublicStats };

/**
 * The signed-in user's kitchen (GET/PATCH /api/cooks/me - cooks only) or
 * cook application in any state (POST /api/cooks, GET /api/cooks/me/application).
 */
export type CookProfile = {
  user_id: string;
  headline: string;
  specialties: string[];
  zone: Zone | null;
  verified_at: string | null;
  /** The application: only an accepted kitchen can cook on the platform. */
  status: CookApplicationStatus;
  submitted_at: string; // the latest (re)submission
  reviewed_at: string | null;
  rejection_reason: string | null; // the admin's reason, on a rejection
  created_at: string;
  updated_at: string;
};

/** One weekly window, kitchen time: day 0 = Monday; closes may be "24:00". */
export type OpeningWindow = { day: number; opens: string; closes: string };

/** GET/PUT /api/cooks/me/availability. */
export type AvailabilitySettings = {
  timezone: string;
  orders_paused: boolean;
  hours: OpeningWindow[];
  availability: Availability;
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

/** An entry of the signed-in user's address book (GET /api/me/addresses). */
export type Address = {
  id: string;
  label: string | null;
  recipient: string;
  phone: string;
  line1: string;
  line2: string | null;
  city: string;
  postal_code: string | null;
  instructions: string | null;
  zone: Zone | null;
  is_default: boolean;
  created_at: string;
  updated_at: string;
};

/** Body for POST /api/me/addresses (`zone` is a slug; blanks = none). */
export type AddressInput = {
  label: string | null;
  recipient: string;
  phone: string;
  line1: string;
  line2: string | null;
  city: string;
  postal_code: string | null;
  instructions: string | null;
  zone: string | null;
  is_default: boolean;
};

/** The copy of an address an order keeps (no id - it is a snapshot). */
export type DeliveryAddress = Omit<Address, "id" | "is_default" | "created_at" | "updated_at">;

export type OrderStatus = "placed" | "accepted" | "ready" | "completed" | "cancelled";

export type OrderItem = {
  dish_id: string | null; // null once the cook deleted the dish
  name: string; // at placement
  unit_price: number; // minor units, at placement
  quantity: number;
  line_total: number;
};

/** An order (POST/GET /api/me/orders...): the cart, frozen, plus its status timeline. */
export type Order = {
  id: string;
  status: OrderStatus;
  cook: { id: string; name: string | null };
  customer: { id: string; name: string | null };
  items: OrderItem[];
  item_count: number;
  total: number;
  note: string | null;
  /** How the food reaches the customer - `pickup` today (delivery: not offered yet). */
  fulfilment: "pickup" | "delivery";
  delivery_address: DeliveryAddress | null;
  created_at: string;
  updated_at: string;
  accepted_at: string | null;
  ready_at: string | null;
  completed_at: string | null;
  cancelled_at: string | null;
  cancelled_by: "customer" | "cook" | null;
  /** The cook's explanation when they rejected/cancelled the order. */
  cancel_reason: string | null;
};

export type OrderPage = { items: Order[]; total: number; limit: number; offset: number };

// --- notifications -----------------------------------------------------------------

/**
 * The panel whose inbox a notification belongs to: `account` (/account -
 * every signed-in user), `cook` (/cook) and `admin` (/admin).
 */
export type NotificationAudience = "account" | "cook" | "admin";

/**
 * One in-app notification (GET /api/me/notifications). `title`/`body` are
 * rendered by the backend; `subject` is what it is about (it may no longer
 * exist); `data` is the snapshot taken when it happened. Named
 * `AppNotification` - `Notification` is the browser's own (Web Notifications).
 */
export type AppNotification = {
  id: string;
  /** What happened, e.g. "order.accepted" (catalog in backend/app/modules/notifications/catalog.py). */
  type: string;
  audience: NotificationAudience;
  title: string;
  body: string | null;
  subject: { kind: "order" | "kitchen" | "review"; id: string } | null;
  actor_id: string | null;
  data: Record<string, unknown>;
  read: boolean;
  read_at: string | null;
  created_at: string;
};

/** A page of one inbox (or all visible ones), plus its unread count. */
export type NotificationPage = {
  items: AppNotification[];
  total: number;
  unread: number;
  limit: number;
  offset: number;
};

/** GET /api/me/notifications/unread-count - per panel (0 without the role). */
export type UnreadCounts = { total: number } & Record<NotificationAudience, number>;

/** The account's food profile (GET/PUT /api/me/preferences). */
export type Preferences = {
  excluded_allergens: string[];
  dietary_preferences: string[];
};

/** One signed-in session (GET /api/me/sessions) - a fingerprint, never the token. */
export type SessionInfo = {
  id: string;
  created_at: string;
  expires_at: string;
  current: boolean;
};

export type StatusCounts = Record<OrderStatus, number>;

export type OrderStats = {
  orders: number;
  by_status: StatusCounts;
  open: number;
  booked_value: number; // non-cancelled totals, minor units
  completed_value: number;
  average_order_value: number;
};

export type OrderPoint = { period: string; orders: number; cancelled: number; value: number };

/** GET /api/me/dashboard - the signed-in user as a buyer. */
export type CustomerDashboard = {
  window: { unit: "day" | "month"; periods: number; start: string; end: string };
  orders: OrderStats;
  spending: OrderPoint[];
  favourite_cooks: { cook_id: string; name: string | null; orders: number; value: number }[];
  favourite_dishes: { dish_id: string | null; name: string; quantity: number; orders: number; value: number }[];
  recent_orders: Order[];
  cart: {
    cook: { id: string; name: string | null } | null;
    lines: number;
    item_count: number;
    total: number;
    unavailable_count: number;
  };
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
  /** Public (on the menu, orderable) or private (only the cook sees it). */
  active: boolean;
};

// --- cook panel ------------------------------------------------------------------

/** A number of orders and their totals (minor units). */
export type Amount = { orders: number; value: number };

/** One dish in a ranking (dashboards, earnings): null id = deleted since. */
export type DishRank = { dish_id: string | null; name: string; quantity: number; orders: number; value: number };

export type ChecklistKey = "display_name" | "bio" | "specialties" | "zone" | "public_dish" | "dish_descriptions";

/** GET /api/cooks/me/dashboard - the signed-in cook's kitchen. */
export type CookDashboard = {
  window: { unit: "day" | "month"; periods: number; start: string; end: string };
  zone: Zone | null;
  orders: OrderStats;
  revenue: OrderPoint[];
  top_dishes: DishRank[];
  customers: { unique: number; repeat: number };
  average_fulfilment_minutes: number | null;
  demand: { carts: number; portions: number; value: number };
  menu: {
    dishes: number;
    active: number;
    inactive: number;
    price: { min: number | null; avg: number | null; max: number | null };
    allergens: { name: string; count: number }[];
    dietary_tags: { name: string; count: number }[];
  };
  recent_orders: Order[];
  /** Earned = completed orders, by (UTC) completion day. */
  earnings: {
    today: Amount;
    last_7_days: Amount;
    this_month: Amount;
    lifetime: Amount;
    awaiting_acceptance: Amount;
    in_progress: Amount;
  };
  performance: {
    accepted: number;
    rejected: number;
    acceptance_rate: number | null; // 0..1
    cancelled_after_accepting: number;
    cancelled_by_customer: number;
    cancellation_rate: number | null; // 0..1
    average_accept_minutes: number | null;
    average_prep_minutes: number | null;
  };
  top_customers: { customer_id: string; name: string | null; orders: number; value: number; last_order_at: string }[];
  /** Open orders (placed, accepted, ready), oldest first - at most 20. */
  queue: Order[];
  checklist: { done: number; total: number; steps: { key: ChecklistKey; done: boolean }[] };
};

// --- admin panel -------------------------------------------------------------------

/** A grid zone with its activity (a heat-map tile on the admin overview). */
export type ZoneStats = Zone & { cooks: number; active_dishes: number; orders: number; value: number };

/** GET /api/admin/dashboard - the whole platform. */
export type AdminDashboard = {
  window: { unit: "day" | "month"; periods: number; start: string; end: string };
  users: {
    total: number;
    customers: number;
    cooks: number;
    admins: number;
    new_in_window: number;
    active_sessions: number;
    /** Cook applications waiting for an admin's decision. */
    pending_cook_applications: number;
  };
  signups: { period: string; count: number }[];
  orders: OrderStats;
  order_series: OrderPoint[];
  top_cooks: { cook_id: string; name: string | null; orders: number; value: number }[];
  top_dishes: DishRank[];
  zones: ZoneStats[];
  menu: CookDashboard["menu"];
  carts: { carts: number; portions: number; value: number; guest_carts: number; account_carts: number };
};

/** One account in the back office (GET /api/admin/users). */
export type AdminUser = {
  id: string;
  email: string;
  display_name: string | null;
  area: string | null;
  roles: string[];
  created_at: string;
  last_login_at: string | null;
  orders_placed: number;
  orders_received: number;
  verified_at: string | null; // cooks: when the kitchen was verified
  cook_application: CookApplicationStatus | null; // null: never applied to cook
};

/** Where a cook application stands: an admin accepts or rejects a pending one. */
export type CookApplicationStatus = "pending" | "accepted" | "rejected";

/** One cook application in the back office (GET /api/admin/cook-applications). */
export type CookApplication = {
  user_id: string;
  email: string;
  display_name: string | null;
  area: string | null;
  bio: string | null;
  headline: string;
  specialties: string[];
  zone: Zone | null;
  status: CookApplicationStatus;
  submitted_at: string; // the latest (re)submission
  reviewed_at: string | null;
  reviewed_by: string | null; // the deciding admin
  rejection_reason: string | null; // shown to the applicant
};

export type CookApplicationPage = { items: CookApplication[]; total: number; limit: number; offset: number };

/** POST/DELETE /api/admin/cooks/{id}/verification. */
export type CookVerification = {
  user_id: string;
  verified: boolean;
  verified_at: string | null;
  verified_by: string | null;
};

export type AdminUserPage = { items: AdminUser[]; total: number; limit: number; offset: number };

export type EarningsGroup = "day" | "week" | "month";

export type EarningsSummary = {
  earned: number;
  orders: number;
  portions: number;
  average_order_value: number;
  cancelled_orders: number;
  cancelled_value: number;
  rejected_orders: number;
};

/** GET /api/cooks/me/earnings - completed orders by completion day over a range. */
export type CookEarnings = {
  range: { start: string; end: string; days: number; group: EarningsGroup };
  summary: EarningsSummary;
  previous: EarningsSummary;
  /** YYYY-MM-DD (day; a week by its Monday) or YYYY-MM, oldest first, zero-filled. */
  series: { period: string; orders: number; earned: number }[];
  dishes: DishRank[];
  lifetime: Amount;
  awaiting_acceptance: Amount;
  in_progress: Amount;
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
  put: <T>(path: string, json: unknown) =>
    call<T>(path, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(json) }),
  patch: <T>(path: string, json: unknown) =>
    call<T>(path, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(json) }),
  delete: <T>(path: string) => call<T>(path, { method: "DELETE" }),
};
