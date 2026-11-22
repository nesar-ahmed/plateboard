"use client";

import { BadgeCheck, Search, Users } from "lucide-react";
import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";

import ConfirmDialog from "@/components/confirm-dialog";
import {
  Avatar,
  Badge,
  EmptyState,
  ErrorBanner,
  PageHeader,
  Pager,
  Spinner,
  cx,
  inputClass,
} from "@/components/ui";
import VerifiedBadge from "@/components/verified-badge";
import { ordersOf } from "@/lib/admin";
import { api, ApiError, type AdminDashboard, type AdminUser, type AdminUserPage, type CookVerification } from "@/lib/api";
import { formatDate, formatRelative } from "@/lib/format";
import { useApi } from "@/lib/use-api";

const PAGE_SIZE = 20;

const ROLES = [
  { key: "all", label: "All", count: (d: AdminDashboard) => d.users.total },
  { key: "customer", label: "Customers", count: (d: AdminDashboard) => d.users.customers },
  { key: "cook", label: "Cooks", count: (d: AdminDashboard) => d.users.cooks },
  { key: "admin", label: "Admins", count: (d: AdminDashboard) => d.users.admins },
];

const ROLE_TONE: Record<string, "herb" | "saffron" | "night"> = { customer: "herb", cook: "saffron", admin: "night" };

export default function AdminUsersPage() {
  return (
    <Suspense fallback={null}>
      <AdminUsers />
    </Suspense>
  );
}

