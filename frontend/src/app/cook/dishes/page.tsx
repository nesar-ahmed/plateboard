"use client";

import { CircleCheck, EyeOff, Pencil, Plus, Trash2, UtensilsCrossed } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useState } from "react";

import ConfirmDialog from "@/components/confirm-dialog";
import DishArt from "@/components/dish-art";
import {
  Badge,
  ButtonLink,
  EmptyState,
  ErrorBanner,
  PageHeader,
  cx,
  ghostButtonClass,
  quietButtonClass,
  smallButton,
} from "@/components/ui";
import { api, ApiError, type CookEarnings, type Dish } from "@/lib/api";
import { formatMinorUnits } from "@/lib/format";
import { plural, utcDaysAgo } from "@/lib/kitchen";
import { useApi } from "@/lib/use-api";

const FILTERS = [
  { key: "all", label: "All" },
  { key: "public", label: "Public" },
  { key: "private", label: "Private" },
] as const;

export default function MenuPage() {
  return (
    <Suspense fallback={null}>
      <Menu />
    </Suspense>
  );
}

/**
 * /cook/dishes - the cook's whole menu (GET /api/me/dishes), public and
 * private. The switch on each card publishes / hides a dish in place (PATCH
 * `active`); sales come from the last 12 months of earnings.
 */
function Menu() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const filter = FILTERS.find((candidate) => candidate.key === params.get("show"))?.key ?? "all";
  const savedId = params.get("saved");
  const deleted = params.get("deleted") === "1";
  const { data: dishes, error, setData } = useApi<Dish[]>("/me/dishes");
  const [salesStart] = useState(() => utcDaysAgo(364));
  const { data: sales } = useApi<CookEarnings>(`/cooks/me/earnings?start=${salesStart}&group=month`);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [errors, setErrors] = useState<string[]>([]);
  const [deleting, setDeleting] = useState<Dish | null>(null);

  const sold = new Map((sales?.dishes ?? []).map((dish) => [dish.dish_id, dish.quantity]));
  const counts = {
    all: dishes?.length ?? 0,
    public: dishes?.filter((dish) => dish.active).length ?? 0,
    private: dishes?.filter((dish) => !dish.active).length ?? 0,
  };
  const shown = (dishes ?? []).filter((dish) =>
    filter === "all" ? true : filter === "public" ? dish.active : !dish.active,
  );
  const saved = savedId ? dishes?.find((dish) => dish.id === savedId) : undefined;

  const show = (key: string) => {
    const next = new URLSearchParams();
    if (key !== "all") next.set("show", key);
    router.replace(next.size ? `${pathname}?${next.toString()}` : pathname, { scroll: false });
  };

  const replace = (updated: Dish) =>
    setData((current) => (current ?? []).map((dish) => (dish.id === updated.id ? updated : dish)));

  const toggle = async (dish: Dish) => {
    setBusyId(dish.id);
    setErrors([]);
    try {
      replace(await api.patch<Dish>(`/me/dishes/${dish.id}`, { active: !dish.active }));
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
    } finally {
      setBusyId(null);
    }
  };

  const remove = async (dish: Dish) => {
    setBusyId(dish.id);
    setErrors([]);
    try {
      await api.delete(`/me/dishes/${dish.id}`);
      setData((current) => (current ?? []).filter((held) => held.id !== dish.id));
      setDeleting(null);
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
      setDeleting(null);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <div className="space-y-6">
      <PageHeader
        size="compact"
        title="Menu"
        lead="Everything you cook. Public dishes are on the menu; private ones stay hidden until you publish them."
        actions={
          <ButtonLink href="/cook/dishes/new" variant="dark" className="h-10">
            <Plus className="h-4 w-4" /> Add dish
          </ButtonLink>
        }
      />

      {(saved || deleted) && (
        <p role="status" className="animate-rise flex items-center gap-2 rounded-2xl bg-herb-soft px-4 py-3 text-sm text-ink">
          <CircleCheck className="h-4 w-4 shrink-0 text-herb" aria-hidden="true" />
          {deleted
            ? "Dish deleted."
            : saved?.active
              ? `${saved.name} is saved and on the menu.`
              : `${saved?.name} is saved as a private dish.`}
        </p>
      )}
      <ErrorBanner lines={[...(error ? [error] : []), ...errors]} />

      <div role="tablist" aria-label="Show dishes" className="flex gap-1 rounded-full border border-line bg-surface p-1 sm:w-fit">
        {FILTERS.map((candidate) => (
          <button
            key={candidate.key}
            role="tab"
            type="button"
            aria-selected={candidate.key === filter}
            onClick={() => show(candidate.key)}
            className={cx(
              "inline-flex h-9 flex-1 items-center justify-center gap-2 rounded-full px-4 text-sm font-medium transition-colors sm:flex-none",
              candidate.key === filter ? "bg-ink text-canvas" : "text-ink-muted hover:text-ink",
            )}
          >
            {candidate.label}
            {dishes && <span className="text-xs tabular-nums opacity-70">{counts[candidate.key]}</span>}
          </button>
        ))}
      </div>

      {!dishes ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3" aria-busy="true">
          {[0, 1, 2].map((key) => (
            <div key={key} className="h-80 animate-pulse rounded-3xl bg-muted" />
          ))}
        </div>
      ) : dishes.length === 0 ? (
        <EmptyState
          icon={<UtensilsCrossed className="h-6 w-6" />}
          title="Your menu is empty"
          action={<ButtonLink href="/cook/dishes/new">Add your first dish</ButtonLink>}
        >
          Add a dish, set a price and publish it - or keep it private while you perfect it.
        </EmptyState>
      ) : shown.length === 0 ? (
        <EmptyState icon={<EyeOff className="h-6 w-6" />} title={`No ${filter} dishes`}>
          {filter === "private"
            ? "Every dish is on the menu. Make one private to hide it for a while."
            : "Publish a private dish to put it on the menu."}
        </EmptyState>
      ) : (
        <ul className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {shown.map((dish) => (
            <li key={dish.id}>
              <MenuCard
                dish={dish}
                sold={sold.get(dish.id) ?? 0}
                highlight={dish.id === savedId}
                busy={busyId === dish.id}
                onToggle={() => void toggle(dish)}
                onDelete={() => setDeleting(dish)}
              />
            </li>
          ))}
        </ul>
      )}

      {deleting && (
        <ConfirmDialog
          title={`Delete ${deleting.name}?`}
          confirmLabel="Delete dish"
          tone="danger"
          busy={busyId === deleting.id}
          onCancel={() => setDeleting(null)}
          onConfirm={() => void remove(deleting)}
        >
          It leaves your menu and any shopper&apos;s bag; orders already placed keep their copy. To hide it for a
          while, make it private instead.
        </ConfirmDialog>
      )}
    </div>
  );
}

