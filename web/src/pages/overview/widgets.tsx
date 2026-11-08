/** Small page-local building blocks of the overview (candidates for components/ui). */
import { clsx } from "clsx";
import type { ReactNode } from "react";

/**
 * Progress meter: the accent fill on a lighter track of the same hue. Decorative — the value is
 * always printed next to it as text.
 */
export function Meter({
  value,
  max,
  color,
  size = "md",
  className,
}: {
  value: number;
  max: number;
  color?: string;
  size?: "sm" | "md";
  className?: string;
}) {
  const pct = max > 0 ? Math.min(Math.max(value / max, 0), 1) * 100 : 0;
  return (
    <div
      aria-hidden
      className={clsx(
        "w-full overflow-hidden rounded-full bg-accent-soft",
        size === "sm" ? "h-1.5" : "h-2",
        className,
      )}
    >
      <div
        className="h-full rounded-full"
        style={{ width: `${pct}%`, background: color ?? "var(--accent)" }}
      />
    </div>
  );
}

/** Label over a medium-size value (+ unit and a small line below). */
export function MiniStat({
  label,
  value,
  unit,
  sub,
  className,
}: {
  label: ReactNode;
  value: ReactNode;
  unit?: string;
  sub?: ReactNode;
  className?: string;
}) {
  return (
    <div className={clsx("min-w-0", className)}>
      <p className="truncate text-xs text-ink-3">{label}</p>
      <p className="mt-1 flex items-baseline gap-1">
        <span className="text-lg leading-none font-semibold text-ink">{value}</span>
        {unit && <span className="text-xs text-ink-3">{unit}</span>}
      </p>
      {sub && <div className="mt-1 text-xs text-ink-3">{sub}</div>}
    </div>
  );
}

/** Big headline value of a card. */
export function BigValue({
  value,
  unit,
  children,
}: {
  value: ReactNode;
  unit?: string;
  children?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-baseline gap-x-1.5 gap-y-1">
      <span className="text-[32px] leading-none font-semibold tracking-tight text-ink">
        {value}
      </span>
      {unit && <span className="text-sm text-ink-3">{unit}</span>}
      {children}
    </div>
  );
}

/**
 * Value against a reference band on a shared scale (bullet): the band is a soft accent wash,
 * the main value a dot with a surface ring, the secondary value a thin tick.
 */
export function BandBullet({
  min,
  max,
  bandLow,
  bandHigh,
  value,
  secondary,
}: {
  min: number;
  max: number;
  bandLow: number | null;
  bandHigh: number | null;
  value: number | null;
  secondary?: number | null;
}) {
  const pos = (v: number) =>
    `${((Math.min(Math.max(v, min), max) - min) / (max - min || 1)) * 100}%`;
  return (
    <div aria-hidden className="relative h-6">
      <div className="absolute inset-x-0 top-1/2 h-1 -translate-y-1/2 rounded-full bg-surface-3" />
      {bandLow !== null && bandHigh !== null && (
        <div
          className="absolute top-1/2 h-3 -translate-y-1/2 rounded-full bg-accent-soft ring-1 ring-accent/40"
          style={{
            left: pos(bandLow),
            width: `calc(${pos(bandHigh)} - ${pos(bandLow)})`,
          }}
        />
      )}
      {secondary !== null && secondary !== undefined && (
        <div
          className="absolute top-1/2 h-5 w-0.5 -translate-x-1/2 -translate-y-1/2 rounded-full bg-ink-2"
          style={{ left: pos(secondary) }}
        />
      )}
      {value !== null && (
        <div
          className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-accent"
          style={{ left: pos(value) }}
        />
      )}
    </div>
  );
}
