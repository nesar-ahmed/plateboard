"use client";

import { MapPin, Pencil, Phone, Plus, Star, Trash2 } from "lucide-react";
import { useState } from "react";

import AddressForm from "@/components/address-form";
import ConfirmDialog from "@/components/confirm-dialog";
import {
  Badge,
  EmptyState,
  ErrorBanner,
  PageHeader,
  cx,
  darkButtonClass,
  quietButtonClass,
  smallButton,
} from "@/components/ui";
import { api, ApiError, type Address } from "@/lib/api";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";

const MAX_ADDRESSES = 10;

/** /account/addresses - the address book checkout picks from. */
export default function AddressesPage() {
  const { user } = useSession();
  const { data: addresses, error, reload } = useApi<Address[]>("/me/addresses");
  const [editing, setEditing] = useState<Address | "new" | null>(null);
  const [deleting, setDeleting] = useState<Address | null>(null);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const act = async (request: () => Promise<unknown>) => {
    setBusy(true);
    setErrors([]);
    try {
      await request();
      await reload();
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
    } finally {
      setBusy(false);
    }
  };

  const full = (addresses?.length ?? 0) >= MAX_ADDRESSES;

  return (
    <div className="space-y-6">
      <PageHeader
        size="compact"
        title="Addresses"
        lead="Where your food goes. Your default is picked automatically at checkout."
        actions={
          addresses &&
          addresses.length > 0 &&
          editing === null && (
            <button type="button" disabled={full} onClick={() => setEditing("new")} className={darkButtonClass}>
              <Plus className="h-4 w-4" /> Add address
            </button>
          )
        }
      />

      <ErrorBanner lines={[...(error ? [error] : []), ...errors]} />
      {full && <p className="text-sm text-ink-soft">You have {MAX_ADDRESSES} addresses - remove one to add another.</p>}

      {editing !== null && (
        <section className="animate-rise rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
          <h2 className="mb-5 font-display text-xl font-semibold text-ink">
            {editing === "new" ? "New address" : `Edit ${editing.label ?? "address"}`}
          </h2>
          <AddressForm
            key={editing === "new" ? "new" : editing.id}
            address={editing === "new" ? undefined : editing}
            defaultRecipient={user?.display_name}
            hasAddresses={(addresses?.length ?? 0) > 0}
            onCancel={() => setEditing(null)}
            onSaved={() => {
              setEditing(null);
              void reload();
            }}
          />
        </section>
      )}

      {!addresses ? (
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2" aria-busy="true">
          {[0, 1].map((key) => (
            <div key={key} className="h-48 animate-pulse rounded-3xl bg-muted" />
          ))}
        </div>
      ) : addresses.length === 0 && editing === null ? (
        <EmptyState
          icon={<MapPin className="h-6 w-6" />}
          title="No addresses yet"
          action={
            <button type="button" onClick={() => setEditing("new")} className={darkButtonClass}>
              <Plus className="h-4 w-4" /> Add your first address
            </button>
          }
        >
          Save a delivery address once and checkout becomes one tap.
        </EmptyState>
      ) : (
        <ul className="grid grid-cols-1 gap-4 md:grid-cols-2">
          {addresses.map((address) => (
            <li
              key={address.id}
              className={cx(
                "flex flex-col rounded-3xl border bg-surface p-5 shadow-card sm:p-6",
                address.is_default ? "border-ink" : "border-line",
              )}
            >
              <div className="flex items-center justify-between gap-3">
                <p className="flex items-center gap-2 font-display text-lg font-semibold text-ink">
                  {address.label ?? "Address"}
                  {address.is_default && <Badge tone="night">Default</Badge>}
                </p>
                {address.zone && (
                  <span className="flex items-center gap-1 text-xs text-ink-soft">
                    <MapPin className="h-3.5 w-3.5" aria-hidden="true" /> {address.zone.name}
                  </span>
                )}
              </div>
              <div className="mt-3 flex-1 text-sm leading-relaxed text-ink-muted">
                <p className="font-medium text-ink">{address.recipient}</p>
                <p>
                  {address.line1}
                  {address.line2 && `, ${address.line2}`}
                </p>
                <p>{[address.postal_code, address.city].filter(Boolean).join(" ")}</p>
                <p className="mt-2 flex items-center gap-1.5 text-xs">
                  <Phone className="h-3 w-3" aria-hidden="true" /> {address.phone}
                </p>
                {address.instructions && <p className="mt-2 text-xs italic">“{address.instructions}”</p>}
              </div>
              <div className="mt-5 flex flex-wrap gap-1 border-t border-line pt-4">
                <button type="button" onClick={() => setEditing(address)} className={cx(quietButtonClass, smallButton)}>
                  <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> Edit
                </button>
                {!address.is_default && (
                  <button
                    type="button"
                    disabled={busy}
                    onClick={() => void act(() => api.patch(`/me/addresses/${address.id}`, { is_default: true }))}
                    className={cx(quietButtonClass, smallButton)}
                  >
                    <Star className="h-3.5 w-3.5" aria-hidden="true" /> Make default
                  </button>
                )}
                <button
                  type="button"
                  onClick={() => setDeleting(address)}
                  className={cx(quietButtonClass, smallButton, "ml-auto hover:bg-danger-soft hover:text-danger")}
                  aria-label={`Delete ${address.label ?? "address"}`}
                >
                  <Trash2 className="h-3.5 w-3.5" aria-hidden="true" /> Delete
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}

      {deleting && (
        <ConfirmDialog
          title={`Delete ${deleting.label ?? "this address"}?`}
          confirmLabel="Delete address"
          tone="danger"
          busy={busy}
          onCancel={() => setDeleting(null)}
          onConfirm={() => {
            const target = deleting;
            setDeleting(null);
            void act(() => api.delete(`/me/addresses/${target.id}`));
          }}
        >
          {deleting.line1}, {deleting.city}. Past orders keep their copy of the address.
          {deleting.is_default && " Your most recently added address becomes the default."}
        </ConfirmDialog>
      )}
    </div>
  );
}
