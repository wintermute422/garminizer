import { clsx } from "clsx";
import { SlidersHorizontal } from "lucide-react";
import { useId, useState } from "react";
import { api } from "@/api/client";
import { fmtShortDate } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { PRESETS, useRange, type PresetKey } from "@/lib/range";
import { bySlot, sportColor, sportLabel } from "@/lib/sports";

interface FilterProps {
  withRange: boolean;
  withSport: boolean;
  fallback?: PresetKey;
  /** The page always shows one sport; this one when none is chosen (no "All sports"). */
  defaultSport?: string;
}

function chip(active: boolean) {
  return clsx(
    "inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs font-medium",
    active ? "border-line-strong bg-surface text-ink" : "border-line text-ink-2 hover:text-ink",
  );
}

function Controls({
  withRange,
  withSport,
  fallback = "90d",
  defaultSport,
  stacked,
}: FilterProps & { stacked: boolean }) {
  const range = useRange(fallback);
  const meta = api.useQuery("get", "/api/meta");
  const mode = useMode();
  const id = useId();
  const [custom, setCustom] = useState(false);
  const sports = [...(meta.data?.sports ?? [])].sort((a, b) =>
    bySlot(a.sport_group, b.sport_group),
  );
  const selectedSport = range.sport ?? defaultSport ?? null;

  return (
    <div
      className={clsx("flex gap-2", stacked ? "flex-col items-stretch" : "flex-wrap items-center")}
    >
      {withRange && (
        <div
          role="radiogroup"
          aria-label="Date range"
          className={clsx(
            "inline-flex rounded-xl border border-line bg-surface-2 p-0.5",
            stacked ? "flex-wrap" : "max-w-full overflow-x-auto",
          )}
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
                stacked && "py-1.5",
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
              stacked && "py-1.5",
              range.preset === null
                ? "bg-surface text-ink shadow-card"
                : "text-ink-2 hover:text-ink",
            )}
          >
            Custom
          </button>
        </div>
      )}
      {withRange && (custom || range.preset === null) && (
        <div className="flex items-center gap-1.5 text-xs text-ink-2">
          <label className="sr-only" htmlFor={`${id}-start`}>
            Start date
          </label>
          <input
            id={`${id}-start`}
            type="date"
            value={range.start}
            max={range.end}
            onChange={(e) => e.target.value && range.setCustom(e.target.value, range.end)}
            className="min-w-0 rounded-lg border border-line bg-surface px-2 py-1 text-ink"
          />
          <span aria-hidden>→</span>
          <label className="sr-only" htmlFor={`${id}-end`}>
            End date
          </label>
          <input
            id={`${id}-end`}
            type="date"
            value={range.end}
            min={range.start}
            onChange={(e) => e.target.value && range.setCustom(range.start, e.target.value)}
            className="min-w-0 rounded-lg border border-line bg-surface px-2 py-1 text-ink"
          />
        </div>
      )}
      {withSport && sports.length > 1 && (
        <div role="radiogroup" aria-label="Sport" className="flex max-w-full flex-wrap gap-1">
          {!defaultSport && (
            <button
              type="button"
              role="radio"
              aria-checked={selectedSport === null}
              onClick={() => range.setSport(null)}
              className={chip(selectedSport === null)}
            >
              All sports
            </button>
          )}
          {sports.map((s) => (
            <button
              key={s.sport_group}
              type="button"
              role="radio"
              aria-checked={selectedSport === s.sport_group}
              onClick={() => range.setSport(s.sport_group)}
              className={chip(selectedSport === s.sport_group)}
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

/** One-line summary of the current filters (mobile trigger). */
function Summary({ withRange, withSport, fallback = "90d", defaultSport }: FilterProps) {
  const range = useRange(fallback);
  const parts: string[] = [];
  if (withRange) {
    const preset = PRESETS.find((p) => p.key === range.preset);
    parts.push(preset ? preset.label : `${fmtShortDate(range.start)} – ${fmtShortDate(range.end)}`);
  }
  if (withSport) {
    const sport = range.sport ?? defaultSport ?? null;
    parts.push(sport ? sportLabel(sport) : "All sports");
  }
  return <>{parts.join(" · ")}</>;
}

/**
 * Global filters above the charts. Desktop: one row of controls. Phones: a single summary
 * button that opens the same controls in a bottom sheet (no tall stack of chips).
 */
export function FilterBar(props: FilterProps) {
  const [open, setOpen] = useState(false);
  return (
    <div data-testid="filter-bar">
      <div className="hidden sm:block">
        <Controls {...props} stacked={false} />
      </div>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-haspopup="dialog"
        className="inline-flex max-w-full items-center gap-2 rounded-xl border border-line bg-surface-2 px-3 py-1.5 text-sm font-medium text-ink sm:hidden"
      >
        <SlidersHorizontal size={15} aria-hidden className="shrink-0 text-ink-3" />
        <span className="truncate">
          <Summary {...props} />
        </span>
      </button>
      {open && (
        <div
          className="fixed inset-0 z-50 sm:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Filters"
        >
          <button
            type="button"
            aria-label="Close filters"
            className="absolute inset-0 bg-black/40"
            onClick={() => setOpen(false)}
          />
          <div className="absolute inset-x-0 bottom-0 max-h-[80vh] overflow-y-auto rounded-t-2xl border-t border-line bg-surface p-4 shadow-card">
            <div className="mx-auto mb-3 h-1 w-10 rounded-full bg-surface-3" aria-hidden />
            <Controls {...props} stacked />
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="mt-4 w-full rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
