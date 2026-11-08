import { Link } from "@tanstack/react-router";
import { useMemo, useState } from "react";
import { api, type Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { SportBadge } from "@/components/SportIcon";
import { Card, EmptyState, ErrorState, ShowAllButton, Skeleton } from "@/components/ui";
import {
  axisTooltip,
  GRID,
  line,
  refLine,
  tooltipRow,
  tooltipTitle,
  valueYAxis,
} from "@/lib/charts";
import {
  distanceUnit,
  distanceValue,
  fmtDate,
  fmtDistance,
  fmtHours,
  fmtNumber,
  fmtPace,
  fmtSpeed,
  type UnitSystem,
} from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";
import { isoDay } from "@/lib/range";
import { sportLabel, usesPace } from "@/lib/sports";
import { CHROME, type Mode } from "@/lib/tokens";
import { gearName, niceAxis, type Gear } from "./gear";

type Activity = Schemas["ActivitySummary"];

function speedText(a: Activity, units: UnitSystem): string {
  if (!a.distance_m || !a.avg_speed_mps) return "";
  return usesPace(a.sport_group)
    ? fmtPace(a.avg_speed_mps, units, a.sport_group === "swim")
    : fmtSpeed(a.avg_speed_mps, units);
}

/** The replacement-distance line, labelled at its start where the cumulative line is low. */
function replaceLine(value: number, label: string, mode: Mode) {
  const base = refLine(value, label, mode);
  return { ...base, label: { ...(base.label as object), position: "insideStartTop" } };
}

function LifetimeChart({
  item,
  activities,
  color,
}: {
  item: Gear;
  activities: Activity[];
  color: string;
}) {
  const mode = useMode();
  const units = useUnits();
  const option = useMemo<ChartOption | null>(() => {
    const acts = activities
      .filter((a) => (a.distance_m ?? 0) > 0)
      .sort((a, b) => a.start_time_local.localeCompare(b.start_time_local));
    if (!acts.length) return null;
    const unit = distanceUnit(units);
    let cum = 0;
    const pts: [number, number][] = [];
    const first = new Date(acts[0]!.start_time_local).getTime();
    const begin = item.date_begin ? new Date(`${item.date_begin}T00:00:00`).getTime() : first;
    pts.push([Math.min(begin, first), 0]);
    for (const a of acts) {
      cum += a.distance_m ?? 0;
      pts.push([new Date(a.start_time_local).getTime(), distanceValue(cum, units)]);
    }
    const limit = item.max_distance_m ? distanceValue(item.max_distance_m, units) : null;
    const total = distanceValue(cum, units);
    const axis = niceAxis(Math.max(total, limit ?? 0) * 1.04);
    return {
      grid: { ...GRID, top: 28, right: 56 },
      tooltip: axisTooltip((p) => {
        const arr = p as { value: [number, number] }[];
        const v = arr[0]?.value;
        if (!v) return "";
        return (
          tooltipTitle(fmtDate(isoDay(new Date(v[0])))) +
          tooltipRow(color, "Total so far", `${fmtNumber(v[1], 0)} ${unit}`) +
          (limit
            ? tooltipRow(
                CHROME[mode].muted,
                "Of replacement distance",
                `${fmtNumber((v[1] / limit) * 100)} %`,
              )
            : "")
        );
      }),
      xAxis: { type: "time", splitNumber: 4 },
      yAxis: valueYAxis(unit, (v) => fmtNumber(v), {
        min: 0,
        max: axis.max,
        interval: axis.interval,
      }),
      series: [
        {
          ...line(gearName(item), pts, color, { area: true }),
          step: "end",
          endLabel: {
            show: true,
            color: CHROME[mode].text,
            fontWeight: 600,
            formatter: () => `${fmtNumber(total)} ${unit}`,
          },
          ...(limit
            ? { markLine: replaceLine(limit, `Replace at ${fmtNumber(limit)} ${unit}`, mode) }
            : {}),
        },
      ],
    };
  }, [activities, item, color, mode, units]);
  if (!option) return <EmptyState title="No distance recorded with this item" />;
  return (
    <Chart option={option} height={230} ariaLabel={`Cumulative distance of ${gearName(item)}`} />
  );
}

const GEAR_ACTIVITIES = 8;

export function GearDetail({ uuid, color }: { uuid: string; color: (uuid: string) => string }) {
  const units = useUnits();
  const q = api.useQuery(
    "get",
    "/api/gear/{uuid}",
    { params: { path: { uuid } } },
    { placeholderData: (prev) => prev },
  );
  const [all, setAll] = useState(false);
  if (q.error) return <ErrorState error={q.error} />;
  if (!q.data) return <Skeleton height={560} />;
  const { item, activities } = q.data;
  const name = gearName(item);
  return (
    <Card
      title={name}
      subtitle={`${fmtNumber(activities.length)} ${activities.length === 1 ? "activity" : "activities"} · ${fmtDistance(item.distance_m, units, 0)} in total`}
    >
      <h3 className="mb-1 text-xs font-medium text-ink-2">Lifetime distance</h3>
      <LifetimeChart item={item} activities={activities} color={color(item.uuid)} />
      <h3 className="mt-4 mb-1 text-xs font-medium text-ink-2">Activities</h3>
      {activities.length === 0 ? (
        <EmptyState title="Not used in any activity yet" />
      ) : (
        <>
          <ul className="-mx-2 flex flex-col">
            {(all ? activities : activities.slice(0, GEAR_ACTIVITIES)).map((a) => (
              <li key={a.activity_id}>
                <Link
                  to="/activities/$activityId"
                  params={{ activityId: String(a.activity_id) }}
                  className="flex items-center gap-3 rounded-xl px-2 py-2 hover:bg-surface-2"
                >
                  <SportBadge group={a.sport_group} size={30} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate text-sm font-medium text-ink">
                      {a.name ?? sportLabel(a.sport_group)}
                    </span>
                    <span className="block text-xs text-ink-3">
                      {fmtDate(a.start_time_local)} · {fmtHours(a.moving_s ?? a.duration_s)}
                    </span>
                  </span>
                  <span className="shrink-0 text-right">
                    <span className="block text-sm text-ink tabular">
                      {a.distance_m ? fmtDistance(a.distance_m, units) : "–"}
                    </span>
                    <span className="block text-xs text-ink-3 tabular">{speedText(a, units)}</span>
                  </span>
                </Link>
              </li>
            ))}
          </ul>
          {activities.length > GEAR_ACTIVITIES && (
            <ShowAllButton
              total={activities.length}
              noun="activities"
              expanded={all}
              onToggle={() => setAll((v) => !v)}
            />
          )}
        </>
      )}
    </Card>
  );
}
