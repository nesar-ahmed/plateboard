"use client";

import { BadgeCheck, CircleCheck, ExternalLink, ShieldQuestion, Store, UserRound } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import CookCard from "@/components/cook-card";
import {
  ErrorBanner,
  Field,
  PageHeader,
  Select,
  Spinner,
  cx,
  darkButtonClass,
  inputClass,
  textareaClass,
} from "@/components/ui";
import { api, ApiError, type Availability, type CookProfile, type CookPublic, type User, type Zone } from "@/lib/api";
import { formatDate, splitList } from "@/lib/format";
import { useKitchen } from "@/lib/kitchen-context";
import { useSession } from "@/lib/session";
import { useApi } from "@/lib/use-api";
import { useZones } from "@/lib/use-zones";

/** /cook/profile - what the public cook page shows (PATCH /api/me/profile + PATCH /api/cooks/me). */
export default function KitchenProfilePage() {
  const { user, refresh } = useSession();
  const kitchen = useKitchen();
  const { zones } = useZones();
  // The public card as customers get it: live availability for the preview.
  const card = useApi<CookPublic>(user ? `/cooks/${user.id}` : null);
  // Lives here, not in the form: saving remounts the form (its key).
  const [saved, setSaved] = useState(false);
  if (!user || !kitchen.profile) {
    return (
      <div className="flex justify-center py-16 text-ink-muted">
        <Spinner className="h-6 w-6" />
      </div>
    );
  }
  return (
    <ProfileForm
      key={`${user.updated_at}|${kitchen.profile.updated_at}`}
      user={user}
      profile={kitchen.profile}
      zones={zones}
      availability={card.data?.availability ?? null}
      saved={saved}
      setSaved={setSaved}
      onUserSaved={refresh}
      onProfileSaved={kitchen.setProfile}
    />
  );
}

