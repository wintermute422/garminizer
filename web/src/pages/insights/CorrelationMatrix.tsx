import { useMemo } from "react";
import type { Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { ScrollArea } from "@/components/ui";
import { itemTooltip, tooltipTitle } from "@/lib/charts";
import { fmtNumber } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { CHROME, DIVERGING } from "@/lib/tokens";
import type { Pair } from "./InsightCards";
import { divergingColor, fmtR, inkOn, lagText, linkText } from "./metrics";

type Correlations = Schemas["InsightCorrelations"];

interface Cell {
  value: [number, number, number];
  x: string;
  y: string;
  n: number;
  lag: number;
  label?: { color: string };
}

export function CorrelationMatrix({
  data,
  labelOf,
  selected,
  onSelect,
}: {
  data: Correlations;
  labelOf: (key: string) => string;
  selected: Pair;
  /** Must be stable (chart events are bound once). */
  onSelect: (p: Pair) => void;
}) {
  const mode = useMode();
  const keys = data.metrics;
  const option = useMemo<ChartOption>(() => {
    const c = CHROME[mode];
    const labels = keys.map(labelOf);
    const cells: Cell[] = [];
    const diagonal: [number, number, number][] = [];
    keys.forEach((kx, i) =>
      keys.forEach((ky, j) => {
        const r = data.r[i]?.[j];
        if (r === null || r === undefined) return;
        if (data.lag === 0 && i === j) {
          diagonal.push([j, i, 1]);
          return;
        }
        cells.push({
          value: [j, i, r],
          x: kx,
          y: ky,
          n: data.n[i]?.[j] ?? 0,
          lag: data.lag,
          label: { color: inkOn(divergingColor(r, mode)) },
        });
      }),
    );
    const si = keys.indexOf(selected.x);
    const sj = keys.indexOf(selected.y);
    const showSel = selected.lag === data.lag && si >= 0 && sj >= 0;
    return {
      grid: { left: 4, right: 12, top: 4, bottom: 4 },
      tooltip: itemTooltip((p) => {
        const d = (p as { data?: Cell }).data;
        if (!d || !("x" in d)) return "";
        const r = d.value[2];
        const when = d.lag === 0 ? "same day" : `${labelOf(d.y)} ${lagText(d.lag)}`;
        return (
          tooltipTitle(`${labelOf(d.x)} × ${labelOf(d.y)}`) +
          `<div style="color:${c.muted};margin-bottom:4px">${when}</div>` +
          `<div><b style="font-variant-numeric:tabular-nums">r = ${fmtR(r)}</b> · ${linkText(r).toLowerCase()}</div>` +
          `<div style="color:${c.muted}">${fmtNumber(d.n)} days · click to explore</div>`
        );
      }),
      xAxis: {
        type: "category",
        data: labels,
        position: "top",
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { interval: 0, rotate: 45, fontSize: 11, color: c.text2 },
        splitArea: { show: false },
      },
      yAxis: {
        type: "category",
        data: labels,
        inverse: true,
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { interval: 0, fontSize: 11, color: c.text2 },
      },
      visualMap: [
        {
          type: "continuous",
          seriesIndex: 0,
          min: -1,
          max: 1,
          // Drawn as an HTML scale under the chart so it stays visible when the matrix scrolls.
          show: false,
          inRange: {
            color: [DIVERGING[mode].negative, DIVERGING[mode].mid, DIVERGING[mode].positive],
          },
        },
        {
          // Heatmaps need a visualMap: a hidden one paints the diagonal and the selection ring.
          type: "piecewise",
          show: false,
          seriesIndex: [1, 2],
          dimension: 2,
          pieces: [
            { value: 1, color: c.grid },
            { value: 0, color: "rgba(0, 0, 0, 0)" },
          ],
        },
      ],
      series: [
        {
          type: "heatmap",
          name: "Correlation",
          data: cells,
          itemStyle: { borderColor: c.surface, borderWidth: 2, borderRadius: 4 },
          label: {
            show: true,
            fontSize: 10,
            fontWeight: 500,
            formatter: (p: { value: [number, number, number] }) =>
              Math.abs(p.value[2]) >= 0.3 ? fmtR(p.value[2]) : "",
          },
          emphasis: { itemStyle: { borderColor: c.text, borderWidth: 1.5 } },
          cursor: "pointer",
        },
        {
          type: "heatmap",
          name: "Same metric",
          data: diagonal,
          silent: true,
          itemStyle: { color: c.grid, borderColor: c.surface, borderWidth: 2, borderRadius: 4 },
          label: { show: false },
        },
        {
          type: "heatmap",
          name: "Selected",
          data: showSel ? [[sj, si, 0]] : [],
          silent: true,
          itemStyle: {
            color: "transparent",
            borderColor: c.text,
            borderWidth: 2,
            borderRadius: 4,
          },
          label: { show: false },
          z: 3,
        },
      ],
    };
  }, [data, keys, labelOf, mode, selected]);

  return (
    <>
      <ScrollArea label="Correlation matrix" className="-mx-1 overflow-x-auto px-1">
        <div className="min-w-[720px]">
          <Chart
            option={option}
            height={keys.length * 26 + 150}
            ariaLabel={`Correlation matrix of ${keys.length} daily metrics, lag ${data.lag} days`}
            onEvents={{
              click: (p) => {
                const d = (p as { data?: Cell }).data;
                if (d && "x" in d) onSelect({ x: d.x, y: d.y, lag: d.lag });
              },
            }}
          />
        </div>
      </ScrollArea>
      <div className="mt-3 flex flex-wrap items-center justify-center gap-x-4 gap-y-2 text-xs text-ink-3">
        <span className="inline-flex items-center gap-2">
          <span>−1 move opposite</span>
          <span
            aria-hidden
            className="h-2 w-40 rounded-full"
            style={{
              background: `linear-gradient(90deg, ${DIVERGING[mode].negative}, ${DIVERGING[mode].mid}, ${DIVERGING[mode].positive})`,
            }}
          />
          <span>move together +1</span>
        </span>
        <span>Values shown where |r| ≥ .30</span>
      </div>
    </>
  );
}
