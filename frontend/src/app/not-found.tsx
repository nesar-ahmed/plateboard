import { Compass } from "lucide-react";

import { ButtonLink, Container } from "@/components/ui";

export default function NotFound() {
  return (
    <Container size="narrow" className="flex flex-col items-center py-24 text-center">
      <span className="flex h-16 w-16 items-center justify-center rounded-full bg-brand-soft text-brand">
        <Compass className="h-8 w-8" aria-hidden="true" />
      </span>
      <p className="mt-6 text-sm font-semibold uppercase tracking-[0.16em] text-brand">404</p>
      <h1 className="mt-2 font-display text-4xl font-semibold tracking-tight text-ink">
        This plate has been cleared.
      </h1>
      <p className="mt-3 max-w-md text-ink-muted">
        The page or dish you&apos;re looking for isn&apos;t on the menu anymore - it may have been
        taken off by its cook.
      </p>
      <div className="mt-8 flex gap-3">
        <ButtonLink href="/dishes">Browse dishes</ButtonLink>
        <ButtonLink href="/" variant="ghost">
          Go home
        </ButtonLink>
      </div>
    </Container>
  );
}
