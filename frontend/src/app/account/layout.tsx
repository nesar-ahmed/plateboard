import type { Metadata } from "next";

import AccountShell from "@/components/account-shell";

/** Server layout: page titles for the user panel; the shell is client-side. */
export const metadata: Metadata = {
  title: { default: "Your account", template: "%s · Your account · Plateboard" },
};

export default function AccountLayout({ children }: { children: React.ReactNode }) {
  return <AccountShell>{children}</AccountShell>;
}
