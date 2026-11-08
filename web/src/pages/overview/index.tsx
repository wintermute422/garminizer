/**
 * Overview ("Today"): one day at a glance — readiness and recovery first, then training,
 * then the week. Defaults to the last day with data; the arrows step through earlier days.
 */
import { clsx } from "clsx";
import { ChevronLeft, ChevronRight } from "lucide-react";
import { useState } from "react";
import { api } from "@/api/client";
import { ErrorState, PageHeader, Skeleton } from "@/components/ui";
import { fmtDate } from "@/lib/format";
import { addDays } from "@/lib/range";
import { RecentCard, WeekCard } from "./activity";
import {
  BodyBatteryCard,
  GoalsCard,
  HrvCard,
  ReadinessCard,
  RestingHrCard,
  SleepCard,
  StressCard,
} from "./recovery";
import { validZone } from "./time";
import { FitnessCard, PerformanceCard, TrainingStatusCard } from "./training";

const STEP =
  "inline-flex items-center justify-center rounded-xl border border-line bg-surface p-2 text-ink-2 shadow-card hover:text-ink disabled:pointer-events-none disabled:opacity-40";

/** Placeholder layout matching the dashboard grid (static class names for Tailwind). */
const SKELETON_SPANS = [
  "xl:col-span-4",
  "xl:col-span-4",
  "lg:col-span-2 xl:col-span-4",
  "xl:col-span-3",
  "xl:col-span-3",
  "xl:col-span-3",
  "xl:col-span-3",
  "lg:col-span-2 xl:col-span-5",
  "xl:col-span-4",
  "xl:col-span-3",
];

function LoadingGrid() {
  return (
    <div className="grid gap-5 lg:grid-cols-2 xl:grid-cols-12">
      {SKELETON_SPANS.map((span, i) => (
        <Skeleton key={i} height={i < 3 ? 250 : 190} className={span} />
      ))}
    </div>
  );
}

export default function OverviewPage() {
  const meta = api.useQuery("get", "/api/meta");
  const [day, setDay] = useState<string | null>(null);
  const q = api.useQuery(
    "get",
    "/api/overview",
    { params: { query: day ? { day } : {} } },
    { placeholderData: (prev) => prev },
  );
  const d = q.data;
  const tz = validZone(meta.data?.athlete?.time_zone);
  const last = meta.data?.last_day ?? null;
  const first = meta.data?.first_day ?? null;
  const isLatest = !!d && (!last || d.day >= last);

  return (
    <>
      <PageHeader
        title="Today"
        description={
          d
            ? `${fmtDate(d.day, { weekday: "long", day: "numeric", month: "long", year: "numeric" })}${isLatest ? " · latest synced day" : ""}`
            : "Your day at a glance."
        }
      >
        {d && (
          <div className="flex items-center gap-1.5">
            {!isLatest && (
              <button
                type="button"
                onClick={() => setDay(null)}
                className="rounded-xl px-3 py-1.5 text-sm font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
              >
                Latest
              </button>
            )}
            <button
              type="button"
              aria-label="Previous day"
              className={STEP}
              disabled={!!first && d.day <= first}
              onClick={() => setDay(addDays(d.day, -1))}
            >
              <ChevronLeft size={16} aria-hidden />
            </button>
            <button
              type="button"
              aria-label="Next day"
              className={STEP}
              disabled={isLatest}
              onClick={() => setDay(addDays(d.day, 1))}
            >
              <ChevronRight size={16} aria-hidden />
            </button>
          </div>
        )}
      </PageHeader>
      {q.error ? (
        <ErrorState error={q.error} />
      ) : !d ? (
        <LoadingGrid />
      ) : (
        <div
          className={clsx(
            "grid gap-5 transition-opacity lg:grid-cols-2 xl:grid-cols-12",
            q.isPlaceholderData && "opacity-60",
          )}
        >
          <ReadinessCard r={d.readiness} className="xl:col-span-4" />
          <SleepCard s={d.sleep} tz={tz} className="xl:col-span-4" />
          <BodyBatteryCard
            b={d.body_battery}
            sleep={d.sleep}
            day={d.day}
            tz={tz}
            className="lg:col-span-2 xl:col-span-4"
          />
          <div className="grid gap-5 sm:grid-cols-2 lg:col-span-2 xl:col-span-12 xl:grid-cols-4">
            <HrvCard h={d.hrv} />
            <RestingHrCard r={d.resting_hr} />
            <StressCard s={d.stress} />
            <GoalsCard steps={d.steps} im={d.intensity_minutes} />
          </div>
          <TrainingStatusCard
            t={d.training_status}
            day={d.day}
            className="lg:col-span-2 xl:col-span-5"
          />
          <FitnessCard f={d.fitness} day={d.day} className="xl:col-span-4" />
          <PerformanceCard v={d.vo2max} races={d.race_predictions} className="xl:col-span-3" />
          <WeekCard week={d.week} day={d.day} className="xl:col-span-5" />
          <RecentCard
            items={d.recent_activities}
            streak={d.streak}
            className="lg:col-span-1 xl:col-span-7"
          />
        </div>
      )}
    </>
  );
}
