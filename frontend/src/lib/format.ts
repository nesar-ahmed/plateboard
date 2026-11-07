/** Display helpers shared by the pages. */

/**
 * Minor units -> major units for display (8900 -> "89.00").
 * The currency symbol is deliberately omitted until the product decides one.
 */
export function formatMinorUnits(minor: number): string {
  return (minor / 100).toLocaleString("en-US", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}

/**
 * "89.00" -> 8900 minor units. Throws a field-style message on bad input;
 * the forms surface it exactly like a server 422.
 */
export function parsePriceToMinorUnits(input: string): number {
  const trimmed = input.trim();
  const value = Number(trimmed);
  if (trimmed === "" || !Number.isFinite(value)) {
    throw new Error("enter a price, e.g. 8.90");
  }
  const minor = Math.round(value * 100);
  if (minor <= 0) {
    throw new Error("price must be positive");
  }
  return minor;
}

/** "a, b , c" -> ["a", "b", "c"]; blanks dropped so the API gets clean lists. */
export function splitList(input: string): string[] {
  return input
    .split(",")
    .map((part) => part.trim())
    .filter((part) => part.length > 0);
}

/** Comma-separated list for rendering, "—" when empty. */
export function joinListOrDash(items: string[]): string {
  return items.length > 0 ? items.join(", ") : "—";
}
