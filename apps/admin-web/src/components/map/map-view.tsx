"use client";

import dynamic from "next/dynamic";
import type { MapViewProps } from "./types";

/** The map implementation is client-only (it needs `window`). */
const Impl = dynamic(() => import("./leaflet-map"), {
  ssr: false,
  loading: () => (
    <div className="h-[420px] animate-pulse rounded-[var(--radius-card)] bg-neutral-200/70" />
  ),
});

export function MapView(props: MapViewProps) {
  return <Impl {...props} />;
}
