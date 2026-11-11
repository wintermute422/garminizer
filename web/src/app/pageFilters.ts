/**
 * The global filters as one page sees them: date range + sport from the URL, with the page's
 * defaults (preset, sport) read from its entry in nav.ts — the same source the filter bar
 * uses, so the filter summary and the page's data can never disagree.
 */
import { keepPreviousData } from "@tanstack/react-query";
import { useNavigate, useRouterState, useSearch } from "@tanstack/react-router";
import { api } from "@/api/client";
import { resolveRange, type GlobalSearch, type PresetKey } from "@/lib/range";
import { navItemFor, type NavItem } from "./nav";

export type PageDefaults = Pick<NavItem, "filters" | "defaultPreset" | "defaultSport">;

export interface ResolvedFilters {
  start: string;
  end: string;
  preset: PresetKey | null;
  /** The page's default preset (what an empty URL shows). */
  defaultPreset: PresetKey;
  /**
   * Chosen sport, else the page's default sport; null for "all sports" and on pages without a
   * sport filter (a sport left in the URL by another page is ignored there).
   */
  sport: string | null;
  /** `{start, end}` for queries that are never sport-filtered. */
  dates: { start: string; end: string };
  /** `{start, end}` plus `sport` when one applies: the query of sport-filtered endpoints. */
  query: { start: string; end: string; sport?: string };
}

/** Pure part of `usePageFilters` (URL search + nav defaults + data extent → filters). */
export function resolvePageFilters(
  search: GlobalSearch,
  page: PageDefaults | undefined,
  meta: { last_day?: string | null; first_day?: string | null } | undefined,
): ResolvedFilters {
  const defaultPreset = page?.defaultPreset ?? "90d";
  const { start, end, preset } = resolveRange(
    search,
    meta?.last_day,
    meta?.first_day,
    defaultPreset,
  );
  const withSport = page?.filters === "range+sport" || page?.filters === "sport";
  const sport = withSport ? (search.sport ?? page?.defaultSport ?? null) : null;
  const dates = { start, end };
  return {
    start,
    end,
    preset,
    defaultPreset,
    sport,
    dates,
    query: sport ? { ...dates, sport } : dates,
  };
}

/** Filters of the current page, plus setters and the query options every page repeats. */
export function usePageFilters() {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const search = useSearch({ strict: false }) as GlobalSearch;
  const navigate = useNavigate();
  const meta = api.useQuery("get", "/api/meta");
  const filters = resolvePageFilters(search, navItemFor(pathname), meta.data);
  const ready = meta.isSuccess;

  const update = (patch: Partial<GlobalSearch>) =>
    navigate({
      to: ".",
      search: (prev: Record<string, unknown>) => {
        const next = { ...prev, ...patch } as Record<string, unknown>;
        for (const k of Object.keys(next)) if (next[k] === undefined) delete next[k];
        return next;
      },
      replace: true,
    } as never);

  return {
    ...filters,
    /** The data extent is known (presets are relative to the last day with data). */
    ready,
    /** Query options for range-dependent queries: wait for the extent, keep the last data. */
    options: { enabled: ready, placeholderData: keepPreviousData },
    setPreset: (preset: PresetKey) => update({ preset, start: undefined, end: undefined }),
    setCustom: (start: string, end: string) => update({ start, end, preset: undefined }),
    setSport: (sport: string | null) => update({ sport: sport ?? undefined }),
  };
}

export type PageFilters = ReturnType<typeof usePageFilters>;