function ProfileForm({
  user,
  profile,
  zones,
  availability,
  saved,
  setSaved,
  onUserSaved,
  onProfileSaved,
}: {
  user: User;
  profile: CookProfile;
  zones: Zone[] | null;
  availability: Availability | null;
  saved: boolean;
  setSaved: (saved: boolean) => void;
  onUserSaved: () => Promise<unknown>;
  onProfileSaved: (profile: CookProfile) => void;
}) {
  const [displayName, setDisplayName] = useState(user.display_name ?? "");
  const [area, setArea] = useState(user.area ?? "");
  const [bio, setBio] = useState(user.bio ?? "");
  const [headline, setHeadline] = useState(profile.headline);
  const [specialties, setSpecialties] = useState(profile.specialties.join(", "));
  const [zone, setZone] = useState(profile.zone?.slug ?? "");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({});

  // Only changed fields are sent; a blanked optional field is sent as null (= clear).
  const userChanges: Record<string, string | null> = {};
  for (const [field, value, server] of [
    ["display_name", displayName, user.display_name],
    ["bio", bio, user.bio],
    ["area", area, user.area],
  ] as const) {
    const trimmed = value.trim();
    if (trimmed !== (server ?? "")) userChanges[field] = trimmed || null;
  }
  const tags = [...new Set(splitList(specialties).map((tag) => tag.toLowerCase()))];
  const kitchenChanges: Record<string, unknown> = {};
  if (headline.trim() !== profile.headline) kitchenChanges.headline = headline.trim();
  if (tags.join("\n") !== profile.specialties.join("\n")) kitchenChanges.specialties = tags;
  if (zone !== (profile.zone?.slug ?? "")) kitchenChanges.zone = zone || null;
  const dirty = Object.keys(userChanges).length + Object.keys(kitchenChanges).length > 0;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    setFieldErrors({});
    setSaved(false);
    try {
      let nextProfile: CookProfile | null = null;
      if (Object.keys(kitchenChanges).length) nextProfile = await api.patch<CookProfile>("/cooks/me", kitchenChanges);
      if (Object.keys(userChanges).length) await api.patch<User>("/me/profile", userChanges);
      setSaved(true);
      // Both remount this form (its key) with the server's answer.
      if (nextProfile) onProfileSaved(nextProfile);
      if (Object.keys(userChanges).length) await onUserSaved();
    } catch (cause) {
      if (cause instanceof ApiError && cause.fieldErrors.length > 0) {
        setFieldErrors(Object.fromEntries(cause.fieldErrors.map((error) => [error.field.split(".")[0], error.message])));
        setErrors(["Please check the highlighted fields."]);
      } else {
        setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
      }
    } finally {
      setBusy(false);
    }
  };

  const invalid = (key: string) => ({
    "aria-invalid": fieldErrors[key] ? true : undefined,
    className: cx(inputClass, fieldErrors[key] && "border-danger"),
  });

  const chosenZone = zones?.find((candidate) => candidate.slug === zone) ?? (zone ? profile.zone : null);
  return (
    <form onSubmit={submit} className="space-y-6">
      <PageHeader
        size="compact"
        title="Kitchen profile"
        lead="How neighbours see you. Changes show on your public page right away."
        actions={
          <Link
            href={`/cooks/${user.id}`}
            className="inline-flex items-center gap-1 text-sm font-semibold text-brand hover:underline"
          >
            View public page <ExternalLink className="h-3.5 w-3.5" aria-hidden="true" />
          </Link>
        }
      />

      <ErrorBanner lines={errors} />
      {saved && !dirty && (
        <p role="status" className="animate-rise flex items-center gap-2 rounded-2xl bg-herb-soft px-4 py-3 text-sm text-ink">
          <CircleCheck className="h-4 w-4 shrink-0 text-herb" aria-hidden="true" /> Kitchen profile saved.
        </p>
      )}

      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[minmax(0,1fr)_300px]">
        <div className="min-w-0 space-y-6">
          <section className="space-y-5 rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
            <h2 className="flex items-center gap-2 font-display text-xl font-semibold text-ink">
              <Store className="h-5 w-5 text-brand" aria-hidden="true" /> Your kitchen
            </h2>
            <Field label="Headline" hint="One line under your name, 3 to 80 characters." error={fieldErrors.headline}>
              <input
                value={headline}
                onChange={(event) => setHeadline(event.target.value)}
                required
                minLength={3}
                maxLength={80}
                {...invalid("headline")}
              />
            </Field>
            <Field
              label="Specialties"
              optional
              hint="Comma separated, up to 10 - e.g. biryani, korma."
              error={fieldErrors.specialties}
            >
              <input value={specialties} onChange={(event) => setSpecialties(event.target.value)} {...invalid("specialties")} />
            </Field>
            <Field
              label="Neighbourhood"
              optional
              hint="Where your kitchen is - customers filter dishes by distance."
              error={fieldErrors.zone}
            >
              <Select value={zone} onChange={(event) => setZone(event.target.value)} disabled={!zones}>
                <option value="">Not set</option>
                {(zones ?? []).map((candidate) => (
                  <option key={candidate.slug} value={candidate.slug}>
                    {candidate.name}
                  </option>
                ))}
              </Select>
            </Field>
          </section>

          <section className="space-y-5 rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
            <h2 className="flex items-center gap-2 font-display text-xl font-semibold text-ink">
              <UserRound className="h-5 w-5 text-ink-soft" aria-hidden="true" /> About you
            </h2>
            <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
              <Field label="Display name" optional hint="Shown on your dishes and orders." error={fieldErrors.display_name}>
                <input
                  value={displayName}
                  onChange={(event) => setDisplayName(event.target.value)}
                  maxLength={60}
                  {...invalid("display_name")}
                />
              </Field>
              <Field label="Area" optional hint="A neighbourhood or town, in your words." error={fieldErrors.area}>
                <input value={area} onChange={(event) => setArea(event.target.value)} maxLength={120} {...invalid("area")} />
              </Field>
            </div>
            <Field label="Your story" optional hint={`${bio.length}/500`} error={fieldErrors.bio}>
              <textarea
                value={bio}
                onChange={(event) => setBio(event.target.value)}
                maxLength={500}
                rows={4}
                placeholder="Third-generation home cook chasing the perfect crunchy alu."
                className={cx(textareaClass, fieldErrors.bio && "border-danger")}
              />
            </Field>
          </section>
        </div>

        <aside aria-label="Preview" className="min-w-0">
          <div className="space-y-3 xl:sticky xl:top-24">
            <p className="text-xs font-semibold uppercase tracking-[0.14em] text-ink-soft">On the cooks page</p>
            <div className="mx-auto max-w-sm">
              {availability ? (
                <CookCard
                  cook={{
                    user_id: user.id,
                    display_name: displayName.trim() || null,
                    bio: bio.trim() || null,
                    area: area.trim() || null,
                    headline: headline.trim() || "Your headline",
                    specialties: tags,
                    zone: chosenZone ?? null,
                    verified: profile.verified_at !== null,
                    verified_at: profile.verified_at,
                    availability,
                    created_at: profile.created_at,
                  }}
                />
              ) : (
                <div className="h-64 animate-pulse rounded-3xl bg-muted" aria-busy="true" />
              )}
            </div>
            <Verification verifiedAt={profile.verified_at} />
          </div>
        </aside>
      </div>

      <div className="sticky bottom-4 z-10 flex flex-col gap-3 rounded-3xl border border-line bg-surface/95 p-4 shadow-lift backdrop-blur sm:flex-row sm:items-center sm:justify-between sm:px-6">
        <p className="text-sm text-ink-muted" aria-live="polite">
          {dirty ? "You have unsaved changes." : "Everything is saved."}
        </p>
        <button type="submit" disabled={busy || !dirty} className={darkButtonClass}>
          {busy && <Spinner />} Save changes
        </button>
      </div>
    </form>
  );
}

/** The kitchen's verification, in the cook's own words. */
function Verification({ verifiedAt }: { verifiedAt: string | null }) {
  if (verifiedAt) {
    return (
      <div className="mx-auto flex max-w-sm gap-3 rounded-3xl border border-herb/25 bg-herb-soft p-4 text-sm">
        <BadgeCheck className="mt-0.5 h-5 w-5 shrink-0 text-herb" aria-hidden="true" />
        <p className="text-ink-muted">
          <span className="block font-semibold text-ink">Verified kitchen</span>
          Checked by the Plateboard team on {formatDate(verifiedAt)}. The badge shows on your public page and cards.
        </p>
      </div>
    );
  }
  return (
    <div className="mx-auto flex max-w-sm gap-3 rounded-3xl border border-line bg-surface p-4 text-sm">
      <ShieldQuestion className="mt-0.5 h-5 w-5 shrink-0 text-ink-soft" aria-hidden="true" />
      <p className="text-ink-muted">
        <span className="block font-semibold text-ink">Not verified yet</span>
        The Plateboard team verifies kitchens. Once yours is checked, a verified badge shows on your public page - a
        complete profile and well-described dishes help.
      </p>
    </div>
  );
}
