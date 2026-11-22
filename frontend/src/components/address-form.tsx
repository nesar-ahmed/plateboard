"use client";

import { Briefcase, House, MapPin } from "lucide-react";
import { useState } from "react";

import {
  ErrorBanner,
  Field,
  Select,
  Spinner,
  cx,
  darkButtonClass,
  inputClass,
  quietButtonClass,
  textareaClass,
} from "@/components/ui";
import { api, ApiError, type Address, type AddressInput } from "@/lib/api";
import { useZones } from "@/lib/use-zones";

const LABELS = [
  { value: "Home", icon: House },
  { value: "Work", icon: Briefcase },
  { value: "Other", icon: MapPin },
];

type Draft = Omit<AddressInput, "label" | "zone"> & { label: string; zone: string };

/**
 * Create (POST /api/me/addresses) or, with `address`, edit (PATCH
 * /api/me/addresses/{id}) an address. Server validation (422) is shown next
 * to the field it names. A first address is always the default, and the
 * default can only be *moved* (to another address), so the checkbox only
 * appears when it can do something.
 */
export default function AddressForm({
  address,
  defaultRecipient,
  hasAddresses,
  onSaved,
  onCancel,
}: {
  address?: Address;
  defaultRecipient?: string | null;
  hasAddresses: boolean;
  onSaved: (address: Address) => void;
  onCancel?: () => void;
}) {
  const { zones } = useZones();
  const [draft, setDraft] = useState<Draft>(
    address
      ? {
          label: address.label ?? "",
          recipient: address.recipient,
          phone: address.phone,
          line1: address.line1,
          line2: address.line2 ?? "",
          city: address.city,
          postal_code: address.postal_code ?? "",
          instructions: address.instructions ?? "",
          zone: address.zone?.slug ?? "",
          is_default: address.is_default,
        }
      : {
          label: "Home",
          recipient: defaultRecipient ?? "",
          phone: "",
          line1: "",
          line2: "",
          city: "",
          postal_code: "",
          instructions: "",
          zone: "",
          is_default: !hasAddresses,
        },
  );
  const [busy, setBusy] = useState(false);
  const [banner, setBanner] = useState<string[]>([]);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  const set = <K extends keyof Draft>(key: K, value: Draft[K]) => setDraft((current) => ({ ...current, [key]: value }));
  const blankToNull = (value: string | null) => (value && value.trim() ? value.trim() : null);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setBanner([]);
    setFieldErrors({});
    const body = {
      label: blankToNull(draft.label),
      recipient: draft.recipient,
      phone: draft.phone,
      line1: draft.line1,
      line2: blankToNull(draft.line2),
      city: draft.city,
      postal_code: blankToNull(draft.postal_code),
      instructions: blankToNull(draft.instructions),
      zone: draft.zone || null,
      is_default: draft.is_default,
    } satisfies AddressInput;
    try {
      const saved = address
        ? await api.patch<Address>(`/me/addresses/${address.id}`, {
            ...body,
            // PATCH only moves the default *to* this address, never away.
            is_default: draft.is_default && !address.is_default ? true : undefined,
          })
        : await api.post<Address>("/me/addresses", body);
      onSaved(saved);
    } catch (cause) {
      if (cause instanceof ApiError && cause.fieldErrors.length > 0) {
        setFieldErrors(Object.fromEntries(cause.fieldErrors.map((error) => [error.field, error.message])));
        setBanner(["Please check the highlighted fields."]);
      } else {
        setBanner(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
      }
    } finally {
      setBusy(false);
    }
  };

  const text = (key: keyof Draft) => ({
    value: String(draft[key] ?? ""),
    onChange: (event: React.ChangeEvent<HTMLInputElement>) => set(key, event.target.value as never),
    "aria-invalid": fieldErrors[key] ? true : undefined,
    className: cx(inputClass, fieldErrors[key] && "border-danger"),
  });

  return (
    <form onSubmit={submit} className="space-y-5" aria-label={address ? "Edit address" : "New address"}>
      <ErrorBanner lines={banner} />

      <fieldset>
        <legend className="mb-2 text-sm font-medium text-ink">Save as</legend>
        <div className="flex flex-wrap gap-2">
          {LABELS.map(({ value, icon: Icon }) => (
            <button
              key={value}
              type="button"
              aria-pressed={draft.label === value}
              onClick={() => set("label", value)}
              className={cx(
                "inline-flex h-9 items-center gap-1.5 rounded-full border px-3.5 text-sm font-medium transition-colors",
                draft.label === value
                  ? "border-ink bg-ink text-canvas"
                  : "border-line-strong bg-surface text-ink-muted hover:text-ink",
              )}
            >
              <Icon className="h-4 w-4" aria-hidden="true" /> {value}
            </button>
          ))}
        </div>
      </fieldset>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Field label="Recipient" error={fieldErrors.recipient}>
          <input {...text("recipient")} autoComplete="name" required maxLength={80} />
        </Field>
        <Field label="Phone" error={fieldErrors.phone} hint="So the cook can reach you.">
          <input {...text("phone")} type="tel" autoComplete="tel" required maxLength={30} placeholder="+1 555 0100" />
        </Field>
      </div>
      <Field label="Street address" error={fieldErrors.line1}>
        <input {...text("line1")} autoComplete="address-line1" required maxLength={120} placeholder="12 Lantern Lane" />
      </Field>
      <Field label="Apartment, floor, building" optional error={fieldErrors.line2}>
        <input {...text("line2")} autoComplete="address-line2" maxLength={120} />
      </Field>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-[1fr_160px]">
        <Field label="City" error={fieldErrors.city}>
          <input {...text("city")} autoComplete="address-level2" required maxLength={80} />
        </Field>
        <Field label="Postal code" optional error={fieldErrors.postal_code}>
          <input {...text("postal_code")} autoComplete="postal-code" maxLength={20} />
        </Field>
      </div>
      <Field label="Neighbourhood" optional hint="Helps match you with cooks nearby." error={fieldErrors.zone}>
        <Select value={draft.zone} onChange={(event) => set("zone", event.target.value)} disabled={!zones}>
          <option value="">Not sure</option>
          {(zones ?? []).map((zone) => (
            <option key={zone.slug} value={zone.slug}>
              {zone.name}
            </option>
          ))}
        </Select>
      </Field>
      <Field label="Delivery instructions" optional error={fieldErrors.instructions}>
        <textarea
          value={draft.instructions ?? ""}
          onChange={(event) => set("instructions", event.target.value)}
          maxLength={200}
          rows={2}
          placeholder="Ring twice, leave with the concierge…"
          className={textareaClass}
        />
      </Field>

      {hasAddresses && !address?.is_default && (
        <label className="flex items-center gap-2.5 text-sm text-ink">
          <input
            type="checkbox"
            checked={draft.is_default}
            onChange={(event) => set("is_default", event.target.checked)}
            className="h-4 w-4 rounded accent-[var(--brand)]"
          />
          Make this my default address
        </label>
      )}

      <div className="flex flex-wrap gap-2 pt-1">
        <button type="submit" disabled={busy} className={darkButtonClass}>
          {busy && <Spinner />} {address ? "Save changes" : "Save address"}
        </button>
        {onCancel && (
          <button type="button" onClick={onCancel} className={quietButtonClass}>
            Cancel
          </button>
        )}
      </div>
    </form>
  );
}
