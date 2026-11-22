import {
  ArrowRight,
  ChefHat,
  CircleCheck,
  Leaf,
  MapPin,
  Search,
  ShieldCheck,
  ShoppingBag,
  Sparkles,
} from "lucide-react";
import Link from "next/link";
import { redirect } from "next/navigation";

import CookCard from "@/components/cook-card";
import DishArt from "@/components/dish-art";
import DishCard from "@/components/dish-card";
import {
  AllergenTag,
  Avatar,
  ButtonLink,
  Container,
  SectionHeading,
  Select,
  Tag,
  cx,
  primaryButtonClass,
  railItemClass,
  railListClass,
} from "@/components/ui";
import type { CookPage, Dish, DishPage, Zone } from "@/lib/api";
import { ALLERGENS } from "@/lib/allergens";
import { toSearchParams } from "@/lib/dish-filters";
import { formatMinorUnits } from "@/lib/format";
import { serverGet } from "@/lib/server-api";

/** Query keys of the dish list: an old `/?zone=...` link goes to /dishes. */
const DISH_LIST_KEYS = ["q", "zone", "max_distance", "min_price", "max_price", "dietary_tag", "exclude_allergen", "offset"];

const DIETS = [
  { tag: "vegetarian", label: "Vegetarian" },
  { tag: "vegan", label: "Vegan" },
  { tag: "gluten free", label: "Gluten free" },
  { tag: "halal", label: "Halal" },
  { tag: "spicy", label: "Spicy" },
  { tag: "sweet", label: "Something sweet" },
];

/**
 * Landing page, rendered on the server: featured dishes, cooks and zones are
 * fetched in parallel from the backend (API_ORIGIN), so everything - hero
 * collage included - is in the HTML. The hero search is a plain GET form to
 * /dishes, so it works before any JavaScript loads.
 */
export default async function LandingPage({ searchParams }: PageProps<"/">) {
  const params = toSearchParams(await searchParams);
  if (DISH_LIST_KEYS.some((key) => params.has(key))) {
    redirect(`/dishes?${params.toString()}`);
  }

  const [dishes, cooks, zones] = await Promise.allSettled([
    serverGet<DishPage>("/dishes?limit=8"),
    serverGet<CookPage>("/cooks?limit=4"),
    serverGet<Zone[]>("/zones"),
  ]);
  const featured = dishes.status === "fulfilled" ? dishes.value.items : [];
  const dishTotal = dishes.status === "fulfilled" ? dishes.value.total : null;
  const cookPage = cooks.status === "fulfilled" ? cooks.value : null;
  const zoneList = zones.status === "fulfilled" ? zones.value : [];

  return (
    <>
      <Hero featured={featured} zones={zoneList} dishTotal={dishTotal} cookTotal={cookPage?.total ?? null} />

      <Container className="py-14 sm:py-20">
        <SectionHeading
          eyebrow="Fresh on the menu"
          title="Just added by your neighbours"
          lead="New dishes from home kitchens near you. Tap + to add a portion to your bag."
          action={
            <ButtonLink href="/dishes" variant="ghost">
              Browse all dishes <ArrowRight className="h-4 w-4" />
            </ButtonLink>
          }
        />
        {featured.length > 0 ? (
          <ul className={cx(railListClass, "sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4")}>
            {featured.map((dish) => (
              <li key={dish.id} className={railItemClass}>
                <DishCard dish={dish} />
              </li>
            ))}
          </ul>
        ) : (
          <p className="rounded-3xl border border-dashed border-line-strong p-10 text-center text-ink-muted">
            The menu is warming up - check back in a moment.
          </p>
        )}
      </Container>

      <HowItWorks />

      {cookPage && cookPage.items.length > 0 && (
        <Container className="py-14 sm:py-20">
          <SectionHeading
            eyebrow="The people behind the food"
            title="Meet the cooks"
            lead="Every dish on Plateboard comes from a real home kitchen with a name and a story."
            action={
              <ButtonLink href="/cooks" variant="ghost">
                All {cookPage.total} cooks <ArrowRight className="h-4 w-4" />
              </ButtonLink>
            }
          />
          <ul className={cx(railListClass, "sm:grid-cols-2 lg:grid-cols-4")}>
            {cookPage.items.map((cook) => (
              <li key={cook.user_id} className={railItemClass}>
                <CookCard cook={cook} />
              </li>
            ))}
          </ul>
        </Container>
      )}

      <Transparency example={featured.find((dish) => dish.allergens.length > 0) ?? featured[0]} />

      <CookCta />
    </>
  );
}

