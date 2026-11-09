import { Link } from "@tanstack/react-router";
import { clsx } from "clsx";
import { ArrowDown, ArrowUp, Search } from "lucide-react";
import { useMemo, useState } from "react";
import { api, type Schemas } from "@/api/client";
import { Card, EmptyState, ErrorState, PageHeader, ScrollArea, Skeleton } from "@/components/ui";
import {
  fmtDate,
  fmtDistance,
  fmtElevation,
  fmtHours,
  fmtLocalTime,
  fmtNumber,
  fmtPace,
  fmtSpeed,
  teLabel,
} from "@/lib/format";
import { useUnits } from "@/lib/preferences";
import { useRange } from "@/lib/range";
import { bySlot, sportLabel, usesPace } from "@/lib/sports";
import { SportBadge, SportIcon } from "@/components/SportIcon";

type Activity = Schemas["ActivitySummary"];
type SortKey = "start_time" | "distance" | "duration" | "load" | "elevation" | "avg_hr" | "pace";
const PAGE = 50;

function Totals() {
  const range = useRange("90d");
  const units = useUnits();
  const q = api.useQuery(
    "get",
    "/api/activities/totals",
    { params: { query: range.query } },
    { enabled: range.ready },
  );
  if (q.isPending) return <Skeleton height={92} />;
  if (q.error) return <ErrorState error={q.error} />;
  const rows = [...(q.data ?? [])].sort((a, b) => bySlot(a.sport_group, b.sport_group));
  if (!rows.length) return null;
  const all = rows.reduce(
    (acc, r) => ({
      n: acc.n + r.activities,
      d: acc.d + (r.distance_m ?? 0),
      t: acc.t + (r.moving_s ?? r.duration_s ?? 0),
      e: acc.e + (r.elevation_gain_m ?? 0),
    }),
    { n: 0, d: 0, t: 0, e: 0 },
  );
  return (
    <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
      <div className="rounded-card border border-line bg-surface p-4 shadow-card">
        <p className="text-xs font-medium text-ink-2">All activities</p>
        <p className="mt-2 text-metric font-semibold text-ink">{fmtNumber(all.n)}</p>
        <p className="mt-1.5 text-xs text-ink-3">
          {fmtHours(all.t)} · {fmtDistance(all.d, units, 0)}
        </p>
      </div>
      {rows.slice(0, 5).map((r) => {
        return (
          <div
            key={r.sport_group}
            className="rounded-card border border-line bg-surface p-4 shadow-card"
          >
            <p className="flex items-center gap-1.5 text-xs font-medium text-ink-2">
              <SportIcon group={r.sport_group} size={14} colored />
              {sportLabel(r.sport_group)}
            </p>
            <p className="mt-2 text-metric font-semibold text-ink">
              {r.distance_m ? fmtDistance(r.distance_m, units, 0) : fmtNumber(r.activities)}
            </p>
            <p className="mt-1.5 text-xs text-ink-3">
              {fmtNumber(r.activities)} × · {fmtHours(r.moving_s ?? r.duration_s)}
            </p>
          </div>
        );
      })}
    </div>
  );
}

function speedText(a: Activity, units: ReturnType<typeof useUnits>): string {
  if (!a.distance_m || !a.avg_speed_mps) return "–";
  return usesPace(a.sport_group)
    ? fmtPace(a.avg_speed_mps, units, a.sport_group === "swim")
    : fmtSpeed(a.avg_speed_mps, units);
}

const COLUMNS: { key: SortKey | null; label: string; className?: string }[] = [
  { key: "start_time", label: "Date" },
  { key: null, label: "Activity" },
  { key: "distance", label: "Distance", className: "text-right" },
  { key: "duration", label: "Time", className: "text-right" },
  { key: "pace", label: "Pace / speed", className: "text-right" },
  { key: "elevation", label: "Elevation", className: "text-right" },
  { key: "avg_hr", label: "Avg HR", className: "text-right" },
  { key: "load", label: "Load", className: "text-right" },
];

