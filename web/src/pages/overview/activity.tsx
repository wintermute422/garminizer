/** Activity cards: this week vs last week by sport (+ streak) and the latest activities. */
import { Link } from "@tanstack/react-router";
import { clsx } from "clsx";
import { ChevronRight, Flame, Trophy } from "lucide-react";
import { api, type Schemas } from "@/api/client";
import { SportBadge, SportIcon } from "@/components/SportIcon";
import { Card, Delta, EmptyState, Skeleton } from "@/components/ui";
import {
  DASH,
  fmtDate,
  fmtDistance,
  fmtHours,
  fmtLocalTime,
  fmtNumber,
  signed,
  teLabel,
} from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";
import { bySlot, sportColor, sportLabel } from "@/lib/sports";
import { addDays } from "@/lib/range";
import { NEUTRAL, SEQUENTIAL } from "@/lib/tokens";

type Overview = Schemas["OverviewToday"];
type SportWeek = Schemas["OverviewSportWeek"];

function sum(rows: SportWeek[], key: "duration_s" | "distance_m" | "activities"): number {
  return rows.reduce((s, r) => s + (r[key] ?? 0), 0);
}

const WEEKDAY_INITIALS = ["M", "T", "W", "T", "F", "S", "S"];

/** Last week and this week as two rows of day cells, shaded by moving time. */
function TwoWeeks({ day }: { day: string }) {
  const mode = useMode();
  const weekday = (new Date(`${day}T12:00:00`).getDay() + 6) % 7;
  const monday = addDays(day, -weekday);
  const start = addDays(monday, -7);
  const cal = api.useQuery("get", "/api/calendar", { params: { query: { start, end: day } } });
  const byDay = new Map((cal.data?.days ?? []).map((d) => [d.day, d]));
  if (cal.isPending) return <Skeleton height={86} />;
  const ramp = SEQUENTIAL[mode];
  const shade = (s: number) =>
    s < 1800 ? ramp[1]! : s < 3600 ? ramp[2]! : s < 5400 ? ramp[3]! : ramp[4]!;
  const rows = [
    { label: "Last week", from: start },
    { label: "This week", from: monday },
  ];
  return (
    <div className="grid grid-cols-[auto_repeat(7,minmax(0,1fr))] items-center gap-1.5 text-xs">
      <span />
      {WEEKDAY_INITIALS.map((w, i) => (
        <span key={i} className="text-center text-ink-3" aria-hidden>
          {w}
        </span>
      ))}
      {rows.map((r) => (
        <div key={r.label} className="contents">
          <span className="pr-2 whitespace-nowrap text-ink-3">{r.label}</span>
          {Array.from({ length: 7 }, (_, i) => {
            const d = addDays(r.from, i);
            const t = byDay.get(d);
            const future = d > day;
            const text = `${fmtDate(d, { weekday: "long", day: "numeric", month: "short" })}: ${
              future
                ? "upcoming"
                : t
                  ? `${fmtHours(t.duration_s)}, ${t.sport_groups.map(sportLabel).join(", ")}`
                  : "rest day"
            }`;
            return (
              <span
                key={d}
                title={text}
                className={clsx(
                  "flex h-7 items-center justify-center gap-0.5 rounded-lg",
                  future ? "border border-dashed border-line" : !t && "bg-surface-3",
                )}
                style={t ? { background: shade(t.duration_s) } : undefined}
              >
                <span className="sr-only">{text}</span>
                {t?.sport_groups.slice(0, 3).map((g) => (
                  <span
                    key={g}
                    aria-hidden
                    className="size-1.5 rounded-full ring-1 ring-surface"
                    style={{ background: sportColor(g, mode) }}
                  />
                ))}
              </span>
            );
          })}
        </div>
      ))}
    </div>
  );
}

