"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";

import CartButton from "@/components/cart-button";
import { api } from "@/lib/api";
import { useSession } from "@/lib/session";

/**
 * Top navigation with the live auth state (shared session, see
 * lib/session.tsx): Login/Register when signed out, the account + Logout
 * when signed in, and the cart icon with its count for everyone - guests
 * have carts too.
 */
export default function Nav() {
  const pathname = usePathname();
  const router = useRouter();
  const { user, checked, refresh } = useSession();

  const logout = async () => {
    try {
      await api.post("/auth/logout", {});
    } finally {
      router.push("/"); // leave signed-in pages first...
      await refresh(); // ...then become a guest; the cart follows (guest cart)
    }
  };

  const linkClass = (href: string) =>
    `text-sm font-medium transition-colors ${
      pathname === href
        ? "text-emerald-700 dark:text-emerald-400"
        : "text-zinc-500 hover:text-zinc-900 dark:text-zinc-400 dark:hover:text-zinc-100"
    }`;

  return (
    <nav className="border-b border-zinc-200 bg-white/80 dark:border-zinc-800 dark:bg-zinc-950/80">
      <div className="mx-auto flex max-w-5xl items-center justify-between gap-4 px-4 py-3">
        <div className="flex items-center gap-5">
          <Link href="/" className="text-base font-semibold tracking-tight text-zinc-900 dark:text-zinc-50">
            Plateboard
          </Link>
          <Link href="/" className={linkClass("/")}>
            Dishes
          </Link>
          <Link href="/cooks" className={linkClass("/cooks")}>
            Cooks
          </Link>
          <Link href="/dashboard" className={linkClass("/dashboard")}>
            Dashboard
          </Link>
          <Link href="/health" className={linkClass("/health")}>
            Health
          </Link>
        </div>
        <div className="flex items-center gap-3">
          <CartButton />
          {checked && !user && (
            <>
              <Link href="/login" className={linkClass("/login")}>
                Log in
              </Link>
              <Link
                href="/register"
                className="rounded-full bg-emerald-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-emerald-700"
              >
                Register
              </Link>
            </>
          )}
          {user && (
            <>
              <span className="hidden text-sm text-zinc-500 sm:inline dark:text-zinc-400">
                {user.display_name ?? user.email}
              </span>
              <button
                type="button"
                onClick={() => void logout()}
                className="rounded-full border border-zinc-300 px-4 py-1.5 text-sm font-medium text-zinc-700 hover:bg-zinc-100 dark:border-zinc-700 dark:text-zinc-300 dark:hover:bg-zinc-800"
              >
                Log out
              </button>
            </>
          )}
        </div>
      </div>
    </nav>
  );
}