export default function ActivitiesPage() {
  const range = useRange("90d");
  const units = useUnits();
  const [sort, setSort] = useState<SortKey>("start_time");
  const [order, setOrder] = useState<"asc" | "desc">("desc");
  const [search, setSearch] = useState("");
  const [limit, setLimit] = useState(PAGE);
  const query = useMemo(
    () => ({
      ...range.query,
      sort,
      order,
      limit,
      ...(range.sport ? { sport: range.sport } : {}),
      ...(search.trim() ? { q: search.trim() } : {}),
    }),
    [range.query.start, range.query.end, range.sport, sort, order, limit, search], // eslint-disable-line react-hooks/exhaustive-deps
  );
  const list = api.useQuery(
    "get",
    "/api/activities",
    { params: { query } },
    { enabled: range.ready, placeholderData: (prev) => prev },
  );

  const toggleSort = (key: SortKey) => {
    if (key === sort) setOrder(order === "desc" ? "asc" : "desc");
    else {
      setSort(key);
      setOrder("desc");
    }
    setLimit(PAGE);
  };

  return (
    <>
      <PageHeader
        title="Activities"
        description={`${fmtDate(range.start)} – ${fmtDate(range.end)}${range.sport ? ` · ${sportLabel(range.sport)}` : ""}`}
      />
      <div className="flex flex-col gap-5">
        <Totals />
        <Card
          title="All activities"
          subtitle={list.data ? `${fmtNumber(list.data.total)} activities` : undefined}
          actions={
            <label className="relative">
              <span className="sr-only">Search by name</span>
              <Search
                size={15}
                className="pointer-events-none absolute top-1/2 left-2.5 -translate-y-1/2 text-ink-3"
                aria-hidden
              />
              <input
                type="search"
                placeholder="Search by name"
                value={search}
                onChange={(e) => {
                  setSearch(e.target.value);
                  setLimit(PAGE);
                }}
                className="w-56 rounded-control border border-line bg-surface-2 py-1.5 pr-3 pl-8 text-sm text-ink placeholder:text-ink-3"
              />
            </label>
          }
        >
          {list.error ? (
            <ErrorState error={list.error} />
          ) : !list.data ? (
            <Skeleton height={420} />
          ) : list.data.items.length === 0 ? (
            <EmptyState title="No activities match these filters" />
          ) : (
            <>
              {/* Desktop table */}
              <ScrollArea
                label="Activities table"
                className="-mx-4 hidden overflow-x-auto sm:-mx-5 md:block"
              >
                <table className="w-full min-w-[860px] text-sm">
                  <thead>
                    <tr className="border-b border-line text-xs text-ink-3">
                      {COLUMNS.map((c) => (
                        <th
                          key={c.label}
                          scope="col"
                          className={clsx(
                            "px-3 py-2 font-medium first:pl-5 last:pr-5",
                            c.className ?? "text-left",
                          )}
                        >
                          {c.key ? (
                            <button
                              type="button"
                              onClick={() => toggleSort(c.key!)}
                              className={clsx(
                                "inline-flex items-center gap-1 hover:text-ink",
                                sort === c.key && "text-ink",
                              )}
                              aria-label={`Sort by ${c.label}`}
                            >
                              {c.label}
                              {sort === c.key &&
                                (order === "desc" ? (
                                  <ArrowDown size={12} />
                                ) : (
                                  <ArrowUp size={12} />
                                ))}
                            </button>
                          ) : (
                            c.label
                          )}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody className="tabular">
                    {list.data.items.map((a) => (
                      <tr
                        key={a.activity_id}
                        className="border-b border-line last:border-0 hover:bg-hover"
                      >
                        <td className="px-3 py-2.5 pl-5 whitespace-nowrap text-ink-2">
                          {fmtDate(a.start_time_local, {
                            day: "numeric",
                            month: "short",
                            year: "numeric",
                          })}
                          <span className="ml-1.5 text-xs text-ink-3">
                            {fmtLocalTime(a.start_time_local)}
                          </span>
                        </td>
                        <td className="px-3 py-2">
                          <Link
                            to="/activities/$activityId"
                            params={{ activityId: String(a.activity_id) }}
                            className="flex items-center gap-2.5 font-medium text-ink hover:text-accent"
                          >
                            <SportBadge group={a.sport_group} />
                            <span className="min-w-0">
                              <span className="block truncate">
                                {a.name ?? sportLabel(a.sport_group)}
                              </span>
                              {a.training_effect_label && (
                                <span className="block text-xs font-normal text-ink-3">
                                  {teLabel(a.training_effect_label)}
                                </span>
                              )}
                            </span>
                          </Link>
                        </td>
                        <td className="px-3 py-2.5 text-right text-ink">
                          {a.distance_m ? fmtDistance(a.distance_m, units) : "–"}
                        </td>
                        <td className="px-3 py-2.5 text-right text-ink">
                          {fmtHours(a.moving_s ?? a.duration_s)}
                        </td>
                        <td className="px-3 py-2.5 text-right text-ink-2">{speedText(a, units)}</td>
                        <td className="px-3 py-2.5 text-right text-ink-2">
                          {a.elevation_gain_m ? fmtElevation(a.elevation_gain_m, units) : "–"}
                        </td>
                        <td className="px-3 py-2.5 text-right text-ink-2">{a.avg_hr ?? "–"}</td>
                        <td className="px-3 py-2.5 pr-5 text-right text-ink-2">
                          {fmtNumber(a.training_load)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </ScrollArea>
              {/* Mobile cards */}
              <ul className="flex flex-col divide-y divide-line md:hidden">
                {list.data.items.map((a) => (
                  <li key={a.activity_id}>
                    <Link
                      to="/activities/$activityId"
                      params={{ activityId: String(a.activity_id) }}
                      className="flex items-center gap-3 py-3"
                    >
                      <SportBadge group={a.sport_group} />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink">
                          {a.name ?? sportLabel(a.sport_group)}
                        </p>
                        <p className="text-xs text-ink-3">
                          {fmtDate(a.start_time_local, { day: "numeric", month: "short" })} ·{" "}
                          {fmtHours(a.moving_s ?? a.duration_s)}
                          {a.distance_m ? ` · ${fmtDistance(a.distance_m, units)}` : ""}
                        </p>
                      </div>
                      <span className="text-xs text-ink-2 tabular">{speedText(a, units)}</span>
                    </Link>
                  </li>
                ))}
              </ul>
              {list.data.items.length < list.data.total && (
                <div className="mt-4 flex justify-center">
                  <button
                    type="button"
                    onClick={() => setLimit((l) => l + PAGE)}
                    className="rounded-control border border-line px-4 py-2 text-sm font-medium text-ink-2 hover:bg-hover hover:text-ink"
                  >
                    Show more ({fmtNumber(list.data.total - list.data.items.length)} left)
                  </button>
                </div>
              )}
            </>
          )}
        </Card>
      </div>
    </>
  );
}
