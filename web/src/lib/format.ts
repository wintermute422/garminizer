/** Formatting helpers. The API speaks SI (m, s, m/s, kg, °C); these convert for display. */
export type UnitSystem = "metric" | "imperial";

const KM_PER_MI = 1.609344;
const FT_PER_M = 3.28084;
const LB_PER_KG = 2.20462;

const nf = (digits: number) =>
  new Intl.NumberFormat(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });

export const DASH = "–";

function ok(v: number | null | undefined): v is number {
  return v !== null && v !== undefined && Number.isFinite(v);
}

export function fmtNumber(v: number | null | undefined, digits = 0): string {
  return ok(v) ? nf(digits).format(v) : DASH;
}

export function fmtCompact(v: number | null | undefined): string {
  if (!ok(v)) return DASH;
  return new Intl.NumberFormat(undefined, { notation: "compact", maximumFractionDigits: 1 }).format(
    v,
  );
}

export function fmtPercent(v: number | null | undefined, digits = 0): string {
  return ok(v) ? `${nf(digits).format(v)} %` : DASH;
}

export function distanceValue(m: number, units: UnitSystem): number {
  return units === "metric" ? m / 1000 : m / 1000 / KM_PER_MI;
}

export function distanceUnit(units: UnitSystem): string {
  return units === "metric" ? "km" : "mi";
}

export function fmtDistance(
  m: number | null | undefined,
  units: UnitSystem,
  digits?: number,
): string {
  if (!ok(m)) return DASH;
  const v = distanceValue(m, units);
  const d = digits ?? (v >= 100 ? 0 : v >= 10 ? 1 : 2);
  return `${nf(d).format(v)} ${distanceUnit(units)}`;
}

export function fmtElevation(m: number | null | undefined, units: UnitSystem): string {
  if (!ok(m)) return DASH;
  return units === "metric" ? `${nf(0).format(m)} m` : `${nf(0).format(m * FT_PER_M)} ft`;
}

export function fmtWeight(kg: number | null | undefined, units: UnitSystem, digits = 1): string {
  if (!ok(kg)) return DASH;
  return units === "metric"
    ? `${nf(digits).format(kg)} kg`
    : `${nf(digits).format(kg * LB_PER_KG)} lb`;
}

export function weightValue(kg: number, units: UnitSystem): number {
  return units === "metric" ? kg : kg * LB_PER_KG;
}

export function fmtTemperature(c: number | null | undefined, units: UnitSystem): string {
  if (!ok(c)) return DASH;
  return units === "metric" ? `${nf(0).format(c)} °C` : `${nf(0).format((c * 9) / 5 + 32)} °F`;
}

/** h:mm:ss for long, m:ss for short durations. */
export function fmtDuration(s: number | null | undefined): string {
  if (!ok(s)) return DASH;
  const total = Math.round(s);
  const h = Math.floor(total / 3600);
  const m = Math.floor((total % 3600) / 60);
  const sec = total % 60;
  const mm = String(m).padStart(h > 0 ? 2 : 1, "0");
  const ss = String(sec).padStart(2, "0");
  return h > 0 ? `${h}:${mm}:${ss}` : `${mm}:${ss}`;
}

/** "3h 05m", "42m" — for totals. */
export function fmtHours(s: number | null | undefined): string {
  if (!ok(s)) return DASH;
  const h = Math.floor(s / 3600);
  const m = Math.round((s % 3600) / 60);
  if (h === 0) return `${m}m`;
  return `${h}h ${String(m).padStart(2, "0")}m`;
}

/** Pace from m/s: min per km or per mile (per 100 m / 100 yd for swimming). */
export function fmtPace(mps: number | null | undefined, units: UnitSystem, swim = false): string {
  if (!ok(mps) || mps <= 0.05) return DASH;
  if (swim) {
    const per = units === "metric" ? 100 : 91.44;
    return `${fmtDuration(per / mps)} /${units === "metric" ? "100 m" : "100 yd"}`;
  }
  const per = units === "metric" ? 1000 : 1000 * KM_PER_MI;
  return `${fmtDuration(per / mps)} /${distanceUnit(units)}`;
}

