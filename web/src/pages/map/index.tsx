import { Link } from "@tanstack/react-router";
import { clsx } from "clsx";
import type { Map as MapLibreMap } from "maplibre-gl";
import {
  ArrowUpRight,
  Grid3x3,
  LocateFixed,
  Route,
  Ruler,
  Shapes,
  SquareDashed,
  X,
} from "lucide-react";
import { useMemo, useState } from "react";
import { api, type Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import { MapView, type MapLayer } from "@/components/MapView";
import { SportBadge } from "@/components/SportIcon";
import {
  Card,
  EmptyState,
  ErrorState,
  LegendItem,
  PageHeader,
  Segmented,
  Skeleton,
  StatTile,
} from "@/components/ui";
import { axisTooltip, GRID, line, tooltipRow, tooltipTitle, valueYAxis } from "@/lib/charts";
import { fmtDate, fmtDistance, fmtNumber, type UnitSystem } from "@/lib/format";
import { boundsOf } from "@/lib/geo";
import { useMode, useUnits } from "@/lib/preferences";
import { useRange } from "@/lib/range";
import { bySlot, sportColor, sportLabel } from "@/lib/sports";
import { BLUE, CATEGORICAL, CHROME, SEQUENTIAL, wash, type Mode } from "@/lib/tokens";
import {
  EMPTY,
  maxClusterTiles,
  placeFeature,
  pointFeatures,
  routeFeatures,
  squareFeature,
  tileFeatures,
  tilesBounds,
  tileWidthM,
  trackFeature,
} from "./geo";

type Track = Schemas["MapTrack"];
type Tiles = Schemas["MapTiles"];
type Place = Schemas["MapPlace"];
type View = "routes" | "heatmap" | "explorer";
type FC = MapLayer["data"];

const VIEWS = [
  { value: "routes", label: "Routes" },
  { value: "heatmap", label: "Heatmap" },
  { value: "explorer", label: "Explorer" },
] as const;

/** Sports are told apart by colour only when few are visible (all-pairs views like a map). */
const MAX_SPORT_COLOURS = 3;

function subtitle(view: View, bySport: boolean): string {
  if (view === "heatmap") return "Where you go most: density of every recorded track point.";
  if (view === "explorer")
    return "Zoom-14 map tiles you have visited (all time). The outlined block is your max square.";
  return bySport
    ? "Every GPS track, coloured by sport; overlaps glow brighter. Click a route for details."
    : "Every GPS track; overlaps glow brighter where you go often. Click a route for details, or pick a sport below to see only its routes.";
}

function tileColors(mode: Mode) {
  return mode === "dark"
    ? { visited: BLUE[550]!, cluster: BLUE[300]! }
    : { visited: BLUE[300]!, cluster: BLUE[550]! };
}

function heatRamp(mode: Mode): string[] {
  return [...SEQUENTIAL[mode]];
}

function buildLayers(
  view: View,
  mode: Mode,
  data: { routes: FC; count: number; heat: FC; tiles: FC; square: FC; selected: FC; focus: FC },
): MapLayer[] {
  const surface = CHROME[mode].surface;
  const ink = CHROME[mode].text;
  const tc = tileColors(mode);
  const ramp = heatRamp(mode);
  const focus: MapLayer = {
    id: "place-focus",
    type: "circle",
    data: data.focus,
    paint: {
      "circle-radius": 11,
      "circle-color": wash(CATEGORICAL[mode][0]!, 0.25),
      "circle-stroke-color": ink,
      "circle-stroke-width": 2,
    },
  };
  if (view === "explorer")
    return [
      {
        id: "tiles-fill",
        type: "fill",
        data: data.tiles,
        paint: {
          "fill-color": ["match", ["get", "kind"], "cluster", tc.cluster, tc.visited],
          "fill-opacity": ["match", ["get", "kind"], "cluster", 0.62, 0.42],
          "fill-outline-color": surface,
        },
      },
      {
        id: "tiles-square-casing",
        type: "line",
        data: data.square,
        paint: { "line-color": surface, "line-width": 6, "line-opacity": 0.9 },
        layout: { "line-join": "round" },
      },
      {
        id: "tiles-square",
        type: "line",
        data: data.square,
        paint: { "line-color": ink, "line-width": 2.5 },
        layout: { "line-join": "round" },
      },
      focus,
    ];
  if (view === "heatmap")
    return [
      {
        id: "heat",
        type: "heatmap",
        data: data.heat,
        paint: {
          "heatmap-weight": 0.22,
          "heatmap-intensity": [
            "interpolate",
            ["linear"],
            ["zoom"],
            4,
            0.25,
            9,
            0.6,
            13,
            1.4,
            16,
            3,
          ],
          "heatmap-radius": ["interpolate", ["linear"], ["zoom"], 4, 2, 9, 5, 13, 10, 16, 22],
          "heatmap-opacity": mode === "dark" ? 0.9 : 0.8,
          "heatmap-color": [
            "interpolate",
            ["linear"],
            ["heatmap-density"],
            0,
            wash(ramp[1]!, 0),
            0.06,
            wash(ramp[1]!, 0.45),
            0.25,
            ramp[1],
            0.5,
            ramp[2],
            0.75,
            ramp[3],
            1,
            ramp[4],
          ],
        },
      },
      focus,
    ];
  return [
    {
      id: "routes",
      type: "line",
      data: data.routes,
      paint: {
        "line-color": ["get", "color"],
        "line-width": ["interpolate", ["linear"], ["zoom"], 5, 0.8, 10, 1.3, 14, 2.4, 17, 4],
        // Few routes barely overlap, so they need more ink to read as a glow.
        "line-opacity":
          data.count < 40 ? 0.8 : data.count < 160 ? 0.6 : mode === "dark" ? 0.45 : 0.38,
        "line-blur": mode === "dark" ? 0.4 : 0,
      },
      layout: { "line-cap": "round", "line-join": "round" },
    },
    {
      id: "route-selected-casing",
      type: "line",
      data: data.selected,
      paint: {
        "line-color": surface,
        "line-width": ["interpolate", ["linear"], ["zoom"], 5, 4, 14, 8],
        "line-opacity": 0.95,
      },
      layout: { "line-cap": "round", "line-join": "round" },
    },
    {
      id: "route-selected",
      type: "line",
      data: data.selected,
      paint: {
        "line-color": ["get", "color"],
        "line-width": ["interpolate", ["linear"], ["zoom"], 5, 2, 14, 4],
      },
      layout: { "line-cap": "round", "line-join": "round" },
    },
    focus,
    {
      // Invisible wide twin of the routes so thin lines are easy to click (opacity 0 is
      // not drawn but still queryable).
      id: "routes-hit",
      type: "line",
      data: data.routes,
      paint: { "line-color": surface, "line-width": 14, "line-opacity": 0 },
      layout: { "line-cap": "round", "line-join": "round" },
    },
  ];
}

interface SportRow {
  group: string;
  activities: number;
  distance: number;
}

function sportRows(tracks: Track[]): SportRow[] {
  const by = new Map<string, SportRow>();
  for (const t of tracks) {
    const row = by.get(t.sport_group) ?? { group: t.sport_group, activities: 0, distance: 0 };
    row.activities += 1;
    row.distance += t.distance_m ?? 0;
    by.set(t.sport_group, row);
  }
  return [...by.values()].sort((a, b) => bySlot(a.group, b.group));
}

function areaText(m2: number, units: UnitSystem): string {
  return units === "metric" ? `${fmtNumber(m2 / 1e6)} km²` : `${fmtNumber(m2 / 2_589_988.11)} mi²`;
}

function coordText(lat: number, lon: number): string {
  return `${Math.abs(lat).toFixed(3)}° ${lat >= 0 ? "N" : "S"}, ${Math.abs(lon).toFixed(3)}° ${lon >= 0 ? "E" : "W"}`;
}

function Legend({
  view,
  sports,
  bySport,
  hasSelection,
  mode,
  className,
}: {
  view: View;
  sports: SportRow[];
  bySport: boolean;
  hasSelection: boolean;
  mode: Mode;
  className: string;
}) {
  const tc = tileColors(mode);
  const ramp = heatRamp(mode);
  return (
    <div className={className}>
      {view === "routes" && !bySport && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <LegendItem color={CATEGORICAL[mode][0]!} label="Route" shape="line" />
          {hasSelection && (
            <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
              <span aria-hidden className="inline-block h-0.5 w-4 rounded-bar bg-ink" />
              Selected
            </span>
          )}
          <span className="text-xs text-ink-3">brighter where routes overlap</span>
        </div>
      )}
      {view === "routes" && bySport && (
        <div className="flex flex-wrap gap-x-3 gap-y-1">
          {sports.map((s) => (
            <LegendItem
              key={s.group}
              color={sportColor(s.group, mode)}
              label={sportLabel(s.group)}
              shape="line"
            />
          ))}
        </div>
      )}
      {view === "heatmap" && (
        <div className="flex items-center gap-2 text-xs text-ink-2">
          <span>Rarely</span>
          <span
            aria-hidden
            className="h-2 w-28 rounded-bar"
            style={{ background: `linear-gradient(90deg, ${ramp.slice(1).join(", ")})` }}
          />
          <span>Often</span>
        </div>
      )}
      {view === "explorer" && (
        <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
          <LegendItem color={wash(tc.visited, 0.75)} label="Visited tile" />
          <LegendItem color={tc.cluster} label="Max cluster" />
          <span className="inline-flex items-center gap-1.5 text-xs text-ink-2">
            <span
              aria-hidden
              className="inline-block size-2.5 rounded-swatch border-2 border-ink"
            />
            Max square
          </span>
        </div>
      )}
    </div>
  );
}

