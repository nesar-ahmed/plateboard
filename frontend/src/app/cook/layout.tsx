import type { Metadata } from "next";

import CookShell from "@/components/cook-shell";

/** Server layout: page titles for the cook panel; the shell is client-side. */
export const metadata: Metadata = {
  title: { default: "Your kitchen", template: "%s · Your kitchen · Plateboard" },
};

export default function CookLayout({ children }: { children: React.ReactNode }) {
  return <CookShell>{children}</CookShell>;
}
