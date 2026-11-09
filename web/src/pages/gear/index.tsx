import { ChevronRight, CircleCheck, OctagonAlert } from "lucide-react";
import { useCallback, useMemo, useState } from "react";
import { api } from "@/api/client";
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  Segmented,
  Skeleton,
  StatTile,
} from "@/components/ui";
import { fmtDistance, fmtNumber } from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";
import { STATUS } from "@/lib/tokens";
import { GearCard } from "./GearCard";
import { GearDetail } from "./GearDetail";
import {
  gearSlots,
  isRetired,
  slotColor,
  sortTypes,
  typeLabel,
  wearLevel,
  type Gear,
} from "./gear";
import { UsageChart } from "./UsageChart";

function Group({
  type,
  items,
  selected,
  onSelect,
  colorOf,
}: {
  type: string;
  items: Gear[];
  selected: string;
  onSelect: (uuid: string) => void;
  colorOf: (uuid: string) => string;
}) {
  const active = items.filter((g) => !isRetired(g));
  const retired = items.filter(isRetired);
  const id = `gear-${type}`;
  const grid = "grid gap-3 sm:grid-cols-2";
  const card = (g: Gear) => (
    <GearCard
      key={g.uuid}
      g={g}
      color={colorOf(g.uuid)}
      selected={g.uuid === selected}
      onSelect={onSelect}
    />
  );
  return (
    <section aria-labelledby={id}>
      <div className="mb-2.5 flex items-baseline justify-between gap-2">
        <h2 id={id} className="text-base font-semibold text-ink">
          {typeLabel(type)}
        </h2>
        <span className="text-xs text-ink-3">
          {fmtNumber(active.length)} active
          {retired.length ? ` · ${fmtNumber(retired.length)} retired` : ""}
        </span>
      </div>
      {active.length > 0 ? (
        <div className={grid}>{active.map(card)}</div>
      ) : (
        <p className="text-sm text-ink-3">No active {typeLabel(type).toLowerCase()}.</p>
      )}
      {retired.length > 0 && (
        <details className="group mt-3">
          <summary className="inline-flex cursor-pointer list-none items-center gap-1 rounded-control py-1 text-sm font-medium text-ink-2 hover:text-ink [&::-webkit-details-marker]:hidden">
            <ChevronRight
              size={16}
              aria-hidden
              className="transition-transform group-open:rotate-90"
            />
            Retired {typeLabel(type).toLowerCase()} ({fmtNumber(retired.length)})
          </summary>
          <div className={`${grid} mt-2.5`}>{retired.map(card)}</div>
        </details>
      )}
    </section>
  );
}

function Tiles({ items }: { items: Gear[] }) {
  const units = useUnits();
  const active = items.filter((g) => !isRetired(g));
  const types = sortTypes(active.map((g) => g.gear_type));
  const distance = items.reduce((s, g) => s + g.distance_m, 0);
  const activities = items.reduce((s, g) => s + g.activities, 0);
  const worn = active.filter((g) => g.wear_pct !== null && wearLevel(g.wear_pct) === "critical");
  const nearing = active.filter((g) => g.wear_pct !== null && wearLevel(g.wear_pct) === "warning");
  const retiredShoes = items.filter((g) => isRetired(g) && g.gear_type === "shoes");
  const life = retiredShoes.length
    ? retiredShoes.reduce((s, g) => s + g.distance_m, 0) / retiredShoes.length
    : null;
  const [dist, distUnit] = fmtDistance(distance, units, 0).split(" ");
  const [lifeV, lifeU] = life !== null ? fmtDistance(life, units, 0).split(" ") : ["–", undefined];
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatTile
        label="Active gear"
        value={fmtNumber(active.length)}
        sub={types
          .map(
            (t) =>
              `${fmtNumber(active.filter((g) => g.gear_type === t).length)} ${typeLabel(t).toLowerCase()}`,
          )
          .join(" · ")}
      />
      <StatTile
        label="Distance on gear"
        value={dist}
        unit={distUnit}
        sub={`${fmtNumber(activities)} activities, all time`}
      />
      <StatTile
        label="Due for replacement"
        value={fmtNumber(worn.length)}
        sub={
          worn.length ? (
            <span className="inline-flex items-center gap-1">
              <OctagonAlert size={13} color={STATUS.critical} aria-hidden />
              {worn.length === 1 ? "1 item to replace" : `${worn.length} items to replace`}
              {nearing.length ? ` · ${nearing.length} nearing` : ""}
            </span>
          ) : (
            <span className="inline-flex items-center gap-1">
              <CircleCheck size={13} color={STATUS.good} aria-hidden />
              {nearing.length ? `${nearing.length} nearing its limit` : "All within limits"}
            </span>
          )
        }
      />
      <StatTile
        label="Average shoe life"
        value={lifeV}
        unit={lifeU}
        sub={
          retiredShoes.length
            ? `over ${fmtNumber(retiredShoes.length)} retired ${retiredShoes.length === 1 ? "pair" : "pairs"}`
            : "No retired shoes yet"
        }
      />
    </div>
  );
}

