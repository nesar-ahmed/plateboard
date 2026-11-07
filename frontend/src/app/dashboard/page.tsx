"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import DishForm from "@/components/dish-form";
import {
  Card,
  ErrorBanner,
  Field,
  Tag,
  dangerButtonClass,
  ghostButtonClass,
  inputClass,
  primaryButtonClass,
} from "@/components/ui";
import {
  api,
  ApiError,
  type Dish,
  type DishInput,
  type User,
} from "@/lib/api";
import { formatMinorUnits, splitList } from "@/lib/format";

/**
 * Signed-in dashboard (client-side gate: any 401 from /api/me bounces to
 * /login). Sections: profile editing, the become-a-cook action, and full
 * management of the cook's own dishes - create, edit, deactivate/reactivate,
 * delete. Prices shown in major units, entered there, stored as minor units.
 */
export default function DashboardPage() {
  const router = useRouter();
  const [me, setMe] = useState<User | null>(null);
  const [checked, setChecked] = useState(false);

  const loadMe = useCallback(async () => {
    try {
      setMe(await api.get<User>("/me"));
    } catch (cause) {
      setMe(null);
      if (cause instanceof ApiError && cause.status === 401) {
        router.replace("/login");
      }
    } finally {
      setChecked(true);
    }
  }, [router]);

  useEffect(() => {
    // Timeout kick-off: the effect body must not directly call a
    // setState-transitive function (react-hooks/set-state-in-effect).
    const kickOff = window.setTimeout(() => void loadMe(), 0);
    return () => window.clearTimeout(kickOff);
  }, [loadMe]);

  if (!checked || !me) {
    return <p className="text-sm text-zinc-500">{checked ? "Redirecting to login..." : "Loading..."}</p>;
  }

  const isCook = me.roles.includes("cook");

  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          Dashboard
        </h1>
        <p className="mt-1 text-sm text-zinc-500 dark:text-zinc-400">
          Signed in as {me.email} {isCook ? "- cook mode" : "- customer"}
        </p>
      </header>

      <ProfileCard me={me} onSaved={setMe} />

      {!isCook && <BecomeCookCard onDone={loadMe} />}

      {isCook && <MyDishes />}
    </div>
  );
}

function ProfileCard({ me, onSaved }: { me: User; onSaved: (user: User) => void }) {
  const [displayName, setDisplayName] = useState(me.display_name ?? "");
  const [bio, setBio] = useState(me.bio ?? "");
  const [area, setArea] = useState(me.area ?? "");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [saved, setSaved] = useState(false);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    setSaved(false);
    // Only changed fields go into the PATCH; blanking a field sends null,
    // which the API understands as "clear it".
    const patch: Record<string, string | null> = {};
    const want = (current: string, server: string | null) => {
      const trimmed = current.trim();
      return trimmed === (server ?? "") ? undefined : trimmed || null;
    };
    for (const [field, value] of [
      ["display_name", want(displayName, me.display_name)],
      ["bio", want(bio, me.bio)],
      ["area", want(area, me.area)],
    ] as const) {
      if (value !== undefined) patch[field] = value;
    }
    try {
      if (Object.keys(patch).length === 0) {
        throw new ApiError(422, "validation_failed", "nothing to save - no field changed", []);
      }
      onSaved(await api.patch<User>("/me/profile", patch));
      setSaved(true);
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Profile">
      <form onSubmit={submit} className="space-y-4">
        <ErrorBanner lines={errors} />
        {saved && <p className="text-sm text-emerald-700 dark:text-emerald-400">Profile saved.</p>}
        <div className="grid gap-4 sm:grid-cols-2">
          <Field label="Display name" hint="Shown on your public cook page.">
            <input value={displayName} onChange={(e) => setDisplayName(e.target.value)} className={inputClass} />
          </Field>
          <Field label="Area" hint="Free text locality, e.g. Mirpur, Dhaka.">
            <input value={area} onChange={(e) => setArea(e.target.value)} className={inputClass} />
          </Field>
        </div>
        <Field label="Bio">
          <textarea value={bio} onChange={(e) => setBio(e.target.value)} rows={2} className={inputClass} />
        </Field>
        <button type="submit" disabled={busy} className={primaryButtonClass}>
          {busy ? "Saving..." : "Save profile"}
        </button>
      </form>
    </Card>
  );
}

