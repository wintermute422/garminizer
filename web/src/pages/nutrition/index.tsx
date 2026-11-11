import { Beef, Flame, Scale, Utensils } from "lucide-react";
import { useState } from "react";
import { api, type Schemas } from "@/api/client";
import { usePageFilters } from "@/app/pageFilters";
import { Chart, type ChartOption } from "@/components/Chart";
import { Card, EmptyState, LegendItem, PageHeader, QueryState, StatTile } from "@/components/ui";
import {
  axisTooltip,
  bars,
  DAY_MS,
  dayAxis,
  dayExtent,
  dayOfPoint,
  dayPoint,
  dayTitle,
  dayTooltip,
  dayX,
  GRID,
  line,
  refLine,
  roundStackTops,
  tooltipRow,
  tooltipTitle,
  valueYAxis,
  type Extent,
} from "@/lib/charts";
import { DASH, fmtDate, fmtNumber, fmtShortDate, signed, titleCase } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { NARROW, useMediaQuery } from "@/lib/useMediaQuery";
import { CHROME, DIVERGING, MEASURE_COLORS, type Mode, barEnd } from "@/lib/tokens";
import { DayCard } from "./DayCard";
import { Setup } from "./Setup";

type Summary = Schemas["NutritionSummary"];
type Point = Schemas["NutritionDailyPoint"];

const KCAL_PER_G = { protein: 4, carbs: 4, fat: 9 } as const;

type Tip = { seriesName: string; color: string; value: [number, number | null] };

/** Title of the day under the crosshair (x is a `dayPoint` noon). */
const xTitle = (x: number) => dayTitle(dayOfPoint(x));

function tipRows(arr: Tip[], fmt: (v: number) => string): string {
  const first = arr[0];
  if (!first) return "";
  return (
    xTitle(first.value[0]) +
    arr
      .filter((a) => a.value[1] != null)
      .map((a) => tooltipRow(a.color, a.seriesName, fmt(a.value[1]!)))
      .join("")
  );
}

function intakeOption(points: Point[], s: Summary, mode: Mode, ext: Extent): ChartOption {
  const c = MEASURE_COLORS[mode];
  const logged = points.filter((p) => p.meals > 0);
  return {
    grid: { ...GRID, top: 12 },
    tooltip: axisTooltip<Tip>((p) => tipRows(p, (v) => `${fmtNumber(v)} kcal`)),
    xAxis: dayAxis(ext.min, ext.max),
    yAxis: valueYAxis(undefined, (v) => fmtNumber(v)),
    series: [
      {
        ...bars(
          "Eaten",
          logged.map((p) => dayPoint(p.day, p.intake_kcal)),
          c.intake,
          mode,
          { barMaxWidth: 14 },
        ),
        ...(s.targets.kcal ? { markLine: refLine(s.targets.kcal, "Target", mode) } : {}),
      },
      line(
        "Garmin burn",
        points.map((p) => dayPoint(p.day, p.total_kcal)),
        c.burn,
      ),
    ],
  };
}

function balanceOption(points: Point[], mode: Mode, ext: Extent): ChartOption {
  const d = DIVERGING[mode];
  const both = points.filter((p) => p.balance_kcal != null && p.meals > 0);
  return {
    grid: { ...GRID, top: 12 },
    tooltip: axisTooltip<Tip>((arr) => {
      const v = arr[0]?.value;
      if (!v || v[1] == null) return "";
      return (
        xTitle(v[0]) +
        tooltipRow(
          v[1] < 0 ? d.negative : d.positive,
          v[1] < 0 ? "Deficit" : "Surplus",
          `${signed(v[1])} kcal`,
        )
      );
    }),
    xAxis: dayAxis(ext.min, ext.max),
    yAxis: valueYAxis(undefined, (v) => signed(v)),
    series: [
      {
        ...bars(
          "Balance",
          both.map((p) => ({
            value: dayPoint(p.day, p.balance_kcal),
            itemStyle: {
              color: p.balance_kcal! < 0 ? d.negative : d.positive,
              borderRadius: barEnd(p.balance_kcal! < 0 ? "down" : "up"),
            },
          })),
          d.negative,
          mode,
          { barMaxWidth: 14 },
        ),
        markLine: {
          silent: true,
          symbol: "none",
          lineStyle: { color: CHROME[mode].axis, width: 1, type: "solid" },
          label: { show: false },
          data: [{ yAxis: 0 }],
        },
      },
    ],
  };
}

