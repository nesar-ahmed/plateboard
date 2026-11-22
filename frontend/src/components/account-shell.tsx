"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { AccountMobileNav, AccountSidebar } from "@/components/account-nav";
import { Container, Spinner } from "@/components/ui";
import { useSession } from "@/lib/session";

/**
 * The user panel shell (/account/*): signed-in only - guests go to
 * `/login?next=<this page>`. Sidebar from `lg`, pill bar below it. Rendered
 * by app/account/layout.tsx (a Server Component, so it can set metadata).
 *
 * Only a visitor who *arrives* signed out is redirected; someone logging out
 * here is already on their way home (the nav navigates), so no race.
 */
export default function AccountShell({ children }: { children: React.ReactNode }) {
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

  return (
    <Container className="py-6 sm:py-10 print:max-w-none print:p-0">
      <div className="grid grid-cols-1 gap-8 lg:grid-cols-[248px_minmax(0,1fr)] lg:gap-12 print:block">
        <AccountSidebar user={user} />
        <div className="min-w-0">
          <AccountMobileNav />
          {children}
        </div>
      </div>
    </Container>
  );
}
