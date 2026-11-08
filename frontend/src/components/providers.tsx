"use client";

import type { ReactNode } from "react";

import CartDrawer from "@/components/cart-drawer";
import { CartProvider } from "@/lib/cart";
import { SessionProvider } from "@/lib/session";

/** App-wide client state: who is signed in, and their (or the guest's) cart. */
export default function Providers({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <CartProvider>
        {children}
        <CartDrawer />
      </CartProvider>
    </SessionProvider>
  );
}
