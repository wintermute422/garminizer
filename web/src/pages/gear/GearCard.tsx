import { clsx } from "clsx";
import { AlertTriangle, CircleCheck, OctagonAlert } from "lucide-react";
import { createElement } from "react";
import { distanceValue, fmtDate, fmtDistance, fmtNumber, distanceUnit } from "@/lib/format";
import { useUnits } from "@/lib/preferences";
import { STATUS, wash } from "@/lib/tokens";
import {
  gearIcon,
  gearMakeModel,
  gearName,
  isRetired,
  typeLabel,
  WEAR_LABEL,
  wearLevel,
  type Gear,
} from "./gear";

const WEAR_ICON = { good: CircleCheck, warning: AlertTriangle, critical: OctagonAlert };

export function WearMeter({ g }: { g: Gear }) {
  const units = useUnits();
  if (!g.max_distance_m || g.wear_pct === null) return null;
  const pct = g.wear_pct;
  const level = wearLevel(pct);
  const color = STATUS[level];
  const unit = distanceUnit(units);
  return (
    <span className="block">
      <span
        aria-hidden
        className="block h-2 overflow-hidden rounded-bar"
        style={{ background: wash(color, 0.18) }}
      >
        <span
          className="block h-full rounded-bar"
          style={{ width: `${Math.min(pct, 100)}%`, background: color }}
        />
      </span>
      <span className="mt-1.5 flex flex-wrap items-center justify-between gap-x-3 gap-y-0.5 text-xs">
        <span className="inline-flex items-center gap-1 font-medium text-ink-2">
          {createElement(WEAR_ICON[level], { size: 14, color, "aria-hidden": true })}
          {WEAR_LABEL[level]}
        </span>
        <span className="text-ink-2 tabular">
          {fmtNumber(distanceValue(g.distance_m, units))} /{" "}
          {fmtNumber(distanceValue(g.max_distance_m, units))} {unit} · {fmtNumber(pct)} %
        </span>
      </span>
    </span>
  );
}

export function GearCard({
  g,
  color,
  selected,
  onSelect,
}: {
  g: Gear;
  color: string;
  selected: boolean;
  onSelect: (uuid: string) => void;
}) {
  const units = useUnits();
  const retired = isRetired(g);
  const [value, unit] = fmtDistance(g.distance_m, units, 0).split(" ");
  const sub = gearMakeModel(g);
  return (
    <button
      type="button"
      aria-pressed={selected}
      onClick={() => onSelect(g.uuid)}
      className={clsx(
        "flex min-w-0 flex-col gap-3 rounded-card border bg-surface p-4 text-left shadow-card transition-colors",
        selected ? "border-accent ring-1 ring-accent" : "border-line hover:border-line-strong",
      )}
    >
      <span className="flex w-full items-start gap-3">
        <span className="inline-flex size-10 shrink-0 items-center justify-center rounded-control bg-surface-2 text-ink-2">
          {createElement(gearIcon(g.gear_type), { size: 19, "aria-hidden": true })}
        </span>
        <span className="min-w-0 flex-1">
          <span className="flex items-center gap-1.5">
            <span
              aria-hidden
              className="inline-block size-2.5 shrink-0 rounded-swatch"
              style={{ background: color }}
            />
            <span className="truncate text-sm font-semibold text-ink">{gearName(g)}</span>
          </span>
          <span className="mt-0.5 block truncate text-xs text-ink-3">
            {sub || typeLabel(g.gear_type, false)}
          </span>
        </span>
        {retired && (
          <span className="shrink-0 rounded-chip border border-line px-2 py-0.5 text-2xs font-medium text-ink-2">
            Retired
          </span>
        )}
      </span>
      <span className="flex items-baseline gap-1">
        <span className="text-metric font-semibold text-ink">{value}</span>
        <span className="text-sm text-ink-3">{unit}</span>
        <span className="ml-auto text-xs text-ink-3 tabular">
          {fmtNumber(g.activities)} {g.activities === 1 ? "activity" : "activities"}
        </span>
      </span>
      <span className="grid w-full grid-cols-2 gap-2 text-xs">
        <span>
          <span className="block text-ink-3">First use</span>
          <span className="block font-medium text-ink-2">{fmtDate(g.date_begin)}</span>
        </span>
        <span>
          <span className="block text-ink-3">{retired ? "Retired" : "Last use"}</span>
          <span className="block font-medium text-ink-2">
            {fmtDate(retired ? (g.date_end ?? g.last_used) : g.last_used)}
          </span>
        </span>
      </span>
      {g.max_distance_m ? (
        <span className="mt-auto block w-full">
          <WearMeter g={g} />
        </span>
      ) : (
        <span className="mt-auto block w-full text-xs text-ink-3">
          {g.activities
            ? `${fmtDistance(g.distance_m / g.activities, units)} per activity on average · no replacement distance set`
            : "No replacement distance set"}
        </span>
      )}
    </button>
  );
}
