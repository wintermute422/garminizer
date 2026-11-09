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
import { CATEGORICAL, CHROME, FONT_SANS, barEnd, type Mode } from "@/lib/tokens";

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
    textStyle: { color: c.text2, fontFamily: FONT_SANS },
    legend: {
      textStyle: { color: c.text2, fontSize: 12 },
      icon: "rect",
      itemWidth: 10,
      itemHeight: 10,
      itemGap: 14,
    },
    tooltip: {
      backgroundColor: c.surface,
      borderColor: c.border,
      borderWidth: 1,
      textStyle: { color: c.text, fontSize: 12 },
      extraCssText: `border-radius:4px;box-shadow:${c.overlay};`,
      axisPointer: { lineStyle: { color: c.axis }, crossStyle: { color: c.axis } },
    },
    categoryAxis: { ...axis, splitLine: { show: false } },
    valueAxis: axis,
    timeAxis: { ...axis, splitLine: { show: false } },
    logAxis: axis,
    line: { symbol: "none", lineStyle: { width: 2 }, emphasis: { lineStyle: { width: 2 } } },
    bar: { itemStyle: { borderRadius: barEnd("up") }, barMaxWidth: 24 },
    scatter: { symbolSize: 8, itemStyle: { borderColor: c.surface, borderWidth: 2 } },
    visualMap: { textStyle: { color: c.muted } },
    dataZoom: {
      borderColor: "transparent",
      textStyle: { color: c.muted },
      fillerColor: c.zoom,
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
  const latest = useRef({ option, onEvents, onReady, ariaLabel });
  useEffect(() => {
    latest.current = { option, onEvents, onReady, ariaLabel };
  });

  useEffect(() => {
    const node = el.current;
    if (!node) return;
    const inst = echarts.init(node, `gz-${mode}`, { renderer: "canvas" });
    chart.current = inst;
    inst.on("finished", () => node.setAttribute("data-chart-ready", "true"));
    inst.setOption(withAria(latest.current.option, latest.current.ariaLabel), true);
    // Handlers are looked up on every event, so callers may pass inline functions.
    for (const name of Object.keys(latest.current.onEvents ?? {})) {
      inst.on(name, (p: unknown) => latest.current.onEvents?.[name]?.(p, inst));
    }
    if (group) {
      inst.group = group;
      echarts.connect(group);
    }
    latest.current.onReady?.(inst);
    // Canvas text is measured once: redraw when the bundled UI font finishes loading.
    if (typeof document !== "undefined" && document.fonts?.status === "loading") {
      void document.fonts.ready.then(() => {
        if (!inst.isDisposed())
          inst.setOption(withAria(latest.current.option, latest.current.ariaLabel), true);
      });
    }
    const ro = new ResizeObserver(() => inst.resize());
    ro.observe(node);
    return () => {
      ro.disconnect();
      inst.dispose();
      chart.current = null;
    };
  }, [mode, group]);

  useEffect(() => {
    // Not ready again until this option has finished rendering (and animating).
    el.current?.setAttribute("data-chart-ready", "false");
    chart.current?.setOption(withAria(option, latest.current.ariaLabel), true);
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

/** ECharts' aria module replaces the container label; feed it ours as the description. */
function withAria(option: ChartOption, label: string): ChartOption {
  const reduced =
    typeof window !== "undefined" &&
    window.matchMedia?.("(prefers-reduced-motion: reduce)").matches === true;
  return {
    aria: { enabled: true, label: { description: label } },
    animationDuration: 450,
    ...(reduced ? { animation: false } : {}),
    ...option,
  };
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
