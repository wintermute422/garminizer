/** [[west, south], [east, north]] */
export type Bounds = [[number, number], [number, number]];

/** Bounds of [[lat, lon], ...] point lists. */
export function boundsOf(tracks: number[][][]): Bounds | null {
  let w = 180;
  let s = 90;
  let e = -180;
  let n = -90;
  for (const t of tracks)
    for (const p of t) {
      const [lat, lon] = p as [number, number];
      w = Math.min(w, lon);
      e = Math.max(e, lon);
      s = Math.min(s, lat);
      n = Math.max(n, lat);
    }
  return w <= e
    ? [
        [w, s],
        [e, n],
      ]
    : null;
}
