import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Info, Sparkles, Trash2, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { api, type Schemas } from "@/api/client";
import { Card, ErrorState, Skeleton, StatusPill } from "@/components/ui";
import { addDays } from "@/lib/range";
import { DASH, fmtDate, fmtNumber, signed, titleCase } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { MEASURE_COLORS, wash } from "@/lib/tokens";

type Day = Schemas["NutritionDay"];
type Meal = Schemas["NutritionMeal"];

/** "07:42" from an ISO datetime that carries the athlete's own UTC offset. */
function wallTime(iso: string): string {
  return iso.slice(11, 16);
}

function grams(v: number | null | undefined): string {
  return v == null ? DASH : `${fmtNumber(v)} g`;
}

/** Intake against a daily target: value, target and a bar that marks the target. */
function Meter({
  label,
  value,
  target,
  unit,
  color,
}: {
  label: string;
  value: number | null | undefined;
  target: number | null | undefined;
  unit: string;
  color: string;
}) {
  const v = value ?? 0;
  const max = Math.max(v, target ?? 0) * 1.08 || 1;
  // Without a target a bar has nothing to be measured against: show the number only.
  return (
    <div>
      <div className="flex items-baseline justify-between gap-2 text-sm">
        <span className="text-ink-2">{label}</span>
        <span className="text-ink tabular">
          <span className="font-medium">{value == null ? DASH : fmtNumber(value)}</span>
          {target ? (
            <span className="text-ink-3">
              {" "}
              / {fmtNumber(target)} {unit}
            </span>
          ) : (
            <span className="text-ink-3"> {unit}</span>
          )}
        </span>
      </div>
      {target ? (
        <div
          className="relative mt-1.5 h-2 rounded-full"
          style={{ background: wash(color, 0.18) }}
          aria-hidden
        >
          <div
            className="h-2 rounded-full"
            style={{ width: `${(v / max) * 100}%`, background: color }}
          />
          <div
            className="absolute -top-1 h-4 w-0.5 rounded-full bg-ink"
            style={{ left: `calc(${(target / max) * 100}% - 1px)` }}
          />
        </div>
      ) : null}
    </div>
  );
}

function MealRow({ meal, onDelete }: { meal: Meal; onDelete: (id: number) => void }) {
  const [confirm, setConfirm] = useState(false);
  return (
    <li className="py-3">
      <div className="flex items-start gap-3">
        <span className="w-11 shrink-0 pt-0.5 text-xs text-ink-3 tabular">
          {wallTime(meal.eaten_at)}
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline justify-between gap-x-3">
            <p className="font-medium text-ink">{meal.name}</p>
            <p className="text-sm text-ink tabular">
              <span className="font-medium">{fmtNumber(meal.kcal)}</span>{" "}
              <span className="text-ink-3">kcal</span>
            </p>
          </div>
          <p className="mt-0.5 text-xs text-ink-3 tabular">
            {titleCase(meal.meal_type)} · protein {grams(meal.protein_g)} · carbs{" "}
            {grams(meal.carbs_g)} · fat {grams(meal.fat_g)}
          </p>
          {meal.items.length > 0 && (
            <details className="mt-1.5 text-xs">
              <summary className="cursor-pointer text-ink-2 hover:text-ink">
                {meal.items.length} {meal.items.length === 1 ? "item" : "items"}
                {meal.source === "claude" && (
                  <span className="ml-2 inline-flex items-center gap-1 text-ink-3">
                    <Sparkles size={12} aria-hidden /> estimated by Claude
                    {meal.confidence ? `, ${meal.confidence} confidence` : ""}
                  </span>
                )}
              </summary>
              <ul className="mt-1.5 flex flex-col gap-1 border-l border-line pl-3">
                {meal.items.map((it) => (
                  <li key={it.idx} className="flex justify-between gap-3 text-ink-2 tabular">
                    <span className="min-w-0">
                      {it.food}
                      {it.amount != null && (
                        <span className="text-ink-3">
                          {" "}
                          · {fmtNumber(it.amount, it.amount % 1 ? 1 : 0)} {it.unit ?? ""}
                        </span>
                      )}
                      {it.grams != null && it.unit !== "g" && (
                        <span className="text-ink-3"> ({fmtNumber(it.grams)} g)</span>
                      )}
                    </span>
                    <span className="shrink-0">{fmtNumber(it.kcal)} kcal</span>
                  </li>
                ))}
              </ul>
              {meal.notes && (
                <p className="mt-1.5 flex gap-1.5 text-ink-3">
                  <Info size={12} className="mt-0.5 shrink-0" aria-hidden />
                  {meal.notes}
                </p>
              )}
            </details>
          )}
          {meal.warnings.map((w) => (
            <p key={w.code} className="mt-1 flex gap-1.5 text-xs text-ink-2">
              <TriangleAlert
                size={12}
                className="mt-0.5 shrink-0"
                color="var(--warning)"
                aria-hidden
              />
              {w.message}
            </p>
          ))}
        </div>
        {confirm ? (
          <span className="flex shrink-0 items-center gap-1">
            <button
              type="button"
              onClick={() => onDelete(meal.meal_id)}
              className="rounded-lg px-2 py-1 text-xs font-medium text-white"
              style={{ background: "var(--critical)" }}
            >
              Delete
            </button>
            <button
              type="button"
              onClick={() => setConfirm(false)}
              className="rounded-lg px-2 py-1 text-xs text-ink-2 hover:bg-surface-2"
            >
              Keep
            </button>
          </span>
        ) : (
          <button
            type="button"
            aria-label={`Delete ${meal.name}`}
            onClick={() => setConfirm(true)}
            className="shrink-0 rounded-lg p-1.5 text-ink-3 hover:bg-surface-2 hover:text-ink"
          >
            <Trash2 size={15} aria-hidden />
          </button>
        )}
      </div>
    </li>
  );
}

