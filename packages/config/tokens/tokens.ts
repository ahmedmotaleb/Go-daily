/**
 * Go Daily design tokens (TypeScript mirror of theme.css).
 *
 * Use these where CSS variables are not available (charts, map layers,
 * canvas). Keep both files in sync.
 */
export const colors = {
  forest: {
    50: "#eef5f1",
    100: "#d5e8dd",
    200: "#a9d0bb",
    300: "#74b192",
    400: "#46906d",
    500: "#2a7352",
    600: "#1e5c41",
    700: "#174a35",
    800: "#123b2b",
    900: "#0d2e21",
    950: "#071c14",
  },
  lime: {
    50: "#f7fde8",
    100: "#edfacb",
    200: "#dbf59c",
    300: "#c3ec62",
    400: "#a8df33",
    500: "#8bc61a",
    600: "#6b9e10",
    700: "#517811",
    800: "#425f14",
    900: "#385016",
  },
  neutral: {
    50: "#f7f8f6",
    100: "#f0f2ee",
    200: "#e0e4dd",
    300: "#c7ccc3",
    400: "#9da498",
    500: "#757c71",
    600: "#585e55",
    700: "#454a42",
    800: "#30342e",
    900: "#1f221e",
    950: "#121411",
  },
  semantic: {
    background: "#f0f2ee",
    surface: "#ffffff",
    text: "#1f221e",
    textMuted: "#585e55",
    border: "#e0e4dd",
    primary: "#123b2b",
    accent: "#a8df33",
    gps: "#a8df33",
    success: "#1e5c41",
    warning: "#a15c07",
    danger: "#b42318",
    info: "#155e63",
  },
} as const;

export type ColorScale = keyof typeof colors;
