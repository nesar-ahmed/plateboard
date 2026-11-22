"use client";

import { Heart } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";

import { Spinner, cx } from "@/components/ui";
import { ApiError } from "@/lib/api";
import { useFavourites } from "@/lib/favourites";
import { useSession } from "@/lib/session";

/** How long a refusal ("your favourites are full") stays next to the heart. */
const NOTICE_MS = 5000;

type Notice = { text: string; manage: boolean };

function noticeFor(cause: unknown): Notice {
  if (cause instanceof ApiError) {
    if (cause.code === "favourites_limit") return { text: cause.message, manage: true };
    // Hidden or deleted since the page was loaded.
    if (cause.status === 404) return { text: "This dish isn't on the menu any more.", manage: false };
    return { text: cause.message, manage: false };
  }
  return { text: "Could not reach the API", manage: false };
}

/**
 * The heart: save a dish to the signed-in customer's favourites, or take it
 * off again (`PUT` / `DELETE /api/me/favourites/{id}`, both idempotent).
 *
 * * `overlay` - round, over a dish card's plate art (next to "+ Add");
 * * `pill` - "Save" / "Saved" with a label, for the dish page.
 *
 * Guests get the heart too: it sends them to log in and back here. It is
 * not shown on the cook's own dishes (they cannot be saved - the "+ Add"
 * spot says "Your dish") nor to accounts that are not customers. A refusal
 * - a full list, a dish hidden meanwhile - shows in a small bubble beside
 * the heart for a few seconds.
 */
export default function FavouriteButton({
  dish,
  variant = "overlay",
  className,
}: {
  dish: { id: string; name: string; cook_id: string };
  variant?: "overlay" | "pill";
  className?: string;
}) {
  const router = useRouter();
  const { user, checked } = useSession();
  const favourites = useFavourites();
  const [pending, setPending] = useState(false);
  const [justSaved, setJustSaved] = useState(false);
  const [notice, setNotice] = useState<Notice | null>(null);

  useEffect(() => {
    if (!notice) return;
    const timer = window.setTimeout(() => setNotice(null), NOTICE_MS);
    return () => window.clearTimeout(timer);
  }, [notice]);

  // Wait for the session: the heart must not flash on the cook's own dish.
  if (!checked) return null;
  if (user && (user.id === dish.cook_id || !favourites.enabled)) return null;

  const saved = favourites.isSaved(dish.id);
  const loading = !!user && favourites.items === null;

  const toggle = async () => {
    if (!user) {
      const here = `${window.location.pathname}${window.location.search}`;
      router.push(`/login?next=${encodeURIComponent(here)}`);
      return;
    }
    setPending(true);
    setNotice(null);
    try {
      if (saved) {
        await favourites.remove(dish.id);
        setJustSaved(false);
      } else {
        await favourites.save(dish.id);
        setJustSaved(true);
      }
    } catch (cause) {
      setNotice(noticeFor(cause));
    } finally {
      setPending(false);
    }
  };

  const icon = pending ? (
    <Spinner />
  ) : (
    <Heart
      className={cx(variant === "pill" ? "h-4 w-4" : "h-[18px] w-[18px]", justSaved && saved && "animate-pop")}
      fill={saved ? "currentColor" : "none"}
      strokeWidth={2.25}
      aria-hidden="true"
    />
  );

  return (
    <div className={cx("relative", className)}>
      <button
        type="button"
        disabled={pending || loading}
        onClick={() => void toggle()}
        aria-pressed={saved}
        aria-label={`Save ${dish.name} to favourites`}
        title={saved ? "Saved to your favourites" : "Save to your favourites"}
        className={cx(
          "inline-flex items-center justify-center transition-all active:scale-95 disabled:opacity-60",
          variant === "overlay"
            ? "h-10 w-10 rounded-full bg-surface/90 shadow-lift ring-1 ring-black/5 backdrop-blur"
            : "h-10 gap-2 rounded-full border px-4 text-sm font-medium",
          variant === "overlay" && (saved ? "text-brand" : "text-ink hover:text-brand"),
          variant === "pill" &&
            (saved
              ? "border-brand/30 bg-brand-soft text-brand"
              : "border-line bg-surface text-ink hover:border-line-strong"),
        )}
      >
        {icon}
        {variant === "pill" && (saved ? "Saved" : "Save")}
      </button>
      {notice && (
        <div
          role="status"
          className="animate-rise absolute right-0 top-full z-30 mt-2 w-64 rounded-2xl bg-ink px-4 py-3 text-left text-xs leading-relaxed text-canvas shadow-pop"
        >
          {notice.text}
          {notice.manage && (
            <Link href="/account/favourites" className="mt-1 block font-semibold underline underline-offset-2">
              Manage favourites
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
