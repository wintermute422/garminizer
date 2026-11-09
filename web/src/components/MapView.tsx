/**
 * MapLibre wrapper. Basemap follows the theme (styles come from /api/meta, OpenFreeMap by
 * default). Data layers are declarative: pass `layers`; they are re-added after style changes.
 */
import * as maplibregl from "maplibre-gl";
import workerUrl from "maplibre-gl/dist/maplibre-gl-worker.mjs?worker&url";
import type { FeatureCollection } from "geojson";
import { useEffect, useRef } from "react";
import { api } from "@/api/client";
import { useMode } from "@/lib/preferences";
import type { Bounds } from "@/lib/geo";

export type { Bounds };

export interface MapLayer {
  id: string;
  type: "line" | "circle" | "heatmap" | "fill" | "symbol";
  data: FeatureCollection;
  paint?: Record<string, unknown>;
  layout?: Record<string, unknown>;
}

export interface MapViewProps {
  layers: MapLayer[];
  bounds?: Bounds | null;
  height?: number | string;
  className?: string;
  ariaLabel: string;
  interactive?: boolean;
  onFeatureClick?: (layerId: string, properties: Record<string, unknown>) => void;
  onReady?: (map: maplibregl.Map) => void;
}

// MapLibre locates its worker relative to its own module, which bundling breaks; give it
// the worker that Vite bundled (works in dev and in the production build).
maplibregl.setWorkerUrl(workerUrl);

const FALLBACK_LIGHT = "https://tiles.openfreemap.org/styles/positron";
const FALLBACK_DARK = "https://tiles.openfreemap.org/styles/dark";

const OWNED = "__gz_layers";

/** Sync the map with the declared layers: add new, update data/paint/layout, remove stale. */
function applyLayers(map: maplibregl.Map, layers: MapLayer[]) {
  const owned =
    ((map as unknown as Record<string, unknown>)[OWNED] as Set<string> | undefined) ??
    new Set<string>();
  const wanted = new Set(layers.map((l) => l.id));
  for (const id of owned) {
    if (!wanted.has(id)) {
      if (map.getLayer(id)) map.removeLayer(id);
      if (map.getSource(id)) map.removeSource(id);
      owned.delete(id);
    }
  }
  for (const layer of layers) {
    const source = map.getSource(layer.id) as maplibregl.GeoJSONSource | undefined;
    if (source && map.getLayer(layer.id)) {
      source.setData(layer.data);
      type PaintKey = Parameters<maplibregl.Map["setPaintProperty"]>[1];
      type LayoutKey = Parameters<maplibregl.Map["setLayoutProperty"]>[1];
      for (const [k, v] of Object.entries(layer.paint ?? {}))
        map.setPaintProperty(layer.id, k as PaintKey, v as never);
      for (const [k, v] of Object.entries(layer.layout ?? {}))
        map.setLayoutProperty(layer.id, k as LayoutKey, v as never);
    } else {
      if (!source) map.addSource(layer.id, { type: "geojson", data: layer.data });
      map.addLayer({
        id: layer.id,
        type: layer.type,
        source: layer.id,
        ...(layer.paint ? { paint: layer.paint } : {}),
        ...(layer.layout ? { layout: layer.layout } : {}),
      } as maplibregl.LayerSpecification);
    }
    owned.add(layer.id);
  }
  (map as unknown as Record<string, unknown>)[OWNED] = owned;
}

export function MapView({
  layers,
  bounds,
  height = 360,
  className,
  ariaLabel,
  interactive = true,
  onFeatureClick,
  onReady,
}: MapViewProps) {
  const el = useRef<HTMLDivElement>(null);
  const map = useRef<maplibregl.Map | null>(null);
  const mode = useMode();
  const meta = api.useQuery("get", "/api/meta");
  const style =
    mode === "dark"
      ? (meta.data?.map_style_url_dark ?? FALLBACK_DARK)
      : (meta.data?.map_style_url ?? FALLBACK_LIGHT);
  const latest = useRef({ layers, onFeatureClick, onReady, bounds });
  useEffect(() => {
    latest.current = { layers, onFeatureClick, onReady, bounds };
  });

  useEffect(() => {
    if (!el.current || !meta.isSuccess) return;
    const m = new maplibregl.Map({
      container: el.current,
      style,
      interactive,
      attributionControl: { compact: true },
      bounds: latest.current.bounds ?? undefined,
      fitBoundsOptions: { padding: 32 },
      center: [0, 30],
      zoom: latest.current.bounds ? undefined : 1.2,
      cooperativeGestures: false,
    });
    if (interactive)
      m.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
    m.on("style.load", () => {
      (m as unknown as Record<string, unknown>)[OWNED] = new Set<string>();
      applyLayers(m, latest.current.layers);
    });
    m.on("load", () => {
      el.current?.setAttribute("data-map-ready", "true");
      latest.current.onReady?.(m);
    });
    m.on("click", (e: maplibregl.MapMouseEvent) => {
      const ids = latest.current.layers.map((l) => l.id).filter((id) => m.getLayer(id));
      const hit = m.queryRenderedFeatures(e.point, { layers: ids })[0];
      if (hit) latest.current.onFeatureClick?.(hit.layer.id, hit.properties ?? {});
    });
    map.current = m;
    return () => {
      m.remove();
      map.current = null;
    };
    // style changes are handled below without recreating the map
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [meta.isSuccess, interactive]);

  useEffect(() => {
    map.current?.setStyle(style);
  }, [style]);

  useEffect(() => {
    const m = map.current;
    if (m?.isStyleLoaded()) applyLayers(m, layers);
  }, [layers]);

  useEffect(() => {
    if (bounds && map.current) map.current.fitBounds(bounds, { padding: 32, duration: 0 });
  }, [bounds]);

  return (
    <div
      ref={el}
      role="region"
      aria-label={ariaLabel}
      data-testid="map"
      className={className}
      style={{ height, width: "100%", borderRadius: "var(--radius-card)", overflow: "hidden" }}
    />
  );
}