function RoutePanel({ track, onClose }: { track: Track; onClose: () => void }) {
  const units = useUnits();
  return (
    <div className="absolute top-2 left-2 w-[min(18rem,calc(100%-4rem))] rounded-card border border-line bg-surface p-3 shadow-overlay">
      <div className="flex items-start gap-2.5">
        <SportBadge group={track.sport_group} size={34} />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-semibold text-ink">
            {track.name ?? sportLabel(track.sport_group)}
          </p>
          <p className="text-xs text-ink-3">
            {fmtDate(track.day, {
              weekday: "short",
              day: "numeric",
              month: "short",
              year: "numeric",
            })}
            {track.distance_m ? ` · ${fmtDistance(track.distance_m, units)}` : ""}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close route details"
          className="-mt-1 -mr-1 rounded-control p-1.5 text-ink-3 hover:bg-hover hover:text-ink"
        >
          <X size={15} aria-hidden />
        </button>
      </div>
      <Link
        to="/activities/$activityId"
        params={{ activityId: String(track.activity_id) }}
        className="mt-2.5 inline-flex items-center gap-1 rounded-control border border-line px-2.5 py-1 text-xs font-medium text-ink-2 hover:bg-hover hover:text-ink"
      >
        Open activity <ArrowUpRight size={14} aria-hidden className="text-accent" />
      </Link>
    </div>
  );
}