/** /admin/users - every account with roles and activity (URL: ?role=&q=&offset=). */
function AdminUsers() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const role = ROLES.find((candidate) => candidate.key === params.get("role"))?.key ?? "all";
  const q = params.get("q") ?? "";
  const offset = Math.max(0, Number(params.get("offset")) || 0);
  const [typed, setTyped] = useState(q);

  const query = new URLSearchParams({ limit: String(PAGE_SIZE), offset: String(offset) });
  if (role !== "all") query.set("role", role);
  if (q) query.set("q", q);
  const { data: page, error, setData } = useApi<AdminUserPage>(`/admin/users?${query.toString()}`);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [revoking, setRevoking] = useState<AdminUser | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  /** POST (verify) or DELETE (revoke) the kitchen's verification; update the row in place. */
  const setVerified = async (user: AdminUser, verified: boolean) => {
    setBusyId(user.id);
    setActionError(null);
    try {
      const path = `/admin/cooks/${user.id}/verification`;
      const result = verified ? await api.post<CookVerification>(path, {}) : await api.delete<CookVerification>(path);
      setData((current) =>
        current && {
          ...current,
          items: current.items.map((row) => (row.id === user.id ? { ...row, verified_at: result.verified_at } : row)),
        },
      );
    } catch (cause) {
      setActionError(cause instanceof ApiError ? cause.message : "Could not reach the API");
    } finally {
      setBusyId(null);
      setRevoking(null);
    }
  };
  const { data: totals } = useApi<AdminDashboard>("/admin/dashboard?days=1");

  const go = (next: { role?: string; q?: string; offset?: number }) => {
    const search = new URLSearchParams();
    const nextRole = next.role ?? role;
    const nextQ = next.q ?? q;
    if (nextRole !== "all") search.set("role", nextRole);
    if (nextQ) search.set("q", nextQ);
    if (next.offset) search.set("offset", String(next.offset));
    router.replace(search.size ? `${pathname}?${search.toString()}` : pathname, { scroll: false });
  };

  // Search as you type (debounced); the URL stays the source of truth.
  useEffect(() => {
    const trimmed = typed.trim();
    if (trimmed === q) return;
    const timer = window.setTimeout(() => go({ q: trimmed, offset: 0 }), 300);
    return () => window.clearTimeout(timer);
    // `go` is rebuilt every render; `typed` and `q` are what matter here.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [typed, q]);

  return (
    <div className="space-y-6">
      <PageHeader size="compact" title="Users" lead="Every account on Plateboard - what they are and what they do." />

      <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
        <div role="tablist" aria-label="Role" className="flex gap-1 overflow-x-auto rounded-full border border-line bg-surface p-1 [scrollbar-width:none] lg:w-fit">
          {ROLES.map((candidate) => (
            <button
              key={candidate.key}
              role="tab"
              type="button"
              aria-selected={candidate.key === role}
              onClick={() => go({ role: candidate.key, offset: 0 })}
              className={cx(
                "inline-flex h-9 shrink-0 items-center gap-2 whitespace-nowrap rounded-full px-4 text-sm font-medium transition-colors",
                candidate.key === role ? "bg-ink text-canvas" : "text-ink-muted hover:text-ink",
              )}
            >
              {candidate.label}
              {totals && <span className="text-xs tabular-nums opacity-70">{candidate.count(totals)}</span>}
            </button>
          ))}
        </div>
        <label className="relative block lg:w-80">
          <span className="sr-only">Search by email or name</span>
          <Search className="pointer-events-none absolute left-3.5 top-1/2 h-4 w-4 -translate-y-1/2 text-ink-soft" aria-hidden="true" />
          <input
            type="search"
            value={typed}
            onChange={(event) => setTyped(event.target.value)}
            placeholder="Search by email or name"
            maxLength={120}
            className={cx(inputClass, "pl-10")}
          />
        </label>
      </div>

      <ErrorBanner lines={[...(error ? [error] : []), ...(actionError ? [actionError] : [])]} />

      {!page ? (
        <div className="h-96 animate-pulse rounded-3xl bg-muted" aria-busy="true" />
      ) : page.items.length === 0 ? (
        <EmptyState icon={<Users className="h-6 w-6" />} title="No one matches">
          {q ? `Nobody with “${q}” in their email or name.` : "No accounts with this role yet."}
        </EmptyState>
      ) : (
        <div className="overflow-hidden rounded-3xl border border-line bg-surface shadow-card">
          <div className="hidden grid-cols-[minmax(0,2fr)_minmax(0,1.3fr)_minmax(0,0.9fr)_minmax(0,0.9fr)_minmax(0,1.2fr)] gap-4 border-b border-line px-6 py-3 text-xs font-semibold uppercase tracking-[0.1em] text-ink-soft md:grid">
            <span>Person</span>
            <span>Roles</span>
            <span>Joined</span>
            <span>Last login</span>
            <span className="text-right">Orders</span>
          </div>
          <ul className="divide-y divide-line">
            {page.items.map((user) => (
              <UserRow
                key={user.id}
                user={user}
                busy={busyId === user.id}
                onVerify={() => void setVerified(user, true)}
                onRevoke={() => setRevoking(user)}
              />
            ))}
          </ul>
        </div>
      )}
      {page && page.total > PAGE_SIZE && (
        <Pager total={page.total} limit={PAGE_SIZE} offset={offset} onMove={(next) => go({ offset: next })} />
      )}

      {revoking && (
        <ConfirmDialog
          title={`Remove ${revoking.display_name ?? "this kitchen"}'s verified badge?`}
          confirmLabel="Remove badge"
          tone="danger"
          busy={busyId === revoking.id}
          onCancel={() => setRevoking(null)}
          onConfirm={() => void setVerified(revoking, false)}
        >
          The badge disappears from their public page and cards straight away. You can verify the kitchen again at any
          time.
        </ConfirmDialog>
      )}
    </div>
  );
}

function UserRow({
  user,
  busy,
  onVerify,
  onRevoke,
}: {
  user: AdminUser;
  busy: boolean;
  onVerify: () => void;
  onRevoke: () => void;
}) {
  const cook = user.roles.includes("cook");
  return (
    <li className="grid grid-cols-2 gap-x-4 gap-y-2 px-5 py-4 md:grid-cols-[minmax(0,2fr)_minmax(0,1.3fr)_minmax(0,0.9fr)_minmax(0,0.9fr)_minmax(0,1.2fr)] md:items-center md:gap-4 md:px-6">
      <div className="col-span-2 flex min-w-0 items-center gap-3 md:col-span-1">
        <Avatar name={user.display_name ?? user.email} size="sm" />
        <div className="min-w-0">
          <p className="truncate text-sm font-medium text-ink">
            {cook ? (
              <Link href={`/cooks/${user.id}`} className="hover:text-brand">
                {user.display_name ?? "No name"}
              </Link>
            ) : (
              (user.display_name ?? "No name")
            )}
          </p>
          <p className="truncate text-xs text-ink-soft">{user.email}</p>
        </div>
      </div>
      <div className="col-span-2 flex flex-wrap items-center gap-1 md:col-span-1">
        {user.roles.map((role) => (
          <Badge key={role} tone={ROLE_TONE[role] ?? "neutral"} className="capitalize">
            {role}
          </Badge>
        ))}
        {!cook && user.cook_application && user.cook_application !== "accepted" && (
          // An open or turned-down cook application - reviewed under Cook applications.
          <Link
            href={user.cook_application === "pending" ? "/admin/applications" : "/admin/applications?tab=rejected"}
            className="relative z-10 rounded-full"
          >
            <Badge tone={user.cook_application === "pending" ? "saffron" : "neutral"}>
              {user.cook_application === "pending" ? "Applied to cook" : "Application rejected"}
            </Badge>
          </Link>
        )}
        {cook && (
          <span className="flex w-full items-center gap-2 pt-1">
            {user.verified_at ? (
              <>
                <VerifiedBadge />
                <button
                  type="button"
                  disabled={busy}
                  onClick={onRevoke}
                  className="h-7 rounded-full px-2 text-xs font-semibold text-ink-muted transition-colors hover:bg-danger-soft hover:text-danger disabled:opacity-50"
                >
                  Revoke
                </button>
              </>
            ) : (
              <button
                type="button"
                disabled={busy}
                onClick={onVerify}
                className="inline-flex h-7 items-center gap-1 rounded-full border border-line-strong bg-surface px-3 text-xs font-semibold text-ink transition-colors hover:bg-muted disabled:opacity-50"
              >
                {busy ? <Spinner className="h-3 w-3" /> : <BadgeCheck className="h-3.5 w-3.5" aria-hidden="true" />}{" "}
                Verify kitchen
              </button>
            )}
          </span>
        )}
      </div>
      <p className="text-sm text-ink-muted">
        <span className="text-ink-soft md:hidden">Joined </span>
        {formatDate(user.created_at)}
      </p>
      <p className="text-sm text-ink-muted">
        <span className="text-ink-soft md:hidden">Last login </span>
        {user.last_login_at ? formatRelative(user.last_login_at) : "Never"}
      </p>
      <div className="col-span-2 flex flex-wrap gap-x-4 gap-y-1 text-sm md:col-span-1 md:justify-end">
        {user.orders_placed > 0 ? (
          <Link href={ordersOf("customer", user.id, user.display_name)} className="font-medium text-ink hover:text-brand">
            {user.orders_placed} placed
          </Link>
        ) : (
          <span className="text-ink-soft">0 placed</span>
        )}
        {cook &&
          (user.orders_received > 0 ? (
            <Link href={ordersOf("cook", user.id, user.display_name)} className="font-medium text-ink hover:text-brand">
              {user.orders_received} received
            </Link>
          ) : (
            <span className="text-ink-soft">0 received</span>
          ))}
      </div>
    </li>
  );
}
