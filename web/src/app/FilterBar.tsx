import { clsx } from "clsx";
import { useState } from "react";
import { api } from "@/api/client";
import { PRESETS, useRange, type PresetKey } from "@/lib/range";
import { useMode } from "@/lib/preferences";
import { bySlot, sportColor, sportLabel } from "@/lib/sports";

/** Global filters in one row above the charts: date range presets (+ custom) and sport. */
export function FilterBar({
  withSport,
  fallback = "90d",
}: {
  withSport: boolean;
  fallback?: PresetKey;
}) {
  const range = useRange(fallback);
  const meta = api.useQuery("get", "/api/meta");
  const mode = useMode();
  const [custom, setCustom] = useState(false);
  const sports = [...(meta.data?.sports ?? [])].sort((a, b) =>
    bySlot(a.sport_group, b.sport_group),
  );

  return (
    <div className="flex flex-wrap items-center gap-2" data-testid="filter-bar">
      <div
        role="radiogroup"
        aria-label="Date range"
        className="inline-flex max-w-full overflow-x-auto rounded-xl border border-line bg-surface-2 p-0.5"
      >
        {PRESETS.map((p) => (
          <button
            key={p.key}
            type="button"
            role="radio"
            aria-checked={range.preset === p.key}
            onClick={() => {
              setCustom(false);
              range.setPreset(p.key as PresetKey);
            }}
            className={clsx(
              "shrink-0 rounded-[10px] px-2.5 py-1 text-xs font-medium whitespace-nowrap",
              range.preset === p.key
                ? "bg-surface text-ink shadow-card"
                : "text-ink-2 hover:text-ink",
            )}
          >
            {p.label}
          </button>
        ))}
        <button
          type="button"
          role="radio"
          aria-checked={range.preset === null}
          onClick={() => setCustom((v) => !v)}
          className={clsx(
            "shrink-0 rounded-[10px] px-2.5 py-1 text-xs font-medium",
            range.preset === null ? "bg-surface text-ink shadow-card" : "text-ink-2 hover:text-ink",
          )}
        >
          Custom
        </button>
      </div>
      {(custom || range.preset === null) && (
        <div className="flex items-center gap-1.5 text-xs text-ink-2">
          <label className="sr-only" htmlFor="range-start">
            Start date
          </label>
          <input
            id="range-start"
            type="date"
            value={range.start}
            max={range.end}
            onChange={(e) => e.target.value && range.setCustom(e.target.value, range.end)}
            className="rounded-lg border border-line bg-surface px-2 py-1 text-ink"
          />
          <span aria-hidden>→</span>
          <label className="sr-only" htmlFor="range-end">
            End date
          </label>
          <input
            id="range-end"
            type="date"
            value={range.end}
            min={range.start}
            onChange={(e) => e.target.value && range.setCustom(range.start, e.target.value)}
            className="rounded-lg border border-line bg-surface px-2 py-1 text-ink"
          />
        </div>
      )}
      {withSport && sports.length > 1 && (
        <div role="radiogroup" aria-label="Sport" className="flex max-w-full flex-wrap gap-1">
          <button
            type="button"
            role="radio"
            aria-checked={range.sport === null}
            onClick={() => range.setSport(null)}
            className={clsx(
              "rounded-full border px-2.5 py-1 text-xs font-medium",
              range.sport === null
                ? "border-line-strong bg-surface text-ink"
                : "border-line text-ink-2 hover:text-ink",
            )}
          >
            All sports
          </button>
          {sports.map((s) => (
            <button
              key={s.sport_group}
              type="button"
              role="radio"
              aria-checked={range.sport === s.sport_group}
              onClick={() => range.setSport(s.sport_group)}
              className={clsx(
                "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
                range.sport === s.sport_group
                  ? "border-line-strong bg-surface text-ink"
                  : "border-line text-ink-2 hover:text-ink",
              )}
            >
              <span
                className="size-2 rounded-full"
                style={{ background: sportColor(s.sport_group, mode) }}
                aria-hidden
              />
              {sportLabel(s.sport_group)}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
