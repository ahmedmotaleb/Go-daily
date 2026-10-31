"use client";

import "leaflet/dist/leaflet.css";
import L from "leaflet";
import { colors } from "@go-daily/config/tokens";
import { useEffect, useRef } from "react";
import { DEFAULT_CENTER, type MapMarker, type MapViewProps, type MarkerTone } from "./types";

/** Leaflet implementation of the provider-neutral MapView. */

const TONE_COLORS: Record<MarkerTone, string> = {
  online: colors.lime[500],
  stale: "#d99a1b",
  offline: colors.neutral[500],
  stop: colors.forest[600],
  start: colors.forest[800],
  end: "#b42318",
  replay: colors.lime[400],
  geofence: colors.forest[500],
};

function markerIcon(m: MapMarker): L.DivIcon {
  const color = TONE_COLORS[m.tone];
  const arrow =
    m.heading !== null && m.heading !== undefined && (m.tone === "online" || m.tone === "replay")
      ? `<span style="position:absolute;inset:-6px;transform:rotate(${m.heading}deg)"><span style="position:absolute;top:-2px;left:50%;margin-left:-4px;border:4px solid transparent;border-bottom:7px solid ${colors.forest[900]}"></span></span>`
      : "";
  return L.divIcon({
    className: "",
    iconSize: [18, 18],
    iconAnchor: [9, 9],
    html: `<span style="position:relative;display:block;width:18px;height:18px;border-radius:9999px;background:${color};border:3px solid #fff;box-shadow:0 0 0 1px ${colors.forest[900]}">${arrow}</span>`,
  });
}

function popupContent(m: MapMarker): HTMLElement {
  // Built with DOM APIs so driver names etc. are never interpreted as HTML.
  const root = document.createElement("div");
  root.dir = "rtl";
  root.style.fontFamily = "inherit";
  const title = document.createElement("strong");
  title.textContent = m.label;
  root.appendChild(title);
  for (const line of m.details ?? []) {
    const p = document.createElement("div");
    p.textContent = line;
    p.style.fontSize = "12px";
    root.appendChild(p);
  }
  return root;
}

export default function LeafletMap({
  tiles,
  markers = [],
  polylines = [],
  circles = [],
  fitTo,
  center = DEFAULT_CENTER,
  height = 420,
  className,
}: MapViewProps) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<L.Map | null>(null);
  const layerRef = useRef<L.LayerGroup | null>(null);
  const fittedRef = useRef(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    const map = L.map(containerRef.current, {
      zoomControl: true,
      attributionControl: true,
    }).setView([center.lat, center.lng], 9);
    L.tileLayer(tiles.url, { attribution: tiles.attribution, maxZoom: tiles.maxZoom }).addTo(map);
    layerRef.current = L.layerGroup().addTo(map);
    mapRef.current = map;
    return () => {
      map.remove();
      mapRef.current = null;
      layerRef.current = null;
      fittedRef.current = false;
    };
  }, [center.lat, center.lng, tiles.url, tiles.attribution, tiles.maxZoom]);

  useEffect(() => {
    const map = mapRef.current;
    const layer = layerRef.current;
    if (!map || !layer) return;
    layer.clearLayers();
    for (const c of circles) {
      L.circle([c.center.lat, c.center.lng], {
        radius: c.radiusM,
        color: TONE_COLORS.geofence,
        weight: 1,
        fillOpacity: 0.08,
      })
        .bindTooltip(c.label)
        .addTo(layer);
    }
    for (const line of polylines) {
      L.polyline(
        line.points.map((p) => [p.lat, p.lng] as [number, number]),
        line.tone === "track"
          ? { color: colors.forest[700], weight: 4, opacity: 0.85 }
          : { color: colors.neutral[400], weight: 3, opacity: 0.6, dashArray: "6 6" },
      ).addTo(layer);
    }
    for (const m of markers) {
      L.marker([m.position.lat, m.position.lng], { icon: markerIcon(m), title: m.label })
        .bindPopup(() => popupContent(m))
        .addTo(layer);
    }
    const bounds = fitTo && fitTo.length ? fitTo : markers.map((m) => m.position);
    if (!fittedRef.current && bounds.length) {
      map.fitBounds(L.latLngBounds(bounds.map((p) => [p.lat, p.lng] as [number, number])), {
        padding: [30, 30],
        maxZoom: 16,
      });
      fittedRef.current = true;
    }
  }, [markers, polylines, circles, fitTo]);

  return (
    <div
      ref={containerRef}
      className={className}
      style={{
        height,
        width: "100%",
        borderRadius: "var(--radius-card)",
        overflow: "hidden",
        zIndex: 0,
      }}
      role="region"
      aria-label="خريطة"
    />
  );
}