function MenuCard({
  dish,
  sold,
  highlight,
  busy,
  onToggle,
  onDelete,
}: {
  dish: Dish;
  sold: number;
  highlight: boolean;
  busy: boolean;
  onToggle: () => void;
  onDelete: () => void;
}) {
  return (
    <article
      className={cx(
        "flex h-full flex-col overflow-hidden rounded-3xl border bg-surface shadow-card transition-shadow hover:shadow-lift",
        highlight ? "border-herb ring-4 ring-herb/15" : "border-line",
      )}
    >
      <div className="relative">
        <DishArt
          dish={dish}
          rounded="rounded-none"
          className={cx("aspect-[16/10] transition-opacity", !dish.active && "opacity-50 grayscale-[40%]")}
        />
        <div className="absolute left-3 top-3">
          {dish.active ? (
            <Badge tone="herb" className="bg-surface/90 backdrop-blur">
              <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden="true" /> Public
            </Badge>
          ) : (
            <Badge tone="night">
              <EyeOff className="h-3 w-3" aria-hidden="true" /> Private
            </Badge>
          )}
        </div>
      </div>
      <div className="flex flex-1 flex-col p-4 sm:p-5">
        <div className="flex items-start justify-between gap-3">
          <h2 className="font-display text-lg font-semibold leading-snug tracking-tight text-ink">
            <Link href={`/cook/dishes/${dish.id}`} className="hover:text-brand">
              {dish.name}
            </Link>
          </h2>
          <p className="shrink-0 font-display text-lg font-semibold tabular-nums text-ink">
            {formatMinorUnits(dish.price)}
          </p>
        </div>
        <p className="mt-1 text-xs text-ink-soft">
          {plural(dish.portions, "portion")} per batch · {sold > 0 ? `${sold} sold in the last 12 months` : "not sold yet"}
        </p>
        {dish.description ? (
          <p className="mt-2 line-clamp-2 text-sm text-ink-muted">{dish.description}</p>
        ) : (
          <p className="mt-2 text-sm italic text-saffron">No description yet</p>
        )}
        <p className={cx("mt-3 text-xs", dish.allergens.length ? "text-saffron" : "text-herb")}>
          {dish.allergens.length ? (
            <>
              <span className="font-semibold">Contains:</span> {dish.allergens.join(", ")}
            </>
          ) : (
            "No declared allergens"
          )}
        </p>

        <div className="mt-auto pt-4">
          <div className="flex items-center gap-2 border-t border-line pt-4">
            <label className="mr-auto flex cursor-pointer items-center gap-2.5 text-sm font-medium text-ink">
              <button
                type="button"
                role="switch"
                aria-checked={dish.active}
                aria-label={`Show ${dish.name} on the public menu`}
                disabled={busy}
                onClick={onToggle}
                className={cx(
                  "relative h-6 w-11 shrink-0 rounded-full transition-colors disabled:opacity-50",
                  dish.active ? "bg-herb" : "bg-line-strong",
                )}
              >
                <span
                  className={cx(
                    "absolute top-0.5 h-5 w-5 rounded-full bg-white shadow transition-all",
                    dish.active ? "left-[22px]" : "left-0.5",
                  )}
                />
              </button>
              {dish.active ? "Public" : "Private"}
            </label>
            <Link href={`/cook/dishes/${dish.id}`} className={cx(ghostButtonClass, smallButton)}>
              <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> Edit
            </Link>
            <button
              type="button"
              onClick={onDelete}
              disabled={busy}
              aria-label={`Delete ${dish.name}`}
              className={cx(quietButtonClass, smallButton, "px-3 hover:bg-danger-soft hover:text-danger")}
            >
              <Trash2 className="h-4 w-4" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </article>
  );
}
