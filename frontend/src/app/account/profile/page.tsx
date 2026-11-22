"use client";

import { ChefHat, Mail } from "lucide-react";
import { useState } from "react";

import {
  Avatar,
  Badge,
  ButtonLink,
  ErrorBanner,
  Field,
  PageHeader,
  Spinner,
  darkButtonClass,
  inputClass,
  textareaClass,
} from "@/components/ui";
import { api, ApiError, type User } from "@/lib/api";
import { formatDate } from "@/lib/format";
import { useSession } from "@/lib/session";

/** /account/profile - display name, bio, area (PATCH /api/me/profile). */
export default function ProfilePage() {
  const { user, refresh } = useSession();
  // Lives here, not in the form: saving remounts the form (its key), which
  // would otherwise drop the "saved" notice straight away.
  const [saved, setSaved] = useState(false);
  if (!user) return null; // the account layout guarantees a user
  return <ProfileForm key={user.updated_at} user={user} onSaved={refresh} saved={saved} setSaved={setSaved} />;
}

function ProfileForm({
  user,
  onSaved,
  saved,
  setSaved,
}: {
  user: User;
  onSaved: () => Promise<unknown>;
  saved: boolean;
  setSaved: (saved: boolean) => void;
}) {
  const [displayName, setDisplayName] = useState(user.display_name ?? "");
  const [bio, setBio] = useState(user.bio ?? "");
  const [area, setArea] = useState(user.area ?? "");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  // Only changed fields are sent; a blanked field is sent as null (= clear).
  const changes: Record<string, string | null> = {};
  for (const [field, value, server] of [
    ["display_name", displayName, user.display_name],
    ["bio", bio, user.bio],
    ["area", area, user.area],
  ] as const) {
    const trimmed = value.trim();
    if (trimmed !== (server ?? "")) changes[field] = trimmed || null;
  }
  const dirty = Object.keys(changes).length > 0;

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    setSaved(false);
    try {
      await api.patch<User>("/me/profile", changes);
      setSaved(true);
      await onSaved();
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
    } finally {
      setBusy(false);
    }
  };

  const roles = user.roles.map((role) => role[0].toUpperCase() + role.slice(1));
  return (
    <div className="space-y-6">
      <PageHeader size="compact" title="Profile" lead="How you appear to the cooks you order from." />

      <section className="flex flex-col gap-5 rounded-3xl border border-line bg-surface p-5 shadow-card sm:flex-row sm:items-center sm:p-6">
        <Avatar name={user.display_name ?? user.email} size="xl" />
        <div className="min-w-0 flex-1">
          <p className="font-display text-2xl font-semibold text-ink">{user.display_name ?? "No name yet"}</p>
          <p className="mt-1 flex items-center gap-1.5 text-sm text-ink-muted">
            <Mail className="h-4 w-4" aria-hidden="true" /> {user.email}
          </p>
          <div className="mt-3 flex flex-wrap items-center gap-2">
            {roles.map((role) => (
              <Badge key={role}>{role}</Badge>
            ))}
            <span className="text-xs text-ink-soft">Member since {formatDate(user.created_at)}</span>
          </div>
        </div>
      </section>

      <form onSubmit={submit} className="space-y-5 rounded-3xl border border-line bg-surface p-5 shadow-card sm:p-6">
        <ErrorBanner lines={errors} />
        {saved && !dirty && (
          <p role="status" className="rounded-2xl bg-herb-soft px-4 py-3 text-sm text-ink">
            Profile saved.
          </p>
        )}
        <div className="grid grid-cols-1 gap-5 sm:grid-cols-2">
          <Field label="Display name" hint="Shown to the cooks you order from." optional>
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} maxLength={60} className={inputClass} />
          </Field>
          <Field label="Area" hint="A neighbourhood or town, e.g. Riverside." optional>
            <input value={area} onChange={(e) => setArea(e.target.value)} maxLength={120} className={inputClass} />
          </Field>
        </div>
        <Field label="About you" hint={`${bio.length}/500`} optional>
          <textarea value={bio} onChange={(e) => setBio(e.target.value)} maxLength={500} rows={4} className={textareaClass} />
        </Field>
        <Field label="Email" hint="Your login - it can't be changed here yet.">
          <input value={user.email} readOnly disabled className={inputClass} />
        </Field>
        <button type="submit" disabled={busy || !dirty} className={darkButtonClass}>
          {busy && <Spinner />} Save profile
        </button>
      </form>

      {!user.roles.includes("cook") && (
        <section className="flex flex-col gap-4 rounded-3xl bg-brand-soft p-5 sm:flex-row sm:items-center sm:justify-between sm:p-6">
          <div className="flex items-center gap-4">
            <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl bg-surface text-brand">
              <ChefHat className="h-6 w-6" aria-hidden="true" />
            </span>
            <div>
              <p className="font-semibold text-ink">Love to cook?</p>
              <p className="text-sm text-ink-muted">
                Apply to open a kitchen and sell your dishes to the neighbourhood - or see where your application
                stands.
              </p>
            </div>
          </div>
          <ButtonLink href="/cook" className="shrink-0">
            Apply to cook
          </ButtonLink>
        </section>
      )}
    </div>
  );
}
