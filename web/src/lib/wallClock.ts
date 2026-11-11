/**
 * The athlete's wall clock: UTC instants shifted into the athlete's time zone and expressed as
 * UTC epochs, so intraday charts (`useUTC: true`) show local time whatever the browser's zone is.
 */

export const HOUR_MS = 3_600_000;

const dtfCache = new Map<string, Intl.DateTimeFormat | null>();

function formatter(tz: string): Intl.DateTimeFormat | null {
  if (!dtfCache.has(tz)) {
    try {
      dtfCache.set(
        tz,
        new Intl.DateTimeFormat("en-US", {
          timeZone: tz,
          hourCycle: "h23",
          year: "numeric",
          month: "numeric",
          day: "numeric",
          hour: "numeric",
          minute: "numeric",
          second: "numeric",
        }),
      );
    } catch {
      dtfCache.set(tz, null);
    }
  }
  return dtfCache.get(tz) ?? null;
}

function offsetAt(tz: string, utcMs: number): number {
  const f = formatter(tz);
  if (!f) return 0;
  const parts = f.formatToParts(new Date(utcMs));
  const get = (type: string) => Number(parts.find((p) => p.type === type)?.value ?? 0);
  const asUtc = Date.UTC(
    get("year"),
    get("month") - 1,
    get("day"),
    get("hour") % 24,
    get("minute"),
    get("second"),
  );
  return asUtc - Math.floor(utcMs / 1000) * 1000;
}

/**
 * UTC instant → the athlete's local wall-clock time expressed as a UTC epoch. Charts that use
 * it set `useUTC: true`, so axes and tooltips show the athlete's local time whatever the
 * browser's time zone is.
 */
export function wallClock(tz: string | null | undefined): (iso: string) => number {
  const zone = tz || "UTC";
  const cache = new Map<number, number>();
  return (iso: string) => {
    const t = Date.parse(iso);
    const hour = Math.floor(t / HOUR_MS);
    let off = cache.get(hour);
    if (off === undefined) {
      off = offsetAt(zone, hour * HOUR_MS);
      cache.set(hour, off);
    }
    return t + off;
  };
}

/** Local midnight of an ISO day in the wall-clock frame (see `wallClock`). */
export function wallMidnight(day: string): number {
  const [y, m, d] = day.split("-").map(Number);
  return Date.UTC(y!, (m ?? 1) - 1, d ?? 1);
}

const pad = (n: number) => String(n).padStart(2, "0");

/** "07:42" of a wall-clock epoch. */
export function fmtWallTime(ms: number): string {
  const d = new Date(ms);
  return `${pad(d.getUTCHours())}:${pad(d.getUTCMinutes())}`;
}

/** Date of a wall-clock epoch, e.g. "Sat 31 Oct". */
export function fmtWallDate(ms: number, opts?: Intl.DateTimeFormatOptions): string {
  return new Date(ms).toLocaleDateString(undefined, {
    ...(opts ?? { weekday: "short", day: "numeric", month: "short" }),
    timeZone: "UTC",
  });
}
