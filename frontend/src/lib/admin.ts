/** Admin-panel helpers (no React). */

/** Link to the admin order list filtered by one party; its name rides along for the filter chip. */
export function ordersOf(party: "cook" | "customer", id: string, name: string | null): string {
  const query = new URLSearchParams({ [`${party}_id`]: id });
  if (name) query.set(party, name);
  return `/admin/orders?${query.toString()}`;
}
