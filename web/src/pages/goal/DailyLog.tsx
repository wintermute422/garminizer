import { clsx } from "clsx";
import { useState } from "react";
import type { Schemas } from "@/api/client";
import { ScrollArea, ShowAllButton } from "@/components/ui";
import { DASH, fmtDate, fmtNumber, signed } from "@/lib/format";
import { useUnits } from "@/lib/preferences";
import { dayNotes, newestFirst } from "./goal";

type Day = Schemas["GoalDay"];

const ROWS = 14;

const num = (v: number | null | undefined, digits = 0) => (v == null ? DASH : fmtNumber(v, digits));

const COLUMNS: { label: string; title?: string; left?: boolean }[] = [
  { label: "Day", left: true },
  { label: "Weight", title: "kg" },
  { label: "Trend", title: "kg, weighted 3-day trend" },
  { label: "Target", title: "kg" },
  { label: "Δ target", title: "Trend minus target (kg)" },
  { label: "Fat %" },
  { label: "Muscle", title: "kg" },
  { label: "Water %" },
  { label: "kcal", title: "Eaten (kcal)" },
  { label: "Protein", title: "g" },
  { label: "Carbs", title: "g" },
  { label: "Fat g" },
  { label: "Sport kcal", title: "Garmin calories of all activities: total / active" },
  { label: "Burn", title: "BMR × activity factor + active training kcal" },
  { label: "Balance", title: "Eaten minus burn (kcal)" },
  { label: "Notes", left: true },
];

function DeltaCell({ d }: { d: Day }) {
  if (d.delta_kg == null) return <>{DASH}</>;
  return (
    <span
      className={clsx(
        "font-medium",
        d.on_plan ? "text-good-text" : d.on_plan === false ? "text-critical-text" : "text-ink",
      )}
    >
      {signed(d.delta_kg, 2)}
    </span>
  );
}

/** Every day of the goal, newest first: body, food, training and the energy balance. */
export function DailyLog({ days }: { days: Day[] }) {
  const units = useUnits();
  const [all, setAll] = useState(false);
  const rows = newestFirst(days);
  const shown = all ? rows : rows.slice(0, ROWS);
  return (
    <>
      <ScrollArea label="Daily log" className="-mx-4 overflow-x-auto sm:-mx-5">
        <table className="w-full min-w-[1180px] text-sm tabular">
          <thead>
            <tr className="border-b border-line text-xs text-ink-3">
              {COLUMNS.map((c) => (
                <th
                  key={c.label}
                  scope="col"
                  title={c.title}
                  className={clsx(
                    "px-2 py-2 font-medium whitespace-nowrap first:pl-4 last:pr-4 sm:first:pl-5 sm:last:pr-5",
                    c.left ? "text-left" : "text-right",
                  )}
                >
                  {c.label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {shown.map((d) => {
              const notes = dayNotes(d, units);
              return (
                <tr key={d.day} className="border-b border-line align-top last:border-b-0">
                  <td className="py-2 pr-2 pl-4 whitespace-nowrap text-ink sm:pl-5">
                    {fmtDate(d.day, { weekday: "short", day: "numeric", month: "short" })}
                  </td>
                  <td className="px-2 py-2 text-right text-ink">{num(d.weight_kg, 1)}</td>
                  <td className="px-2 py-2 text-right font-medium text-ink">
                    {num(d.trend_kg, 2)}
                  </td>
                  <td className="px-2 py-2 text-right text-ink-2">{num(d.target_kg, 2)}</td>
                  <td className="px-2 py-2 text-right">
                    <DeltaCell d={d} />
                  </td>
                  <td className="px-2 py-2 text-right text-ink-2">{num(d.body_fat_pct, 1)}</td>
                  <td className="px-2 py-2 text-right text-ink-2">{num(d.muscle_mass_kg, 1)}</td>
                  <td className="px-2 py-2 text-right text-ink-2">{num(d.body_water_pct, 1)}</td>
                  <td className="px-2 py-2 text-right text-ink">{num(d.intake_kcal)}</td>
                  <td className="px-2 py-2 text-right text-ink-2">{num(d.protein_g)}</td>
                  <td className="px-2 py-2 text-right text-ink-2">{num(d.carbs_g)}</td>
                  <td className="px-2 py-2 text-right text-ink-2">{num(d.fat_g)}</td>
                  <td className="px-2 py-2 text-right whitespace-nowrap text-ink-2">
                    {d.sport_kcal == null ? (
                      DASH
                    ) : (
                      <>
                        {num(d.sport_kcal)}
                        <span className="text-ink-3"> / {num(d.training_kcal)}</span>
                      </>
                    )}
                  </td>
                  <td className="px-2 py-2 text-right text-ink-2">{num(d.burn_kcal)}</td>
                  <td className="px-2 py-2 text-right font-medium whitespace-nowrap text-ink">
                    {d.balance_kcal == null ? DASH : signed(d.balance_kcal)}
                  </td>
                  <td className="min-w-72 py-2 pr-4 pl-2 text-xs text-ink-2 sm:pr-5">
                    {notes.length === 0 ? (
                      <span className="text-ink-3">{DASH}</span>
                    ) : (
                      notes.map((n, i) => (
                        <span key={i} className="block">
                          {n}
                        </span>
                      ))
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </ScrollArea>
      {rows.length > ROWS && (
        <ShowAllButton
          total={rows.length}
          noun="days"
          expanded={all}
          onToggle={() => setAll((v) => !v)}
        />
      )}
    </>
  );
}
