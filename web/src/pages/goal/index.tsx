import { Droplets, Dumbbell, Flag, Percent, Scale, Target, TrendingDown, Zap } from "lucide-react";
import { useMemo } from "react";
import { api, type Schemas } from "@/api/client";
import { Chart } from "@/components/Chart";
import {
  Card,
  EmptyState,
  LegendItem,
  PageHeader,
  QueryState,
  StatTile,
  StatusPill,
} from "@/components/ui";
import { dayExtent } from "@/lib/charts";
import { DASH, fmtDate, fmtNumber, fmtShortDate, signed } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { DIVERGING } from "@/lib/tokens";
import { balanceOption, fatOption, goalColors, trendOption } from "./charts";
import { CheckpointList } from "./Checkpoints";
import { DailyLog } from "./DailyLog";
import { fmtRate, kg, maxDay, WEEKDAYS } from "./goal";
import { SettingsForm } from "./Settings";

type View = Schemas["GoalView"];
type Settings = Schemas["GoalSettings"];

const TILE_GRID = "grid grid-cols-2 gap-3 md:grid-cols-4";

function description(s: Settings | null): string {
  const weekday = WEEKDAYS[s?.checkpoint_weekday ?? 6] ?? "Sunday";
  const n = s?.trend_weights?.length ?? 3;
  return `Weighted ${n}-day trend against a target line that falls by the planned rate; checkpoints every ${weekday}.`;
}

function Summary({ v, s }: { v: View; s: Settings }) {
  const accepted = s.accepted_checkpoints?.length ?? 0;
  const left = v.status?.days_left;
  return (
    <span className="mt-1 block text-ink-3 tabular">
      Start {kg(s.start_weight_kg)} on {fmtDate(s.start_day)} · {fmtRate(s.rate_kg_per_week)} ·
      until {fmtDate(s.end_day)}
      {left != null && left > 0 ? ` (${left} days left)` : ""} · {accepted}{" "}
      {accepted === 1 ? "checkpoint" : "checkpoints"} counted as reached by hand
    </span>
  );
}

function Tiles({ v }: { v: View }) {
  const st = v.status;
  if (!st) return null;
  const w = st.week;
  const asOf = st.as_of ? `as of ${fmtShortDate(st.as_of)}` : "no weigh-in yet";
  return (
    <div className={TILE_GRID}>
      <StatTile
        icon={<Scale size={15} aria-hidden />}
        label="Trend"
        value={fmtNumber(st.trend_kg, 2)}
        unit="kg"
        sub={asOf}
      />
      <StatTile
        icon={<Target size={15} aria-hidden />}
        label="Target today"
        value={fmtNumber(st.target_today_kg, 2)}
        unit="kg"
        sub={st.target_end_kg != null ? `${kg(st.target_end_kg, 2)} at the end` : undefined}
      />
      <StatTile
        icon={<Flag size={15} aria-hidden />}
        label="Deviation"
        value={st.delta_kg == null ? DASH : signed(st.delta_kg, 2)}
        unit="kg"
        delta={
          st.on_plan == null ? null : (
            <StatusPill
              status={st.on_plan ? "good" : "warning"}
              label={st.on_plan ? "On plan" : "Above target"}
            />
          )
        }
        sub={st.as_of ? `trend − target, ${fmtShortDate(st.as_of)}` : undefined}
      />
      <StatTile
        icon={<TrendingDown size={15} aria-hidden />}
        label="Since start"
        value={st.since_start_kg == null ? DASH : signed(st.since_start_kg, 2)}
        unit="kg"
        sub={v.settings ? `from ${kg(v.settings.start_weight_kg)}` : undefined}
      />
      <StatTile
        icon={<Percent size={15} aria-hidden />}
        label="Body fat"
        value={fmtNumber(st.body_fat_pct, 1)}
        unit="%"
        sub={st.body_fat_day ? `weigh-in ${fmtShortDate(st.body_fat_day)}` : "no reading"}
      />
      <StatTile
        icon={<Dumbbell size={15} aria-hidden />}
        label="Muscle mass"
        value={fmtNumber(st.muscle_mass_kg, 1)}
        unit="kg"
        sub={st.body_fat_day ? `weigh-in ${fmtShortDate(st.body_fat_day)}` : undefined}
      />
      <StatTile
        icon={<Droplets size={15} aria-hidden />}
        label="Body water"
        value={fmtNumber(st.body_water_pct, 1)}
        unit="%"
        sub={st.body_fat_day ? `weigh-in ${fmtShortDate(st.body_fat_day)}` : undefined}
      />
      <StatTile
        icon={<Zap size={15} aria-hidden />}
        label="Balance, 7 days"
        value={w.balance_kcal == null ? DASH : signed(w.balance_kcal)}
        unit="kcal"
        sub={
          w.days_logged === 0
            ? "no meals logged in the last 7 days"
            : `target ${signed(w.target_balance_kcal)} · ${w.days_logged} ${
                w.days_logged === 1 ? "day" : "days"
              } logged`
        }
      />
    </div>
  );
}

