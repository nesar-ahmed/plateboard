import type { Metadata } from "next";

/** Server layout only for the page title (the checkout page is a Client Component). */
export const metadata: Metadata = { title: "Checkout" };

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
