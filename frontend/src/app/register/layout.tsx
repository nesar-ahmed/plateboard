import type { Metadata } from "next";

/** Server layout only for the page title (the registration page is a Client Component). */
export const metadata: Metadata = { title: "Create your account" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
