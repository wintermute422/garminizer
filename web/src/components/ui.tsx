/** Small presentational building blocks shared by every page. */
import { clsx } from "clsx";
import { queriesState, type QueryData, type QueryLike } from "@/lib/queries";
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
        "min-w-0 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5",
        className,
      )}
    >
      {(title || actions) && (
        <header className="mb-3 flex flex-wrap items-start justify-between gap-2">
          <div className="min-w-0">
            {title && <h2 className="text-sm font-semibold tracking-tight text-ink">{title}</h2>}
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
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3 border-b border-rule pb-4">
      <div className="min-w-0">
        <h1 className="text-2xl font-semibold tracking-tight text-ink sm:text-display">{title}</h1>
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
        "flex min-w-0 flex-col justify-between gap-3 rounded-card border border-line bg-surface p-4 shadow-card",
        className,
      )}
    >
      <div className="flex items-center gap-2 text-eyebrow text-ink-2 uppercase">
        {icon}
        <span className="truncate">{label}</span>
      </div>
      <div className="flex items-end justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-baseline gap-1">
            <span className="text-metric font-semibold text-ink tabular">{value}</span>
            {unit && <span className="text-sm text-ink-3">{unit}</span>}
          </div>
          <div className="mt-1.5 flex min-h-4 flex-wrap items-center gap-2 text-xs text-ink-3">
            {delta}
            {sub}
          </div>
        </div>
        {trend && <div className="hidden w-24 shrink-0 sm:block">{trend}</div>}
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
      <span className="inline-flex items-center gap-1.5 rounded-chip border border-line px-2 py-1 text-xs font-medium text-ink-2">
        {label}
      </span>
    );
  }
  const Icon = STATUS_ICON[status];
  return (
    <span className="inline-flex items-center gap-1.5 rounded-chip border border-line bg-surface-2 px-2 py-1 text-xs font-medium text-ink">
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
      className="inline-flex max-w-full overflow-x-auto rounded-control border border-line bg-surface p-0.5"
    >
      {options.map((o) => (
        <button
          key={o.value}
          type="button"
          role="radio"
          aria-checked={o.value === value}
          onClick={() => onChange(o.value)}
          className={clsx(
            "shrink-0 rounded-chip font-medium whitespace-nowrap transition-colors",
            size === "sm" ? "px-2.5 py-1 text-xs" : "px-3 py-1.5 text-sm",
            o.value === value
              ? "bg-selected text-on-selected"
              : "text-ink-2 hover:bg-hover hover:text-ink active:bg-pressed",
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
          className="inline-block size-2.5 rounded-swatch"
          style={{ background: color }}
          aria-hidden
        />
      ) : (
        <span
          className="inline-block h-0.5 w-4 rounded-bar"
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
      className={clsx("animate-pulse rounded-card bg-surface-2", className)}
      style={{ height }}
    />
  );
}

/**
 * "Show all N …" / "Show fewer" under a list cut to its first rows. Long lists use this rather
 * than an inner scroll area: an inner scroll has no visible cue and traps scrolling on phones.
 */
export function ShowAllButton({
  total,
  noun,
  expanded,
  onToggle,
}: {
  total: number;
  noun: string;
  expanded: boolean;
  onToggle: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onToggle}
      aria-expanded={expanded}
      className="mt-2 w-full rounded-control border border-line py-1.5 text-xs font-medium text-ink-2 transition-colors hover:bg-hover hover:text-ink active:bg-pressed"
    >
      {expanded ? "Show fewer" : `Show all ${total} ${noun}`}
    </button>
  );
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="flex flex-col items-center justify-center gap-1 rounded-card border border-dashed border-line-strong px-6 py-10 text-center">
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
      className="rounded-card border border-line border-l-2 border-l-critical bg-surface-2 px-4 py-3 text-sm text-critical-text"
    >
      {message}
    </div>
  );
}

interface QueryStateProps<D> {
  /** Skeleton height while loading (ignored when `skeleton` is given). */
  height?: number;
  /** Custom loading placeholder (must contain `Skeleton`s so e2e readiness waits for it). */
  skeleton?: ReactNode;
  isEmpty?: (data: D) => boolean;
  empty?: ReactNode;
  children: (data: D) => ReactNode;
}

/**
 * Renders loading / error / empty / content for one query (`query`) or several (`queries`,
 * children get the data tuple): any pending → skeleton, first error wins, then content.
 */
export function QueryState<T>(props: QueryStateProps<T> & { query: QueryLike<T> }): ReactNode;
export function QueryState<Qs extends readonly QueryLike<unknown>[]>(
  props: QueryStateProps<QueryData<Qs>> & { queries: readonly [...Qs] },
): ReactNode;
export function QueryState(
  props: QueryStateProps<never> & {
    query?: QueryLike<unknown>;
    queries?: readonly QueryLike<unknown>[];
  },
): ReactNode {
  const { height = 200, skeleton, empty } = props;
  const isEmpty = props.isEmpty as ((data: unknown) => boolean) | undefined;
  const children = props.children as (data: unknown) => ReactNode;
  const s = props.queries ? queriesState(props.queries) : queriesState([props.query!]);
  if (s.state === "loading") return skeleton ?? <Skeleton height={height} />;
  if (s.state === "error") return <ErrorState error={s.error} />;
  const data = props.queries ? s.data : s.data[0];
  if (isEmpty?.(data)) return <>{empty ?? <EmptyState title="No data for this period" />}</>;
  return <>{children(data)}</>;
}