export default function GearPage() {
  const mode = useMode();
  const q = api.useQuery("get", "/api/gear");
  const [picked, setPicked] = useState<string | null>(null);
  const [chartType, setChartType] = useState<string | null>(null);
  const items = useMemo(() => q.data ?? [], [q.data]);
  const slots = useMemo(() => gearSlots(items), [items]);
  const colorOf = useCallback((uuid: string) => slotColor(slots.get(uuid), mode), [slots, mode]);
  const select = useCallback((uuid: string) => setPicked(uuid), []);

  const header = (
    <PageHeader
      title="Gear"
      description="Your shoes and bikes: how far they have carried you, and when to replace them."
    />
  );
  // The list endpoint declares no error responses, so its error type is `never`.
  const error: unknown = q.error;
  if (error)
    return (
      <>
        {header}
        <ErrorState error={error} />
      </>
    );
  if (!q.data)
    return (
      <>
        {header}
        <div className="flex flex-col gap-5">
          <Skeleton height={96} />
          <Skeleton height={480} />
        </div>
      </>
    );
  if (!items.length)
    return (
      <>
        {header}
        <EmptyState title="No gear yet">
          Add shoes or bikes in Garmin Connect and link them to activities; they appear here after
          the next sync.
        </EmptyState>
      </>
    );

  const selected = items.find((g) => g.uuid === picked) ?? items[0]!;
  const types = sortTypes(items.map((g) => g.gear_type));
  const chartTypes = types.filter((t) => items.some((g) => g.gear_type === t && g.usage.length));
  const type =
    chartType && chartTypes.includes(chartType)
      ? chartType
      : chartTypes.includes(selected.gear_type)
        ? selected.gear_type
        : (chartTypes[0] ?? types[0]!);

  return (
    <>
      {header}
      <div className="flex flex-col gap-5">
        <Tiles items={items} />
        <div className="grid items-start gap-5 lg:grid-cols-5">
          <div className="flex flex-col gap-6 lg:col-span-3">
            {types.map((t) => (
              <Group
                key={t}
                type={t}
                items={items.filter((g) => g.gear_type === t)}
                selected={selected.uuid}
                onSelect={select}
                colorOf={colorOf}
              />
            ))}
          </div>
          <div className="lg:sticky lg:top-20 lg:col-span-2">
            <GearDetail uuid={selected.uuid} color={colorOf} />
          </div>
        </div>
        <Card
          title="Monthly usage"
          subtitle="Distance per month, stacked by item. Click a bar or a legend entry to select that item."
          actions={
            chartTypes.length > 1 ? (
              <Segmented
                size="sm"
                label="Gear type"
                value={type}
                onChange={setChartType}
                options={chartTypes.map((t) => ({ value: t, label: typeLabel(t) }))}
              />
            ) : undefined
          }
        >
          <UsageChart
            items={items.filter((g) => g.gear_type === type)}
            slots={slots}
            selected={selected.uuid}
            onSelect={select}
            typeName={typeLabel(type)}
          />
        </Card>
      </div>
    </>
  );
}
