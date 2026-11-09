/** Records lists: best times by distance (+ progression), top activities, Garmin PRs. */
import { Link } from "@tanstack/react-router";
import { clsx } from "clsx";
import { Trophy } from "lucide-react";
import { useMemo, useState, type ReactNode } from "react";
import { api, type Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { SportBadge, SportIcon } from "@/components/SportIcon";
import { Card, EmptyState, QueryState, ScrollArea, Segmented, Sparkline } from "@/components/ui";
import { axisTooltip, GRID, tooltipRow, tooltipTitle, valueYAxis } from "@/lib/charts";
import {
  DASH,
  fmtDate,
  fmtDistance,
  fmtDuration,
  fmtElevation,
  fmtNumber,
  fmtPace,
  fmtSpeed,
  teLabel,
  type UnitSystem,
} from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";
import { sportColor, sportLabel, usesPace } from "@/lib/sports";
import { CHROME } from "@/lib/tokens";
import { dayMs, fmtTimeDelta, niceDuration, prInfo } from "./util";

type Distance = Schemas["RecordsDistance"];
type Activity = Schemas["ActivitySummary"];

function paceText(distance: number, seconds: number, sport: string, units: UnitSystem): string {
  const mps = distance / seconds;
  return usesPace(sport) ? fmtPace(mps, units, sport === "swim") : fmtSpeed(mps, units);
}

function ActivityLink({ id, children }: { id: number; children: ReactNode }) {
  return (
    <Link
      to="/activities/$activityId"
      params={{ activityId: String(id) }}
      className="text-ink-2 underline decoration-line-strong underline-offset-2 hover:text-accent"
    >
      {children}
    </Link>
  );
}

/** Step chart of every new all-time best for one distance, extended to the last day. */
function Progression({
  row,
  sport,
  lastDay,
}: {
  row: Distance;
  sport: string;
  lastDay: string | null;
}) {
  const mode = useMode();
  const units = useUnits();
  const option = useMemo<ChartOption>(() => {
    const color = sportColor(sport, mode);
    const prog = row.progression;
    const last = prog[prog.length - 1];
    const tail =
      last && lastDay && lastDay > last.day
        ? [{ value: [dayMs(lastDay), last.seconds], symbol: "none" }]
        : [];
    const secs = prog.map((p) => p.seconds);
    const lo = Math.min(...secs);
    const hi = Math.max(...secs);
    const axis = niceDuration(lo - (hi - lo) * 0.06, hi + (hi - lo) * 0.06);
    return {
      grid: { ...GRID, top: 16, right: 16 },
      tooltip: axisTooltip((p) => {
        const i = (p as { dataIndex: number }[])[0]?.dataIndex ?? -1;
        const pt = prog[Math.min(i, prog.length - 1)];
        if (!pt) return "";
        const before = prog[prog.indexOf(pt) - 1];
        return (
          tooltipTitle(i >= prog.length ? "Current best" : fmtDate(pt.day)) +
          tooltipRow(color, row.label, fmtDuration(pt.seconds)) +
          tooltipRow("transparent", "Pace", paceText(row.distance_m, pt.seconds, sport, units)) +
          (before && i < prog.length
            ? tooltipRow("transparent", "Improvement", fmtTimeDelta(pt.seconds - before.seconds))
            : "")
        );
      }),
      xAxis: { type: "time", splitLine: { show: false }, axisLabel: { hideOverlap: true } },
      yAxis: valueYAxis(undefined, (v) => fmtDuration(v), {
        inverse: true,
        ...axis,
      }),
      series: [
        {
          type: "line",
          name: row.label,
          step: "end",
          symbol: "circle",
          symbolSize: 8,
          showSymbol: true,
          lineStyle: { width: 2, color },
          itemStyle: {
            color,
            borderColor: CHROME[mode].surface,
            borderWidth: 2,
          },
          data: [...prog.map((p) => ({ value: [dayMs(p.day), p.seconds] })), ...tail],
        },
      ],
    };
  }, [row, sport, lastDay, mode, units]);
  return (
    <Chart option={option} height={240} ariaLabel={`Progression of the ${row.label} best time`} />
  );
}

const PREFERRED = [5000, 10000, 21097.5, 42195];

/** Best times over standard distances, this year's best and the progression of each. */
export function DistancesCard({
  rows,
  sport,
  lastDay,
}: {
  rows: Distance[];
  sport: string;
  lastDay: string | null;
}) {
  const units = useUnits();
  const mode = useMode();
  const withBest = rows.filter((r) => r.best !== null);
  const [selected, setSelected] = useState<number | null>(null);
  const fallback =
    withBest.find((r) => PREFERRED.includes(r.distance_m) && r.progression.length > 1) ??
    withBest[0];
  const current = withBest.find((r) => r.distance_m === selected) ?? fallback;
  const year = lastDay?.slice(0, 4) ?? "This year";
  if (!withBest.length)
    return (
      <Card className="lg:col-span-2" title={`Best times by distance · ${sportLabel(sport)}`}>
        <EmptyState title={`No best efforts for ${sportLabel(sport).toLowerCase()} yet`} />
      </Card>
    );
  return (
    <Card
      className="lg:col-span-2"
      title={`Best times by distance · ${sportLabel(sport)}`}
      subtitle="Fastest stretch of each distance inside any activity; pick a row to see how the record fell"
    >
      <div className="grid gap-5 xl:grid-cols-5">
        <ScrollArea
          label="Best times table"
          className="relative -mx-5 hidden overflow-x-auto sm:block xl:col-span-3 xl:mx-0"
        >
          <table className="w-full min-w-[560px] text-sm">
            <thead>
              <tr className="border-b border-line text-xs text-ink-3">
                <th scope="col" className="py-2 pr-3 pl-4 text-left font-medium sm:pl-5 xl:pl-0">
                  Distance
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  Best
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  {usesPace(sport) ? "Pace" : "Speed"}
                </th>
                <th scope="col" className="px-3 py-2 text-left font-medium">
                  Set on
                </th>
                <th scope="col" className="px-3 py-2 text-right font-medium">
                  {year}
                </th>
                <th scope="col" className="py-2 pr-4 pl-3 text-left font-medium sm:pr-5 xl:pr-0">
                  <span className="sr-only">Progression</span>
                </th>
              </tr>
            </thead>
            <tbody className="tabular">
              {withBest.map((r) => {
                const best = r.best!;
                const ty = r.best_this_year;
                const active = r.distance_m === current?.distance_m;
                return (
                  <tr
                    key={r.distance_m}
                    className={clsx("border-b border-line last:border-0", active && "bg-surface-2")}
                  >
                    <td className="py-1.5 pr-3 pl-4 sm:pl-5 xl:pl-2">
                      <button
                        type="button"
                        aria-pressed={active}
                        onClick={() => setSelected(r.distance_m)}
                        className={clsx(
                          "rounded-control px-1.5 py-1 text-left font-medium whitespace-nowrap",
                          active ? "text-ink" : "text-ink-2 hover:text-ink",
                        )}
                      >
                        {r.label}
                      </button>
                    </td>
                    <td className="px-3 py-1.5 text-right font-semibold text-ink">
                      {fmtDuration(best.seconds)}
                    </td>
                    <td className="px-3 py-1.5 text-right whitespace-nowrap text-ink-2">
                      {paceText(r.distance_m, best.seconds, sport, units)}
                    </td>
                    <td className="max-w-[220px] truncate px-3 py-1.5 text-xs whitespace-nowrap">
                      <ActivityLink id={best.activity_id}>{fmtDate(best.day)}</ActivityLink>
                      {best.name && <span className="ml-1.5 text-ink-3">{best.name}</span>}
                    </td>
                    <td className="px-3 py-1.5 text-right whitespace-nowrap">
                      {ty ? (
                        ty.activity_id === best.activity_id || ty.seconds - best.seconds < 0.5 ? (
                          <span className="inline-flex items-center gap-1 text-ink">
                            <Trophy size={13} aria-hidden className="text-ink-3" />
                            {fmtDuration(ty.seconds)}
                          </span>
                        ) : (
                          <span className="text-ink-2">
                            {fmtDuration(ty.seconds)}{" "}
                            <span className="text-xs text-ink-3">
                              {fmtTimeDelta(ty.seconds - best.seconds)}
                            </span>
                          </span>
                        )
                      ) : (
                        <span className="text-ink-3">{DASH}</span>
                      )}
                    </td>
                    <td className="w-24 py-1.5 pr-4 pl-3 sm:pr-5 xl:pr-0">
                      {r.progression.length > 1 ? (
                        <Sparkline
                          values={r.progression.map((p) => -p.seconds)}
                          color={sportColor(sport, mode)}
                          height={24}
                          label={`${r.label}: ${r.progression.length} records`}
                        />
                      ) : (
                        <span className="text-xs text-ink-3">1 record</span>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </ScrollArea>
        {/* Phones: two-line rows instead of a wide table. */}
        <ul className="-mx-4 flex flex-col divide-y divide-line sm:hidden">
          {withBest.map((r) => {
            const best = r.best!;
            const ty = r.best_this_year;
            const active = r.distance_m === current?.distance_m;
            const tie =
              ty && (ty.activity_id === best.activity_id || ty.seconds - best.seconds < 0.5);
            return (
              <li key={r.distance_m} className={clsx("px-4 py-2.5", active && "bg-surface-2")}>
                <div className="flex items-baseline justify-between gap-3">
                  <button
                    type="button"
                    aria-pressed={active}
                    onClick={() => setSelected(r.distance_m)}
                    className={clsx(
                      "-ml-1.5 rounded-control px-1.5 py-0.5 text-left text-sm font-medium",
                      active ? "text-ink" : "text-ink-2",
                    )}
                  >
                    {r.label}
                  </button>
                  <span className="text-sm font-semibold text-ink tabular">
                    {fmtDuration(best.seconds)}
                  </span>
                </div>
                <div className="mt-0.5 flex flex-wrap items-baseline justify-between gap-x-3 gap-y-0.5 text-xs text-ink-3 tabular">
                  <span>
                    {paceText(r.distance_m, best.seconds, sport, units)} ·{" "}
                    <ActivityLink id={best.activity_id}>{fmtDate(best.day)}</ActivityLink>
                  </span>
                  <span>
                    {year}:{" "}
                    {ty ? (
                      tie ? (
                        <span className="inline-flex items-center gap-1 text-ink-2">
                          <Trophy size={12} aria-hidden />
                          {fmtDuration(ty.seconds)}
                        </span>
                      ) : (
                        <>
                          <span className="text-ink-2">{fmtDuration(ty.seconds)}</span>{" "}
                          {fmtTimeDelta(ty.seconds - best.seconds)}
                        </>
                      )
                    ) : (
                      DASH
                    )}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
        {current && (
          <div className="min-w-0 xl:col-span-2">
            <p className="text-xs font-medium text-ink-2">
              {current.label} record progression ·{" "}
              <span className="text-ink-3">
                {current.progression.length}{" "}
                {current.progression.length === 1 ? "record" : "records"}; faster is up
              </span>
            </p>
            <Progression row={current} sport={sport} lastDay={lastDay} />
          </div>
        )}
      </div>
    </Card>
  );
}

type TopBy = "distance" | "duration" | "elevation" | "load" | "speed";

function topValue(a: Activity, by: TopBy, units: UnitSystem): { main: string; raw: number } {
  switch (by) {
    case "distance":
      return { main: fmtDistance(a.distance_m, units), raw: a.distance_m ?? 0 };
    case "duration": {
      const s = a.moving_s ?? a.duration_s ?? 0;
      return { main: fmtDuration(s), raw: s };
    }
    case "elevation":
      return { main: fmtElevation(a.elevation_gain_m, units), raw: a.elevation_gain_m ?? 0 };
    case "load":
      return { main: fmtNumber(a.training_load), raw: a.training_load ?? 0 };
    case "speed":
      return {
        main: usesPace(a.sport_group)
          ? fmtPace(a.avg_speed_mps, units, a.sport_group === "swim")
          : fmtSpeed(a.avg_speed_mps, units),
        raw: a.avg_speed_mps ?? 0,
      };
  }
}

function topContext(a: Activity, by: TopBy, units: UnitSystem): string {
  const time = fmtDuration(a.moving_s ?? a.duration_s);
  if (by === "duration" || by === "speed" || by === "elevation")
    return a.distance_m ? fmtDistance(a.distance_m, units) : time;
  if (by === "load") return teLabel(a.training_effect_label);
  return time;
}

/** All-time top activities by a chosen measure. */
export function TopCard({ sport }: { sport: string }) {
  const units = useUnits();
  const mode = useMode();
  const [by, setBy] = useState<TopBy>("distance");
  const q = api.useQuery(
    "get",
    "/api/records/top",
    { params: { query: { sport, by, limit: 10 } } },
    { placeholderData: (prev) => prev },
  );
  const pace = usesPace(sport);
  return (
    <Card
      title={`Top 10 · ${sportLabel(sport)}`}
      subtitle="Your biggest days of all time"
      actions={
        <Segmented
          size="sm"
          label="Rank top activities by"
          value={by}
          onChange={setBy}
          options={[
            { value: "distance", label: "Distance" },
            { value: "duration", label: "Time" },
            { value: "elevation", label: "Climb" },
            { value: "load", label: "Load" },
            { value: "speed", label: pace ? "Pace" : "Speed" },
          ]}
        />
      }
    >
      <QueryState
        query={q}
        height={420}
        isEmpty={(d) => d.length === 0}
        empty={<EmptyState title="No activities to rank" />}
      >
        {(items) => {
          const max = Math.max(...items.map((a) => topValue(a, by, units).raw), 1e-9);
          return (
            <ol className="flex flex-col divide-y divide-line">
              {items.map((a, i) => {
                const v = topValue(a, by, units);
                return (
                  <li key={a.activity_id}>
                    <Link
                      to="/activities/$activityId"
                      params={{ activityId: String(a.activity_id) }}
                      className="group flex items-center gap-3 py-2"
                    >
                      <span className="w-5 shrink-0 text-right text-xs text-ink-3 tabular">
                        {i + 1}
                      </span>
                      <SportBadge group={a.sport_group} size={30} />
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-sm font-medium text-ink group-hover:text-accent">
                          {a.name ?? sportLabel(a.sport_group)}
                        </span>
                        <span className="block truncate text-xs text-ink-3">
                          {fmtDate(a.start_time_local)} · {topContext(a, by, units)}
                        </span>
                      </span>
                      <span className="flex w-24 shrink-0 flex-col items-end gap-1">
                        <span className="text-sm font-semibold whitespace-nowrap text-ink tabular">
                          {v.main}
                        </span>
                        <span
                          className="h-1 rounded-bar"
                          style={{
                            width: `${Math.max(6, (v.raw / max) * 100)}%`,
                            background: sportColor(a.sport_group, mode),
                            opacity: 0.8,
                          }}
                          aria-hidden
                        />
                      </span>
                    </Link>
                  </li>
                );
              })}
            </ol>
          );
        }}
      </QueryState>
    </Card>
  );
}

function prValue(
  p: Schemas["RecordsPersonal"],
  units: UnitSystem,
): { main: string; sub: string | null } {
  const info = prInfo(p.type_key);
  switch (info.kind) {
    case "time":
      return {
        main: fmtDuration(p.value),
        sub: info.distance ? paceText(info.distance, p.value, info.sport ?? "run", units) : null,
      };
    case "distance":
      return { main: fmtDistance(p.value, units), sub: null };
    case "elevation":
      return { main: fmtElevation(p.value, units), sub: null };
    case "power":
      return { main: `${fmtNumber(p.value)} W`, sub: null };
    case "steps":
      return { main: fmtNumber(p.value), sub: "steps" };
    case "days":
      return { main: `${fmtNumber(p.value)} days`, sub: null };
    default:
      return { main: fmtNumber(p.value, Number.isInteger(p.value) ? 0 : 1), sub: null };
  }
}

/** Personal records as Garmin tracks them. */
export function PersonalCard() {
  const units = useUnits();
  const q = api.useQuery("get", "/api/records/personal");
  return (
    <Card title="Garmin personal records" subtitle="As recorded by Garmin Connect, all sports">
      <QueryState
        query={q}
        height={420}
        isEmpty={(d) => d.length === 0}
        empty={<EmptyState title="Garmin has no personal records yet" />}
      >
        {(items) => (
          <ul className="flex flex-col divide-y divide-line">
            {items.map((p) => {
              const info = prInfo(p.type_key);
              const v = prValue(p, units);
              return (
                <li key={p.record_id} className="flex items-center gap-3 py-2.5">
                  <span className="inline-flex size-[30px] shrink-0 items-center justify-center rounded-control bg-surface-2 text-ink-2">
                    {info.sport ? (
                      <SportIcon group={info.sport} size={15} />
                    ) : (
                      <Trophy size={15} aria-hidden />
                    )}
                  </span>
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-ink">
                      {info.label}
                      {info.sport && info.kind === "time" && (
                        <span className="font-normal text-ink-3">
                          {" "}
                          · {sportLabel(info.sport).toLowerCase()}
                        </span>
                      )}
                    </span>
                    <span className="block truncate text-xs text-ink-3">
                      {p.achieved_at ? fmtDate(p.achieved_at) : DASH}
                      {p.activity_id ? (
                        <>
                          {" · "}
                          <ActivityLink id={p.activity_id}>
                            {p.activity_name ?? "activity"}
                          </ActivityLink>
                        </>
                      ) : null}
                    </span>
                  </span>
                  <span className="text-right">
                    <span className="block text-sm font-semibold whitespace-nowrap text-ink tabular">
                      {v.main}
                    </span>
                    {v.sub && <span className="block text-xs text-ink-3 tabular">{v.sub}</span>}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
      </QueryState>
    </Card>
  );
}
