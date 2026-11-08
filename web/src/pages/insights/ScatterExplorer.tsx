import { ArrowLeftRight } from "lucide-react";
import { useMemo } from "react";
import type { Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { EmptyState, Segmented } from "@/components/ui";
import {
  GRID,
  itemTooltip,
  line,
  scatter,
  tooltipRow,
  tooltipTitle,
  valueYAxis,
} from "@/lib/charts";
import { fmtDate, fmtNumber } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { CATEGORICAL, CHROME, DIVERGING } from "@/lib/tokens";
import type { Pair } from "./InsightCards";
import { axisName, fmtR, lagText, linkText, phrase, strength, type MetricView } from "./metrics";

type Scatter = Schemas["InsightScatter"];
type Metric = Schemas["InsightMetric"];

const LAGS = [
  { value: "0", label: "Same day" },
  { value: "1", label: "+1 day" },
  { value: "2", label: "+2 days" },
] as const;

function MetricSelect({
  id,
  label,
  value,
  metrics,
  onChange,
}: {
  id: string;
  label: string;
  value: string;
  metrics: Metric[];
  onChange: (v: string) => void;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1 sm:w-60">
      <label htmlFor={id} className="text-xs font-medium text-ink-3">
        {label}
      </label>
      <select
        id={id}
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-xl border border-line bg-surface-2 px-2.5 py-1.5 text-sm text-ink"
      >
        {metrics.map((m) => (
          <option key={m.key} value={m.key}>
            {m.label}
          </option>
        ))}
      </select>
    </div>
  );
}

export function ScatterControls({
  pair,
  metrics,
  onChange,
}: {
  pair: Pair;
  metrics: Metric[];
  onChange: (p: Pair) => void;
}) {
  return (
    <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end">
      <div className="grid grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)] items-end gap-2 sm:flex sm:gap-3">
        <MetricSelect
          id="scatter-x"
          label="X · on day d"
          value={pair.x}
          metrics={metrics}
          onChange={(x) => onChange({ ...pair, x })}
        />
        <button
          type="button"
          onClick={() => onChange({ ...pair, x: pair.y, y: pair.x })}
          aria-label="Swap X and Y"
          title="Swap X and Y"
          className="mb-px rounded-xl border border-line bg-surface-2 p-2 text-ink-2 hover:text-ink"
        >
          <ArrowLeftRight size={15} aria-hidden />
        </button>
        <MetricSelect
          id="scatter-y"
          label={`Y · ${lagText(pair.lag)}`}
          value={pair.y}
          metrics={metrics}
          onChange={(y) => onChange({ ...pair, y })}
        />
      </div>
      <div className="flex flex-col gap-1">
        <span className="text-xs font-medium text-ink-3" aria-hidden>
          Lag
        </span>
        <Segmented
          label="Lag between X and Y"
          value={String(pair.lag) as (typeof LAGS)[number]["value"]}
          onChange={(v) => onChange({ ...pair, lag: Number(v) })}
          options={LAGS}
        />
      </div>
    </div>
  );
}

function RScale({ r }: { r: number }) {
  const mode = useMode();
  const d = DIVERGING[mode];
  return (
    <div className="mt-3" aria-hidden>
      <div
        className="relative h-2 rounded-full"
        style={{ background: `linear-gradient(90deg, ${d.negative}, ${d.mid}, ${d.positive})` }}
      >
        <span
          className="absolute top-1/2 size-3.5 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-surface bg-ink shadow-card"
          style={{ left: `${((Math.max(-1, Math.min(1, r)) + 1) / 2) * 100}%` }}
        />
      </div>
      <div className="mt-1 flex justify-between text-[11px] text-ink-3 tabular">
        <span>−1</span>
        <span>0</span>
        <span>+1</span>
      </div>
    </div>
  );
}

function Reading({ data, xv, yv }: { data: Scatter; xv: MetricView; yv: MetricView }) {
  if (data.r === null) {
    return <p className="text-sm text-ink-2">Not enough variation to compute a correlation.</p>;
  }
  const r = data.r;
  const s = strength(r);
  const when = lagText(data.lag);
  const sentence =
    s === "none"
      ? `${xv.label} and ${phrase(yv.label)} ${when} barely move together.`
      : `When ${phrase(xv.label)} is higher, ${phrase(yv.label)} ${when} tends to be ${r > 0 ? "higher" : "lower"}${s === "weak" ? ", but only slightly" : ""}.`;
  // Slope in display units per "step" of x.
  const scaleX = xv.value(1) - xv.value(0);
  const scaleY = yv.value(1) - yv.value(0);
  const slope =
    data.slope !== null && scaleX !== 0 ? (data.slope * scaleY * xv.step) / scaleX : null;
  return (
    <div className="flex flex-col gap-4">
      <div>
        <p className="text-xs font-medium text-ink-3">Correlation (Pearson r)</p>
        <p className="mt-1 text-[40px] leading-none font-semibold tracking-tight text-ink">
          {fmtR(r)}
        </p>
        <RScale r={r} />
        <p className="mt-2 text-sm font-semibold text-ink">{linkText(r)}</p>
        <p className="text-xs text-ink-3">{fmtNumber(data.n)} days with both values</p>
      </div>
      <p className="text-sm leading-relaxed text-ink-2">{sentence}</p>
      {slope !== null && s !== "none" && (
        <p className="text-sm leading-relaxed text-ink-2">
          On average, <b className="font-semibold text-ink">{xv.amount(xv.step)}</b> goes with{" "}
          <b className="font-semibold text-ink">{yv.amount(slope)}</b>
          {data.lag ? ` ${when}` : ""}.
        </p>
      )}
      <p className="text-xs leading-relaxed text-ink-3">
        r² ≈ {fmtNumber(r * r * 100)} %: the share of day-to-day variation in {phrase(yv.label)}{" "}
        that lines up with {phrase(xv.label)}. A link is not proof of cause.
      </p>
    </div>
  );
}

export function ScatterView({ data, xv, yv }: { data: Scatter; xv: MetricView; yv: MetricView }) {
  const mode = useMode();
  const option = useMemo<ChartOption | null>(() => {
    if (data.points.length < 3) return null;
    const c = CHROME[mode];
    const dot = CATEGORICAL[mode][0]!;
    const pts = data.points.map((p) => ({ value: [xv.value(p.x), yv.value(p.y)], day: p.day }));
    const xsSi = data.points.map((p) => p.x);
    const x0 = Math.min(...xsSi);
    const x1 = Math.max(...xsSi);
    const fit =
      data.slope !== null && data.intercept !== null && x1 > x0
        ? [
            [xv.value(x0), yv.value(data.slope * x0 + data.intercept)],
            [xv.value(x1), yv.value(data.slope * x1 + data.intercept)],
          ]
        : [];
    const fmtX = (v: number) => fmtNumber(v, xv.digits);
    const fmtY = (v: number) => fmtNumber(v, yv.digits);
    return {
      grid: { ...GRID, top: 44, bottom: 30, right: 16 },
      legend: { top: 0, left: 0, data: ["Days", "Linear fit"] },
      tooltip: itemTooltip((p) => {
        const it = p as { seriesName: string; data: { value: [number, number]; day: string } };
        if (it.seriesName !== "Days") return "";
        const raw = data.points.find((q) => q.day === it.data.day);
        return (
          tooltipTitle(
            fmtDate(it.data.day, {
              weekday: "short",
              day: "numeric",
              month: "short",
              year: "numeric",
            }),
          ) +
          tooltipRow(dot, xv.label, raw ? xv.text(raw.x) : fmtX(it.data.value[0])) +
          tooltipRow(
            c.text2,
            `${yv.label}${data.lag ? ` (${lagText(data.lag)})` : ""}`,
            raw ? yv.text(raw.y) : fmtY(it.data.value[1]),
          )
        );
      }),
      xAxis: {
        type: "value",
        scale: true,
        name: axisName(xv),
        nameLocation: "middle",
        nameGap: 26,
        nameTextStyle: { color: c.muted, fontSize: 11 },
        splitNumber: 5,
        axisLabel: { formatter: fmtX },
        splitLine: { show: true },
      },
      yAxis: valueYAxis(axisName(yv), fmtY, { scale: true }),
      series: [
        {
          ...scatter("Days", pts, dot, 8),
          itemStyle: { color: dot, opacity: 0.6, borderColor: c.surface, borderWidth: 1 },
          emphasis: { scale: 1.6, itemStyle: { opacity: 1 } },
        },
        {
          ...line("Linear fit", fit, c.text, { width: 2 }),
          silent: true,
          z: 5,
          tooltip: { show: false },
        },
      ],
    };
  }, [data, xv, yv, mode]);

  if (!option)
    return (
      <EmptyState title="Not enough days with both metrics">
        Pick another pair or a longer date range.
      </EmptyState>
    );
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_280px]">
      <Chart
        option={option}
        height={360}
        ariaLabel={`Scatter plot of ${xv.label} against ${yv.label} ${lagText(data.lag)}, with a linear fit`}
      />
      <Reading data={data} xv={xv} yv={yv} />
    </div>
  );
}
