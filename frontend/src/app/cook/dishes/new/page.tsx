"use client";

import { ArrowLeft } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";

import DishForm from "@/components/dish-form";
import { PageHeader } from "@/components/ui";
import { api, type Dish } from "@/lib/api";
import { useKitchen } from "@/lib/kitchen-context";
import { useSession } from "@/lib/session";

/** /cook/dishes/new - add a dish (POST /api/me/dishes), public or a private draft. */
export default function NewDishPage() {
  const router = useRouter();
  const { user } = useSession();
  const { profile } = useKitchen();

  return (
    <div className="space-y-6">
      <Link href="/cook/dishes" className="inline-flex items-center gap-1.5 text-sm text-ink-muted hover:text-ink">
        <ArrowLeft className="h-4 w-4" /> Menu
      </Link>
      <PageHeader
        size="compact"
        title="Add a dish"
        lead="Publish it right away, or keep it private until it's ready."
      />
      <DishForm
        cookName={user?.display_name ?? null}
        zone={profile?.zone ?? null}
        cancelHref="/cook/dishes"
        onSubmit={async (values) => {
          const created = await api.post<Dish>("/me/dishes", values);
          router.push(`/cook/dishes?saved=${created.id}`);
        }}
      />
    </div>
  );
}
