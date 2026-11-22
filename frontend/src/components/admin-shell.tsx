"use client";

import { ShieldAlert } from "lucide-react";
import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { AdminMobileNav, AdminSidebar } from "@/components/admin-nav";
import { ButtonLink, Container, EmptyState, Spinner } from "@/components/ui";
import { AdminProvider } from "@/lib/admin-context";
import { homeFor, useSession } from "@/lib/session";

/**
 * The admin panel shell (/admin/*), twin of the account and cook shells:
 * guests go to `/login?next=<this page>`, signed-in users without the admin
 * role see a "no access" notice (the API would answer 403 anyway), admins
 * get the sidebar (from `lg`) or pill bar plus the shared panel state (the
 * pending cook-application count, lib/admin-context.tsx).
 */
export default function AdminShell({ children }: { children: React.ReactNode }) {
  const { user, checked } = useSession();
  const router = useRouter();
  const pathname = usePathname();
  const sawUser = useRef(false);

  useEffect(() => {
    if (user) sawUser.current = true;
    else if (checked && !sawUser.current) router.replace(`/login?next=${encodeURIComponent(pathname)}`);
  }, [checked, user, router, pathname]);

  if (!checked || !user) {
    return (
      <Container className="flex justify-center py-24 text-ink-muted">
        <Spinner className="h-6 w-6" />
      </Container>
    );
  }

  if (!user.roles.includes("admin")) {
    return (
      <Container size="narrow" className="py-16">
        <EmptyState
          icon={<ShieldAlert className="h-6 w-6" />}
          title="This area is for Plateboard admins"
          action={<ButtonLink href={homeFor(user)}>Go to your {homeFor(user) === "/cook" ? "kitchen" : "account"}</ButtonLink>}
        >
          You&apos;re signed in as {user.email}, which doesn&apos;t have admin access.
        </EmptyState>
      </Container>
    );
  }

  return (
    <AdminProvider>
      <Container className="py-6 sm:py-10">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[248px_minmax(0,1fr)] lg:gap-12">
          <AdminSidebar user={user} />
          <div className="min-w-0">
            <AdminMobileNav />
            {children}
          </div>
        </div>
      </Container>
    </AdminProvider>
  );
}