export function paceSeconds(mps: number, units: UnitSystem): number {
  return (units === "metric" ? 1000 : 1000 * KM_PER_MI) / mps;
}

export function fmtSpeed(mps: number | null | undefined, units: UnitSystem): string {
  if (!ok(mps)) return DASH;
  const v = units === "metric" ? mps * 3.6 : (mps * 3.6) / KM_PER_MI;
  return `${nf(1).format(v)} ${units === "metric" ? "km/h" : "mph"}`;
}

export function speedValue(mps: number, units: UnitSystem): number {
  return units === "metric" ? mps * 3.6 : (mps * 3.6) / KM_PER_MI;
}

export function speedUnit(units: UnitSystem): string {
  return units === "metric" ? "km/h" : "mph";
}

export function fmtDate(iso: string | null | undefined, opts?: Intl.DateTimeFormatOptions): string {
  if (!iso) return DASH;
  const d = new Date(iso.length === 10 ? `${iso}T12:00:00` : iso);
  return d.toLocaleDateString(
    undefined,
    opts ?? { day: "numeric", month: "short", year: "numeric" },
  );
}

export function fmtShortDate(iso: string | null | undefined): string {
  return fmtDate(iso, { day: "numeric", month: "short" });
}

/** Local wall-clock time of a naive local ISO datetime ("2026-06-01T07:12:00"). */
export function fmtLocalTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  return new Date(iso).toLocaleTimeString(undefined, { hour: "2-digit", minute: "2-digit" });
}

/** Minutes after local noon of the previous day (API sleep convention) → "23:40". */
export function fmtClockFromNoon(minutes: number | null | undefined): string {
  if (!ok(minutes)) return DASH;
  const m = Math.round(minutes + 12 * 60) % (24 * 60);
  return `${String(Math.floor(m / 60)).padStart(2, "0")}:${String(m % 60).padStart(2, "0")}`;
}

export function signed(v: number | null | undefined, digits = 0, suffix = ""): string {
  if (!ok(v)) return DASH;
  const s = nf(digits).format(Math.abs(v));
  return `${v > 0 ? "+" : v < 0 ? "−" : "±"}${s}${suffix}`;
}

const TE_LABELS: Record<string, string> = {
  RECOVERY: "Recovery",
  AEROBIC_BASE: "Aerobic base",
  TEMPO: "Tempo",
  LACTATE_THRESHOLD: "Lactate threshold",
  VO2MAX: "VO2 max",
  ANAEROBIC_CAPACITY: "Anaerobic capacity",
  SPRINT: "Sprint",
  NO_BENEFIT: "No benefit",
};

/** Garmin training-effect label → readable text. */
export function teLabel(key: string | null | undefined): string {
  if (!key) return DASH;
  return TE_LABELS[key] ?? titleCase(key);
}

/** Trailing moving average for display smoothing (nulls stay null). */
export function smooth(values: (number | null)[], window: number): (number | null)[] {
  if (window <= 1) return values;
  const out: (number | null)[] = [];
  let sum = 0;
  let n = 0;
  const q: (number | null)[] = [];
  for (const v of values) {
    q.push(v);
    if (v !== null) {
      sum += v;
      n += 1;
    }
    if (q.length > window) {
      const old = q.shift();
      if (old !== null && old !== undefined) {
        sum -= old;
        n -= 1;
      }
    }
    out.push(v === null || n === 0 ? null : sum / n);
  }
  return out;
}

export function titleCase(key: string | null | undefined): string {
  if (!key) return DASH;
  return key
    .toLowerCase()
    .split(/[_\s]+/)
    .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
    .join(" ");
}