function macroOption(points: Point[], mode: Mode, ext: Extent, dense: boolean): ChartOption {
  const c = MEASURE_COLORS[mode];
  const logged = points.filter((p) => p.meals > 0);
  const series = (["protein", "carbs", "fat"] as const).map((k) =>
    bars(
      titleCase(k),
      logged.map((p) => {
        const g = p[`${k}_g`];
        return dayPoint(p.day, g == null ? null : g * KCAL_PER_G[k]);
      }),
      c[k],
      mode,
      { stack: "kcal", barMaxWidth: 14 },
    ),
  );
  // Thin columns (phones, long ranges): the 1px surface gaps would wash the colours out.
  const styled = dense
    ? series.map((x) => ({ ...x, itemStyle: { ...(x.itemStyle as object), borderWidth: 0 } }))
    : series;
  return {
    grid: { ...GRID, top: 12 },
    tooltip: axisTooltip(
      dayTooltip(
        logged,
        (p) => p.day,
        (p) =>
          dayTitle(p.day) +
          (["protein", "carbs", "fat"] as const)
            .map((k) => {
              const g = p[`${k}_g`];
              return tooltipRow(
                c[k],
                titleCase(k),
                g == null ? DASH : `${fmtNumber(g)} g · ${fmtNumber(g * KCAL_PER_G[k])} kcal`,
              );
            })
            .join(""),
      ),
    ),
    xAxis: dayAxis(ext.min, ext.max),
    yAxis: valueYAxis(undefined, (v) => fmtNumber(v)),
    series: roundStackTops(styled, mode),
  };
}

function proteinOption(points: Point[], s: Summary, mode: Mode, ext: Extent): ChartOption | null {
  const kg = s.weight_kg;
  if (!kg) return null;
  const c = MEASURE_COLORS[mode];
  const target = s.targets.protein_g_per_kg;
  const logged = points.filter((p) => p.meals > 0 && p.protein_g != null);
  return {
    grid: { ...GRID, top: 12, right: 40 },
    tooltip: axisTooltip<Tip>((p) => tipRows(p, (v) => `${fmtNumber(v, 1)} g/kg`)),
    xAxis: dayAxis(ext.min, ext.max),
    yAxis: valueYAxis(undefined, (v) => fmtNumber(v, 1), { min: 0 }),
    series: [
      {
        ...line(
          "Protein per kg",
          logged.map((p) => dayPoint(p.day, p.protein_g! / kg)),
          c.protein,
        ),
        showSymbol: logged.length < 60,
        symbolSize: 6,
        ...(target ? { markLine: refLine(target, `Target ${fmtNumber(target, 1)}`, mode) } : {}),
      },
    ],
  };
}