function DayBody({ d }: { d: Day }) {
  const mode = useMode();
  const c = MEASURE_COLORS[mode];
  const qc = useQueryClient();
  const remove = api.useMutation("delete", "/api/nutrition/meals/{meal_id}");
  const t = d.totals;
  const burn = d.garmin.total_kcal;
  const balance = d.balance_kcal;
  const tg = d.targets;
  const hasTargets = [tg.kcal, tg.protein_g, tg.carbs_g, tg.fat_g, d.protein_target_g].some(
    (v) => v != null,
  );
  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,5fr)_minmax(0,7fr)]">
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-3 gap-3 text-sm">
          <div>
            <p className="text-xs text-ink-3">Eaten</p>
            <p className="text-xl font-semibold text-ink tabular">{fmtNumber(t.kcal)}</p>
            <p className="text-xs text-ink-3">kcal</p>
          </div>
          <div>
            <p className="text-xs text-ink-3">Garmin burn</p>
            <p className="text-xl font-semibold text-ink tabular">{fmtNumber(burn)}</p>
            <p className="text-xs text-ink-3">
              kcal{d.garmin.active_kcal != null && ` · ${fmtNumber(d.garmin.active_kcal)} active`}
            </p>
          </div>
          <div>
            <p className="text-xs text-ink-3">Balance</p>
            <p className="text-xl font-semibold text-ink tabular">
              {balance == null ? DASH : signed(balance)}
            </p>
            <p className="text-xs text-ink-3">
              {balance == null ? "no Garmin data" : balance < 0 ? "kcal deficit" : "kcal surplus"}
            </p>
          </div>
        </div>
        {d.is_today && (
          <p className="text-xs text-ink-3">
            Today is still running: intake and Garmin&apos;s burn both keep growing until midnight.
          </p>
        )}
        <div className="flex flex-col gap-3">
          <Meter
            label="Energy"
            value={t.kcal}
            target={d.targets.kcal}
            unit="kcal"
            color={c.intake}
          />
          <Meter
            label="Protein"
            value={t.protein_g}
            target={d.protein_target_g ?? d.targets.protein_g}
            unit="g"
            color={c.protein}
          />
          <Meter
            label="Carbs"
            value={t.carbs_g}
            target={d.targets.carbs_g}
            unit="g"
            color={c.carbs}
          />
          <Meter label="Fat" value={t.fat_g} target={d.targets.fat_g} unit="g" color={c.fat} />
        </div>
        <p className="text-xs text-ink-3">
          {d.protein_g_per_kg != null && d.weight_kg != null
            ? `Protein ${fmtNumber(d.protein_g_per_kg, 1)} g per kg body weight (${fmtNumber(d.weight_kg, 1)} kg). `
            : ""}
          {hasTargets
            ? "The line on each bar marks your daily target."
            : 'No daily targets yet. Ask Claude, e.g. "set my targets to 2,600 kcal and 1.8 g protein per kg".'}
        </p>
      </div>
      <div className="min-w-0">
        <p className="text-xs font-medium text-ink-2">
          {d.meals.length === 0
            ? "No meals logged"
            : `${d.meals.length} ${d.meals.length === 1 ? "meal" : "meals"}`}
        </p>
        {d.meals.length > 0 && (
          <ul className="divide-y divide-line">
            {d.meals.map((m) => (
              <MealRow
                key={m.meal_id}
                meal={m}
                onDelete={(id) =>
                  remove.mutate(
                    { params: { path: { meal_id: id } } },
                    { onSuccess: () => qc.invalidateQueries() },
                  )
                }
              />
            ))}
          </ul>
        )}
        {remove.error && <ErrorState error={remove.error} />}
      </div>
    </div>
  );
}

/** One day: meals, totals against targets, and Garmin's burn for the same day. */
export function DayCard({
  day,
  onDay,
  maxDay,
}: {
  day: string;
  onDay: (d: string) => void;
  maxDay: string;
}) {
  const q = api.useQuery("get", "/api/nutrition/day", { params: { query: { day } } });
  const label = fmtDate(day, { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  return (
    <Card
      title={label}
      subtitle="Meals, totals against your targets, and what Garmin says you burned"
      actions={
        <div className="flex items-center gap-1">
          {q.data?.is_today && <StatusPill status={null} label="Today" />}
          <button
            type="button"
            aria-label="Previous day"
            onClick={() => onDay(addDays(day, -1))}
            className="rounded-lg p-1.5 text-ink-2 hover:bg-surface-2 hover:text-ink"
          >
            <ChevronLeft size={18} aria-hidden />
          </button>
          <button
            type="button"
            aria-label="Next day"
            disabled={day >= maxDay}
            onClick={() => onDay(addDays(day, 1))}
            className="rounded-lg p-1.5 text-ink-2 hover:bg-surface-2 hover:text-ink disabled:opacity-40"
          >
            <ChevronRight size={18} aria-hidden />
          </button>
        </div>
      }
    >
      {q.isPending ? (
        <Skeleton height={280} />
      ) : q.isError ? (
        <ErrorState error={q.error as unknown} />
      ) : (
        <DayBody d={q.data} />
      )}
    </Card>
  );
}
