/** ECharts options of the weight-goal page (trend vs target, body fat, energy balance). */
import type { Schemas } from "@/api/client";
import type { ChartOption } from "@/components/Chart";
import {
  axisTooltip,
  bars,
  cased,
  dayAxis,
  dayOfPoint,
  dayPoint,
  dayTitle,
  dayTooltip,
  dayX,
  dotSize,
  dotStyle,
  GRID_WITH_LEGEND,
  halo,
  legend,
  legendItems,
  line,
  niceScale,
  scatter,
  tooltipMuted,
  tooltipRow,
  valueYAxis,
  type Extent,
  type TipParam,
} from "@/lib/charts";
import { DASH, fmtNumber, signed } from "@/lib/format";
import { CHROME, DIVERGING, barEnd, measureColors, type Mode } from "@/lib/tokens";
import { checkpointState, targetAt } from "./goal";

type View = Schemas["GoalView"];
type Day = Schemas["GoalDay"];

const KG_STEPS = [0.25, 0.5, 1, 2, 5, 10] as const;
const PCT_STEPS = [0.25, 0.5, 1, 2, 5] as const;

/** Colours of the page: weight (dots + trend), target (ink), body fat, regression (ink). */
export function goalColors(mode: Mode) {
  const m = measureColors(mode);
  return {
    weight: m.weight,
    target: CHROME[mode].text2,
    fat: m.fat,
    regression: CHROME[mode].text2,
  };
}

/** Day of the first hovered point (x is a `dayPoint` noon), else of the axis pointer. */
function hoveredDay(params: TipParam[]): string | null {
  for (const p of params) {
    const v = p.value;
    if (Array.isArray(v) && typeof v[0] === "number") return dayOfPoint(v[0]);
  }
  const x = params[0]?.axisValue;
  return typeof x === "number" ? dayOfPoint(x) : null;
}

const kg = (v: number | null | undefined, digits = 1) =>
  v == null ? DASH : `${fmtNumber(v, digits)} kg`;

const todayLine = (today: string, mode: Mode) => ({
  xAxis: dayX(today),
  lineStyle: { color: CHROME[mode].axis, type: "solid", width: 1 },
  label: {
    show: true,
    formatter: "Today",
    position: "insideEndTop",
    color: CHROME[mode].muted,
    fontSize: 11,
    ...halo(mode),
  },
});

/** Weigh-ins (dots), weighted trend (line) and the stepped, dashed target line. */
export function trendOption(v: View, ext: Extent, mode: Mode): ChartOption {
  const c = goalColors(mode);
  const byDay = new Map(v.days.map((d) => [d.day, d]));
  const checkpoints = new Map(v.checkpoints.map((cp) => [cp.day, cp]));
  const weighIns = v.days.filter((d) => d.weight_kg != null);
  const values = [
    ...weighIns.map((d) => d.weight_kg!),
    ...v.days.flatMap((d) => (d.trend_kg == null ? [] : [d.trend_kg])),
    ...v.target_line.map((p) => p.target_kg),
  ];
  const y = values.length
    ? niceScale(Math.min(...values), Math.max(...values), { steps: KG_STEPS, ticks: 4 })
    : null;
  return {
    grid: { ...GRID_WITH_LEGEND, right: 44 },
    legend: {
      ...legend(),
      data: [
        ...legendItems([
          ["Weigh-ins", "dot"],
          ["Trend", "line"],
          ["Target", "line"],
        ]),
        { name: "Checkpoints", icon: "diamond" },
      ],
    },
    tooltip: axisTooltip((arr) => {
      const day = hoveredDay(arr);
      if (!day) return "";
      const d = byDay.get(day);
      const cp = checkpoints.get(day);
      const target = d?.target_kg ?? targetAt(v.target_line, day);
      if (!d && target == null) return "";
      return (
        dayTitle(day) +
        (d ? tooltipRow(c.weight, "Weigh-in", kg(d.weight_kg)) : "") +
        (d ? tooltipRow(c.weight, "Trend", kg(d.trend_kg, 2)) : "") +
        tooltipRow(c.target, "Target", kg(target, 2)) +
        (d?.delta_kg != null
          ? tooltipMuted("Trend − target", `${signed(d.delta_kg, 2)} kg`, mode)
          : "") +
        (cp ? tooltipMuted("Checkpoint", checkpointState(cp).label, mode) : "")
      );
    }),
    xAxis: dayAxis(ext.min, ext.max),
    yAxis: valueYAxis(undefined, (n) => fmtNumber(n, Number.isInteger(n) ? 0 : 1), {
      ...(y ? { min: y.min, max: y.max, interval: y.interval } : { scale: true }),
    }),
    series: [
      {
        ...scatter(
          "Weigh-ins",
          weighIns.map((d) => dayPoint(d.day, d.weight_kg)),
          c.weight,
          dotSize(weighIns.length, 5),
        ),
        itemStyle: { ...dotStyle(c.weight, mode), opacity: mode === "dark" ? 0.6 : 0.5 },
        z: 2,
      },
      {
        ...line(
          "Target",
          v.target_line.map((p) => dayPoint(p.day, p.target_kg)),
          c.target,
          { dashed: true, width: 1.5 },
        ),
        z: 3,
        markLine: { silent: true, symbol: "none", data: [todayLine(v.today, mode)] },
      },
      {
        type: "scatter",
        name: "Checkpoints",
        data: v.checkpoints.map((cp) => dayPoint(cp.day, cp.target_kg)),
        symbol: "diamond",
        symbolSize: 8,
        itemStyle: { color: CHROME[mode].surface, borderColor: c.target, borderWidth: 1.5 },
        z: 5,
      },
      ...cased(
        {
          ...line(
            "Trend",
            // Days without a trend (no weigh-in yet) are bridged; the line ends at the last one.
            v.days.filter((d) => d.trend_kg != null).map((d) => dayPoint(d.day, d.trend_kg)),
            c.weight,
          ),
          endLabel: {
            show: true,
            color: CHROME[mode].text2,
            fontSize: 11,
            distance: 6,
            formatter: (p: { value: [number, number | null] }) =>
              p.value[1] == null ? "" : fmtNumber(p.value[1], 1),
          },
        },
        mode,
      ),
    ],
  };
}