function BecomeCookCard({ onDone }: { onDone: () => Promise<void> }) {
  const [headline, setHeadline] = useState("");
  const [specialties, setSpecialties] = useState("");
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);

  const submit = async (event: React.FormEvent) => {
    event.preventDefault();
    setBusy(true);
    setErrors([]);
    try {
      await api.post("/cooks", {
        headline: headline.trim(),
        specialties: splitList(specialties),
      });
      await onDone(); // role flips -> dashboard re-renders with dish tools
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Could not reach the API"]);
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card title="Become a cook">
      <p className="-mt-2 mb-4 text-sm text-zinc-500 dark:text-zinc-400">
        One step: a headline and a few specialty tags open the dish tools.
      </p>
      <form onSubmit={submit} className="space-y-4">
        <ErrorBanner lines={errors} />
        <Field label="Headline">
          <input
            value={headline}
            onChange={(e) => setHeadline(e.target.value)}
            placeholder="Home chef of the decade"
            required
            minLength={3}
            className={inputClass}
          />
        </Field>
        <Field label="Specialties" hint="Comma separated, lowercase tags.">
          <input
            value={specialties}
            onChange={(e) => setSpecialties(e.target.value)}
            placeholder="biryani, korma"
            className={inputClass}
          />
        </Field>
        <button type="submit" disabled={busy} className={primaryButtonClass}>
          {busy ? "Cooking up..." : "Become a cook"}
        </button>
      </form>
    </Card>
  );
}

function MyDishes() {
  const [dishes, setDishes] = useState<Dish[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [errors, setErrors] = useState<string[]>([]);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [reloadToken, setReloadToken] = useState(0);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const mine = await api.get<Dish[]>("/me/dishes");
        if (active) setDishes(mine);
      } catch (cause) {
        if (active) setErrors(cause instanceof ApiError ? [cause.message] : ["Could not reach the API"]);
      }
    };
    void load();
    return () => {
      active = false;
    };
  }, [reloadToken]);

  const refresh = () => setReloadToken((token) => token + 1);

  const run = async (action: () => Promise<unknown>) => {
    setBusy(true);
    setErrors([]);
    try {
      await action();
      refresh();
      return true;
    } catch (cause) {
      setErrors(cause instanceof ApiError ? cause.lines : ["Request failed"]);
      return false;
    } finally {
      setBusy(false);
    }
  };

  const createDish = async (values: DishInput) => {
    const ok = await run(() => api.post<Dish>("/me/dishes", values));
    if (ok) setEditingId(null);
  };

  const editDish = async (dishId: string, values: DishInput) => {
    const ok = await run(() => api.patch<Dish>(`/me/dishes/${dishId}`, values));
    if (ok) setEditingId(null);
  };

  const toggleActive = (dish: Dish) =>
    void run(() => api.patch<Dish>(`/me/dishes/${dish.id}`, { active: !dish.active }));

  const removeDish = (dish: Dish) => void run(() => api.delete<void>(`/me/dishes/${dish.id}`));

  return (
    <div className="space-y-6">
      <Card title="Add a dish">
        <DishForm submitLabel="Add dish" busy={busy} errors={errors} onSubmit={createDish} />
      </Card>

      <section>
        <h2 className="mb-3 text-lg font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
          My dishes
        </h2>
        <ErrorBanner lines={errors} />
        {dishes === null ? (
          <p className="text-sm text-zinc-500">Loading...</p>
        ) : dishes.length === 0 ? (
          <p className="text-sm text-zinc-500">Nothing on your menu yet - add the first dish above.</p>
        ) : (
          <ul className="space-y-3">
            {dishes.map((dish) => (
              <li key={dish.id}>
                <Card>
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="font-semibold text-zinc-900 dark:text-zinc-50">{dish.name}</h3>
                      <p className="mt-0.5 text-sm text-zinc-500 dark:text-zinc-400">
                        <span className="font-mono">{formatMinorUnits(dish.price)}</span>
                        {" · "}
                        {dish.portions} portions
                        {" · "}
                        {dish.allergens.length > 0 ? dish.allergens.join(", ") : "no allergens"}
                      </p>
                    </div>
                    <div className="flex items-center gap-2">
                      <Tag>{dish.active ? "active" : "deactivated"}</Tag>
                      <button
                        type="button"
                        disabled={busy}
                        onClick={() => setEditingId(editingId === dish.id ? null : dish.id)}
                        className={ghostButtonClass}
                      >
                        {editingId === dish.id ? "Close" : "Edit"}
                      </button>
                      <button type="button" disabled={busy} onClick={() => toggleActive(dish)} className={ghostButtonClass}>
                        {dish.active ? "Deactivate" : "Reactivate"}
                      </button>
                      <button type="button" disabled={busy} onClick={() => removeDish(dish)} className={dangerButtonClass}>
                        Delete
                      </button>
                    </div>
                  </div>
                  {editingId === dish.id && (
                    <div className="mt-4 border-t border-zinc-100 pt-4 dark:border-zinc-800">
                      <DishForm
                        dish={dish}
                        submitLabel="Save changes"
                        busy={busy}
                        errors={[]}
                        onCancel={() => setEditingId(null)}
                        onSubmit={(values) => editDish(dish.id, values)}
                      />
                    </div>
                  )}
                </Card>
              </li>
            ))}
          </ul>
        )}
      </section>
    </div>
  );
}
