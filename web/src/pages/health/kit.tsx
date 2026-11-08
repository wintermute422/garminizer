/**
 * Presentational pieces shared by the health, sleep and body pages: a metric tile with a
 * full-width sparkline (fits two-up on a phone), a stepper for day/night navigation and fact rows.
 */
import { ChevronLeft, ChevronRight } from "lucide-react";
import type { ReactNode } from "react";
import { Delta, Skeleton, type DeltaDirection } from "@/components/ui";
import { fmtDelta } from "@/lib/format";
import { shown } from "./util";

/** Sparkline that stretches to its container: de-emphasised line, accented last point. */
export function Spark({
  values,
  color,
  label,
  height = 28,
}: {
  values: (number | null)[];
  color: string;
  label: string;
  height?: number;
}) {
  const pts = values
    .map((v, i) => [i, v] as const)
    .filter((p): p is readonly [number, number] => p[1] !== null && Number.isFinite(p[1]));
  if (pts.length < 2) return <div style={{ height }} aria-hidden />;
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const pad = 4;
  const sx = (x: number) => ((x - x0) / Math.max(x1 - x0, 1)) * 100;
  const sy = (y: number) =>
    height - pad - ((y - y0) / Math.max(y1 - y0, 1e-9)) * (height - 2 * pad);
  const d = pts
    .map(([x, y], i) => `${i ? "L" : "M"}${sx(x).toFixed(2)},${sy(y).toFixed(2)}`)
    .join("");
  const last = pts[pts.length - 1]!;
  return (
    <div className="relative" style={{ height }} role="img" aria-label={label}>
      <svg
        viewBox={`0 0 100 ${height}`}
        preserveAspectRatio="none"
        width="100%"
        height={height}
        className="block overflow-visible"
        aria-hidden
      >
        <path
          d={d}
          fill="none"
          stroke="var(--text-muted)"
          strokeWidth={1.5}
          strokeLinejoin="round"
          strokeLinecap="round"
          opacity={0.7}
          vectorEffect="non-scaling-stroke"
        />
      </svg>
      <span
        aria-hidden
        className="absolute size-[9px] -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface"
        style={{ left: `${sx(last[0])}%`, top: sy(last[1]), background: color }}
      />
    </div>
  );
}

/** Stat tile: label (+ optional badge), value + unit, delta/sub line, sparkline at the bottom. */
export function MetricTile({
  label,
  icon,
  value,
  unit,
  delta,
  sub,
  badge,
  spark,
}: {
  label: string;
  icon?: ReactNode;
  value: ReactNode;
  unit?: string;
  delta?: ReactNode;
  sub?: ReactNode;
  badge?: ReactNode;
  spark?: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-2 rounded-2xl border border-line bg-surface p-4 shadow-card">
      <div className="flex min-h-6 items-center justify-between gap-2">
        <span className="flex min-w-0 items-center gap-1.5 text-xs font-medium text-ink-2">
          {icon && (
            <span className="shrink-0 text-ink-3" aria-hidden>
              {icon}
            </span>
          )}
          <span className="truncate">{label}</span>
        </span>
        {badge}
      </div>
      <div className="flex items-baseline gap-1">
        <span className="text-[26px] leading-none font-semibold whitespace-nowrap text-ink">
          {value}
        </span>
        {unit && <span className="truncate text-sm text-ink-3">{unit}</span>}
      </div>
      <div className="flex min-h-4 flex-wrap items-center gap-x-2 gap-y-0.5 text-xs text-ink-3">
        {delta}
        {sub}
      </div>
      {spark && <div className="mt-auto pt-1">{spark}</div>}
    </div>
  );
}

export function TileSkeletons({ n, className }: { n: number; className: string }) {
  return (
    <div className={className}>
      {Array.from({ length: n }, (_, i) => (
        <Skeleton key={i} height={136} className="rounded-2xl" />
      ))}
    </div>
  );
}

/** Previous / next stepper around a label (days, nights). */
export function Stepper({
  label,
  onPrev,
  onNext,
  prevLabel,
  nextLabel,
  children,
}: {
  label: ReactNode;
  onPrev: (() => void) | null;
  onNext: (() => void) | null;
  prevLabel: string;
  nextLabel: string;
  children?: ReactNode;
}) {
  const btn =
    "rounded-lg p-1.5 text-ink-2 hover:bg-surface-2 hover:text-ink disabled:pointer-events-none disabled:opacity-35";
  return (
    <div className="flex items-center gap-1">
      <button
        type="button"
        className={btn}
        onClick={onPrev ?? undefined}
        disabled={!onPrev}
        aria-label={prevLabel}
      >
        <ChevronLeft size={16} aria-hidden />
      </button>
      {children ?? (
        <span className="min-w-[7.5rem] text-center text-sm font-medium text-ink tabular">
          {label}
        </span>
      )}
      <button
        type="button"
        className={btn}
        onClick={onNext ?? undefined}
        disabled={!onNext}
        aria-label={nextLabel}
      >
        <ChevronRight size={16} aria-hidden />
      </button>
    </div>
  );
}

export function FactRow({
  label,
  value,
  sub,
}: {
  label: ReactNode;
  value: ReactNode;
  sub?: ReactNode;
}) {
  return (
    <div className="flex items-baseline justify-between gap-3 py-2">
      <span className="text-sm text-ink-2">{label}</span>
      <span className="text-right text-sm font-medium text-ink tabular">
        {value}
        {sub && <span className="ml-1 text-xs font-normal text-ink-3">{sub}</span>}
      </span>
    </div>
  );
}

/** "−1.2 bpm" delta with a hover hint naming the comparison. */
export function DeltaHint({ title, children }: { title: string; children: ReactNode }) {
  return (
    <span title={title} className="inline-flex">
      {children}
    </span>
  );
}

/**
 * Change vs the previous period: arrow + signed value, or a neutral "no change" when the value
 * rounds to zero at the displayed precision.
 */
export function Change({
  value,
  digits,
  unit = "",
  direction,
  title,
}: {
  value: number | null;
  digits: number;
  unit?: string;
  direction: DeltaDirection;
  title: string;
}) {
  const v = shown(value, digits);
  if (v == null) return null;
  return (
    <DeltaHint title={title}>
      <Delta value={v} text={fmtDelta(v, digits, unit)} direction={direction} />
    </DeltaHint>
  );
}
