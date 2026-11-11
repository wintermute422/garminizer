import { clsx } from "clsx";
import { SlidersHorizontal } from "lucide-react";
import { useRouterState } from "@tanstack/react-router";
import { useId, useState } from "react";
import { api } from "@/api/client";
import { fmtShortDate } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { PRESETS, type PresetKey } from "@/lib/range";
import { bySlot, sportColor, sportLabel } from "@/lib/sports";
import { navItemFor } from "./nav";
import { usePageFilters } from "./pageFilters";

/** Which controls the page has (its nav.ts entry holds the defaults: usePageFilters). */
interface FilterProps {
  withRange: boolean;
  withSport: boolean;
}

function chip(active: boolean) {
  return clsx(
    "inline-flex items-center gap-1.5 rounded-chip border px-2.5 py-1 text-xs font-medium transition-colors",
    active
      ? "border-rule bg-surface text-ink"
      : "border-line text-ink-2 hover:bg-hover hover:text-ink active:bg-pressed",
  );
}

function Controls({ withRange, withSport, stacked }: FilterProps & { stacked: boolean }) {
  const range = usePageFilters();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const defaultSport = navItemFor(pathname)?.defaultSport;
  const meta = api.useQuery("get", "/api/meta");
  const mode = useMode();
  const id = useId();
  const [custom, setCustom] = useState(false);
  const sports = [...(meta.data?.sports ?? [])].sort((a, b) =>
    bySlot(a.sport_group, b.sport_group),
  );
  const selectedSport = range.sport;

  return (
    <div
      className={clsx("flex gap-2", stacked ? "flex-col items-stretch" : "flex-wrap items-center")}
    >
      {withRange && (
        <div
          role="radiogroup"
          aria-label="Date range"
          className={clsx(
            "inline-flex rounded-control border border-line bg-surface p-0.5",
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
                "shrink-0 rounded-chip px-2.5 py-1 text-xs font-medium whitespace-nowrap transition-colors",
                stacked && "py-1.5",
                range.preset === p.key
                  ? "bg-selected text-on-selected"
                  : "text-ink-2 hover:bg-hover hover:text-ink active:bg-pressed",
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
              "shrink-0 rounded-chip px-2.5 py-1 text-xs font-medium transition-colors",
              stacked && "py-1.5",
              range.preset === null
                ? "bg-selected text-on-selected"
                : "text-ink-2 hover:bg-hover hover:text-ink active:bg-pressed",
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
            className="min-w-0 rounded-control border border-line-strong bg-surface px-2 py-1 text-ink"
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
            className="min-w-0 rounded-control border border-line-strong bg-surface px-2 py-1 text-ink"
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
                className="size-2 rounded-swatch"
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
function Summary({ withRange, withSport }: FilterProps) {
  const range = usePageFilters();
  const parts: string[] = [];
  if (withRange) {
    const preset = PRESETS.find((p) => p.key === range.preset);
    parts.push(preset ? preset.label : `${fmtShortDate(range.start)} – ${fmtShortDate(range.end)}`);
  }
  if (withSport) {
    const sport = range.sport;
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
        className="inline-flex max-w-full items-center gap-2 rounded-control border border-line bg-surface px-3 py-1.5 text-sm font-medium text-ink active:bg-pressed sm:hidden"
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
            className="absolute inset-0 bg-scrim"
            onClick={() => setOpen(false)}
          />
          <div className="absolute inset-x-0 bottom-0 max-h-[80vh] overflow-y-auto rounded-t-card border-t border-rule bg-surface p-4 shadow-overlay">
            <div className="mx-auto mb-3 h-1 w-10 rounded-bar bg-surface-3" aria-hidden />
            <Controls {...props} stacked />
            <button
              type="button"
              onClick={() => setOpen(false)}
              className="mt-4 w-full rounded-control bg-action px-4 py-2.5 text-sm font-semibold text-on-action transition-colors hover:bg-action-hover"
            >
              Done
            </button>
          </div>
        </div>
      )}
    </div>
  );
}
