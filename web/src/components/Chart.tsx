/**
 * ECharts wrapper: tree-shaken build, light/dark themes from the design tokens, resize-aware,
 * optional `group` to link crosshairs across charts, and `data-chart-ready` once rendered
 * (used by the e2e tests to assert that every chart actually drew something).
 */
import {
  BarChart,
  BoxplotChart,
  CustomChart,
  GaugeChart,
  HeatmapChart,
  LineChart,
  PieChart,
  ScatterChart,
} from "echarts/charts";
import {
  AriaComponent,
  AxisPointerComponent,
  CalendarComponent,
  DataZoomComponent,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  PolarComponent,
  SingleAxisComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
} from "echarts/components";
import * as echarts from "echarts/core";
import { CanvasRenderer } from "echarts/renderers";
import { useEffect, useRef } from "react";
import { useMode } from "@/lib/preferences";
import { CATEGORICAL, CHROME, type Mode } from "@/lib/tokens";

echarts.use([
  LineChart,
  BarChart,
  ScatterChart,
  HeatmapChart,
  CustomChart,
  BoxplotChart,
  PieChart,
  GaugeChart,
  AriaComponent,
  AxisPointerComponent,
  CalendarComponent,
  DataZoomComponent,
  DatasetComponent,
  GridComponent,
  LegendComponent,
  MarkAreaComponent,
  MarkLineComponent,
  MarkPointComponent,
  PolarComponent,
  SingleAxisComponent,
  TitleComponent,
  TooltipComponent,
  VisualMapComponent,
  CanvasRenderer,
]);

export type ChartOption = echarts.EChartsCoreOption;
export type ChartInstance = echarts.ECharts;

const FONT = 'system-ui, -apple-system, "Segoe UI", Roboto, sans-serif';

function theme(mode: Mode): object {
  const c = CHROME[mode];
  const axis = {
    axisLine: { lineStyle: { color: c.axis } },
    axisTick: { show: false },
    axisLabel: { color: c.muted, fontSize: 11 },
    splitLine: { lineStyle: { color: c.grid, width: 1, type: "solid" } },
    nameTextStyle: { color: c.muted, fontSize: 11 },
  };
  return {
    color: [...CATEGORICAL[mode]],
    backgroundColor: "transparent",
    textStyle: { color: c.text2, fontFamily: FONT },
    legend: {
      textStyle: { color: c.text2, fontSize: 12 },
      icon: "roundRect",
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 14,
    },
    tooltip: {
      backgroundColor: c.surface,
      borderColor: mode === "dark" ? "rgba(255,255,255,0.12)" : "rgba(11,11,11,0.12)",
      borderWidth: 1,
      textStyle: { color: c.text, fontSize: 12 },
      extraCssText: "border-radius:10px;box-shadow:0 8px 24px rgba(0,0,0,.18);",
      axisPointer: { lineStyle: { color: c.axis }, crossStyle: { color: c.axis } },
    },
    categoryAxis: { ...axis, splitLine: { show: false } },
    valueAxis: axis,
    timeAxis: { ...axis, splitLine: { show: false } },
    logAxis: axis,
    line: { symbol: "none", lineStyle: { width: 2 }, emphasis: { lineStyle: { width: 2 } } },
    bar: { itemStyle: { borderRadius: [4, 4, 0, 0] }, barMaxWidth: 24 },
    scatter: { symbolSize: 8, itemStyle: { borderColor: c.surface, borderWidth: 2 } },
    visualMap: { textStyle: { color: c.muted } },
    dataZoom: {
      borderColor: "transparent",
      textStyle: { color: c.muted },
      fillerColor: mode === "dark" ? "rgba(57,135,229,0.15)" : "rgba(42,120,214,0.12)",
    },
    calendar: {
      itemStyle: { color: "transparent", borderColor: c.surface, borderWidth: 2 },
      splitLine: { show: false },
      dayLabel: { color: c.muted },
      monthLabel: { color: c.muted },
      yearLabel: { show: false },
    },
  };
}

echarts.registerTheme("gz-light", theme("light"));
echarts.registerTheme("gz-dark", theme("dark"));

export interface ChartProps {
  option: ChartOption;
  height?: number | string;
  className?: string;
  /** Charts with the same group share tooltip/crosshair (echarts.connect). */
  group?: string;
  ariaLabel: string;
  onEvents?: Record<string, (params: unknown, chart: ChartInstance) => void>;
  onReady?: (chart: ChartInstance) => void;
}

export function Chart({
  option,
  height = 260,
  className,
  group,
  ariaLabel,
  onEvents,
  onReady,
}: ChartProps) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<ChartInstance | null>(null);
  const mode = useMode();
  const latest = useRef({ option, onEvents, onReady });
  useEffect(() => {
    latest.current = { option, onEvents, onReady };
  });

  useEffect(() => {
    const node = el.current;
    if (!node) return;
    const inst = echarts.init(node, `gz-${mode}`, { renderer: "canvas" });
    chart.current = inst;
    inst.on("finished", () => node.setAttribute("data-chart-ready", "true"));
    inst.setOption({ aria: { enabled: true }, ...latest.current.option }, true);
    for (const [name, fn] of Object.entries(latest.current.onEvents ?? {})) {
      inst.on(name, (p: unknown) => fn(p, inst));
    }
    if (group) {
      inst.group = group;
      echarts.connect(group);
    }
    latest.current.onReady?.(inst);
    const ro = new ResizeObserver(() => inst.resize());
    ro.observe(node);
    return () => {
      ro.disconnect();
      inst.dispose();
      chart.current = null;
    };
  }, [mode, group]);

  useEffect(() => {
    chart.current?.setOption({ aria: { enabled: true }, ...option }, true);
  }, [option]);

  return (
    <div
      ref={el}
      role="img"
      aria-label={ariaLabel}
      data-testid="chart"
      data-points={countPoints(option)}
      className={className}
      style={{ height, width: "100%" }}
    />
  );
}

/** Number of data points across all series/datasets (e2e asserts charts are not empty). */
function countPoints(option: ChartOption): number {
  const asArray = (v: unknown): unknown[] => (Array.isArray(v) ? v : v ? [v] : []);
  let n = 0;
  for (const s of asArray((option as { series?: unknown }).series)) {
    const data = (s as { data?: unknown }).data;
    if (Array.isArray(data)) n += data.length;
  }
  for (const d of asArray((option as { dataset?: unknown }).dataset)) {
    const source = (d as { source?: unknown }).source;
    if (Array.isArray(source)) n += source.length;
  }
  return n;
}
