import { api, type Schemas } from "@/api/client";
import { usePageFilters } from "@/app/pageFilters";
import { Delta, PageHeader, QueryState, Skeleton, StatTile } from "@/components/ui";
import {
  distanceUnit,
  fmtDistance,
  fmtDuration,
  fmtMonth,
  fmtPace,
  fmtSpeed,
  signed,
} from "@/lib/format";
import { useUnits } from "@/lib/preferences";
import { sportLabel, usesPace } from "@/lib/sports";
import { CumulativeCard, CurveCard } from "./Curves";
import { DistancesCard, PersonalCard, TopCard } from "./Lists";
import { doyDate } from "./util";

type Distance = Schemas["RecordsDistance"];
type Cumulative = Schemas["RecordsCumulative"];

const HEADLINE = [5000, 10000, 21097.5, 42195, 1000, 1609.344, 400, 15000, 30000];

function Tiles({
  sport,
  distances,
  cumulative,
}: {
  sport: string;
  distances: Distance[];
  cumulative: Cumulative | undefined;
}) {
  const units = useUnits();
  const years = [...(cumulative?.years ?? [])].sort((a, b) => a.year - b.year);
  const current = years[years.length - 1];
  const last = current?.points[current.points.length - 1];
  const prev = years.find((y) => current && y.year === current.year - 1);
  const prevSame = last ? prev?.points.find((p) => p.day_of_year === last.day_of_year) : undefined;
  const pct =
    last && prevSame && prevSame.value > 0 ? (last.value / prevSame.value - 1) * 100 : null;
  const bests = HEADLINE.map((d) => distances.find((r) => r.distance_m === d && r.best))
    .filter((r): r is Distance => r !== undefined)
    .slice(0, current ? 3 : 4);
  const pace = (r: Distance) => {
    const mps = r.distance_m / r.best!.seconds;
    return usesPace(sport) ? fmtPace(mps, units, sport === "swim") : fmtSpeed(mps, units);
  };
  if (!current && !bests.length) return null;
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      {current && last && (
        <StatTile
          label={`${current.year} so far`}
          value={fmtDistance(last.value, units, 0).split(" ")[0]}
          unit={distanceUnit(units)}
          delta={
            pct !== null && prev ? (
              <Delta value={pct} text={`${signed(pct, 0, " %")} vs ${prev.year}`} />
            ) : undefined
          }
          sub={`by ${doyDate(current.year, last.day_of_year)}`}
        />
      )}
      {bests.map((r) => (
        <StatTile
          key={r.distance_m}
          label={`Best ${/^\d/.test(r.label) ? r.label : r.label.toLowerCase()}`}
          value={fmtDuration(r.best!.seconds)}
          sub={`${pace(r)} · ${fmtMonth(r.best!.day)}`}
        />
      ))}
      {/* Sports without standard-distance bests: fill the row with distance totals instead. */}
      {current && bests.length < 2 && prev && (
        <StatTile
          label={`${prev.year} total`}
          value={fmtDistance(prev.total, units, 0).split(" ")[0]}
          unit={distanceUnit(units)}
          sub="whole calendar year"
        />
      )}
      {current && bests.length < 1 && years.length > 1 && (
        <StatTile
          label="All time"
          value={
            fmtDistance(
              years.reduce((s, y) => s + y.total, 0),
              units,
              0,
            ).split(" ")[0]
          }
          unit={distanceUnit(units)}
          sub={`since ${years[0]!.year}`}
        />
      )}
    </div>
  );
}

export default function RecordsPage() {
  // Records always show one sport: nav.ts gives the page a default (run).
  const sport = usePageFilters().sport!;
  const meta = api.useQuery("get", "/api/meta");
  const distances = api.useQuery(
    "get",
    "/api/records/distances",
    { params: { query: { sport } } },
    { placeholderData: (prev) => prev },
  );
  const cumulative = api.useQuery(
    "get",
    "/api/records/cumulative",
    { params: { query: { sport, metric: "distance" } } },
    { placeholderData: (prev) => prev },
  );
  const lastDay = meta.data?.last_day ?? null;

  return (
    <>
      <PageHeader
        title="Records"
        description={`All-time bests, year-over-year totals and Garmin's personal records for ${sportLabel(sport).toLowerCase()}`}
      />
      <div className="flex flex-col gap-5">
        {/* Both feed the tiles: an error in either is shown (cumulative's used to be dropped). */}
        <QueryState queries={[distances, cumulative]} height={104}>
          {([d, c]) => <Tiles sport={sport} distances={d} cumulative={c} />}
        </QueryState>
        <div className="grid gap-5 lg:grid-cols-2">
          <CurveCard sport={sport} />
          <QueryState
            query={distances}
            skeleton={<Skeleton height={360} className="lg:col-span-2" />}
          >
            {(rows) => <DistancesCard rows={rows} sport={sport} lastDay={lastDay} />}
          </QueryState>
          <CumulativeCard sport={sport} />
          <TopCard sport={sport} />
          <PersonalCard />
        </div>
      </div>
    </>
  );
}
