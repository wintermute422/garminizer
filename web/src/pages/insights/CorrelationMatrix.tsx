import { useMemo } from "react";
import type { Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { itemTooltip, tooltipTitle } from "@/lib/charts";
import { fmtNumber } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { CHROME, DIVERGING } from "@/lib/tokens";
import type { Pair } from "./InsightCards";
import {
  correlationPairs,
  divergingColor,
  fmtR,
  inkOn,
  lagText,
  linkText,
  type PairStat,
} from "./metrics";

type Correlations = Schemas["InsightCorrelations"];

interface Cell {
  value: [number, number, number];
  pair: PairStat;
  label?: { color: string };
}

/**
 * Correlation heatmap. Without a lag the matrix is symmetric, so only the lower triangle is
 * drawn; with a lag every ordered pair is (columns on day d, rows on day d + lag). Pairs that
 * are computed from each other are greyed out instead of shouting a meaningless r ≈ 1.
 */
export function CorrelationMatrix({
  data,
  labelOf,
  selected,
  onSelect,
}: {
  data: Correlations;
  labelOf: (key: string) => string;
  selected: Pair;
  onSelect: (p: Pair) => void;
}) {
  const mode = useMode();
  const keys = data.metrics;
  const triangle = data.lag === 0;
  const rows = triangle ? keys.slice(1) : keys;
  const cols = triangle ? keys.slice(0, -1) : keys;
  const option = useMemo<ChartOption>(() => {
    const c = CHROME[mode];
    const at = (p: { a: number; b: number }): [number, number] => [p.a, triangle ? p.b - 1 : p.b];
    const cells: Cell[] = [];
    const muted: Cell[] = [];
    for (const p of correlationPairs(data)) {
      if (p.r === null) continue;
      const [x, y] = at(p);
      if (p.derived) muted.push({ value: [x, y, 1], pair: p });
      else
        cells.push({
          value: [x, y, p.r],
          pair: p,
          label: { color: inkOn(divergingColor(p.r, mode)) },
        });
    }
    const diagonal: [number, number, number][] = triangle ? [] : keys.map((_, i) => [i, i, 1]);
    const sx = keys.indexOf(selected.x);
    const sy = keys.indexOf(selected.y);
    const sel =
      selected.lag !== data.lag || sx < 0 || sy < 0 || sx === sy
        ? []
        : triangle
          ? [[...at({ a: Math.min(sx, sy), b: Math.max(sx, sy) }), 0]]
          : [[sx, sy, 0]];
    return {
      grid: { left: 4, right: 12, top: 8, bottom: 4 },
      tooltip: itemTooltip((params) => {
        const d = (params as { data?: Cell }).data;
        if (!d || !("pair" in d)) return "";
        const p = d.pair;
        const head = tooltipTitle(`${labelOf(p.x)} × ${labelOf(p.y)}`);
        const when = p.lag === 0 ? "same day" : `${labelOf(p.y)} ${lagText(p.lag)}`;
        if (p.derived)
          return `${head}<div style="color:${c.muted}">Computed from each other, so their link says nothing.</div>`;
        const r = d.value[2];
        return (
          head +
          `<div style="color:${c.muted};margin-bottom:4px">${when}</div>` +
          `<div>${linkText(r)} · <b style="font-variant-numeric:tabular-nums">r ${fmtR(r)}</b></div>` +
          `<div style="color:${c.muted}">${fmtNumber(p.n)} days · click to explore</div>`
        );
      }),
      xAxis: {
        type: "category",
        data: cols.map(labelOf),
        axisLine: { show: false },
        axisTick: { show: false },
        axisLabel: { interval: 0, rotate: 40, fontSize: 11, color: c.text2 },
        splitArea: { show: false },
      },
      yAxis: {
        type: "category",
        data: rows.map(labelOf),
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
          // Drawn as an HTML scale under the chart.
          show: false,
          inRange: {
            color: [DIVERGING[mode].negative, DIVERGING[mode].mid, DIVERGING[mode].positive],
          },
        },
        {
          // Heatmaps need a visualMap: a hidden one paints muted cells and the selection ring.
          type: "piecewise",
          show: false,
          seriesIndex: [1, 2],
          dimension: 2,
          pieces: [
            { value: 1, color: c.surface },
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
          name: "Not compared",
          data: [...muted, ...diagonal],
          // Empty outlined cells with a dash: "not compared", clearly unlike a weak r.
          itemStyle: { borderColor: c.grid, borderWidth: 1, borderRadius: 4 },
          label: { show: true, formatter: () => "–", color: c.muted, fontSize: 11 },
          emphasis: { disabled: true },
        },
        {
          type: "heatmap",
          name: "Selected",
          data: sel,
          silent: true,
          itemStyle: { borderColor: c.text, borderWidth: 2, borderRadius: 4 },
          label: { show: false },
          z: 3,
        },
      ],
    };
  }, [data, keys, rows, cols, triangle, labelOf, mode, selected]);

  return (
    <>
      <Chart
        option={option}
        height={rows.length * 28 + 140}
        ariaLabel={`Correlation matrix of ${keys.length} daily metrics${data.lag ? `, ${lagText(data.lag)}` : ""}`}
        onEvents={{
          click: (p) => {
            const d = (p as { data?: Cell }).data;
            if (d && "pair" in d && !d.pair.derived)
              onSelect({ x: d.pair.x, y: d.pair.y, lag: d.pair.lag });
          },
        }}
      />
      <div className="mt-3 flex flex-wrap items-center justify-center gap-x-5 gap-y-2 text-xs text-ink-3">
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
        <span className="inline-flex items-center gap-1.5">
          <span
            aria-hidden
            className="inline-flex size-3.5 items-center justify-center rounded-[3px] border border-line-strong text-[10px] leading-none"
          >
            –
          </span>
          Computed from each other
        </span>
      </div>
    </>
  );
}
