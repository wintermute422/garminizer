/** Small presentational building blocks shared by every page. */
import { clsx } from "clsx";
import {
  AlertTriangle,
  ArrowDownRight,
  ArrowUpRight,
  CircleCheck,
  CircleAlert,
  Minus,
  OctagonAlert,
} from "lucide-react";
import type { ReactNode } from "react";
import { STATUS, type Status } from "@/lib/tokens";

export function Card({
  title,
  subtitle,
  actions,
  children,
  className,
  bodyClassName,
  id,
}: {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  children: ReactNode;
  className?: string;
  bodyClassName?: string;
  id?: string;
}) {
  return (
    <section
      id={id}
      className={clsx(
        "min-w-0 rounded-2xl border border-line bg-surface p-4 shadow-card sm:p-5",
        className,
      )}
    >
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold text-ink">{title}</h2>}
            {subtitle && <p className="mt-0.5 text-xs text-ink-3">{subtitle}</p>}
          </div>
          {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={bodyClassName}>{children}</div>
    </section>
  );
}

export function PageHeader({
  title,
  description,
  children,
}: {
  title: string;
  description?: ReactNode;
  children?: ReactNode;
}) {
  return (
    <div className="mb-5 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-[28px]">{title}</h1>
        {description && <p className="mt-1 max-w-2xl text-sm text-ink-2">{description}</p>}
      </div>
      {children && <div className="flex flex-wrap items-center gap-2">{children}</div>}
    </div>
  );
}

export type DeltaDirection = "up-good" | "down-good" | "neutral";

export function Delta({
  value,
  text,
  direction = "up-good",
}: {
  value: number | null | undefined;
  text: string;
  direction?: DeltaDirection;
}) {
  if (value === null || value === undefined || !Number.isFinite(value)) return null;
  const up = value > 0;
  const flat = Math.abs(value) < 1e-9;
  const good = direction === "neutral" || flat ? null : direction === "up-good" ? up : !up;
  const Icon = flat ? Minus : up ? ArrowUpRight : ArrowDownRight;
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-0.5 text-xs font-medium tabular",
        good === null ? "text-ink-3" : good ? "text-good-text" : "text-critical-text",
      )}
    >
      <Icon size={14} aria-hidden />
      {text}
    </span>
  );
}

export function StatTile({
  label,
  value,
  unit,
  sub,
  delta,
  trend,
  className,
  icon,
}: {
  label: string;
  value: ReactNode;
  unit?: string;
  sub?: ReactNode;
  delta?: ReactNode;
  trend?: ReactNode;
  className?: string;
  icon?: ReactNode;
}) {
  return (
    <div
      className={clsx(
        "flex min-w-0 flex-col justify-between gap-2 rounded-2xl border border-line bg-surface p-4 shadow-card",
        className,
      )}
    >
      <div className="flex items-center gap-2 text-xs font-medium text-ink-2">
        {icon}
        <span className="truncate">{label}</span>
      </div>
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-baseline gap-1">
            <span className="text-[26px] leading-none font-semibold text-ink">{value}</span>
            {unit && <span className="text-sm text-ink-3">{unit}</span>}
          </div>
          <div className="mt-1.5 flex flex-wrap items-center gap-2 text-xs text-ink-3">
            {delta}
            {sub}
          </div>
        </div>
        {trend && <div className="w-24 shrink-0">{trend}</div>}
      </div>
    </div>
  );
}

/** Tiny line, de-emphasised; last point accented. */
export function Sparkline({
  values,
  color = "var(--accent)",
  height = 32,
  label,
}: {
  values: (number | null)[];
  color?: string;
  height?: number;
  label: string;
}) {
  const pts = values
    .map((v, i) => [i, v] as const)
    .filter((p): p is [number, number] => p[1] !== null);
  if (pts.length < 2) return null;
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  const [x0, x1] = [Math.min(...xs), Math.max(...xs)];
  const [y0, y1] = [Math.min(...ys), Math.max(...ys)];
  const w = 96;
  const sx = (x: number) => ((x - x0) / Math.max(x1 - x0, 1)) * (w - 6) + 3;
  const sy = (y: number) => height - 4 - ((y - y0) / Math.max(y1 - y0, 1e-9)) * (height - 8);
  const d = pts
    .map(([x, y], i) => `${i ? "L" : "M"}${sx(x).toFixed(1)},${sy(y).toFixed(1)}`)
    .join("");
  const last = pts[pts.length - 1]!;
  return (
    <svg viewBox={`0 0 ${w} ${height}`} width="100%" height={height} role="img" aria-label={label}>
      <path
        d={d}
        fill="none"
        stroke="var(--text-muted)"
        strokeWidth={1.5}
        strokeLinejoin="round"
        strokeLinecap="round"
        opacity={0.7}
      />
      <circle
        cx={sx(last[0])}
        cy={sy(last[1])}
        r={3.5}
        fill={color}
        stroke="var(--surface-1)"
        strokeWidth={2}
      />
    </svg>
  );
}

