"use client";

import { EyeOff, Heart, Trash2, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { AddToCartButton } from "@/components/add-to-cart";
import ConfirmDialog from "@/components/confirm-dialog";
import DishArt from "@/components/dish-art";
import DishCard from "@/components/dish-card";
import {
  Avatar,
  Badge,
  ButtonLink,
  EmptyState,
  ErrorBanner,
  PageHeader,
  cx,
  quietButtonClass,
  smallButton,
} from "@/components/ui";
import { ApiError, type Favourite } from "@/lib/api";
import { useFavourites } from "@/lib/favourites";
import { formatMinorUnits } from "@/lib/format";

const GRID = "grid grid-cols-1 gap-5 sm:grid-cols-2 xl:grid-cols-3";

/**
 * /account/favourites (GET /api/me/favourites) - the dishes the customer
 * saved with the heart, newest first, each with "+ Add" straight to the bag
 * (POST /api/me/favourites/{id}/cart: another kitchen's bag asks first, like
 * everywhere). Un-hearting a dish takes it off with an *Undo*. Dishes their
 * cook has hidden since stay listed apart as "not available right now" -
 * they can't go to the bag, and removing one is final (it can't be saved
 * again while hidden), so that asks first. Reloaded on every visit: a cook
 * may have hidden or published a dish meanwhile.
 */
export default function FavouritesPage() {
  const { enabled, items, max, error, lastRemoved, remove, undoRemove, clearLastRemoved, reload } = useFavourites();
  const [removing, setRemoving] = useState<Favourite | null>(null);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  useEffect(() => {
    // Timeout kick-off (react-hooks/set-state-in-effect). An "Undo" left
    // over from a heart tapped on another page does not belong here.
    const kickOff = window.setTimeout(() => {
      clearLastRemoved();
      void reload();
    }, 0);
    return () => window.clearTimeout(kickOff);
  }, [clearLastRemoved, reload]);

  const act = async (request: () => Promise<void>) => {
    setBusy(true);
    setErrors([]);
    try {
      await request();
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
      void reload();
    } finally {
      setBusy(false);
    }
  };

  if (!enabled) {
    return (
      <div className="space-y-6">
        <PageHeader size="compact" title="Favourites" />
        <EmptyState icon={<Heart className="h-6 w-6" />} title="Favourites are for shoppers">
          Only customer accounts can save dishes.
        </EmptyState>
      </div>
    );
  }

  const available = items?.filter((item) => item.available) ?? [];
  const hidden = items?.filter((item) => !item.available) ?? [];
  const full = items !== null && max !== null && items.length >= max;

  return (
    <div className="space-y-6">
      <PageHeader
        size="compact"
        title="Favourites"
        lead="Dishes you've saved - add one to your bag in a tap."
        actions={
          items !== null &&
          items.length > 0 && (
            <ButtonLink href="/dishes" variant="ghost" className={smallButton}>
              Browse dishes
            </ButtonLink>
          )
        }
      />

      <ErrorBanner lines={[...(error ? [error] : []), ...errors]} />

      {lastRemoved && (
        <div
          role="status"
          className="animate-rise flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-line bg-surface px-4 py-3 text-sm text-ink-muted shadow-card"
        >
          <p className="min-w-0">
            Removed <span className="font-semibold text-ink">{lastRemoved.dish.name}</span> from your favourites.
          </p>
          <div className="flex items-center gap-1">
            <button
              type="button"
              disabled={busy}
              onClick={() => void act(undoRemove)}
              className={cx(quietButtonClass, smallButton, "font-semibold text-brand")}
            >
              Undo
            </button>
            <button
              type="button"
              onClick={clearLastRemoved}
              aria-label="Dismiss"
              className="flex h-9 w-9 items-center justify-center rounded-full text-ink-soft hover:bg-muted hover:text-ink"
            >
              <X className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      )}

      {items === null ? (
        !error && (
          <div className={GRID} aria-busy="true">
            {[0, 1, 2].map((key) => (
              <div key={key} className="h-80 animate-pulse rounded-3xl bg-muted" />
            ))}
          </div>
        )
      ) : items.length === 0 ? (
        <EmptyState
          icon={<Heart className="h-6 w-6" />}
          title="No favourites yet"
          action={<ButtonLink href="/dishes">Browse dishes</ButtonLink>}
        >
          Tap the heart on any dish to keep it here - then add it to your bag in one tap.
        </EmptyState>
      ) : (
        <>
          <p className="text-sm text-ink-muted">
            <span className="font-semibold text-ink">{items.length}</span> of {max} saved
            {hidden.length > 0 && ` · ${hidden.length} not available right now`}
            {full && " · your list is full - remove a dish to save another"}
          </p>

          {available.length > 0 && (
            <ul className={GRID}>
              {available.map((favourite) => (
                <li key={favourite.dish.id}>
                  <DishCard
                    dish={favourite.dish}
                    action={
                      <AddToCartButton
                        dish={favourite.dish}
                        source="favourites"
                        // Refused (e.g. hidden a moment ago): show the list as it is now.
                        onDone={(added) => {
                          if (!added) void reload();
                        }}
                      />
                    }
                  />
                </li>
              ))}
            </ul>
          )}

          {hidden.length > 0 && (
            <section aria-labelledby="hidden-favourites" className="space-y-4">
              <div>
                <h2 id="hidden-favourites" className="font-display text-lg font-semibold text-ink">
                  Not available right now
                </h2>
                <p className="mt-0.5 text-sm text-ink-muted">
                  Their cooks have taken these off the menu for now. They stay here and can be ordered again once
                  the cook brings them back.
                </p>
              </div>
              <ul className={GRID}>
                {hidden.map((favourite) => (
                  <li key={favourite.dish.id}>
                    <HiddenFavourite favourite={favourite} onRemove={() => setRemoving(favourite)} />
                  </li>
                ))}
              </ul>
            </section>
          )}
        </>
      )}

      {removing && (
        <ConfirmDialog
          title="Remove from favourites?"
          confirmLabel="Remove"
          tone="danger"
          busy={busy}
          onConfirm={() =>
            void act(async () => {
              await remove(removing.dish.id);
              setRemoving(null);
            })
          }
          onCancel={() => setRemoving(null)}
        >
          {removing.dish.name} is off the menu right now, so you can&apos;t save it again until{" "}
          {removing.dish.cook_name ?? "its cook"} brings it back.
        </ConfirmDialog>
      )}
    </div>
  );
}

/**
 * A saved dish its cook has hidden: dimmed plate art, what it was, whose it
 * is - no link to the dish page (hidden dishes aren't public) and no "+ Add".
 */
function HiddenFavourite({ favourite, onRemove }: { favourite: Favourite; onRemove: () => void }) {
  const { dish } = favourite;
  return (
    <article className="flex h-full flex-col overflow-hidden rounded-3xl border border-dashed border-line-strong bg-surface">
      <div className="relative">
        <DishArt dish={dish} rounded="rounded-none" className="aspect-[4/3] opacity-45 grayscale" />
        <div className="absolute left-3 top-3">
          <Badge tone="saffron">
            <EyeOff className="h-3 w-3" aria-hidden="true" /> Not available
          </Badge>
        </div>
      </div>
      <div className="flex flex-1 flex-col p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <h3 className="font-display text-lg font-semibold leading-snug tracking-tight text-ink-muted">
            {dish.name}
          </h3>
          <p className="shrink-0 font-display text-lg font-semibold tabular-nums text-ink-soft">
            {formatMinorUnits(dish.price)}
          </p>
        </div>
        <p className="mt-1.5 text-sm leading-relaxed text-ink-muted">Hidden by the cook - it can&apos;t go in your bag for now.</p>
        <div className="mt-auto flex items-center justify-between gap-3 border-t border-line pt-3 text-xs">
          <Link
            href={`/cooks/${dish.cook_id}`}
            className="flex min-w-0 items-center gap-2 font-medium text-ink hover:text-brand"
          >
            <Avatar name={dish.cook_name} size="sm" className="h-6 w-6 text-[10px]" />
            <span className="truncate">{dish.cook_name ?? "Home cook"}</span>
          </Link>
          <button type="button" onClick={onRemove} className={cx(quietButtonClass, smallButton, "-mr-2 shrink-0")}>
            <Trash2 className="h-3.5 w-3.5" aria-hidden="true" /> Remove
          </button>
        </div>
      </div>
    </article>
  );
}