function weeklyOption(
  s: Summary,
  mode: Mode,
  range: Extent,
  kind: "balance" | "weight",
): ChartOption | null {
  const weeks = s.weeks.filter((w) =>
    kind === "balance" ? w.balance_kcal != null : w.weight_kg != null,
  );
  if (weeks.length < 2) return null;
  // Weeks are placed on their Monday, which can fall before the range starts.
  const ext = { min: Math.min(range.min, dayX(weeks[0]!.week) - DAY_MS), max: range.max };
  const d = DIVERGING[mode];
  const c = MEASURE_COLORS[mode];
  return {
    grid: { ...GRID, top: 12 },
    tooltip: axisTooltip<Tip>((arr) => {
      const v = arr[0]?.value;
      if (!v || v[1] == null) return "";
      const w = weeks.find((x) => dayX(x.week) === v[0]);
      const title = tooltipTitle(`Week of ${fmtDate(w?.week ?? null)}`);
      return kind === "balance"
        ? title +
            tooltipRow(
              v[1] < 0 ? d.negative : d.positive,
              "Average balance",
              `${signed(v[1])} kcal/day`,
            ) +
            `<div style="opacity:.7;margin-top:4px">${w?.days_logged ?? 0} days logged</div>`
        : title + tooltipRow(c.weight, "Average weight", `${fmtNumber(v[1], 1)} kg`);
    }),
    xAxis: dayAxis(ext.min, ext.max),
    yAxis: valueYAxis(undefined, (v) => (kind === "balance" ? signed(v) : fmtNumber(v, 1)), {
      scale: kind === "weight",
    }),
    series: [
      kind === "balance"
        ? bars(
            "Average balance",
            weeks.map((w) => ({
              value: dayPoint(w.week, w.balance_kcal),
              itemStyle: {
                color: w.balance_kcal! < 0 ? d.negative : d.positive,
                borderRadius: barEnd(w.balance_kcal! < 0 ? "down" : "up"),
              },
            })),
            d.negative,
            mode,
            { barMaxWidth: 18 },
          )
        : {
            ...line(
              "Average weight",
              weeks.map((w) => dayPoint(w.week, w.weight_kg)),
              c.weight,
            ),
            showSymbol: true,
            symbolSize: 6,
          },
    ],
  };
}

/** 100 % bar of where the energy came from, with the shares written out. */
function EnergySplit({ s }: { s: Summary }) {
  const mode = useMode();
  const c = MEASURE_COLORS[mode];
  const parts = [
    { key: "protein", label: "Protein", pct: s.macro_split.protein_pct, color: c.protein },
    { key: "carbs", label: "Carbs", pct: s.macro_split.carbs_pct, color: c.carbs },
    { key: "fat", label: "Fat", pct: s.macro_split.fat_pct, color: c.fat },
    {
      key: "alcohol",
      label: "Alcohol",
      pct: s.macro_split.alcohol_pct,
      color: CHROME[mode].muted,
    },
  ].filter((p) => (p.pct ?? 0) > 0.5);
  const avg = { protein: s.avg_protein_g, carbs: s.avg_carbs_g, fat: s.avg_fat_g } as Record<
    string,
    number | null
  >;
  return (
    <Card title="Where the energy comes from" subtitle="Share of logged kcal in this period">
      {parts.length === 0 ? (
        <EmptyState title="No macros logged in this period" />
      ) : (
        <>
          <div className="flex h-3 gap-0.5 overflow-hidden rounded-bar" aria-hidden>
            {parts.map((p) => (
              <div key={p.key} style={{ width: `${p.pct}%`, background: p.color }} />
            ))}
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-x-6 gap-y-3 text-sm sm:grid-cols-4">
            {parts.map((p) => (
              <div key={p.key}>
                <dt className="flex items-center gap-1.5 text-xs text-ink-2">
                  <span
                    className="inline-block size-2.5 rounded-swatch"
                    style={{ background: p.color }}
                    aria-hidden
                  />
                  {p.label}
                </dt>
                <dd className="mt-0.5 text-ink tabular">
                  <span className="text-lg font-semibold">{fmtNumber(p.pct)} %</span>
                  {avg[p.key] != null && (
                    <span className="ml-1.5 text-xs text-ink-3">{fmtNumber(avg[p.key])} g/day</span>
                  )}
                </dd>
              </div>
            ))}
          </dl>
          {s.avg_fiber_g != null && (
            <p className="mt-3 text-xs text-ink-3">Fibre {fmtNumber(s.avg_fiber_g)} g/day</p>
          )}
        </>
      )}
    </Card>
  );
}

