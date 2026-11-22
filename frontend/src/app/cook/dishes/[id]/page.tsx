"use client";

import { ArrowLeft, ExternalLink, Trash2 } from "lucide-react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import ConfirmDialog from "@/components/confirm-dialog";
import DishForm from "@/components/dish-form";
import { Badge, ButtonLink, ErrorBanner, PageHeader, Spinner, cx, dangerButtonClass, smallButton } from "@/components/ui";
import { api, ApiError, type Dish } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useKitchen } from "@/lib/kitchen-context";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

/** /cook/dishes/{id} - edit one of my dishes (GET/PATCH/DELETE /api/me/dishes/{id}). */
export default function EditDishPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();
  const { user } = useSession();
  const { profile } = useKitchen();
  const { data: dish, error } = useApi<Dish>(`/me/dishes/${id}`);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState<string | null>(null);

  const remove = async () => {
    setDeleting(true);
    try {
      await api.delete(`/me/dishes/${id}`);
      router.push("/cook/dishes?deleted=1");
    } catch (cause) {
      setDeleteError(cause instanceof ApiError ? cause.message : "Could not reach the API");
      setConfirmDelete(false);
      setDeleting(false);
    }
  };

  if (!dish) {
    return error ? (
      <div className="space-y-4">
        <ErrorBanner lines={[error]} />
        <ButtonLink href="/cook/dishes" variant="ghost">
          Back to the menu
        </ButtonLink>
      </div>
    ) : (
      <div className="flex justify-center py-16 text-ink-muted">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <Link href="/cook/dishes" className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Menu
      </Link>
      <PageHeader
        size="compact"
        eyebrow={`Added ${formatDate(dish.created_at)}`}
        title={dish.name}
        actions={
          <>
            <Badge tone={dish.active ? "herb" : "neutral"} className="px-3 py-1 text-sm">
              {dish.active ? "Public" : "Private"}
            </Badge>
            {dish.active && (
              <Link href={`/dishes/${dish.id}`} className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline">
                View on the menu <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
              </Link>
            )}
          </>
        }
      />
      <ErrorBanner lines={deleteError ? [deleteError] : []} />

      <DishForm
        key={dish.updated_at}
        dish={dish}
        cookName={user?.display_name ?? null}
        zone={profile?.zone ?? null}
        cancelHref="/cook/dishes"
        onSubmit={async (values) => {
          await api.patch<Dish>(`/me/dishes/${dish.id}`, values);
          router.push(`/cook/dishes?saved=${dish.id}`);
        }}
      />

      <section className="flex flex-col gap-4 rounded-3xl border border-danger/25 p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
        <div>
          <h2 className="font-semibold text-ink">Delete this dish</h2>
          <p className="text-sm text-ink-muted">
            Gone for good - to take it off the menu for a while, make it private instead. Past orders keep their copy.
          </p>
        </div>
        <button type="button" onClick={() => setConfirmDelete(true)} className={cx(dangerButtonClass, smallButton, "shrink-0")}>
          <Trash2 className="h-4 w-4" aria-hidden="true" /> Delete dish
        </button>
      </section>

      {confirmDelete && (
        <ConfirmDialog
          title={`Delete ${dish.name}?`}
          confirmLabel="Delete dish"
          tone="danger"
          busy={deleting}
          onCancel={() => setConfirmDelete(false)}
          onConfirm={() => void remove()}
        >
          It leaves your menu and any shopper&apos;s bag. Orders already placed keep their copy of it. This can&apos;t be
          undone.
        </ConfirmDialog>
      )}
    </div>
  );
}