function GoalBody({ v }: { v: View }) {
  const mode = useMode();
  const s = v.settings!;
  const built = useMemo(() => {
    const today = v.today;
    const plan = dayExtent(s.start_day, maxDay(s.end_day, today));
    const sofar = dayExtent(s.start_day, maxDay(s.start_day, today));
    return {
      trend: trendOption(v, plan, mode),
      fat: v.body_fat.length ? fatOption(v, sofar, mode) : null,
      balance: v.days.some((d) => d.meals > 0 && d.balance_kcal != null)
        ? balanceOption(v, sofar, mode)
        : null,
    };
  }, [v, s, mode]);
  const c = goalColors(mode);
  const d = DIVERGING[mode];
  const reg = v.body_fat_regression;
  return (
    <div className="flex flex-col gap-5">
      <Tiles v={v} />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          title="Trend vs target"
          subtitle="kg; weigh-ins, weighted trend and the target line with its checkpoints"
          className="lg:col-span-2"
        >
          <Chart
            option={built.trend}
            zoom
            height={300}
            ariaLabel="Weight trend against the target line of the weight goal"
          />
        </Card>
        <Card
          title="Body fat"
          subtitle={
            reg
              ? `Readings, trend and the regression of the last weeks: ${signed(reg.slope_pct_per_week, 2)} percentage points per week`
              : "Readings and trend (%)"
          }
        >
          {built.fat ? (
            <Chart
              option={built.fat}
              height={240}
              ariaLabel="Body fat readings with trend and regression line"
            />
          ) : (
            <EmptyState title="No body-fat readings since the start">
              Body fat needs a body-composition scale such as the Garmin Index S2.
            </EmptyState>
          )}
        </Card>
        <Card
          title="Energy balance"
          subtitle={
            v.target_daily_balance_kcal != null
              ? `Eaten minus burn per logged day; the goal needs ${signed(v.target_daily_balance_kcal)} kcal a day`
              : "Eaten minus burn per logged day"
          }
        >
          {built.balance ? (
            <>
              <div className="mb-2 flex flex-wrap gap-4">
                <LegendItem color={d.negative} label="Deficit" />
                <LegendItem color={d.positive} label="Surplus" />
                <LegendItem
                  color={c.target}
                  label={`Daily target ${signed(v.target_daily_balance_kcal)} kcal`}
                  shape="line"
                />
              </div>
              <Chart
                option={built.balance}
                height={212}
                ariaLabel="Daily energy balance against the goal's daily target"
              />
            </>
          ) : (
            <EmptyState title="No meals logged since the start">
              Log meals through Claude Desktop to see the daily balance against the goal.
            </EmptyState>
          )}
        </Card>
        <Card
          title="Checkpoints"
          subtitle={`Every ${WEEKDAYS[s.checkpoint_weekday] ?? "Sunday"}: is the trend below the target? (kg)`}
          className="lg:col-span-2"
        >
          <CheckpointList checkpoints={v.checkpoints} />
        </Card>
        <Card
          title="Daily log"
          subtitle="Every day of the goal, newest first. Burn = BMR × activity factor + active training kcal"
          className="lg:col-span-2"
        >
          <DailyLog days={v.days} />
        </Card>
        <Card
          title="Settings"
          subtitle="The goal and the inputs of the energy model"
          className="lg:col-span-2"
        >
          <SettingsForm
            key={JSON.stringify(s)}
            settings={s}
            profile={v.profile}
            bmr={v.bmr_today}
            today={v.today}
          />
        </Card>
      </div>
    </div>
  );
}

function Setup({ v }: { v: View }) {
  return (
    <Card title="Set up a weight goal" subtitle="No weight goal yet">
      <p className="mb-5 max-w-2xl text-sm text-ink-2">
        Pick a start weight and a weekly rate: the page then follows your weighted weight trend
        against a target line, checks it every week and adds up the energy balance from your logged
        meals. You can also ask Claude Desktop to set it (tool{" "}
        <code className="rounded-chip bg-surface-2 px-1 text-ink">set_weight_goal</code>).
      </p>
      <SettingsForm settings={null} profile={v.profile} bmr={v.bmr_today} today={v.today} />
    </Card>
  );
}

export default function GoalPage() {
  const q = api.useQuery("get", "/api/goal");
  const v = q.data;
  return (
    <>
      <PageHeader
        title="Weight goal"
        description={
          <>
            {description(v?.settings ?? null)}
            {v?.configured && v.settings && <Summary v={v} s={v.settings} />}
          </>
        }
      />
      <QueryState query={q} height={420}>
        {(data) => (data.configured && data.settings ? <GoalBody v={data} /> : <Setup v={data} />)}
      </QueryState>
    </>
  );
}
