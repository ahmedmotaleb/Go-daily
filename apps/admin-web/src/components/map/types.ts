/**
 * Provider-neutral map model. Business screens build these plain objects;
 * only the provider implementation (leaflet-map.tsx) knows a map library,
 * so swapping vendors means writing one new implementation file.
 */
export type LatLng = { lat: number; lng: number };

export type MarkerTone =
  "online" | "stale" | "offline" | "stop" | "start" | "end" | "replay" | "geofence";

export type MapMarker = {
  id: string;
  position: LatLng;
  tone: MarkerTone;
  label: string;
  /** Plain text lines shown in the popup (never HTML). */
  details?: string[];
  heading?: number | null;
};

export type MapPolyline = { id: string; points: LatLng[]; tone: "track" | "faded" };

export type MapCircle = { id: string; center: LatLng; radiusM: number; label: string };

export type TileConfig = { url: string; attribution: string; maxZoom: number };

export type MapViewProps = {
  tiles: TileConfig;
  markers?: MapMarker[];
  polylines?: MapPolyline[];
  circles?: MapCircle[];
  /** Points to fit the initial view to; falls back to `center`. */
  fitTo?: LatLng[];
  center?: LatLng;
  height?: number;
  className?: string;
};

/** Default view: Cairo / Nile Delta. */
export const DEFAULT_CENTER: LatLng = { lat: 30.6, lng: 31.2 };
