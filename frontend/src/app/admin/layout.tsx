import type { Metadata } from "next";

import AdminShell from "@/components/admin-shell";

/** Server layout: page titles for the admin panel; the shell is client-side. */
export const metadata: Metadata = {
  title: { default: "Admin", template: "%s · Admin · Plateboard" },
};

export default function AdminLayout({ children }: { children: React.ReactNode }) {
  return <AdminShell>{children}</AdminShell>;
}
