"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, useRef } from "react";

import { CookMobileNav, CookSidebar } from "@/components/cook-nav";
import KitchenOnboarding from "@/components/kitchen-onboarding";
import { Container, Spinner } from "@/components/ui";
import { KitchenProvider } from "@/lib/kitchen-context";
import { useSession } from "@/lib/session";

/**
 * The cook panel shell (/cook/*), twin of the account shell: guests go to
 * `/login?next=<this page>`, signed-in users without a kitchen get the cook
 * application (KitchenOnboarding: apply, "in review", the admin's answer,
 * apply again), cooks get the sidebar (from `lg`) or pill bar plus the
 * shared kitchen state (profile, open-request count).
 */
export default function CookShell({ children }: { children: React.ReactNode }) {
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

  if (!user.roles.includes("cook")) {
    return (
      <Container className="py-6 sm:py-10">
        <KitchenOnboarding />
      </Container>
    );
  }

  return (
    <KitchenProvider>
      <Container className="py-6 sm:py-10 print:max-w-none print:p-0">
        <div className="grid grid-cols-1 gap-8 lg:grid-cols-[248px_minmax(0,1fr)] lg:gap-12 print:block">
          <CookSidebar user={user} />
          <div className="min-w-0">
            <CookMobileNav />
            {children}
          </div>
        </div>
      </Container>
    </KitchenProvider>
  );
}