// --- hero ------------------------------------------------------------------------------------

function Hero({
  featured,
  zones,
  dishTotal,
  cookTotal,
}: {
  featured: Dish[];
  zones: Zone[];
  dishTotal: number | null;
  cookTotal: number | null;
}) {
  const stats = [
    cookTotal !== null && { value: cookTotal, label: "home cooks" },
    dishTotal !== null && { value: dishTotal, label: "dishes on the menu" },
    zones.length > 0 && { value: zones.length, label: "neighbourhoods" },
  ].filter(Boolean) as { value: number; label: string }[];

  return (
    <section className="relative overflow-hidden">
      {/* warm wash behind the hero */}
      <div
        aria-hidden="true"
        className="absolute inset-x-0 top-0 -z-10 h-[640px] bg-[radial-gradient(60%_60%_at_80%_10%,var(--brand-soft),transparent_70%),radial-gradient(50%_50%_at_0%_30%,var(--saffron-soft),transparent_70%)]"
      />
      <Container size="wide" className="grid grid-cols-1 items-center gap-12 pb-16 pt-10 sm:pt-16 lg:grid-cols-[minmax(0,1.1fr)_minmax(0,0.9fr)] lg:pb-24">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full border border-line bg-surface/70 px-3 py-1 text-xs font-medium text-ink-muted backdrop-blur">
            <Sparkles className="h-3.5 w-3.5 text-brand" aria-hidden="true" />
            Home-cooked, ordered from the people next door
          </p>
          <h1 className="mt-6 font-display text-[2.75rem] font-semibold leading-[1.02] tracking-tight text-ink sm:text-6xl lg:text-7xl">
            Dinner from the kitchen{" "}
            <span className="italic text-brand">next door.</span>
          </h1>
          <p className="mt-6 max-w-xl text-lg leading-relaxed text-ink-muted">
            Order dishes cooked by people in your neighbourhood. Every ingredient listed, every
            allergen declared - and one kitchen per order, so it arrives together.
          </p>

          <form
            action="/dishes"
            method="get"
            role="search"
            className="mt-8 flex flex-col gap-2 rounded-3xl border border-line bg-surface p-2 shadow-lift sm:flex-row sm:items-center sm:rounded-full"
          >
            <label className="relative flex-1">
              <span className="sr-only">What are you craving?</span>
              <Search className="pointer-events-none absolute left-4 top-1/2 h-5 w-5 -translate-y-1/2 text-ink-soft" />
              <input
                name="q"
                type="search"
                placeholder="Try biryani or dumplings"
                className="h-12 w-full rounded-full bg-transparent pl-12 pr-4 text-base text-ink placeholder:text-ink-soft focus:outline-none"
              />
            </label>
            {zones.length > 0 && (
              <label className="sm:w-52 sm:border-l sm:border-line sm:pl-2">
                <span className="sr-only">Neighbourhood</span>
                <Select name="zone" defaultValue="" className="h-12 rounded-full border-0 bg-muted shadow-none sm:bg-transparent">
                  <option value="">Any neighbourhood</option>
                  {zones.map((zone) => (
                    <option key={zone.slug} value={zone.slug}>
                      Near {zone.name}
                    </option>
                  ))}
                </Select>
                {/* "Near" = the zone and its direct neighbours */}
                <input type="hidden" name="max_distance" value="1" />
              </label>
            )}
            <button type="submit" className={cx(primaryButtonClass, "h-12 px-7 text-[15px]")}>
              Find food
            </button>
          </form>

          <div className="mt-5 flex flex-wrap items-center gap-2">
            <span className="mr-1 text-sm text-ink-soft">Popular:</span>
            {DIETS.slice(0, 5).map((diet) => (
              <Link
                key={diet.tag}
                href={`/dishes?dietary_tag=${encodeURIComponent(diet.tag)}`}
                className="rounded-full border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink-muted transition-colors hover:border-ink-soft hover:text-ink"
              >
                {diet.label}
              </Link>
            ))}
          </div>

          {stats.length > 0 && (
            <dl className="mt-10 flex flex-wrap gap-x-10 gap-y-4">
              {stats.map((stat) => (
                <div key={stat.label}>
                  <dt className="sr-only">{stat.label}</dt>
                  <dd className="font-display text-3xl font-semibold text-ink">
                    {stat.value}
                    <span className="ml-2 font-sans text-sm font-normal text-ink-muted">{stat.label}</span>
                  </dd>
                </div>
              ))}
            </dl>
          )}
        </div>

        <HeroCollage dishes={featured.slice(0, 3)} />
      </Container>
    </section>
  );
}

