import { useCallback, useMemo, useState } from "react";
import { api } from "@/api/client";
import { usePageFilters } from "@/app/pageFilters";
import { Card, PageHeader, QueryState, Segmented, Skeleton } from "@/components/ui";
import { fmtDate } from "@/lib/format";
import { useUnits } from "@/lib/preferences";
import { CorrelationMatrix } from "./CorrelationMatrix";
import { InsightCards, type Pair } from "./InsightCards";
import { lagText, metricView, phrase } from "./metrics";
import { ScatterControls, ScatterView } from "./ScatterExplorer";
import { StrongestLinks } from "./StrongestLinks";
import { useMediaQuery } from "@/lib/useMediaQuery";
import { WeekdayPatterns, type WeekdayKey } from "./WeekdayPatterns";

const MATRIX_LAGS = [
  { value: "0", label: "Same day" },
  { value: "1", label: "1 day" },
  { value: "2", label: "2 days" },
] as const;
type LagValue = (typeof MATRIX_LAGS)[number]["value"];

function scrollToScatter() {
  document
    .getElementById("scatter-explorer")
    ?.scrollIntoView({ behavior: "smooth", block: "start" });
}

export default function InsightsPage() {
  const range = usePageFilters();
  // A readable matrix needs room for ~20 columns; narrower screens get a ranked list.
  const wide = useMediaQuery("(min-width: 1280px)");
  const units = useUnits();
  const [pair, setPair] = useState<Pair>({ x: "sleep_score", y: "readiness", lag: 0 });
  const [matrixLag, setMatrixLag] = useState<LagValue>("0");
  const query = range.dates;
  const enabled = { enabled: range.ready };

  const metricsQ = api.useQuery("get", "/api/insights/metrics");
  const cardsQ = api.useQuery("get", "/api/insights/cards", { params: { query } }, enabled);
  const corrQ = api.useQuery(
    "get",
    "/api/insights/correlations",
    { params: { query: { ...query, lag: Number(matrixLag) } } },
    range.options,
  );
  const scatterQ = api.useQuery(
    "get",
    "/api/insights/scatter",
    { params: { query: { ...query, x: pair.x, y: pair.y, lag: pair.lag } } },
    range.options,
  );
  const weekdayQ = api.useQuery("get", "/api/insights/weekday", { params: { query } }, enabled);

  const metrics = metricsQ.data;
  const labelOf = useCallback(
    (key: string) => metrics?.find((m) => m.key === key)?.label ?? key,
    [metrics],
  );
  const views = useMemo(() => {
    const keys: WeekdayKey[] = ["sleep_s", "steps", "avg_stress", "hrv_ms", "load", "readiness"];
    return Object.fromEntries(keys.map((k) => [k, metricView(k, metrics, units)])) as Record<
      WeekdayKey,
      ReturnType<typeof metricView>
    >;
  }, [metrics, units]);
  const weekdayView = useCallback((k: WeekdayKey) => views[k], [views]);
  // The chart shows what was loaded (the previous pair stays visible while the next loads).
  const shownX = scatterQ.data?.x ?? pair.x;
  const shownY = scatterQ.data?.y ?? pair.y;
  const xv = useMemo(() => metricView(shownX, metrics, units), [shownX, metrics, units]);
  const yv = useMemo(() => metricView(shownY, metrics, units), [shownY, metrics, units]);

  const explore = useCallback((p: Pair) => {
    setPair(p);
    scrollToScatter();
  }, []);
  const selectCell = useCallback((p: Pair) => {
    setPair(p);
    scrollToScatter();
  }, []);

  return (
    <>
      <PageHeader
        title="Insights"
        description={`Patterns and correlations in your daily data · ${fmtDate(range.start)} – ${fmtDate(range.end)}`}
      />
      <div className="flex flex-col gap-5">
        <QueryState
          query={cardsQ}
          skeleton={
            <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
              {Array.from({ length: 6 }, (_, i) => (
                <Skeleton key={i} height={168} />
              ))}
            </div>
          }
        >
          {(cards) => <InsightCards cards={cards} onExplore={explore} />}
        </QueryState>

        <Card
          title="How your metrics move together"
          subtitle={
            !wide
              ? `The strongest links between your daily metrics${matrixLag === "0" ? "" : ` (first metric on day d, second ${lagText(Number(matrixLag))})`}. Tap one to explore it.`
              : matrixLag === "0"
                ? "Pearson r between daily metrics on the same day. Click a cell to explore the pair."
                : `Column metric on day d against the row metric ${lagText(Number(matrixLag))}. Click a cell to explore the pair.`
          }
          actions={
            <Segmented
              size="sm"
              label="Lag between the two metrics"
              value={matrixLag}
              onChange={setMatrixLag}
              options={MATRIX_LAGS}
            />
          }
        >
          <QueryState queries={[corrQ, metricsQ]} height={wide ? 640 : 480}>
            {([corr]) =>
              wide ? (
                <CorrelationMatrix
                  data={corr}
                  labelOf={labelOf}
                  selected={pair}
                  onSelect={selectCell}
                />
              ) : (
                <StrongestLinks data={corr} labelOf={labelOf} onSelect={selectCell} />
              )
            }
          </QueryState>
        </Card>

        <Card
          id="scatter-explorer"
          className="scroll-mt-20"
          title="Scatter explorer"
          subtitle={`Each dot is one day: ${phrase(labelOf(pair.x))} on day d against ${phrase(labelOf(pair.y))} ${lagText(pair.lag)}.`}
        >
          {metrics && (
            <div className="mb-4">
              <ScatterControls pair={pair} metrics={metrics} onChange={setPair} />
            </div>
          )}
          <QueryState queries={[scatterQ, metricsQ]} height={360}>
            {([points]) => <ScatterView data={points} xv={xv} yv={yv} />}
          </QueryState>
        </Card>

        <Card
          title="Weekly rhythm"
          subtitle="Average per weekday in this period; the highest day is highlighted, the dashed line is the weekly average."
        >
          <QueryState queries={[weekdayQ, metricsQ]} height={340}>
            {([rows]) => <WeekdayPatterns rows={rows} view={weekdayView} />}
          </QueryState>
        </Card>
      </div>
    </>
  );
}
