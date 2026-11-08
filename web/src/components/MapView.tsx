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

function applyLayers(map: maplibregl.Map, layers: MapLayer[]) {
  for (const layer of layers) {
    const source = map.getSource(layer.id) as maplibregl.GeoJSONSource | undefined;
    if (source) {
      source.setData(layer.data);
    } else {
      map.addSource(layer.id, { type: "geojson", data: layer.data });
      map.addLayer({
        id: layer.id,
        type: layer.type,
        source: layer.id,
        ...(layer.paint ? { paint: layer.paint } : {}),
        ...(layer.layout ? { layout: layer.layout } : {}),
      } as maplibregl.LayerSpecification);
    }
  }
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
    m.on("style.load", () => applyLayers(m, latest.current.layers));
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
      style={{ height, width: "100%", borderRadius: 14, overflow: "hidden" }}
    />
  );
}