/** Three featured dishes as an overlapping, slightly rotated stack. */
function HeroCollage({ dishes }: { dishes: Dish[] }) {
  if (dishes.length === 0) return null;
  const [main, second, third] = dishes;
  return (
    <div aria-hidden="true" className="relative mx-auto hidden h-[520px] w-full max-w-[520px] sm:block">
      <figure className="absolute left-0 top-[7%] w-[64%] rotate-[-3deg] rounded-[2rem] bg-surface p-3 shadow-pop">
        <DishArt dish={main} size="lg" className="aspect-square" rounded="rounded-[1.5rem]" />
        <figcaption className="flex items-center justify-between gap-3 px-2 pb-1 pt-3">
          <div className="min-w-0">
            <p className="truncate font-display text-lg font-semibold text-ink">{main.name}</p>
            <p className="truncate text-xs text-ink-muted">by {main.cook_name ?? "a home cook"}</p>
          </div>
          <span className="rounded-full bg-ink px-3 py-1 text-sm font-semibold text-canvas">
            {formatMinorUnits(main.price)}
          </span>
        </figcaption>
      </figure>
      {second && (
        <figure className="absolute right-0 top-[24%] w-[42%] rotate-[4deg] rounded-[1.6rem] bg-surface p-2.5 shadow-pop">
          <DishArt dish={second} size="md" className="aspect-square" rounded="rounded-[1.2rem]" />
          <figcaption className="truncate px-1.5 pb-0.5 pt-2 text-sm font-semibold text-ink">{second.name}</figcaption>
        </figure>
      )}
      {third && (
        <div className="absolute bottom-[3%] right-[2%] flex items-center gap-3 rounded-2xl bg-surface p-2.5 pr-4 shadow-pop">
          <DishArt dish={third} size="xs" className="h-12 w-12" rounded="rounded-xl" />
          <div>
            <p className="text-sm font-semibold text-ink">{third.name}</p>
            <p className="flex items-center gap-1 text-xs text-herb">
              <CircleCheck className="h-3.5 w-3.5" /> Allergens declared
            </p>
          </div>
        </div>
      )}
      <div className="absolute right-[4%] top-[8%] flex items-center gap-2 rounded-full bg-surface px-3 py-2 text-xs font-semibold text-ink shadow-lift">
        <Avatar name={main.cook_name} size="sm" className="h-6 w-6 text-[10px]" />
        From a kitchen in {main.zone?.name ?? "your area"}
      </div>
    </div>
  );
}

// --- how it works ----------------------------------------------------------------------------

function HowItWorks() {
  const steps = [
    {
      icon: MapPin,
      title: "Find a cook near you",
      body: "Browse today's dishes by neighbourhood, diet or craving. Filter out any allergen in one tap.",
    },
    {
      icon: ShoppingBag,
      title: "Fill your bag from one kitchen",
      body: "Every order comes from a single cook, so everything is made together and arrives together.",
    },
    {
      icon: ChefHat,
      title: "They cook, you follow along",
      body: "Your cook accepts the order and you see it move from accepted to ready to on its way.",
    },
  ];
  return (
    <section id="how-it-works" className="border-y border-line bg-surface">
      <Container className="py-14 sm:py-20">
        <SectionHeading
          eyebrow="How it works"
          title="Three steps from their stove to your table"
        />
        <ol className="grid grid-cols-1 gap-6 md:grid-cols-3">
          {steps.map((step, index) => (
            <li key={step.title} className="relative rounded-3xl bg-canvas p-7">
              <span className="absolute right-6 top-5 font-display text-5xl font-semibold text-line-strong">
                {index + 1}
              </span>
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-soft text-brand">
                <step.icon className="h-6 w-6" aria-hidden="true" />
              </span>
              <h3 className="mt-6 font-display text-xl font-semibold tracking-tight text-ink">{step.title}</h3>
              <p className="mt-2 leading-relaxed text-ink-muted">{step.body}</p>
            </li>
          ))}
        </ol>
      </Container>
    </section>
  );
}

// --- transparency ----------------------------------------------------------------------------

