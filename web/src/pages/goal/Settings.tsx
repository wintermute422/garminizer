import { useQueryClient } from "@tanstack/react-query";
import { Loader2, Trash2 } from "lucide-react";
import { useState, type FormEvent, type ReactNode } from "react";
import { api, type Schemas } from "@/api/client";
import { FactRow } from "@/components/kit";
import { DASH, fmtDate, fmtNumber, titleCase } from "@/lib/format";
import { defaultEnd, formErrors, WEEKDAYS } from "./goal";

type Settings = Schemas["GoalSettings"];
type Profile = Schemas["GoalProfile"];
type Bmr = Schemas["GoalBmr"];

const INPUT =
  "w-full rounded-control border border-line-strong bg-surface px-3 py-2 text-sm text-ink tabular aria-invalid:border-critical";

interface FormState {
  start_day: string;
  start_weight_kg: string;
  rate_kg_per_week: string;
  end_day: string;
  checkpoint_weekday: string;
  activity_factor: string;
  sex: "" | "male" | "female";
  height_cm: string;
  birth_date: string;
}

function initial(s: Settings | null, today: string): FormState {
  const str = (v: number | null | undefined) => (v == null ? "" : String(v));
  return {
    start_day: s?.start_day ?? today,
    start_weight_kg: str(s?.start_weight_kg),
    rate_kg_per_week: str(s?.rate_kg_per_week ?? 0.5),
    end_day: s?.end_day ?? defaultEnd(today),
    checkpoint_weekday: str(s?.checkpoint_weekday ?? 6),
    activity_factor: str(s?.activity_factor ?? 1.25),
    sex: s?.sex ?? "",
    height_cm: str(s?.height_cm),
    birth_date: s?.birth_date ?? "",
  };
}

function toBody(f: FormState, prev: Settings | null): Settings {
  const num = (v: string) => Number(v.replace(",", "."));
  return {
    start_day: f.start_day,
    start_weight_kg: num(f.start_weight_kg),
    rate_kg_per_week: num(f.rate_kg_per_week),
    end_day: f.end_day,
    checkpoint_weekday: Number(f.checkpoint_weekday),
    activity_factor: num(f.activity_factor),
    sex: f.sex || null,
    height_cm: f.height_cm.trim() ? num(f.height_cm) : null,
    birth_date: f.birth_date || null,
    // Kept as they are: set through the checkpoint list and Claude Desktop.
    ...(prev
      ? { accepted_checkpoints: prev.accepted_checkpoints, trend_weights: prev.trend_weights }
      : {}),
  };
}

function Field({
  id,
  label,
  hint,
  error,
  children,
}: {
  id: string;
  label: string;
  hint?: ReactNode;
  error?: string;
  children: ReactNode;
}) {
  return (
    <div className="flex min-w-0 flex-col gap-1">
      <label htmlFor={id} className="text-xs font-medium text-ink-2">
        {label}
      </label>
      {children}
      {error ? (
        <p id={`${id}-error`} role="alert" className="text-xs text-critical-text">
          {error}
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-ink-3">
          {hint}
        </p>
      ) : null}
    </div>
  );
}

/** Today's resting energy and what it was computed from, with the baseline it implies. */
function BmrFacts({ bmr, factor }: { bmr: Bmr | null; factor: number | null }) {
  if (!bmr) {
    return (
      <p className="text-sm text-ink-3">
        No resting energy for today yet: it needs a weigh-in, or Garmin&apos;s BMR from a synced
        day.
      </p>
    );
  }
  const formulas = [
    ["Mifflin-St Jeor", bmr.mifflin_st_jeor],
    ["Harris-Benedict", bmr.harris_benedict],
    ["Katch-McArdle", bmr.katch_mcardle],
  ] as const;
  return (
    <div className="divide-y divide-line">
      <FactRow
        label="Resting energy (BMR) today"
        value={`${fmtNumber(bmr.kcal)} kcal`}
        sub={bmr.source === "formulas" ? "formula mean" : "Garmin"}
      />
      {bmr.source === "formulas" &&
        formulas
          .filter(([, v]) => v != null)
          .map(([name, v]) => <FactRow key={name} label={name} value={`${fmtNumber(v)} kcal`} />)}
      <FactRow
        label="Everyday burn without training"
        value={factor ? `${fmtNumber(bmr.kcal * factor)} kcal` : DASH}
        sub={factor ? `BMR × ${fmtNumber(factor, 2)}` : undefined}
      />
      <p className="py-2 text-xs text-ink-3">
        From {bmr.weight_kg != null ? `${fmtNumber(bmr.weight_kg, 1)} kg` : "no weight"}
        {bmr.height_cm != null && `, ${fmtNumber(bmr.height_cm)} cm`}
        {bmr.age_years != null && `, ${bmr.age_years} years`}
        {bmr.sex && `, ${bmr.sex}`}
        {bmr.body_fat_pct != null && `, ${fmtNumber(bmr.body_fat_pct, 1)} % body fat`}.
        {bmr.missing.length > 0 && ` Missing: ${bmr.missing.map(titleCase).join(", ")}.`}
      </p>
    </div>
  );
}

