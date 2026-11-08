import { useMemo } from "react";
import type { Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { EmptyState } from "@/components/ui";
import { categoryXAxis, itemTooltip, refLine, tooltipTitle, valueYAxis } from "@/lib/charts";
import { fmtCompact, fmtNumber } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { BLUE, CHROME } from "@/lib/tokens";
import type { MetricView } from "./metrics";

type Weekday = Schemas["InsightWeekday"];
export type WeekdayKey = "sleep_s" | "steps" | "avg_stress" | "hrv_ms" | "load" | "readiness";

const DAY = (i: number, weekday: "short" | "long") =>
  new Date(2024, 0, 1 + i).toLocaleDateString(undefined, { weekday });

function Multiple({ rows, mv, k }: { rows: Weekday[]; mv: MetricView; k: WeekdayKey }) {
  const mode = useMode();
  const values = useMemo(
    () => Array.from({ length: 7 }, (_, i) => rows.find((r) => r.weekday === i)?.[k] ?? null),
    [rows, k],
  );
  const avg = useMemo(() => {
    const finite = values.filter((v): v is number => v !== null);
    return finite.length ? finite.reduce((a, v) => a + v, 0) / finite.length : null;
  }, [values]);
  const short = (v: number) => (k === "steps" ? fmtCompact(v) : mv.text(v));
  const option = useMemo<ChartOption | null>(() => {
    if (avg === null) return null;
    const c = CHROME[mode];
    const max = Math.max(...values.map((v) => v ?? -Infinity));
    const peak = values.indexOf(max);
    const label = (v: number) => (k === "steps" ? fmtCompact(v) : mv.text(v));
    // Both steps clear 3:1 against the card; the peak is the strongest step of the same hue.
    const [soft, strong] = mode === "dark" ? [BLUE[500]!, BLUE[200]!] : [BLUE[400]!, BLUE[650]!];
    return {
      grid: { left: 4, right: 8, top: 20, bottom: 4 },
      tooltip: itemTooltip((p) => {
        const it = p as { dataIndex: number };
        const v = values[it.dataIndex];
        return v === null || v === undefined
          ? ""
          : `${tooltipTitle(DAY(it.dataIndex, "long"))}${mv.label}: <b>${mv.text(v)}</b>`;
      }),
      xAxis: categoryXAxis(
        values.map((_, i) => DAY(i, "short")),
        { axisLabel: { fontSize: 10, interval: 0 } },
      ),
      yAxis: valueYAxis(undefined, undefined, {
        splitNumber: 2,
        boundaryGap: [0, "22%"],
        axisLabel: {
          fontSize: 10,
          formatter: (v: number) => (k === "steps" ? fmtCompact(v) : fmtNumber(v, 0)),
        },
      }),
      series: [
        {
          type: "bar",
          name: mv.label,
          barMaxWidth: 22,
          data: values.map((v, i) =>
            v === null
              ? null
              : {
                  value: mv.value(v),
                  itemStyle: { color: i === peak ? strong : soft, borderRadius: [4, 4, 0, 0] },
                  label:
                    i === peak
                      ? {
                          show: true,
                          position: "top",
                          color: c.text,
                          fontSize: 11,
                          fontWeight: 600,
                          formatter: () => label(v),
                        }
                      : { show: false },
                },
          ),
          markLine: { ...refLine(mv.value(avg), "", mode), label: { show: false } },
        },
      ],
    };
  }, [values, avg, mode, mv, k]);

  return (
    <div className="min-w-0">
      <div className="mb-1 flex items-baseline justify-between gap-2">
        <h3 className="truncate text-xs font-semibold text-ink">
          {mv.label}
          {mv.unit && mv.unit !== "steps" && (
            <span className="font-normal text-ink-3"> · {mv.unit}</span>
          )}
        </h3>
        <span className="shrink-0 text-xs text-ink-3 tabular">
          {avg === null ? "no data" : `avg ${short(avg)}`}
        </span>
      </div>
      {option ? (
        <Chart option={option} height={140} ariaLabel={`Average ${mv.label} by weekday`} />
      ) : (
        <div className="flex h-[140px] items-center justify-center rounded-xl border border-dashed border-line text-xs text-ink-3">
          No data in this period
        </div>
      )}
    </div>
  );
}

export function WeekdayPatterns({
  rows,
  view,
}: {
  rows: Weekday[];
  view: (k: WeekdayKey) => MetricView;
}) {
  const keys: WeekdayKey[] = ["sleep_s", "steps", "avg_stress", "hrv_ms", "load", "readiness"];
  const any = rows.some((r) => keys.some((k) => r[k] !== null));
  if (!any) return <EmptyState title="No daily data in this period" />;
  return (
    <div className="grid gap-x-6 gap-y-5 sm:grid-cols-2 xl:grid-cols-3">
      {keys.map((k) => (
        <Multiple key={k} rows={rows} mv={view(k)} k={k} />
      ))}
    </div>
  );
}
