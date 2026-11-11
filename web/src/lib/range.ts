/**
 * Global date range + sport filter, kept in the URL (?preset=90d&sport=run or ?start=&end=)
 * so every view is shareable and survives reloads. Presets are relative to the last day with
 * data (not today), so a paused sync never shows empty charts.
 */

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