/** Create or edit the goal; remove it (with a confirmation step). */
export function SettingsForm({
  settings,
  profile,
  bmr,
  today,
}: {
  settings: Settings | null;
  profile: Profile;
  bmr: Bmr | null;
  today: string;
}) {
  const qc = useQueryClient();
  const save = api.useMutation("put", "/api/goal/settings");
  const remove = api.useMutation("delete", "/api/goal/settings");
  const [f, setF] = useState(() => initial(settings, today));
  const [confirm, setConfirm] = useState(false);
  const [saved, setSaved] = useState(false);
  const errors = formErrors(save.error);
  // The 404 (no goal) is not in the OpenAPI schema, so the typed error is `never`.
  const removeError: unknown = remove.error;
  const set =
    <K extends keyof FormState>(k: K) =>
    (value: FormState[K]) => {
      setSaved(false);
      setF((prev) => ({ ...prev, [k]: value }));
    };
  const submit = (e: FormEvent) => {
    e.preventDefault();
    save.mutate(
      { body: toBody(f, settings) },
      {
        onSuccess: () => {
          setSaved(true);
          void qc.invalidateQueries();
        },
      },
    );
  };
  const aria = (k: keyof FormState, hint = false) =>
    errors.fields[k]
      ? { "aria-invalid": true, "aria-describedby": `goal-${k}-error` }
      : hint
        ? { "aria-describedby": `goal-${k}-hint` }
        : {};
  const factor = Number(f.activity_factor.replace(",", "."));

  return (
    <div className="grid gap-6 lg:grid-cols-[minmax(0,7fr)_minmax(0,5fr)]">
      <form onSubmit={submit} className="flex flex-col gap-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <Field id="goal-start_day" label="Start day" error={errors.fields.start_day}>
            <input
              id="goal-start_day"
              type="date"
              required
              value={f.start_day}
              onChange={(e) => set("start_day")(e.target.value)}
              className={INPUT}
              {...aria("start_day")}
            />
          </Field>
          <Field
            id="goal-start_weight_kg"
            label="Start weight (kg)"
            hint={
              bmr?.weight_kg != null
                ? `Weight on the start day (latest: ${fmtNumber(bmr.weight_kg, 1)} kg)`
                : "Weight on the start day"
            }
            error={errors.fields.start_weight_kg}
          >
            <input
              id="goal-start_weight_kg"
              type="number"
              inputMode="decimal"
              required
              min={20}
              max={400}
              step={0.1}
              value={f.start_weight_kg}
              onChange={(e) => set("start_weight_kg")(e.target.value)}
              className={INPUT}
              {...aria("start_weight_kg", true)}
            />
          </Field>
          <Field
            id="goal-rate_kg_per_week"
            label="Planned loss (kg per week)"
            hint="0.25–0.5 kg is a sustainable pace"
            error={errors.fields.rate_kg_per_week}
          >
            <input
              id="goal-rate_kg_per_week"
              type="number"
              inputMode="decimal"
              required
              min={0.05}
              max={2}
              step={0.05}
              value={f.rate_kg_per_week}
              onChange={(e) => set("rate_kg_per_week")(e.target.value)}
              className={INPUT}
              {...aria("rate_kg_per_week", true)}
            />
          </Field>
          <Field id="goal-end_day" label="End day" error={errors.fields.end_day}>
            <input
              id="goal-end_day"
              type="date"
              required
              min={f.start_day || undefined}
              value={f.end_day}
              onChange={(e) => set("end_day")(e.target.value)}
              className={INPUT}
              {...aria("end_day")}
            />
          </Field>
          <Field
            id="goal-checkpoint_weekday"
            label="Checkpoint every"
            error={errors.fields.checkpoint_weekday}
          >
            <select
              id="goal-checkpoint_weekday"
              value={f.checkpoint_weekday}
              onChange={(e) => set("checkpoint_weekday")(e.target.value)}
              className={INPUT}
              {...aria("checkpoint_weekday")}
            >
              {WEEKDAYS.map((w, i) => (
                <option key={w} value={i}>
                  {w}
                </option>
              ))}
            </select>
          </Field>
          <Field
            id="goal-activity_factor"
            label="Activity factor"
            hint="BMR × this = everyday burn without training (1.2 desk job)"
            error={errors.fields.activity_factor}
          >
            <input
              id="goal-activity_factor"
              type="number"
              inputMode="decimal"
              required
              min={1}
              max={2.5}
              step={0.05}
              value={f.activity_factor}
              onChange={(e) => set("activity_factor")(e.target.value)}
              className={INPUT}
              {...aria("activity_factor", true)}
            />
          </Field>
        </div>
        <fieldset className="grid gap-4 rounded-card border border-line p-4 sm:grid-cols-3">
          <legend className="px-1 text-xs font-medium text-ink-2">
            For the BMR formulas (empty = Garmin profile)
          </legend>
          <Field id="goal-sex" label="Sex" error={errors.fields.sex}>
            <select
              id="goal-sex"
              value={f.sex}
              onChange={(e) => set("sex")(e.target.value as FormState["sex"])}
              className={INPUT}
              {...aria("sex")}
            >
              <option value="">Profile ({profile.sex ?? "not set"})</option>
              <option value="male">Male</option>
              <option value="female">Female</option>
            </select>
          </Field>
          <Field id="goal-height_cm" label="Height (cm)" error={errors.fields.height_cm}>
            <input
              id="goal-height_cm"
              type="number"
              inputMode="decimal"
              min={100}
              max={250}
              step={1}
              placeholder={profile.height_cm != null ? `${fmtNumber(profile.height_cm)}` : ""}
              value={f.height_cm}
              onChange={(e) => set("height_cm")(e.target.value)}
              className={INPUT}
              {...aria("height_cm")}
            />
          </Field>
          <Field
            id="goal-birth_date"
            label="Birth date"
            hint={profile.birth_date ? `Profile: ${fmtDate(profile.birth_date)}` : undefined}
            error={errors.fields.birth_date}
          >
            <input
              id="goal-birth_date"
              type="date"
              value={f.birth_date}
              onChange={(e) => set("birth_date")(e.target.value)}
              className={INPUT}
              {...aria("birth_date", !!profile.birth_date)}
            />
          </Field>
        </fieldset>
        {errors.general.length > 0 && (
          <p role="alert" className="text-xs text-critical-text">
            {errors.general.join(" ")}
          </p>
        )}
        <div className="flex flex-wrap items-center gap-3">
          <button
            type="submit"
            disabled={save.isPending}
            className="inline-flex items-center justify-center gap-2 rounded-control bg-action px-4 py-2 text-sm font-semibold text-on-action transition-colors hover:bg-action-hover disabled:opacity-60"
          >
            {save.isPending && <Loader2 size={16} className="animate-spin" aria-hidden />}
            {settings ? "Save goal" : "Start goal"}
          </button>
          {saved && !save.isPending && (
            <span role="status" className="text-xs text-ink-3">
              Saved.
            </span>
          )}
          {settings &&
            (confirm ? (
              <span className="flex flex-wrap items-center gap-2 sm:ml-auto">
                <span className="text-xs text-ink-2">Remove the goal? Your data stays.</span>
                <button
                  type="button"
                  disabled={remove.isPending}
                  onClick={() =>
                    remove.mutate(
                      {},
                      {
                        onSuccess: () => {
                          setConfirm(false);
                          void qc.invalidateQueries();
                        },
                      },
                    )
                  }
                  className="rounded-control bg-danger px-3 py-1.5 text-xs font-medium text-on-danger disabled:opacity-60"
                >
                  Remove
                </button>
                <button
                  type="button"
                  onClick={() => setConfirm(false)}
                  className="rounded-control px-3 py-1.5 text-xs text-ink-2 hover:bg-hover"
                >
                  Keep
                </button>
              </span>
            ) : (
              <button
                type="button"
                onClick={() => setConfirm(true)}
                className="inline-flex items-center gap-1.5 rounded-control px-3 py-2 text-sm text-ink-2 hover:bg-hover hover:text-ink sm:ml-auto"
              >
                <Trash2 size={15} aria-hidden />
                Remove goal
              </button>
            ))}
        </div>
        {removeError != null && (
          <p role="alert" className="text-xs text-critical-text">
            {formErrors(removeError).general.join(" ")}
          </p>
        )}
      </form>
      <div className="min-w-0">
        <p className="mb-1 text-eyebrow text-ink-2 uppercase">Energy model</p>
        <BmrFacts bmr={bmr} factor={Number.isFinite(factor) && factor > 0 ? factor : null} />
      </div>
    </div>
  );
}