function MealTypes({ s }: { s: Summary }) {
  const mode = useMode();
  const color = MEASURE_COLORS[mode].intake;
  const rows = [...s.by_meal_type].sort((a, b) => b.kcal_pct - a.kcal_pct);
  const max = Math.max(1, ...rows.map((r) => r.kcal_pct));
  return (
    <Card title="Meals of the day" subtitle="Share of logged kcal by meal">
      <ul className="flex flex-col gap-2.5 text-sm">
        {rows.map((r) => (
          <li key={r.meal_type} className="grid grid-cols-[6rem_1fr_auto] items-center gap-3">
            <span className="text-ink-2">{titleCase(r.meal_type)}</span>
            <span className="h-2 rounded-bar" style={{ background: "var(--surface-2)" }}>
              <span
                className="block h-2 rounded-bar"
                style={{ width: `${(r.kcal_pct / max) * 100}%`, background: color }}
              />
            </span>
            <span className="text-right text-ink tabular">
              {fmtNumber(r.kcal_pct)} %{" "}
              <span className="text-xs text-ink-3">
                · {r.meals} {r.meals === 1 ? "meal" : "meals"}
              </span>
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Tiles({ s }: { s: Summary }) {
  const balance = s.avg_balance_kcal;
  return (
    <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
      <StatTile
        icon={<Utensils size={15} aria-hidden />}
        label="Eaten per day"
        value={fmtNumber(s.avg_intake_kcal)}
        unit="kcal"
        sub={`${s.days_logged} of ${s.days} days logged`}
      />
      <StatTile
        icon={<Flame size={15} aria-hidden />}
        label="Garmin burn per day"
        value={fmtNumber(s.avg_total_kcal)}
        unit="kcal"
        sub={
          s.avg_active_kcal != null ? `${fmtNumber(s.avg_active_kcal)} active` : "on logged days"
        }
      />
      <StatTile
        icon={<Scale size={15} aria-hidden />}
        label="Energy balance"
        value={balance == null ? DASH : signed(balance)}
        unit="kcal/day"
        sub={balance == null ? "needs Garmin calories" : balance < 0 ? "deficit" : "surplus"}
      />
      <StatTile
        icon={<Beef size={15} aria-hidden />}
        label="Protein"
        value={fmtNumber(s.protein_g_per_kg, 1)}
        unit="g/kg"
        sub={
          s.avg_protein_g == null
            ? "no protein logged"
            : `${fmtNumber(s.avg_protein_g)} g/day${
                s.protein_target_g ? ` · target ${fmtNumber(s.protein_target_g)} g` : ""
              }`
        }
      />
    </div>
  );
}

export default function NutritionPage() {
  const range = usePageFilters();
  const query = { params: { query: range.dates } };
  const summary = api.useQuery("get", "/api/nutrition/summary", query, range.options);
  const daily = api.useQuery("get", "/api/nutrition/daily", query, range.options);
  return (
    <>
      <PageHeader
        title="Nutrition"
        description={`Meals you log through Claude Desktop, against what Garmin says you burned · ${fmtShortDate(range.start)} – ${fmtDate(range.end)}`}
      />
      <QueryState queries={[summary, daily]} height={420}>
        {([s, points]) => <NutritionBody s={s} points={points} />}
      </QueryState>
    </>
  );
}

function NutritionBody({ s, points }: { s: Summary; points: Point[] }) {
  const mode = useMode();
  const [picked, setPicked] = useState<string | null>(null);
  const narrow = useMediaQuery(NARROW);
  const lastLogged = [...points].reverse().find((p) => p.meals > 0)?.day ?? s.end;
  const day = picked ?? lastLogged;

  if (s.meals === 0) {
    return (
      <div className="grid gap-5">
        <Setup />
        <DayCard day={day} onDay={setPicked} maxDay={s.end} />
      </div>
    );
  }

  const ext = dayExtent(s.start, s.end);
  const dense = narrow || points.length > 120;
  const protein = proteinOption(points, s, mode, ext);
  const weeklyBalance = weeklyOption(s, mode, ext, "balance");
  const weeklyWeight = weeklyOption(s, mode, ext, "weight");
  const c = MEASURE_COLORS[mode];
  const d = DIVERGING[mode];
  return (
    <div className="flex flex-col gap-5">
      <Tiles s={s} />
      <DayCard day={day} onDay={setPicked} maxDay={s.end} />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card title="Eaten vs Garmin burn" subtitle="kcal per day; bars only on logged days">
          <div className="mb-2 flex flex-wrap gap-4">
            <LegendItem color={c.intake} label="Eaten" />
            <LegendItem color={c.burn} label="Garmin burn (total)" shape="line" />
          </div>
          <Chart
            option={intakeOption(points, s, mode, ext)}
            zoom
            height={240}
            ariaLabel="Daily intake against Garmin's total burn"
            onEvents={{
              click: (e) => {
                const v = (e as { value?: [number, unknown] }).value;
                if (Array.isArray(v)) setPicked(new Date(v[0]).toISOString().slice(0, 10));
              },
            }}
          />
        </Card>
        <Card
          title="Daily energy balance"
          subtitle="Eaten minus Garmin's total burn, on days with both"
        >
          <div className="mb-2 flex flex-wrap gap-4">
            <LegendItem color={d.negative} label="Deficit" />
            <LegendItem color={d.positive} label="Surplus" />
          </div>
          <Chart
            option={balanceOption(points, mode, ext)}
            zoom
            height={240}
            ariaLabel="Daily energy balance"
          />
        </Card>
        <Card title="Macros per day" subtitle="kcal from protein, carbs and fat">
          <div className="mb-2 flex flex-wrap gap-4">
            <LegendItem color={c.protein} label="Protein" />
            <LegendItem color={c.carbs} label="Carbs" />
            <LegendItem color={c.fat} label="Fat" />
          </div>
          <Chart
            option={macroOption(points, mode, ext, dense)}
            zoom
            height={240}
            ariaLabel="Energy from protein, carbs and fat per day"
          />
        </Card>
        {protein ? (
          <Card
            title="Protein per kg body weight"
            subtitle={`g/kg per logged day, using your latest weight (${fmtNumber(s.weight_kg, 1)} kg)`}
          >
            <Chart option={protein} zoom height={268} ariaLabel="Protein per kg body weight" />
          </Card>
        ) : (
          <Card title="Protein per kg body weight">
            <EmptyState title="No weigh-in yet">
              Protein per kg needs at least one weight measurement from Garmin.
            </EmptyState>
          </Card>
        )}
        <EnergySplit s={s} />
        <MealTypes s={s} />
        {(weeklyBalance || weeklyWeight) && (
          <Card
            title="Week by week: balance and weight"
            subtitle="Average balance per logged day next to the week's average weight"
            className="lg:col-span-2"
          >
            <div className="grid gap-5 md:grid-cols-2">
              <div>
                <p className="mb-1 text-xs font-medium text-ink-2">Average balance (kcal/day)</p>
                {weeklyBalance ? (
                  <Chart option={weeklyBalance} height={200} ariaLabel="Weekly energy balance" />
                ) : (
                  <EmptyState title="Not enough weeks with Garmin calories" />
                )}
              </div>
              <div>
                <p className="mb-1 text-xs font-medium text-ink-2">Average weight (kg)</p>
                {weeklyWeight ? (
                  <Chart option={weeklyWeight} height={200} ariaLabel="Weekly average weight" />
                ) : (
                  <EmptyState title="Not enough weigh-ins" />
                )}
              </div>
            </div>
          </Card>
        )}
      </div>
    </div>
  );
}
