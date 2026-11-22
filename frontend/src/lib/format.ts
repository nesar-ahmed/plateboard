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

/**
 * Optional price filter input -> minor units: blank -> null, "4.5" -> 450.
 * Unlike parsePriceToMinorUnits, zero is allowed (a lower bound of 0 is
 * meaningful); negative or non-numeric input throws a field-style message.
 */
export function parseOptionalPriceToMinorUnits(input: string): number | null {
  const trimmed = input.trim();
  if (trimmed === "") return null;
  const value = Number(trimmed);
  if (!Number.isFinite(value) || value < 0) {
    throw new Error("prices must be numbers of 0 or more, e.g. 8.90");
  }
  return Math.round(value * 100);
}

/** Minor units -> editable input text (890 -> "8.90"); null -> "". */
export function minorUnitsToInput(minor: number | null): string {
  return minor === null ? "" : (minor / 100).toFixed(2);
}

/** Grid distance for people: 0 -> "in this zone", 1 -> "1 step away". */
export function formatDistance(steps: number): string {
  if (steps === 0) return "in this zone";
  return `${steps} ${steps === 1 ? "step" : "steps"} away`;
}

/** "8 Nov 2026" - dates in the user's locale. */
export function formatDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" });
}

/** "8 Nov 2026, 14:05". */
export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/** "3 min ago", "2 h ago", "yesterday", else a date - for activity feeds. */
export function formatRelative(iso: string, now: number = Date.now()): string {
  const minutes = Math.round((now - new Date(iso).getTime()) / 60000);
  if (minutes < 1) return "just now";
  if (minutes < 60) return `${minutes} min ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours} h ago`;
  if (hours < 48) return "yesterday";
  return formatDate(iso);
}

/** A badge count, capped like most apps do: 7 -> "7", 120 -> "99+". */
export function formatCount(count: number): string {
  return count > 99 ? "99+" : String(count);
}

/** Short, human order reference: "#0CA946F8". */
export function orderRef(id: string): string {
  return `#${id.slice(0, 8).toUpperCase()}`;
}

/** Invoice number derived from the order id: "INV-0CA946F8". */
export function invoiceNumber(id: string): string {
  return `INV-${id.slice(0, 8).toUpperCase()}`;
}