export function WeekCard({
  week,
  day,
  className,
}: {
  week: Overview["week"];
  day: string;
  className?: string;
}) {
  const mode = useMode();
  const units = useUnits();
  const sports = [
    ...new Set([...week.this_week, ...week.last_week].map((r) => r.sport_group)),
  ].sort(bySlot);
  const find = (rows: SportWeek[], g: string) => rows.find((r) => r.sport_group === g);
  const max = Math.max(1, ...[...week.this_week, ...week.last_week].map((r) => r.duration_s ?? 0));
  const thisTime = sum(week.this_week, "duration_s");
  const lastTime = sum(week.last_week, "duration_s");
  const change = lastTime > 0 ? ((thisTime - lastTime) / lastTime) * 100 : null;
  return (
    <Card
      title="This week vs last week"
      subtitle="Moving time by sport · this week runs Monday to today"
      className={className}
    >
      {sports.length === 0 ? (
        <EmptyState title="No activities in the last two weeks" />
      ) : (
        <div className="flex flex-col gap-4">
          <div className="grid grid-cols-3 gap-3">
            <div>
              <p className="text-xs text-ink-3">This week</p>
              <p className="mt-1 text-xl leading-none font-semibold text-ink">
                {fmtHours(thisTime)}
              </p>
              <p className="mt-1 text-xs text-ink-3">
                {fmtNumber(sum(week.this_week, "activities"))} activities
              </p>
            </div>
            <div>
              <p className="text-xs text-ink-3">Last week</p>
              <p className="mt-1 text-xl leading-none font-semibold text-ink-2">
                {fmtHours(lastTime)}
              </p>
              <p className="mt-1 text-xs text-ink-3">
                {fmtNumber(sum(week.last_week, "activities"))} activities
              </p>
            </div>
            <div>
              <p className="text-xs text-ink-3">Change</p>
              <p className="mt-1.5">
                <Delta
                  value={change}
                  text={change === null ? DASH : `${signed(change)} %`}
                  direction="neutral"
                />
              </p>
            </div>
          </div>
          <TwoWeeks day={day} />
          <table className="w-full text-sm">
            <caption className="sr-only">Moving time per sport, this week and last week</caption>
            <thead>
              <tr className="text-xs text-ink-3">
                <th scope="col" className="pb-1.5 text-left font-medium">
                  Sport
                </th>
                <th scope="col" className="pb-1.5 font-medium">
                  <span className="sr-only">Comparison bars</span>
                </th>
                <th scope="col" className="pb-1.5 pl-2 text-right font-medium whitespace-nowrap">
                  This week
                </th>
                <th scope="col" className="pb-1.5 pl-2 text-right font-medium whitespace-nowrap">
                  Last week
                </th>
              </tr>
            </thead>
            <tbody>
              {sports.map((g) => {
                const now = find(week.this_week, g);
                const prev = find(week.last_week, g);
                const color = sportColor(g, mode);
                return (
                  <tr key={g} className="border-t border-line">
                    <th scope="row" className="py-2 pr-2 text-left font-normal">
                      <span className="flex items-center gap-2 text-ink">
                        <SportIcon group={g} size={15} colored />
                        <span className="truncate">{sportLabel(g)}</span>
                      </span>
                    </th>
                    <td className="w-full py-2" aria-hidden>
                      <div className="flex flex-col gap-1">
                        <span
                          className="block h-2 rounded-full"
                          style={{
                            width: `${((now?.duration_s ?? 0) / max) * 100}%`,
                            minWidth: now ? 4 : 0,
                            background: color,
                          }}
                        />
                        <span
                          className="block h-1 rounded-full"
                          style={{
                            width: `${((prev?.duration_s ?? 0) / max) * 100}%`,
                            minWidth: prev ? 4 : 0,
                            background: NEUTRAL[mode],
                            opacity: 0.6,
                          }}
                        />
                      </div>
                    </td>
                    <td className="py-2 pl-2 text-right whitespace-nowrap tabular">
                      <span className="block text-ink">
                        {now ? fmtHours(now.duration_s) : DASH}
                      </span>
                      {now?.distance_m ? (
                        <span className="block text-xs text-ink-3">
                          {fmtDistance(now.distance_m, units)}
                        </span>
                      ) : null}
                    </td>
                    <td className="py-2 pl-2 text-right whitespace-nowrap tabular">
                      <span className="block text-ink-2">
                        {prev ? fmtHours(prev.duration_s) : DASH}
                      </span>
                      {prev?.distance_m ? (
                        <span className="block text-xs text-ink-3">
                          {fmtDistance(prev.distance_m, units)}
                        </span>
                      ) : null}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

function StreakStrip({ streak }: { streak: Overview["streak"] }) {
  const days = (n: number) => `${fmtNumber(n)} ${n === 1 ? "day" : "days"}`;
  return (
    <div className="grid grid-cols-2 gap-3 rounded-xl bg-surface-2 p-3">
      <div className="flex items-center gap-2.5">
        <Flame size={18} className="text-ink-3" aria-hidden />
        <div>
          <p className="text-xs text-ink-3">Current streak</p>
          <p className="text-sm font-semibold text-ink">{days(streak.current)}</p>
        </div>
      </div>
      <div className="flex items-center gap-2.5">
        <Trophy size={18} className="text-ink-3" aria-hidden />
        <div>
          <p className="text-xs text-ink-3">Longest streak</p>
          <p className="text-sm font-semibold text-ink">{days(streak.longest)}</p>
        </div>
      </div>
    </div>
  );
}

export function RecentCard({
  items,
  streak,
  className,
}: {
  items: Overview["recent_activities"];
  streak: Overview["streak"];
  className?: string;
}) {
  const units = useUnits();
  return (
    <Card
      title="Recent activities"
      actions={
        <Link
          to="/activities"
          className="inline-flex items-center gap-0.5 rounded-lg text-xs font-medium text-ink-2 hover:text-ink"
        >
          All activities <ChevronRight size={14} aria-hidden />
        </Link>
      }
      className={clsx("flex flex-col", className)}
      bodyClassName="flex flex-1 flex-col gap-4"
    >
      {items.length === 0 ? (
        <EmptyState title="No activities yet" />
      ) : (
        <ul className="-mx-2 flex flex-col">
          {items.map((a) => (
            <li key={a.activity_id}>
              <Link
                to="/activities/$activityId"
                params={{ activityId: String(a.activity_id) }}
                className="flex items-center gap-3 rounded-xl px-2 py-2.5 hover:bg-surface-2"
              >
                <SportBadge group={a.sport_group} size={36} />
                <div className="min-w-0 flex-1">
                  <p className="truncate text-sm font-medium text-ink">
                    {a.name ?? sportLabel(a.sport_group)}
                  </p>
                  <p className="truncate text-xs text-ink-3">
                    {fmtDate(a.start_time_local, {
                      weekday: "short",
                      day: "numeric",
                      month: "short",
                    })}{" "}
                    · {fmtLocalTime(a.start_time_local)}
                    {a.training_effect_label ? ` · ${teLabel(a.training_effect_label)}` : ""}
                  </p>
                </div>
                <div className="shrink-0 text-right tabular">
                  <p className="text-sm font-medium text-ink">
                    {a.distance_m ? fmtDistance(a.distance_m, units) : fmtHours(a.duration_s)}
                  </p>
                  <p className="text-xs text-ink-3">
                    {a.distance_m ? fmtHours(a.moving_s ?? a.duration_s) : DASH}
                    {a.training_load ? ` · load ${fmtNumber(a.training_load)}` : ""}
                  </p>
                </div>
              </Link>
            </li>
          ))}
        </ul>
      )}
      <div className="mt-auto">
        <StreakStrip streak={streak} />
      </div>
    </Card>
  );
}
