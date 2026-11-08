/**
 * Year in review: a "wrapped"-style recap of one calendar year — hero totals, highlights,
 * sports, months, every day, best efforts and health. The selected year lives in component
 * state (default: the latest year with data).
 */
import { clsx } from "clsx";
import { useState } from "react";
import { api } from "@/api/client";
import { EmptyState, ErrorState, PageHeader, Segmented, Skeleton } from "@/components/ui";
import { BestEfforts, BySport, Health, Hero, Highlights, Monthly, YearHeatmap } from "./sections";

function Loading() {
  return (
    <div className="flex flex-col gap-5">
      <Skeleton height={260} />
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} height={120} />
        ))}
      </div>
      <div className="grid gap-5 lg:grid-cols-2">
        <Skeleton height={360} />
        <Skeleton height={360} />
      </div>
    </div>
  );
}

export default function YearPage() {
  const meta = api.useQuery("get", "/api/meta");
  const years = api.useQuery("get", "/api/year");
  const [selected, setSelected] = useState<number | null>(null);
  const list = years.data ?? [];
  const year = selected ?? list[0]?.year ?? null;
  const review = api.useQuery(
    "get",
    "/api/year/{year}",
    { params: { path: { year: year ?? 0 } } },
    { enabled: year !== null, placeholderData: (prev) => prev },
  );
  const hasPrev = year !== null && list.some((y) => y.year === year - 1 && y.activities > 0);
  const prevReview = api.useQuery(
    "get",
    "/api/year/{year}",
    { params: { path: { year: (year ?? 0) - 1 } } },
    { enabled: hasPrev },
  );

  const r = review.data;
  const prev = hasPrev && prevReview.data?.year === (year ?? 0) - 1 ? prevReview.data : null;
  const last = meta.data?.last_day ?? null;
  const first = meta.data?.first_day ?? null;
  const partial = r && last && last.slice(0, 4) === String(r.year) && last < `${r.year}-12-31`;
  const start = r ? (first && first > `${r.year}-01-01` ? first : `${r.year}-01-01`) : "";
  const end = r ? (partial && last ? last : `${r.year}-12-31`) : "";

  // Compare with the previous year: whole years, or the same months when this year is running.
  let compare: {
    label: string;
    distance_m: number;
    duration_s: number;
    activities: number;
  } | null = null;
  // Only against a previous year that was tracked from 1 January (else the numbers mislead).
  const prevComplete = !!r && (!first || first <= `${r.year - 1}-01-01`);
  if (r && prev && prevComplete && prev.totals.activities > 0) {
    if (partial && last) {
      const m = Number(last.slice(5, 7));
      const months = prev.monthly.filter((x) => x.month <= m);
      compare = {
        label: `vs Jan–${new Date(2000, m - 1, 15).toLocaleDateString(undefined, { month: "short" })} ${prev.year}`,
        distance_m: months.reduce((n, x) => n + x.distance_m, 0),
        duration_s: months.reduce((n, x) => n + x.duration_s, 0),
        activities: months.reduce((n, x) => n + x.activities, 0),
      };
    } else {
      compare = {
        label: `vs ${prev.year}`,
        distance_m: prev.totals.distance_m,
        duration_s: prev.totals.moving_s || prev.totals.duration_s,
        activities: prev.totals.activities,
      };
    }
  }

  const options = [...list]
    .sort((a, b) => a.year - b.year)
    .map((y) => ({ value: String(y.year), label: String(y.year) }));

  return (
    <>
      <PageHeader
        title="Year in review"
        description={
          year ? `Your ${year} in numbers, highlights and days.` : "Your year in numbers."
        }
      >
        {options.length > 1 && year !== null && (
          <Segmented
            label="Year"
            value={String(year)}
            onChange={(v) => setSelected(Number(v))}
            options={options}
          />
        )}
      </PageHeader>
      {years.error || review.error ? (
        <ErrorState error={years.error ?? review.error} />
      ) : years.isSuccess && list.length === 0 ? (
        <EmptyState title="No data yet">
          Sync your Garmin account to get your first recap.
        </EmptyState>
      ) : !r ? (
        <Loading />
      ) : (
        <div
          className={clsx(
            "flex flex-col gap-5 transition-opacity",
            review.isPlaceholderData && "opacity-60",
          )}
        >
          <Hero r={r} start={start} end={end} compare={compare} />
          <Highlights r={r} />
          <div className="grid gap-5 lg:grid-cols-2">
            <BySport r={r} />
            <Monthly r={r} prev={prev} />
          </div>
          <YearHeatmap r={r} start={start} end={end} />
          <div className="grid gap-5 xl:grid-cols-12">
            <BestEfforts r={r} prev={prev} className="xl:col-span-7" />
            <Health r={r} className="xl:col-span-5" />
          </div>
        </div>
      )}
    </>
  );
}
