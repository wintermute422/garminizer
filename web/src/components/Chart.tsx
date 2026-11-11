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
import { clsx } from "clsx";
import { RotateCcw } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import {
  isZoomed,
  withZoom,
  ZOOM_MIN_SPAN,
  ZOOM_SLIDER_SPACE,
  zoomAround,
  zoomedDayTicks,
  type ZoomWindow,
} from "@/lib/charts";
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
  /**
   * Zoomable x-axis (time series): slider under the plot, ctrl+wheel / pinch on it, a reset
   * button while zoomed. `dayAxis` ticks are recomputed for the visible window. "linked": only
   * the plot gestures, for a `group` member whose partner chart carries the slider.
   */
  zoom?: boolean | "linked";
}

export function Chart({
  option,
  height = 260,
  className,
  group,
  ariaLabel,
  onEvents,
  onReady,
  zoom = false,
}: ChartProps) {
  const el = useRef<HTMLDivElement>(null);
  const chart = useRef<ChartInstance | null>(null);
  const mode = useMode();
  // Zoom state belongs to one rendered option: a new option (or theme) starts unzoomed.
  const [zoomedOn, setZoomedOn] = useState<{ option: ChartOption; mode: Mode } | null>(null);
  const zoomed = zoomedOn?.option === option && zoomedOn.mode === mode;
  const latest = useRef({ option, onEvents, onReady, ariaLabel, zoom, mode });
  useEffect(() => {
    latest.current = { option, onEvents, onReady, ariaLabel, zoom, mode };
  });

  useEffect(() => {
    const node = el.current;
    if (!node) return;
    const inst = echarts.init(node, `gz-${mode}`, { renderer: "canvas" });
    chart.current = inst;
    const render = () => {
      const l = latest.current;
      inst.setOption(prepare(l.option, l.zoom, l.mode, l.ariaLabel), true);
    };
    inst.on("finished", () => node.setAttribute("data-chart-ready", "true"));
    render();
    // Handlers are looked up on every event, so callers may pass inline functions.
    for (const name of Object.keys(latest.current.onEvents ?? {})) {
      inst.on(name, (p: unknown) => latest.current.onEvents?.[name]?.(p, inst));
    }
    if (latest.current.zoom) {
      inst.on("datazoom", () => {
        const w = (inst.getOption().dataZoom as ZoomWindow[] | undefined)?.[0];
        const { option: current, mode: m } = latest.current;
        setZoomedOn(isZoomed(w) ? { option: current, mode: m } : null);
        const ticks = w ? zoomedDayTicks(current, w) : null;
        if (ticks) inst.setOption(ticks);
      });
    }
    // ctrl+wheel (and trackpad pinch, which browsers report as ctrl+wheel) zooms around the
    // pointer; a plain wheel keeps scrolling the page.
    const onWheel = (e: WheelEvent) => {
      if (!latest.current.zoom || !e.ctrlKey) return;
      const box = node.getBoundingClientRect();
      const px: [number, number] = [e.clientX - box.left, e.clientY - box.top];
      if (!inst.containPixel({ gridIndex: 0 }, px)) return;
      const w = (inst.getOption().dataZoom as ZoomWindow[] | undefined)?.[0];
      const x = inst.convertFromPixel({ xAxisIndex: 0 }, px[0]) as number;
      const delta = Math.max(-100, Math.min(100, e.deltaY * (e.deltaMode === 1 ? 33 : 1)));
      const isTime = firstXAxis(latest.current.option)?.type === "time";
      const next = w && zoomAround(w, x, Math.exp(delta * 0.003), isTime ? ZOOM_MIN_SPAN : 0);
      if (!next) return;
      e.preventDefault();
      inst.dispatchAction({ type: "dataZoom", ...next });
    };
    node.addEventListener("wheel", onWheel, { passive: false });
    if (group) {
      inst.group = group;
      echarts.connect(group);
    }
    latest.current.onReady?.(inst);
    // Canvas text is measured once: redraw when the bundled UI font finishes loading.
    if (typeof document !== "undefined" && document.fonts?.status === "loading") {
      void document.fonts.ready.then(() => {
        if (!inst.isDisposed()) render();
      });
    }
    const ro = new ResizeObserver(() => inst.resize());
    ro.observe(node);
    return () => {
      node.removeEventListener("wheel", onWheel);
      ro.disconnect();
      inst.dispose();
      chart.current = null;
    };
  }, [mode, group]);

  useEffect(() => {
    // Not ready again until this option has finished rendering (and animating).
    el.current?.setAttribute("data-chart-ready", "false");
    const l = latest.current;
    chart.current?.setOption(prepare(option, l.zoom, l.mode, l.ariaLabel), true);
  }, [option]);

  const slider = zoom === true;
  const plot = (
    <div
      ref={el}
      role="img"
      aria-label={ariaLabel}
      data-testid="chart"
      data-points={countPoints(option)}
      data-zoomed={zoom ? String(zoomed) : undefined}
      className={slider ? undefined : className}
      style={{
        height: slider ? withSliderSpace(height) : height,
        width: "100%",
      }}
    />
  );
  if (!slider) return plot;
  return (
    <div className={clsx("relative", className)}>
      {plot}
      {zoomed && (
        <button
          type="button"
          onClick={() => chart.current?.dispatchAction({ type: "dataZoom", start: 0, end: 100 })}
          className="absolute right-0 top-0 inline-flex items-center gap-1 rounded-control border border-line bg-surface px-2 py-0.5 text-xs font-medium text-ink-2 transition-colors hover:bg-hover hover:text-ink active:bg-pressed"
        >
          <RotateCcw aria-hidden className="h-3 w-3" />
          Reset zoom
        </button>
      )}
    </div>
  );
}

function firstXAxis(option: ChartOption): { type?: string } | undefined {
  const x = (option as { xAxis?: unknown }).xAxis;
  return (Array.isArray(x) ? x[0] : x) as { type?: string } | undefined;
}

function prepare(
  option: ChartOption,
  zoom: boolean | "linked",
  mode: Mode,
  label: string,
): ChartOption {
  return withAria(zoom ? withZoom(option, mode, zoom === true) : option, label);
}

function withSliderSpace(height: number | string): number | string {
  return typeof height === "number"
    ? height + ZOOM_SLIDER_SPACE
    : `calc(${height} + ${ZOOM_SLIDER_SPACE}px)`;
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