interface TilePick {
  x: number;
  y: number;
  visits: number;
  first: string;
  kind: string;
}

function TilePanel({
  tile,
  inSquare,
  onClose,
}: {
  tile: TilePick;
  inSquare: boolean;
  onClose: () => void;
}) {
  const notes = [
    tile.kind === "cluster" ? "part of your max cluster" : null,
    inSquare ? "inside your max square" : null,
  ].filter(Boolean);
  return (
    <div className="absolute top-2 left-2 w-[min(17rem,calc(100%-4rem))] rounded-card border border-line bg-surface p-3 shadow-overlay">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-ink">
            {fmtNumber(tile.visits)} {tile.visits === 1 ? "visit" : "visits"}
          </p>
          <p className="text-xs text-ink-3">
            First visited {fmtDate(tile.first)} · tile {tile.x}/{tile.y}
          </p>
          {notes.length > 0 && (
            <p className="mt-1 text-xs text-ink-2">
              {notes.join(", ").replace(/^./, (ch) => ch.toUpperCase())}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Close tile details"
          className="-mt-1 -mr-1 rounded-control p-1.5 text-ink-3 hover:bg-hover hover:text-ink"
        >
          <X size={15} aria-hidden />
        </button>
      </div>
    </div>
  );
}

function SportsCard({ rows, active }: { rows: SportRow[]; active: string | null }) {
  const mode = useMode();
  const units = useUnits();
  const range = useRange("90d");
  const total = rows.reduce((s, r) => s + r.distance, 0) || 1;
  return (
    <Card
      title="Sports on the map"
      subtitle={
        active
          ? "Filtered to one sport; click it again to show all"
          : "Click a sport to show only its routes"
      }
    >
      {rows.length === 0 ? (
        <EmptyState title="No GPS tracks in this period" />
      ) : (
        <ul className="flex flex-col gap-1">
          {rows.map((r) => {
            const color = sportColor(r.group, mode);
            const pressed = active === r.group;
            return (
              <li key={r.group}>
                <button
                  type="button"
                  aria-pressed={pressed}
                  onClick={() => range.setSport(pressed ? null : r.group)}
                  className={clsx(
                    "flex w-full items-center gap-3 rounded-control px-2 py-2 text-left transition-colors hover:bg-hover",
                    pressed && "bg-surface-2",
                  )}
                >
                  <SportBadge group={r.group} size={30} />
                  <span className="min-w-0 flex-1">
                    <span className="flex items-baseline justify-between gap-2">
                      <span className="truncate text-sm font-medium text-ink">
                        {sportLabel(r.group)}
                      </span>
                      <span className="text-sm text-ink tabular">
                        {fmtDistance(r.distance, units, 0)}
                      </span>
                    </span>
                    <span className="mt-1 flex items-center gap-2">
                      <span className="h-1.5 flex-1 overflow-hidden rounded-bar bg-surface-3">
                        <span
                          aria-hidden
                          className="block h-full rounded-bar"
                          style={{ width: `${(r.distance / total) * 100}%`, background: color }}
                        />
                      </span>
                      <span className="w-20 text-right text-xs text-ink-3 tabular">
                        {fmtNumber(r.activities)} {r.activities === 1 ? "route" : "routes"}
                      </span>
                    </span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </Card>
  );
}

function PlacesCard({
  places,
  onFocus,
  focused,
}: {
  places: Place[] | undefined;
  onFocus: (p: Place) => void;
  focused: Place | null;
}) {
  const top = (places ?? []).slice(0, 6);
  const max = top[0]?.activities ?? 1;
  return (
    <Card
      title="Favourite start places"
      subtitle="Starts within 150 m of each other count as one place"
    >
      {!places ? (
        <Skeleton height={220} />
      ) : top.length === 0 ? (
        <EmptyState title="No start points in this period" />
      ) : (
        <ol className="flex flex-col gap-1">
          {top.map((p, i) => {
            const isFocused = focused?.lat === p.lat && focused?.lon === p.lon;
            return (
              <li key={`${p.lat},${p.lon}`} className="flex items-center gap-3 px-1 py-1.5">
                <span className="min-w-0 flex-1">
                  <span className="flex items-baseline justify-between gap-2">
                    <span className="text-sm font-medium text-ink">Place {i + 1}</span>
                    <span className="text-sm text-ink-2 tabular">
                      {fmtNumber(p.activities)} {p.activities === 1 ? "start" : "starts"}
                    </span>
                  </span>
                  <span className="mt-1 block h-1.5 overflow-hidden rounded-bar bg-surface-3">
                    <span
                      aria-hidden
                      className="block h-full rounded-bar bg-accent"
                      style={{ width: `${(p.activities / max) * 100}%` }}
                    />
                  </span>
                  <span className="mt-1 block truncate text-2xs text-ink-3 tabular">
                    {coordText(p.lat, p.lon)}
                  </span>
                </span>
                <button
                  type="button"
                  onClick={() => onFocus(p)}
                  aria-label={`Show place ${i + 1} on the map`}
                  aria-pressed={isFocused}
                  title="Show on the map"
                  className={clsx(
                    "rounded-control p-1.5 hover:bg-hover hover:text-ink",
                    isFocused ? "text-accent" : "text-ink-3",
                  )}
                >
                  <LocateFixed size={16} aria-hidden />
                </button>
              </li>
            );
          })}
        </ol>
      )}
    </Card>
  );
}

function ExplorationCard({ tiles }: { tiles: Tiles | undefined }) {
  const mode = useMode();
  const option = useMemo<ChartOption | null>(() => {
    if (!tiles || tiles.tiles.length === 0) return null;
    const perMonth = new Map<string, number>();
    for (const t of tiles.tiles) {
      const m = t.first_visit.slice(0, 7);
      perMonth.set(m, (perMonth.get(m) ?? 0) + 1);
    }
    const months = [...perMonth.keys()].sort();
    const first = months[0]!;
    const last = months[months.length - 1]!;
    const points: { value: [number, number]; added: number }[] = [];
    let total = 0;
    for (let d = new Date(`${first}-01T12:00:00`); ; d.setMonth(d.getMonth() + 1)) {
      const k = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}`;
      const added = perMonth.get(k) ?? 0;
      total += added;
      points.push({ value: [d.getTime(), total], added });
      if (k >= last) break;
    }
    const color = CATEGORICAL[mode][0]!;
    return {
      grid: { ...GRID, top: 24, right: 44 },
      tooltip: axisTooltip((p) => {
        const arr = p as { data: { value: [number, number]; added: number } }[];
        const it = arr[0]?.data;
        if (!it) return "";
        const month = new Date(it.value[0]).toLocaleDateString(undefined, {
          month: "long",
          year: "numeric",
        });
        return (
          tooltipTitle(month) +
          tooltipRow(color, "New tiles", `+${fmtNumber(it.added)}`) +
          tooltipRow(CHROME[mode].muted, "Total", fmtNumber(it.value[1]))
        );
      }),
      xAxis: { type: "time", splitNumber: 4 },
      yAxis: valueYAxis("tiles", (v) => fmtNumber(v)),
      series: [
        {
          ...line("Tiles visited", points, color, { area: true }),
          step: "end",
          endLabel: {
            show: true,
            color: CHROME[mode].text,
            fontWeight: 600,
            formatter: (p: { value: [number, number] }) => fmtNumber(p.value[1]),
          },
        },
      ],
    };
  }, [tiles, mode]);
  return (
    <Card
      title="Exploration over time"
      subtitle="Distinct zoom-14 tiles visited, cumulative (all time)"
    >
      {!tiles ? (
        <Skeleton height={280} />
      ) : !option ? (
        <EmptyState title="No explorer tiles yet" />
      ) : (
        <Chart
          option={option}
          height={280}
          ariaLabel="Cumulative explorer tiles visited per month"
        />
      )}
    </Card>
  );
}

export default function MapPage() {
  const range = useRange("90d");
  const mode = useMode();
  const units = useUnits();
  const [view, setView] = useState<View>("routes");
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const [tilePick, setTilePick] = useState<TilePick | null>(null);
  const [focus, setFocus] = useState<Place | null>(null);
  const [map, setMap] = useState<MapLibreMap | null>(null);

  const query = { ...range.query, ...(range.sport ? { sport: range.sport } : {}) };
  const tracksQ = api.useQuery(
    "get",
    "/api/map/tracks",
    { params: { query: { ...query, detail: "low" } } },
    { enabled: range.ready },
  );
  const tilesQ = api.useQuery("get", "/api/map/tiles", { params: { query: { zoom: 14 } } });
  const placesQ = api.useQuery(
    "get",
    "/api/map/places",
    { params: { query } },
    { enabled: range.ready },
  );

  const tracks = tracksQ.data;
  const tiles = tilesQ.data;

  const geo = useMemo(() => {
    const t = tracks ?? [];
    const zoom = tiles?.zoom ?? 14;
    const cluster = maxClusterTiles(tiles?.tiles ?? []);
    const rows = sportRows(t);
    const bySport = rows.length <= MAX_SPORT_COLOURS;
    const accent = CATEGORICAL[mode][0]!;
    return {
      bySport,
      byId: new Map(t.map((x) => [x.activity_id, x])),
      routes: routeFeatures(t, (g) => (bySport ? sportColor(g, mode) : accent)),
      tiles: tileFeatures(tiles?.tiles ?? [], zoom, cluster),
      square: squareFeature(tiles?.max_square ?? null, zoom),
      trackBounds: boundsOf(t.map((x) => x.points)),
      tileBounds: tilesBounds(tiles?.tiles ?? [], zoom),
      rows,
      distance: t.reduce((s, x) => s + (x.distance_m ?? 0), 0),
    };
  }, [tracks, tiles, mode]);
  const heat = useMemo(
    () => (view === "heatmap" && tracks ? pointFeatures(tracks) : EMPTY),
    [view, tracks],
  );

  const selectedTrack = selectedId !== null ? geo.byId.get(selectedId) : undefined;
  const layers = useMemo(
    () =>
      buildLayers(view, mode, {
        routes: geo.routes,
        count: tracks?.length ?? 0,
        heat,
        tiles: geo.tiles,
        square: geo.square,
        selected: trackFeature(
          selectedTrack,
          geo.bySport ? sportColor(selectedTrack?.sport_group ?? "", mode) : CHROME[mode].text,
        ),
        focus: placeFeature(focus),
      }),
    [view, mode, geo, heat, selectedTrack, focus, tracks],
  );
  const bounds = useMemo(
    () =>
      view === "explorer"
        ? (geo.tileBounds ?? geo.trackBounds)
        : (geo.trackBounds ?? geo.tileBounds),
    [view, geo],
  );

  const changeView = (v: View) => {
    setView(v);
    setSelectedId(null);
    setTilePick(null);
  };

  const square = tiles?.max_square ?? null;
  const tileW = tileWidthM(square?.y ?? tiles?.tiles[0]?.y ?? 0, tiles?.zoom ?? 14);
  const inSquare = (t: TilePick) =>
    !!square &&
    t.x >= square.x &&
    t.x < square.x + square.size &&
    t.y >= square.y &&
    t.y < square.y + square.size;

  const loading = tracksQ.isPending || tilesQ.isPending;
  const noData = !loading && (tracks?.length ?? 0) === 0 && (tiles?.total ?? 0) === 0;

  return (
    <>
      <PageHeader
        title="Map"
        description={`Every route you have recorded · ${fmtDate(range.start)} – ${fmtDate(range.end)}${range.sport ? ` · ${sportLabel(range.sport)}` : ""}`}
      />
      <div className="flex flex-col gap-5">
        <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
          {loading ? (
            Array.from({ length: 5 }, (_, i) => (
              <Skeleton key={i} height={96} className={i === 4 ? "col-span-2 md:col-span-1" : ""} />
            ))
          ) : (
            <>
              <StatTile
                label="Activities shown"
                icon={<Route size={14} aria-hidden className="text-ink-3" />}
                value={fmtNumber(tracks?.length ?? 0)}
                sub={`${geo.rows.length} ${geo.rows.length === 1 ? "sport" : "sports"} with GPS`}
              />
              <StatTile
                label="Total distance"
                icon={<Ruler size={14} aria-hidden className="text-ink-3" />}
                value={fmtDistance(geo.distance, units, 0).split(" ")[0]}
                unit={fmtDistance(geo.distance, units, 0).split(" ")[1]}
                sub="on the map"
              />
              <StatTile
                label="Tiles visited"
                icon={<Grid3x3 size={14} aria-hidden className="text-ink-3" />}
                value={fmtNumber(tiles?.total ?? 0)}
                sub={`all time · ≈ ${fmtDistance(tileW, units, 1)} each`}
              />
              <StatTile
                label="Max square"
                icon={<SquareDashed size={14} aria-hidden className="text-ink-3" />}
                value={square ? `${square.size}×${square.size}` : "–"}
                sub={
                  square
                    ? `≈ ${fmtDistance(square.size * tileW, units, 1)} across`
                    : "no square yet"
                }
              />
              <StatTile
                className="col-span-2 md:col-span-1"
                label="Max cluster"
                icon={<Shapes size={14} aria-hidden className="text-ink-3" />}
                value={fmtNumber(tiles?.max_cluster ?? 0)}
                unit="tiles"
                sub={`≈ ${areaText((tiles?.max_cluster ?? 0) * tileW * tileW, units)} fully explored`}
              />
            </>
          )}
        </div>

        <Card
          title="Your map"
          subtitle={subtitle(view, geo.bySport)}
          actions={
            <Segmented label="Map view" value={view} onChange={changeView} options={VIEWS} />
          }
        >
          {tracksQ.error ? (
            <ErrorState error={tracksQ.error} />
          ) : loading ? (
            <Skeleton height={520} />
          ) : noData ? (
            <EmptyState title="No GPS tracks yet">
              Activities recorded with GPS show up here once they are synced.
            </EmptyState>
          ) : (
            <div className="relative h-[60vh] min-h-[320px] lg:h-[72vh] lg:min-h-[520px]">
              <MapView
                layers={layers}
                bounds={bounds}
                height="100%"
                ariaLabel={`Map of ${fmtNumber(tracks?.length ?? 0)} routes, ${view} view`}
                onReady={setMap}
                onFeatureClick={(layer, props) => {
                  if (layer === "routes-hit") {
                    setSelectedId(Number(props.id));
                    setTilePick(null);
                  } else if (layer === "tiles-fill") {
                    setTilePick({
                      x: Number(props.x),
                      y: Number(props.y),
                      visits: Number(props.visits),
                      first: String(props.first),
                      kind: String(props.kind),
                    });
                  }
                }}
              />
              {view !== "explorer" && (tracks?.length ?? 0) === 0 && (
                <div className="absolute inset-x-0 top-1/3 mx-auto w-fit max-w-[80%] rounded-card border border-line bg-surface px-4 py-3 text-center text-sm text-ink-2 shadow-overlay">
                  No GPS tracks in this period. Try a longer range or the Explorer view.
                </div>
              )}
              {view === "routes" && selectedTrack && (
                <RoutePanel track={selectedTrack} onClose={() => setSelectedId(null)} />
              )}
              {view === "explorer" && tilePick && (
                <TilePanel
                  tile={tilePick}
                  inSquare={inSquare(tilePick)}
                  onClose={() => setTilePick(null)}
                />
              )}
              <Legend
                view={view}
                sports={geo.rows}
                bySport={geo.bySport}
                hasSelection={!!selectedTrack}
                mode={mode}
                className="pointer-events-none absolute bottom-2 left-2 hidden max-w-[calc(100%-4rem)] rounded-card border border-line bg-surface px-3 py-2 shadow-overlay sm:block"
              />
            </div>
          )}
          {!loading && !noData && (
            <Legend
              view={view}
              sports={geo.rows}
              bySport={geo.bySport}
              hasSelection={!!selectedTrack}
              mode={mode}
              className="mt-3 sm:hidden"
            />
          )}
        </Card>

        <div className="grid gap-5 lg:grid-cols-3">
          {loading ? (
            <Skeleton height={260} />
          ) : (
            <SportsCard rows={geo.rows} active={range.sport} />
          )}
          {placesQ.error ? (
            <ErrorState error={placesQ.error} />
          ) : (
            <PlacesCard
              places={placesQ.data}
              focused={focus}
              onFocus={(p) => {
                setFocus(p);
                map?.flyTo({ center: [p.lon, p.lat], zoom: 13.5, duration: 900 });
              }}
            />
          )}
          {tilesQ.error ? <ErrorState error={tilesQ.error} /> : <ExplorationCard tiles={tiles} />}
        </div>
        <p className="text-xs text-ink-3">
          Routes are simplified to at most 120 points each. Explorer tiles count every activity,
          independent of the date and sport filter.
        </p>
      </div>
    </>
  );
}
