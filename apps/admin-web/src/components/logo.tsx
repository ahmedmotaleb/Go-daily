import clsx from "clsx";

/** Intrinsic sizes of the official artwork in /public/brand (640 px wide). */
const HEIGHT = { plain: 236, tagline: 285 } as const;

/**
 * The official Go Daily logo, unchanged (no redrawing or recolouring).
 * `inverted` is the white version for dark surfaces. The tagline
 * ("Ride. Deliver. Explore.") is only legible from 140 px wide, so it is
 * opt-in; the logo is never shown under 88 px.
 */
export function Logo({
  className,
  inverted = false,
  tagline = false,
  width = 120,
}: {
  className?: string;
  inverted?: boolean;
  tagline?: boolean;
  width?: number;
}) {
  const size = Math.max(88, width);
  const withTagline = tagline && size >= 140;
  const src = `/brand/logo-on-${inverted ? "dark" : "light"}${withTagline ? "-tagline" : ""}.png`;
  const height = Math.round((size * HEIGHT[withTagline ? "tagline" : "plain"]) / 640);
  return (
    // eslint-disable-next-line @next/next/no-img-element -- static brand file, already sized
    <img
      src={src}
      alt={withTagline ? "Go Daily — Ride. Deliver. Explore." : "Go Daily"}
      width={size}
      height={height}
      className={clsx("block h-auto shrink-0", className)}
      decoding="async"
    />
  );
}
