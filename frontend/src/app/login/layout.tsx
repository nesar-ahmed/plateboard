import type { Metadata } from "next";

/** Server layout only for the page title (the login page is a Client Component). */
export const metadata: Metadata = { title: "Log in" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
