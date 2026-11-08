/**
 * Global date range + sport filter, kept in the URL (?preset=90d&sport=run or ?start=&end=)
 * so every view is shareable and survives reloads. Presets are relative to the last day with
 * data (not today), so a paused sync never shows empty charts.
 */
import { useNavigate, useSearch } from "@tanstack/react-router";
import { api } from "@/api/client";

export const PRESETS = [
  { key: "30d", label: "30 days", days: 30 },
  { key: "90d", label: "90 days", days: 90 },
  { key: "180d", label: "6 months", days: 182 },
  { key: "365d", label: "1 year", days: 365 },
  { key: "730d", label: "2 years", days: 730 },
  { key: "ytd", label: "This year", days: null },
  { key: "all", label: "All time", days: null },
] as const;
export type PresetKey = (typeof PRESETS)[number]["key"];

export interface GlobalSearch {
  preset?: PresetKey;
  start?: string;
  end?: string;
  sport?: string;
}

export function validateGlobalSearch(search: Record<string, unknown>): GlobalSearch {
  const out: GlobalSearch = {};
  const preset = search.preset;
  if (typeof preset === "string" && PRESETS.some((p) => p.key === preset)) {
    out.preset = preset as PresetKey;
  }
  const iso = /^\d{4}-\d{2}-\d{2}$/;
  if (typeof search.start === "string" && iso.test(search.start)) out.start = search.start;
  if (typeof search.end === "string" && iso.test(search.end)) out.end = search.end;
  if (typeof search.sport === "string" && search.sport) out.sport = search.sport;
  return out;
}

export function isoDay(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

export function addDays(iso: string, days: number): string {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + days);
  return isoDay(d);
}

export function resolveRange(
  search: GlobalSearch,
  lastDay: string | null | undefined,
  firstDay: string | null | undefined,
  fallback: PresetKey = "90d",
): { start: string; end: string; preset: PresetKey | null } {
  const end = search.end ?? lastDay ?? isoDay(new Date());
  if (search.start) return { start: search.start, end, preset: null };
  const key = search.preset ?? fallback;
  const preset = PRESETS.find((p) => p.key === key) ?? PRESETS[1];
  if (preset.key === "all") return { start: firstDay ?? addDays(end, -3650), end, preset: "all" };
  if (preset.key === "ytd") return { start: `${end.slice(0, 4)}-01-01`, end, preset: "ytd" };
  return { start: addDays(end, -((preset.days ?? 90) - 1)), end, preset: preset.key };
}

/** Current range + setters. `fallback` is the page's default preset. */
export function useRange(fallback: PresetKey = "90d") {
  const search = useSearch({ strict: false }) as GlobalSearch;
  const navigate = useNavigate();
  const meta = api.useQuery("get", "/api/meta");
  const range = resolveRange(search, meta.data?.last_day, meta.data?.first_day, fallback);

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
    ...range,
    sport: search.sport ?? null,
    ready: meta.isSuccess,
    query: { start: range.start, end: range.end },
    setPreset: (preset: PresetKey) => update({ preset, start: undefined, end: undefined }),
    setCustom: (start: string, end: string) => update({ start, end, preset: undefined }),
    setSport: (sport: string | null) => update({ sport: sport ?? undefined }),
  };
}
