import DishDirectory from "@/components/dish-directory";
import { ApiError, type DishPage, type Zone } from "@/lib/api";
import { dishFiltersToParams, parseDishFilters, parseOffset, toSearchParams } from "@/lib/dish-filters";
import { serverGet } from "@/lib/server-api";

const PAGE_SIZE = 12;

function errorLines(cause: unknown): string[] {
  return cause instanceof ApiError ? cause.lines : ["Could not reach the API"];
}

/**
 * Public dish list, rendered on the server.
 *
 * The first page of dishes (and the zone list for the filters) is fetched
 * here, in parallel, straight from the backend, so the cards are part of the
 * HTML - visible before any JavaScript runs, with no browser round trip
 * after hydration. The URL query string is the state (lib/dish-filters.ts)
 * and is forwarded to GET /api/dishes as-is, so a shared link reproduces the
 * exact list; filter changes navigate, which re-runs this component.
 */
export default async function DishDirectoryPage({ searchParams }: PageProps<"/">) {
  const params = toSearchParams(await searchParams);
  const filters = parseDishFilters(params);
  const offset = parseOffset(params);

  const query = dishFiltersToParams(filters, offset);
  query.set("limit", String(PAGE_SIZE));
  const [dishes, zones] = await Promise.allSettled([
    serverGet<DishPage>(`/dishes?${query.toString()}`),
    serverGet<Zone[]>("/zones"),
  ]);

  return (
    <DishDirectory
      filters={filters}
      offset={offset}
      pageSize={PAGE_SIZE}
      page={dishes.status === "fulfilled" ? dishes.value : null}
      errors={dishes.status === "rejected" ? errorLines(dishes.reason) : []}
      zones={zones.status === "fulfilled" ? zones.value : null}
      zonesError={zones.status === "rejected" ? errorLines(zones.reason)[0] : null}
    />
  );
}
