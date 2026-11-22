/**
 * Review vocabulary shared by server and client components. (A plain module on
 * purpose: a Server Component importing a value from a "use client" file gets
 * a client reference, not the value.)
 */

/** Reviews fetched per page: the first page is server-rendered, "Show more" adds the next. */
export const REVIEWS_PAGE_SIZE = 4;

/** Longest review text (mirrors the backend's COMMENT_MAX_LENGTH). */
export const REVIEW_MAX_LENGTH = 1000;

/** What each star means - shown while choosing a rating. */
export const RATING_LABELS: Record<number, string> = {
  1: "Poor",
  2: "Fair",
  3: "Good",
  4: "Very good",
  5: "Excellent",
};

/** 4.666 -> "4.7" (one decimal, like most stores). */
export function formatAverage(average: number | null): string {
  return average === null ? "–" : average.toFixed(1);
}

export function reviewCount(count: number): string {
  return `${count} ${count === 1 ? "review" : "reviews"}`;
}

/** Longest cook reply (mirrors the backend's REPLY_MAX_LENGTH). */
export const REPLY_MAX_LENGTH = 1000;

/** One-tap starters for a cook's reply, by how the review went (the cook edits before posting). */
export function replyStarters(rating: number): string[] {
  return rating >= 4
    ? ["Thank you so much - see you next time!", "So glad you enjoyed it - thanks for ordering!"]
    : [
        "Thank you for the honest feedback - I'll work on it.",
        "Sorry it wasn't right this time - I'd love another chance to cook for you.",
      ];
}
