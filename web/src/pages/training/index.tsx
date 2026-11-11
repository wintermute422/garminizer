import { CircleCheck } from "lucide-react";
import { api, type Schemas } from "@/api/client";
import { usePageFilters } from "@/app/pageFilters";
import { Delta, ErrorState, PageHeader, Skeleton, Sparkline, StatTile } from "@/components/ui";
import { DASH, fmtDate, fmtDelta, fmtNumber, signed } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { addDays } from "@/lib/range";
import { sportLabel } from "@/lib/sports";
import { CATEGORICAL, DIVERGING, MEASURE_COLORS, STATUS } from "@/lib/tokens";
import { acwrState } from "@/lib/status";
import { AcwrCard, FocusCard, PmcCard, StatusCard } from "./LoadCharts";
import { formZone } from "./util";
import { EffectsCard, IntensityCard, VolumeCard } from "./VolumeCharts";

type LoadPoint = Schemas["TrainingLoadPoint"];
type StatusPoint = Schemas["TrainingStatusPoint"];

/** Fitness, fatigue, form (28-day change) and Garmin's acute:chronic ratio. */
function LoadTiles({ data, status }: { data: LoadPoint[]; status: StatusPoint[] }) {
  const mode = useMode();
  const last = data[data.length - 1];
  if (!last) return null;
  const ref = data.find((d) => d.day === addDays(last.day, -28));
  const m = MEASURE_COLORS[mode];
  // Same value and wording as the Overview: Garmin's own ratio from the training status.
  const garmin = [...status].reverse().find((d) => d.acwr !== null);
  const acwr = garmin ? acwrState(garmin.acwr_status) : null;
  const change = (now: number, then: number | undefined, direction: "up-good" | "neutral") => {
    if (then === undefined) return undefined;
    const d = Math.round((now - then) * 10) / 10;
    return <Delta value={d} text={`${fmtDelta(d, 1)} in 28 days`} direction={direction} />;
  };
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatTile
        label="Fitness (CTL)"
        value={fmtNumber(last.ctl)}
        delta={change(last.ctl, ref?.ctl, "up-good")}
        trend={
          <Sparkline values={data.map((d) => d.ctl)} color={m.fitness} label="Fitness trend" />
        }
      />
      <StatTile
        label="Fatigue (ATL)"
        value={fmtNumber(last.atl)}
        delta={change(last.atl, ref?.atl, "neutral")}
        trend={
          <Sparkline values={data.map((d) => d.atl)} color={m.fatigue} label="Fatigue trend" />
        }
      />
      <StatTile
        label="Form (TSB)"
        value={signed(last.tsb)}
        unit={formZone(last.tsb).toLowerCase()}
        delta={change(last.tsb, ref?.tsb, "neutral")}
        trend={
          <Sparkline
            values={data.map((d) => d.tsb)}
            color={last.tsb >= 0 ? DIVERGING[mode].negative : DIVERGING[mode].positive}
            label="Form trend"
          />
        }
      />
      <StatTile
        label="Acute : chronic (Garmin)"
        value={garmin?.acwr != null ? fmtNumber(garmin.acwr, 2) : DASH}
        sub={
          garmin?.acwr_status && acwr ? (
            <span className="inline-flex items-center gap-1">
              {acwr.status === "good" && <CircleCheck size={12} color={STATUS.good} aria-hidden />}
              {acwr.label}
            </span>
          ) : garmin ? (
            fmtDate(garmin.day)
          ) : undefined
        }
        trend={
          <Sparkline
            values={status.filter((d) => d.acwr !== null).map((d) => d.acwr!)}
            color={CATEGORICAL[mode][0]!}
            label="Garmin acute to chronic ratio trend"
          />
        }
      />
    </div>
  );
}

export default function TrainingPage() {
  const range = usePageFilters();
  const load = api.useQuery(
    "get",
    "/api/training/load",
    { params: { query: range.dates } },
    range.options,
  );
  const status = api.useQuery(
    "get",
    "/api/training/status",
    { params: { query: range.dates } },
    range.options,
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
        {load.isPending || status.isPending ? (
          <Skeleton height={104} />
        ) : load.error ? (
          <ErrorState error={load.error} />
        ) : (
          <LoadTiles data={load.data ?? []} status={status.data ?? []} />
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
          <VolumeCard />
          <IntensityCard />
          <EffectsCard />
        </div>
      </div>
    </>
  );
}
