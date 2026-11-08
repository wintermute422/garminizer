/**
 * Page-local geo helpers for the map page: slippy-tile maths, GeoJSON builders for routes,
 * heatmap points and explorer tiles, and the explorer "max cluster" (computed locally so the
 * cluster can be drawn; the API only returns its size).
 */
import type { Feature, FeatureCollection, LineString, Point, Polygon } from "geojson";
import type { Schemas } from "@/api/client";
import type { Bounds } from "@/lib/geo";

type Track = Schemas["MapTrack"];
type Tile = Schemas["MapTile"];
type Square = Schemas["MapSquare"];

export const EMPTY: FeatureCollection = { type: "FeatureCollection", features: [] };

export function tileLon(x: number, z: number): number {
  return (x / 2 ** z) * 360 - 180;
}

export function tileLat(y: number, z: number): number {
  const n = Math.PI - (2 * Math.PI * y) / 2 ** z;
  return (180 / Math.PI) * Math.atan(Math.sinh(n));
}

/** Closed ring (lon/lat) around the block of w × h tiles whose top-left tile is (x, y). */
export function tileRing(x: number, y: number, z: number, w = 1, h = 1): [number, number][] {
  const west = tileLon(x, z);
  const east = tileLon(x + w, z);
  const north = tileLat(y, z);
  const south = tileLat(y + h, z);
  return [
    [west, north],
    [east, north],
    [east, south],
    [west, south],
    [west, north],
  ];
}

/** Ground width of one tile at the tile's latitude, in metres. */
export function tileWidthM(y: number, z: number): number {
  const lat = (tileLat(y, z) + tileLat(y + 1, z)) / 2;
  return (40_075_016.686 * Math.cos((lat * Math.PI) / 180)) / 2 ** z;
}

const key = (x: number, y: number) => `${x}/${y}`;

/** Tiles of the largest 4-connected group of tiles whose 4 neighbours are all visited. */
export function maxClusterTiles(tiles: Tile[]): Set<string> {
  const visited = new Set(tiles.map((t) => key(t.x, t.y)));
  const around = (x: number, y: number): [number, number][] => [
    [x - 1, y],
    [x + 1, y],
    [x, y - 1],
    [x, y + 1],
  ];
  const inner = new Set(
    tiles
      .filter((t) => around(t.x, t.y).every(([a, b]) => visited.has(key(a, b))))
      .map((t) => key(t.x, t.y)),
  );
  let best = new Set<string>();
  const seen = new Set<string>();
  for (const start of inner) {
    if (seen.has(start)) continue;
    seen.add(start);
    const group = new Set<string>([start]);
    const queue = [start];
    while (queue.length) {
      const [x, y] = queue.pop()!.split("/").map(Number) as [number, number];
      for (const [a, b] of around(x, y)) {
        const k = key(a, b);
        if (inner.has(k) && !seen.has(k)) {
          seen.add(k);
          group.add(k);
          queue.push(k);
        }
      }
    }
    if (group.size > best.size) best = group;
  }
  return best;
}

export function tileFeatures(tiles: Tile[], zoom: number, cluster: Set<string>): FeatureCollection {
  const features: Feature<Polygon>[] = tiles.map((t) => ({
    type: "Feature",
    properties: {
      kind: cluster.has(key(t.x, t.y)) ? "cluster" : "visited",
      x: t.x,
      y: t.y,
      visits: t.visits,
      first: t.first_visit,
    },
    geometry: { type: "Polygon", coordinates: [tileRing(t.x, t.y, zoom)] },
  }));
  return { type: "FeatureCollection", features };
}

export function squareFeature(square: Square | null, zoom: number): FeatureCollection {
  if (!square || square.size < 1) return EMPTY;
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: {
          type: "LineString",
          coordinates: tileRing(square.x, square.y, zoom, square.size, square.size),
        },
      },
    ],
  };
}

export function tilesBounds(tiles: Tile[], zoom: number): Bounds | null {
  if (!tiles.length) return null;
  const xs = tiles.map((t) => t.x);
  const ys = tiles.map((t) => t.y);
  const [x0, x1, y0, y1] = [Math.min(...xs), Math.max(...xs) + 1, Math.min(...ys), Math.max(...ys)];
  return [
    [tileLon(x0, zoom), tileLat(y1 + 1, zoom)],
    [tileLon(x1, zoom), tileLat(y0, zoom)],
  ];
}

/** Routes as GeoJSON lines; rarer sports are drawn last so they stay visible on top. */
export function routeFeatures(
  tracks: Track[],
  colorOf: (group: string) => string,
): FeatureCollection {
  const count = new Map<string, number>();
  for (const t of tracks) count.set(t.sport_group, (count.get(t.sport_group) ?? 0) + 1);
  const ordered = [...tracks].sort(
    (a, b) => (count.get(b.sport_group) ?? 0) - (count.get(a.sport_group) ?? 0),
  );
  const features: Feature<LineString>[] = [];
  for (const t of ordered) {
    if (t.points.length < 2) continue;
    features.push({
      type: "Feature",
      properties: { id: t.activity_id, color: colorOf(t.sport_group) },
      geometry: { type: "LineString", coordinates: t.points.map(([lat, lon]) => [lon!, lat!]) },
    });
  }
  return { type: "FeatureCollection", features };
}

export function trackFeature(track: Track | undefined, color: string): FeatureCollection {
  if (!track || track.points.length < 2) return EMPTY;
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: { color },
        geometry: {
          type: "LineString",
          coordinates: track.points.map(([lat, lon]) => [lon!, lat!]),
        },
      },
    ],
  };
}

export function pointFeatures(tracks: Track[]): FeatureCollection {
  const features: Feature<Point>[] = [];
  for (const t of tracks)
    for (const [lat, lon] of t.points)
      features.push({
        type: "Feature",
        properties: {},
        geometry: { type: "Point", coordinates: [lon!, lat!] },
      });
  return { type: "FeatureCollection", features };
}

export function placeFeature(place: { lat: number; lon: number } | null): FeatureCollection {
  if (!place) return EMPTY;
  return {
    type: "FeatureCollection",
    features: [
      {
        type: "Feature",
        properties: {},
        geometry: { type: "Point", coordinates: [place.lon, place.lat] },
      },
    ],
  };
}