function Transparency({ example }: { example?: Dish }) {
  return (
    <section className="bg-canvas">
      <Container className="grid grid-cols-1 items-center gap-12 py-14 sm:py-20 lg:grid-cols-2">
        <div>
          <p className="inline-flex items-center gap-2 rounded-full bg-herb-soft px-3 py-1 text-xs font-semibold text-herb">
            <ShieldCheck className="h-3.5 w-3.5" aria-hidden="true" /> Food you can trust
          </p>
          <h2 className="mt-5 font-display text-3xl font-semibold tracking-tight text-ink sm:text-4xl">
            Know exactly what&apos;s on your plate.
          </h2>
          <p className="mt-4 text-lg leading-relaxed text-ink-muted">
            Cooks declare allergens from the {ALLERGENS.length} major groups and list every
            ingredient. Exclude what you can&apos;t eat and it disappears from the menu.
          </p>
          <ul className="mt-8 space-y-4">
            {[
              "Ingredient lists on every dish, searchable",
              `${ALLERGENS.length} allergen groups, declared by the cook`,
              "Dietary tags like vegan, halal and gluten free",
            ].map((point) => (
              <li key={point} className="flex items-start gap-3 text-ink">
                <CircleCheck className="mt-0.5 h-5 w-5 shrink-0 text-herb" aria-hidden="true" />
                {point}
              </li>
            ))}
          </ul>
        </div>

        {example && (
          <div className="rounded-[2rem] border border-line bg-surface p-6 shadow-lift sm:p-8">
            <div className="flex items-center gap-4">
              <DishArt dish={example} size="sm" className="h-20 w-20 shrink-0" />
              <div>
                <p className="font-display text-xl font-semibold text-ink">{example.name}</p>
                <p className="text-sm text-ink-muted">by {example.cook_name ?? "a home cook"}</p>
              </div>
            </div>
            <dl className="mt-6 space-y-5 text-sm">
              <div>
                <dt className="font-semibold text-ink">Ingredients</dt>
                <dd className="mt-1.5 leading-relaxed text-ink-muted">
                  {example.ingredients.length > 0 ? example.ingredients.join(", ") : "Listed by the cook"}
                </dd>
              </div>
              <div>
                <dt className="font-semibold text-ink">Contains</dt>
                <dd className="mt-2 flex flex-wrap gap-1.5">
                  {example.allergens.length > 0 ? (
                    example.allergens.map((allergen) => <AllergenTag key={allergen}>{allergen}</AllergenTag>)
                  ) : (
                    <span className="text-herb">No declared allergens</span>
                  )}
                </dd>
              </div>
              {example.dietary_tags.length > 0 && (
                <div>
                  <dt className="font-semibold text-ink">Suitable for</dt>
                  <dd className="mt-2 flex flex-wrap gap-1.5">
                    {example.dietary_tags.map((tag) => (
                      <Tag key={tag} className="capitalize">
                        <Leaf className="mr-1 h-3 w-3" aria-hidden="true" />
                        {tag}
                      </Tag>
                    ))}
                  </dd>
                </div>
              )}
            </dl>
          </div>
        )}
      </Container>
    </section>
  );
}

// --- cook CTA --------------------------------------------------------------------------------

function CookCta() {
  return (
    <Container className="pb-6 pt-4">
      <section className="grain relative overflow-hidden rounded-[2rem] bg-night px-6 py-14 text-on-night sm:px-12 sm:py-16">
        <div
          aria-hidden="true"
          className="absolute -right-24 -top-24 h-80 w-80 rounded-full bg-[radial-gradient(circle,var(--brand)_0%,transparent_70%)] opacity-40"
        />
        <div className="relative max-w-2xl">
          <p className="text-xs font-semibold uppercase tracking-[0.16em] text-brand">For home cooks</p>
          <h2 className="mt-3 font-display text-3xl font-semibold tracking-tight sm:text-5xl">
            Cook something your neighbours would love?
          </h2>
          <p className="mt-4 text-lg text-on-night/70">
            Open your kitchen on Plateboard: publish your dishes, set your prices and take orders
            from people nearby.
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
            <ButtonLink href="/register?next=/cook" className="h-12 px-7">
              Open your kitchen <ArrowRight className="h-4 w-4" />
            </ButtonLink>
            <Link
              href="/cooks"
              className="inline-flex h-12 items-center rounded-full border border-on-night/25 px-7 text-sm font-semibold text-on-night transition-colors hover:bg-on-night/10"
            >
              Meet the cooks
            </Link>
          </div>
        </div>
      </section>
    </Container>
  );
}
