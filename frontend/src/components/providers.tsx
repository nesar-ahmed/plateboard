"use client";

import type { ReactNode } from "react";

import CartDrawer from "@/components/cart-drawer";
import { CartProvider } from "@/lib/cart";
import { FavouritesProvider } from "@/lib/favourites";
import { NotificationsProvider } from "@/lib/notifications";
import { SessionProvider } from "@/lib/session";

/**
 * App-wide client state: who is signed in, their (or the guest's) cart,
 * their favourite dishes and their unread notification counts.
 */
export default function Providers({ children }: { children: ReactNode }) {
  return (
    <SessionProvider>
      <NotificationsProvider>
        <CartProvider>
          <FavouritesProvider>
            {children}
            <CartDrawer />
          </FavouritesProvider>
        </CartProvider>
      </NotificationsProvider>
    </SessionProvider>
  );
}
