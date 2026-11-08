/**
 * Wall-clock helpers in the athlete's time zone (the API stores UTC instants; the overview shows
 * them as the athlete's local time regardless of the browser's zone). Candidates for lib/format.
 */

const PARTS = new Map<string, Intl.DateTimeFormat>();

/** The zone if the runtime knows it, else undefined (= browser zone). */
export function validZone(tz: string | null | undefined): string | undefined {
  if (!tz) return undefined;
  try {
    new Intl.DateTimeFormat(undefined, { timeZone: tz });
    return tz;
  } catch {
    return undefined;
  }
}

function partsFormat(tz: string | undefined): Intl.DateTimeFormat {
  const key = tz ?? "";
  let f = PARTS.get(key);
  if (!f) {
    f = new Intl.DateTimeFormat("en-CA", {
      timeZone: tz,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hourCycle: "h23",
    });
    PARTS.set(key, f);
  }
  return f;
}

/** Hours since local midnight of `day` (negative the evening before, > 24 the day after). */
export function hoursIntoDay(iso: string, day: string, tz: string | undefined): number {
  const p: Record<string, string> = {};
  for (const part of partsFormat(tz).formatToParts(new Date(iso))) p[part.type] = part.value;
  const local = `${p.year}-${p.month}-${p.day}`;
  let h = Number(p.hour) + Number(p.minute) / 60;
  if (local < day) h -= 24;
  else if (local > day) h += 24;
  return h;
}

/** "07:28" — local wall-clock time of a UTC instant. */
export function fmtClock(iso: string | null | undefined, tz: string | undefined): string {
  if (!iso) return "–";
  return new Date(iso).toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    timeZone: tz,
  });
}

/** "07:30" for a fractional hour of the day. */
export function fmtHourOfDay(h: number): string {
  const total = Math.round((((h % 24) + 24) % 24) * 60);
  return `${String(Math.floor(total / 60) % 24).padStart(2, "0")}:${String(total % 60).padStart(2, "0")}`;
}
