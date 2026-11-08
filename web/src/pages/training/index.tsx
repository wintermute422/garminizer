import { api, type Schemas } from "@/api/client";
import {
  Delta,
  ErrorState,
  PageHeader,
  Skeleton,
  Sparkline,
  StatTile,
  StatusPill,
} from "@/components/ui";
import { fmtDate, fmtNumber, signed } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { addDays, useRange } from "@/lib/range";
import { sportLabel } from "@/lib/sports";
import { CATEGORICAL, DIVERGING } from "@/lib/tokens";
import { AcwrCard, FocusCard, PmcCard, StatusCard } from "./LoadCharts";
import { acwrZone, formZone, useWide } from "./util";
import { EffectsCard, IntensityCard, VolumeCard } from "./VolumeCharts";

type LoadPoint = Schemas["TrainingLoadPoint"];

function Trend({ values, color, label }: { values: number[]; color: string; label: string }) {
  return <Sparkline values={values} color={color} label={label} />;
}

/** Fitness, fatigue, form (28-day change) and ACWR with its zone. */
function LoadTiles({ data }: { data: LoadPoint[] }) {
  const mode = useMode();
  const wide = useWide();
  const last = data[data.length - 1];
  if (!last) return null;
  const ref = data.find((d) => d.day === addDays(last.day, -28));
  const cat = CATEGORICAL[mode];
  const acwrPoint = [...data].reverse().find((d) => d.acwr !== null);
  const acwr = acwrPoint?.acwr ?? null;
  const zone = acwr !== null ? acwrZone(acwr) : null;
  const change = (now: number, then: number | undefined, direction: "up-good" | "neutral") =>
    then === undefined ? undefined : (
      <Delta value={now - then} text={`${signed(now - then, 1)} in 28 d`} direction={direction} />
    );
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatTile
        label="Fitness (CTL)"
        value={fmtNumber(last.ctl)}
        delta={change(last.ctl, ref?.ctl, "up-good")}
        trend={
          wide ? (
            <Trend values={data.map((d) => d.ctl)} color={cat[0]!} label="Fitness trend" />
          ) : undefined
        }
      />
      <StatTile
        label="Fatigue (ATL)"
        value={fmtNumber(last.atl)}
        delta={change(last.atl, ref?.atl, "neutral")}
        trend={
          wide ? (
            <Trend values={data.map((d) => d.atl)} color={cat[1]!} label="Fatigue trend" />
          ) : undefined
        }
      />
      <StatTile
        label="Form (TSB)"
        value={signed(last.tsb)}
        delta={change(last.tsb, ref?.tsb, "neutral")}
        sub={formZone(last.tsb)}
        trend={
          wide ? (
            <Trend
              values={data.map((d) => d.tsb)}
              color={last.tsb >= 0 ? DIVERGING[mode].negative : DIVERGING[mode].positive}
              label="Form trend"
            />
          ) : undefined
        }
      />
      <StatTile
        label="Acute : chronic ratio"
        value={acwr !== null ? fmtNumber(acwr, 2) : "–"}
        sub={zone ? <StatusPill status={zone.status} label={zone.label} /> : undefined}
        trend={
          wide ? (
            <Trend
              values={data.filter((d) => d.acwr !== null).map((d) => d.acwr!)}
              color={cat[0]!}
              label="ACWR trend"
            />
          ) : undefined
        }
      />
    </div>
  );
}

export default function TrainingPage() {
  const range = useRange("90d");
  const sportQuery = range.sport
    ? { ...range.query, sport: range.sport }
    : { start: range.query.start, end: range.query.end };
  const load = api.useQuery(
    "get",
    "/api/training/load",
    { params: { query: range.query } },
    { enabled: range.ready, placeholderData: (prev) => prev },
  );
  const status = api.useQuery(
    "get",
    "/api/training/status",
    { params: { query: range.query } },
    { enabled: range.ready, placeholderData: (prev) => prev },
  );

  return (
    <>
      <PageHeader
        title="Training load"
        description={`Fitness, fatigue and form · ${fmtDate(range.start)} – ${fmtDate(range.end)}${
          range.sport
            ? ` · volume, intensity and effects for ${sportLabel(range.sport).toLowerCase()}`
            : ""
        }`}
      />
      <div className="flex flex-col gap-5">
        {load.isPending ? (
          <Skeleton height={104} />
        ) : load.error ? (
          <ErrorState error={load.error} />
        ) : (
          <LoadTiles data={load.data ?? []} />
        )}
        <div className="grid gap-5 lg:grid-cols-2">
          <PmcCard
            query={load}
            start={range.start}
            end={range.end}
            sportFiltered={range.sport !== null}
          />
          <StatusCard query={status} start={range.start} end={range.end} />
          <AcwrCard query={load} start={range.start} end={range.end} />
          <FocusCard query={status} />
          <VolumeCard query={sportQuery} ready={range.ready} />
          <IntensityCard query={sportQuery} ready={range.ready} />
          <EffectsCard query={sportQuery} ready={range.ready} />
        </div>
      </div>
    </>
  );
}
