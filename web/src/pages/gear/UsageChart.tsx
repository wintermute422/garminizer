import { clsx } from "clsx";
import { useMemo } from "react";
import { Chart, type ChartOption } from "@/components/Chart";
import { EmptyState, LegendItem } from "@/components/ui";
import {
  bars,
  categoryXAxis,
  GRID,
  itemTooltip,
  tooltipRow,
  tooltipTitle,
  valueYAxis,
} from "@/lib/charts";
import { distanceUnit, distanceValue, fmtDate, fmtMonth, fmtNumber } from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";
import { CHROME, barEnd } from "@/lib/tokens";
import { gearName, slotColor, type Gear } from "./gear";

interface Stack {
  id: string;
  name: string;
  color: string;
  slot: number;
  byMonth: Map<string, number>;
}

function monthRange(first: string, last: string): string[] {
  const out: string[] = [];
  const d = new Date(`${first.slice(0, 7)}-01T12:00:00`);
  for (;;) {
    const k = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
    out.push(k);
    if (k >= last.slice(0, 7)) break;
    d.setMonth(d.getMonth() + 1);
  }
  return out;
}

const monthLabel = (k: string, long = false) =>
  long ? fmtDate(`${k}-01`, { month: "long", year: "numeric" }) : fmtMonth(`${k}-01`);

export function UsageChart({
  items,
  slots,
  selected,
  onSelect,
  typeName,
}: {
  items: Gear[];
  slots: Map<string, number | null>;
  selected: string | null;
  /** Must be stable (chart events are bound once). */
  onSelect: (uuid: string) => void;
  typeName: string;
}) {
  const mode = useMode();
  const units = useUnits();
  const stacks = useMemo(() => {
    const used = items.filter((g) => g.usage.some((u) => u.distance_m > 0));
    const stacks: Stack[] = [];
    const other: Stack = {
      id: "other",
      name: "Other",
      color: slotColor(null, mode),
      slot: 99,
      byMonth: new Map(),
    };
    for (const g of used) {
      const slot = slots.get(g.uuid) ?? null;
      const target =
        slot === null
          ? other
          : {
              id: g.uuid,
              name: gearName(g),
              color: slotColor(slot, mode),
              slot,
              byMonth: new Map<string, number>(),
            };
      for (const u of g.usage) {
        const k = u.month.slice(0, 7);
        target.byMonth.set(k, (target.byMonth.get(k) ?? 0) + u.distance_m);
      }
      if (slot !== null) stacks.push(target);
    }
    if (other.byMonth.size) stacks.push(other);
    return stacks.sort((a, b) => a.slot - b.slot);
  }, [items, slots, mode]);
  const option = useMemo<ChartOption | null>(() => {
    if (!stacks.length) return null;
    const all = stacks.flatMap((s) => [...s.byMonth.keys()]).sort();
    const months = monthRange(all[0]!, all[all.length - 1]!);
    const totals = months.map((m) => stacks.reduce((s, st) => s + (st.byMonth.get(m) ?? 0), 0));
    const top = months.map((m) => {
      for (let i = stacks.length - 1; i >= 0; i--)
        if ((stacks[i]!.byMonth.get(m) ?? 0) > 0) return i;
      return -1;
    });
    const unit = distanceUnit(units);
    const series = stacks.map((st, si) => {
      // The selected item is outlined in ink; the others keep full colour (contrast ≥ 3:1).
      const isSel = selected === st.id;
      const base = bars(st.name, [], st.color, mode, { stack: "gear" });
      return {
        ...base,
        id: st.id,
        z: isSel ? 3 : 2,
        itemStyle: {
          ...(base.itemStyle as object),
          ...(isSel ? { borderColor: CHROME[mode].text, borderWidth: 1.5 } : {}),
        },
        data: months.map((m, mi) => {
          const v = st.byMonth.get(m);
          if (!v) return null;
          return {
            value: distanceValue(v, units),
            ...(top[mi] === si ? { itemStyle: { borderRadius: barEnd("up") } } : {}),
          };
        }),
      };
    });
    return {
      grid: { ...GRID, top: 28 },
      legend: { show: false },
      tooltip: itemTooltip((p) => {
        const it = p as { seriesName: string; color: string; dataIndex: number; value: number };
        const m = months[it.dataIndex]!;
        const total = distanceValue(totals[it.dataIndex] ?? 0, units);
        return (
          tooltipTitle(monthLabel(m, true)) +
          tooltipRow(it.color, it.seriesName, `${fmtNumber(it.value, 1)} ${unit}`) +
          tooltipRow(
            CHROME[mode].muted,
            `All ${typeName.toLowerCase()}`,
            `${fmtNumber(total, 1)} ${unit}`,
          )
        );
      }),
      xAxis: categoryXAxis(months.map((m) => monthLabel(m))),
      yAxis: valueYAxis(unit, (v) => fmtNumber(v)),
      series,
    };
  }, [stacks, selected, mode, units, typeName]);

  if (!option) return <EmptyState title={`No ${typeName.toLowerCase()} usage recorded`} />;
  return (
    <div>
      {/* HTML legend: wraps on phones, and its entries select the item like the bars do. */}
      <ul className="mb-2 flex flex-wrap gap-x-1 gap-y-1" aria-label="Legend">
        {stacks.map((st) => {
          const isSel = st.id === selected;
          return (
            <li key={st.id}>
              {st.id === "other" ? (
                <span className="inline-flex px-1.5 py-0.5">
                  <LegendItem color={st.color} label={st.name} />
                </span>
              ) : (
                <button
                  type="button"
                  aria-pressed={isSel}
                  onClick={() => onSelect(st.id)}
                  className={clsx(
                    "rounded-control border px-1.5 py-0.5 hover:bg-hover",
                    isSel ? "border-line-strong bg-surface-2" : "border-transparent",
                  )}
                >
                  <LegendItem color={st.color} label={st.name} />
                </button>
              )}
            </li>
          );
        })}
      </ul>
      <Chart
        option={option}
        height={290}
        ariaLabel={`Distance per month by item, ${typeName.toLowerCase()}`}
        onEvents={{
          click: (p) => {
            const id = (p as { seriesId?: string }).seriesId;
            if (id && id !== "other") onSelect(id);
          },
        }}
      />
    </div>
  );
}
