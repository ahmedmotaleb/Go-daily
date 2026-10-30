import "server-only";
import type { TileConfig } from "@/components/map/types";

/**
 * Map tiles are configured per environment (runtime, not build time).
 * The OpenStreetMap default is for development only; production should set
 * MAP_TILE_URL to a provider with an appropriate usage agreement.
 */
export function tileConfig(): TileConfig {
  return {
    url: process.env.MAP_TILE_URL ?? "https://tile.openstreetmap.org/{z}/{x}/{y}.png",
    attribution: process.env.MAP_TILE_ATTRIBUTION ?? "© OpenStreetMap contributors",
    maxZoom: Number(process.env.MAP_TILE_MAX_ZOOM ?? 19),
  };
}