/** Body-fat readings (dots), their EWMA trend and the dashed regression line. */
export function fatOption(v: View, ext: Extent, mode: Mode): ChartOption {
  const c = goalColors(mode);
  const reg = v.body_fat_regression;
  const regName = reg ? `Regression ${signed(reg.slope_pct_per_week, 2)} pp/week` : "Regression";
  const values = [
    ...v.body_fat.map((p) => p.body_fat_pct),
    ...v.body_fat.map((p) => p.trend_pct),
    ...(reg ? [reg.start_pct, reg.end_pct] : []),
  ];
  const y = niceScale(Math.min(...values), Math.max(...values), { steps: PCT_STEPS, ticks: 4 });
  const byDay = new Map(v.body_fat.map((p) => [p.day, p]));
  return {
    grid: { ...GRID_WITH_LEGEND, right: 44 },
    legend: {
      ...legend(),
      data: legendItems([
        ["Readings", "dot"],
        ["Trend", "line"],
        ...(reg ? ([[regName, "line"]] as [string, "line"][]) : []),
      ]),
    },
    tooltip: axisTooltip((arr) => {
      const day = hoveredDay(arr);
      const p = day ? byDay.get(day) : undefined;
      if (!day || !p) return "";
      return (
        dayTitle(day) +
        tooltipRow(c.fat, "Reading", `${fmtNumber(p.body_fat_pct, 1)} %`) +
        tooltipRow(c.fat, "Trend", `${fmtNumber(p.trend_pct, 2)} %`)
      );
    }),
    xAxis: dayAxis(ext.min, ext.max),
    yAxis: valueYAxis(undefined, (n) => fmtNumber(n, Number.isInteger(n) ? 0 : 1), {
      min: y.min,
      max: y.max,
      interval: y.interval,
    }),
    series: [
      {
        ...scatter(
          "Readings",
          v.body_fat.map((p) => dayPoint(p.day, p.body_fat_pct)),
          c.fat,
          dotSize(v.body_fat.length, 5),
        ),
        itemStyle: dotStyle(c.fat, mode),
      },
      ...(reg
        ? [
            {
              ...line(
                regName,
                [dayPoint(reg.start_day, reg.start_pct), dayPoint(reg.end_day, reg.end_pct)],
                c.regression,
                { dashed: true, width: 1.5 },
              ),
              silent: true,
              tooltip: { show: false },
              z: 3,
            },
          ]
        : []),
      ...cased(
        {
          ...line(
            "Trend",
            v.body_fat.map((p) => dayPoint(p.day, p.trend_pct)),
            c.fat,
          ),
          endLabel: {
            show: true,
            color: CHROME[mode].text2,
            fontSize: 11,
            distance: 6,
            formatter: (p: { value: [number, number | null] }) =>
              p.value[1] == null ? "" : `${fmtNumber(p.value[1], 1)}`,
          },
        },
        mode,
      ),
    ],
  };
}

/** Daily balance bars (deficit / surplus) with the zero line and the goal's daily target. */
export function balanceOption(v: View, ext: Extent, mode: Mode): ChartOption {
  const d = DIVERGING[mode];
  const logged: Day[] = v.days.filter((x) => x.meals > 0 && x.balance_kcal != null);
  const target = v.target_daily_balance_kcal;
  const ch = CHROME[mode];
  return {
    grid: { left: 4, right: 12, top: 16, bottom: 4 },
    tooltip: axisTooltip(
      dayTooltip(
        logged,
        (x) => x.day,
        (x) =>
          dayTitle(x.day) +
          tooltipRow(
            x.balance_kcal! < 0 ? d.negative : d.positive,
            x.balance_kcal! < 0 ? "Deficit" : "Surplus",
            `${signed(x.balance_kcal)} kcal`,
          ) +
          tooltipMuted("Eaten", `${fmtNumber(x.intake_kcal)} kcal`, mode) +
          tooltipMuted("Burn", `${fmtNumber(x.burn_kcal)} kcal`, mode) +
          (target != null ? tooltipMuted("Target", `${signed(target)} kcal`, mode) : ""),
      ),
    ),
    xAxis: dayAxis(ext.min, ext.max),
    yAxis: valueYAxis(undefined, (n) => signed(n)),
    series: [
      {
        ...bars(
          "Balance",
          logged.map((x) => ({
            value: dayPoint(x.day, x.balance_kcal),
            itemStyle: {
              color: x.balance_kcal! < 0 ? d.negative : d.positive,
              borderRadius: barEnd(x.balance_kcal! < 0 ? "down" : "up"),
            },
          })),
          d.negative,
          mode,
          { barMaxWidth: 14 },
        ),
        markLine: {
          silent: true,
          symbol: "none",
          data: [
            {
              yAxis: 0,
              lineStyle: { color: ch.axis, width: 1, type: "solid" },
              label: { show: false },
            },
            ...(target != null
              ? [
                  {
                    yAxis: target,
                    lineStyle: { color: ch.text2, width: 1, type: [4, 4] },
                    // Named in the legend above the chart: a label here would cut through bars.
                    label: { show: false },
                  },
                ]
              : []),
          ],
        },
      },
    ],
  };
}
