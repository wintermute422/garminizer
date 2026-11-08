import { useMemo } from "react";
import { api, type Schemas } from "@/api/client";
import { Delta, ErrorState, PageHeader, Skeleton, Sparkline, StatTile } from "@/components/ui";
import { DASH, fmtDate, fmtDelta, fmtNumber } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { useRange } from "@/lib/range";
import { sportColor } from "@/lib/sports";
import {
  EfficiencyCard,
  EnduranceCard,
  FitnessAgeCard,
  HillCard,
  RaceCard,
  Vo2Card,
} from "./Charts";
import { ageOn, firstLast, sentenceCase } from "./util";

type Series = Schemas["PerformanceSeries"];

function trend(values: number[], color: string, label: string) {
  return values.length < 2 ? undefined : <Sparkline values={values} color={color} label={label} />;
}

function change<T>(
  rows: T[],
  get: (r: T) => number | null | undefined,
  digits: number,
  direction: "up-good" | "down-good",
) {
  const fl = firstLast(rows, get);
  if (!fl || fl.firstRow === undefined) return { delta: undefined, since: undefined };
  const d = Math.round((fl.last - fl.first) * 10 ** digits) / 10 ** digits;
  return {
    delta: <Delta value={d} text={fmtDelta(d, digits)} direction={direction} />,
    since: "this period",
  };
}

function Tiles({ s, age }: { s: Series; age: number | null }) {
  const mode = useMode();
  const l = s.latest;
  const run = change(s.vo2max, (d) => d.running, 1, "up-good");
  const ride = change(s.vo2max, (d) => d.cycling, 1, "up-good");
  const fit = change(s.fitness_age, (d) => d.value, 1, "down-good");
  const end = change(s.endurance, (d) => d.score, 0, "up-good");
  const hill = change(s.hill, (d) => d.score, 0, "up-good");
  const hillLast = [...s.hill].reverse().find((d) => d.endurance !== null || d.strength !== null);
  const younger = age !== null && l.fitness_age !== null ? age - l.fitness_age : null;
  const values = <T,>(rows: T[], get: (r: T) => number | null) =>
    rows.map(get).filter((v): v is number => v !== null);
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
      <StatTile
        label="VO2max running"
        value={fmtNumber(l.vo2max_running, 1)}
        delta={run.delta}

        trend={trend(
          values(s.vo2max, (d) => d.running),
          sportColor("run", mode),
          "VO2max running trend",
        )}
      />
      <StatTile
        label="VO2max cycling"
        value={fmtNumber(l.vo2max_cycling, 1)}
        delta={ride.delta}

        trend={trend(
          values(s.vo2max, (d) => d.cycling),
          sportColor("ride", mode),
          "VO2max cycling trend",
        )}
      />
      <StatTile
        label="Fitness age"
        value={fmtNumber(l.fitness_age, 1)}
        unit="yrs"
        delta={fit.delta}
        sub={
          younger !== null
            ? younger >= 0
              ? `${fmtNumber(younger, 1)} yrs younger than you`
              : `${fmtNumber(-younger, 1)} yrs older than you`
            : fit.since
        }
      />
      <StatTile
        label="Endurance score"
        value={fmtNumber(l.endurance_score)}
        delta={end.delta}
        sub={l.endurance_class ? sentenceCase(l.endurance_class) : undefined}
      />
      <StatTile
        className="col-span-2 md:col-span-1"
        label="Hill score"
        value={fmtNumber(l.hill_score)}
        delta={hill.delta}
        sub={
          hillLast
            ? `endurance ${fmtNumber(hillLast.endurance)} · strength ${fmtNumber(hillLast.strength)}`
            : undefined
        }
      />
    </div>
  );
}

export default function PerformancePage() {
  const range = useRange("90d");
  const meta = api.useQuery("get", "/api/meta");
  const perf = api.useQuery(
    "get",
    "/api/performance",
    { params: { query: range.query } },
    { enabled: range.ready, placeholderData: (prev) => prev },
  );
  const eff = api.useQuery(
    "get",
    "/api/performance/efficiency",
    { params: { query: { ...range.query, sport: "run" } } },
    { enabled: range.ready, placeholderData: (prev) => prev },
  );
  const distances = api.useQuery("get", "/api/records/distances", {
    params: { query: { sport: "run" } },
  });
  const bests = useMemo(
    () =>
      new Map(
        (distances.data ?? [])
          .filter((d) => d.best !== null)
          .map((d) => [d.distance_m, d.best!.seconds]),
      ),
    [distances.data],
  );
  const birth = meta.data?.athlete?.birth_date ?? null;
  const age = birth ? ageOn(birth, range.end) : null;

  return (
    <>
      <PageHeader
        title="Performance"
        description={`VO2max, race predictions and efficiency · ${fmtDate(range.start)} – ${fmtDate(range.end)}`}
      />
      {perf.isPending ? (
        <div className="flex flex-col gap-5">
          <Skeleton height={104} />
          <Skeleton height={320} />
        </div>
      ) : perf.error ? (
        <ErrorState error={perf.error} />
      ) : perf.data ? (
        <div className="flex flex-col gap-5">
          <Tiles s={perf.data} age={age} />
          <div className="grid gap-5 lg:grid-cols-2">
            <Vo2Card data={perf.data.vo2max} />
            <EnduranceCard data={perf.data.endurance} />
            <RaceCard data={perf.data.race_predictions} latest={perf.data.latest} bests={bests} />
            <HillCard data={perf.data.hill} />
            <FitnessAgeCard data={perf.data.fitness_age} age={age} />
            {eff.isPending ? (
              <Skeleton height={320} className="lg:col-span-2" />
            ) : eff.error ? (
              <ErrorState error={eff.error} />
            ) : (
              <EfficiencyCard data={eff.data ?? []} />
            )}
          </div>
        </div>
      ) : (
        <p className="text-sm text-ink-3">{DASH}</p>
      )}
    </>
  );
}