const STATUS_ICON = {
  good: CircleCheck,
  warning: AlertTriangle,
  serious: CircleAlert,
  critical: OctagonAlert,
};

/** Status always ships with an icon + label, never colour alone. */
export function StatusPill({ status, label }: { status: Status | null; label: string }) {
  if (!status) {
    return (
      <span className="inline-flex items-center gap-1.5 rounded-full border border-line px-2.5 py-1 text-xs font-medium text-ink-2">
        {label}
      </span>
    );
  }
  const Icon = STATUS_ICON[status];
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface-2 px-2.5 py-1 text-xs font-medium text-ink">
      <Icon size={14} color={STATUS[status]} aria-hidden />
      {label}
    </span>
  );
}

export function Segmented<T extends string>({
  options,
  value,
  onChange,
  label,
  size = "md",
}: {
  options: readonly { value: T; label: string }[];
  value: T;
  onChange: (v: T) => void;
  label: string;
  size?: "sm" | "md";
}) {
  return (
    <div
      role="radiogroup"
      aria-label={label}
      className="inline-flex max-w-full overflow-x-auto rounded-xl border border-line bg-surface-2 p-0.5"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "shrink-0 rounded-[10px] font-medium whitespace-nowrap transition-colors",
            size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm",
            o.value === value ? "bg-surface text-ink shadow-card" : "text-ink-2 hover:text-ink",
          )}
        >
          {o.label}
        </button>
      ))}
    </div>
  );
}

export function LegendItem({
  color,
  label,
  shape = "dot",
}: {
  color: string;
  label: string;
  shape?: "dot" | "line";
}) {
  return (
    <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
      {shape === "dot" ? (
        <span
          className="inline-block size-2.5 rounded-[3px]"
          style={{ background: color }}
          aria-hidden
        />
      ) : (
        <span
          className="inline-block h-0.5 w-4 rounded"
          style={{ background: color }}
          aria-hidden
        />
      )}
      {label}
    </span>
  );
}

/** Scrollable container that keyboard users can focus and scroll (WCAG scrollable-region). */
export function ScrollArea({
  label,
  className,
  children,
}: {
  label: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <div role="region" aria-label={label} tabIndex={0} className={clsx("relative", className)}>
      {children}
    </div>
  );
}

export function Skeleton({ className, height = 120 }: { className?: string; height?: number }) {
  return (
    <div
      aria-hidden
      className={clsx("animate-pulse rounded-xl bg-surface-2", className)}
      style={{ height }}
    />
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 rounded-xl border border-dashed border-line px-6 py-10 text-center">
      <p className="text-sm font-medium text-ink-2">{title}</p>
      {children && <div className="max-w-md text-xs text-ink-3">{children}</div>}
    </div>
  );
}

export function ErrorState({ error }: { error: unknown }) {
  const message =
    (error as { detail?: string } | null)?.detail ??
    (error instanceof Error ? error.message : "Something went wrong loading this data.");
  return (
    <div
      role="alert"
      className="rounded-xl border border-line bg-surface-2 px-4 py-3 text-sm text-critical-text"
    >
      {message}
    </div>
  );
}

/** Renders loading / error / empty / content for a query result. */
export function QueryState<T>({
  query,
  height = 200,
  isEmpty,
  empty,
  children,
}: {
  query: { data?: T; isPending: boolean; error: unknown };
  height?: number;
  isEmpty?: (data: T) => boolean;
  empty?: ReactNode;
  children: (data: T) => ReactNode;
}) {
  if (query.isPending) return <Skeleton height={height} />;
  if (query.error) return <ErrorState error={query.error} />;
  if (query.data === undefined) return <Skeleton height={height} />;
  if (isEmpty?.(query.data)) return <>{empty ?? <EmptyState title="No data for this period" />}</>;
  return <>{children(query.data)}</>;
}
