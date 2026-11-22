import { ChefHat } from "lucide-react";
import type { Metadata } from "next";

import CookCard from "@/components/cook-card";
import { ButtonLink, EmptyState, ErrorBanner, Page, PageHeader } from "@/components/ui";
import { ApiError, type CookPage } from "@/lib/api";
import { serverGet } from "@/lib/server-api";

export const metadata: Metadata = { title: "Home cooks" };

const PAGE_SIZE = 12;

/** Public directory of cooks (GET /api/cooks), rendered on the server; `?offset=` pages. */
export default async function CookDirectory({ searchParams }: PageProps<"/cooks">) {
  const raw = (await searchParams).offset;
  const offset = Math.max(0, Number.parseInt(Array.isArray(raw) ? raw[0] : (raw ?? "0"), 10) || 0);
  let page: CookPage | null = null;
  let errors: string[] = [];
  try {
    page = await serverGet<CookPage>(`/cooks?limit=${PAGE_SIZE}&offset=${offset}`);
  } catch (cause) {
    errors = cause instanceof ApiError ? cause.lines : ["Could not reach the API"];
  }

  return (
    <Page>
      <PageHeader
        eyebrow="The people behind the food"
        title="Meet the cooks"
        lead="Home cooks with a public Plateboard kitchen. Open a profile to see what they're cooking today."
      />
      <ErrorBanner lines={errors} />
      {page && page.items.length === 0 && (
        <EmptyState
          icon={<ChefHat className="h-6 w-6" />}
          title="No cooks yet"
          action={<ButtonLink href="/register?next=/cook">Open your kitchen</ButtonLink>}
        >
          The first kitchen is a sign-up away.
        </EmptyState>
      )}
      {page && page.items.length > 0 && (
        <ul className="grid grid-cols-1 gap-5 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {page.items.map((cook) => (
            <li key={cook.user_id}>
              <CookCard cook={cook} />
            </li>
          ))}
        </ul>
      )}
      {page && page.total > PAGE_SIZE && (
        <nav aria-label="Pagination" className="mt-10 flex justify-center gap-2 border-t border-line pt-6">
          {offset > 0 && (
            <ButtonLink variant="ghost" href={`/cooks?offset=${Math.max(0, offset - PAGE_SIZE)}`}>
              Previous
            </ButtonLink>
          )}
          {offset + PAGE_SIZE < page.total && (
            <ButtonLink variant="ghost" href={`/cooks?offset=${offset + PAGE_SIZE}`}>
              Next
            </ButtonLink>
          )}
        </nav>
      )}
    </Page>
  );
}
