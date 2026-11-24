/**
 * Go Daily design tokens (TypeScript mirror of theme.css, Design System 0.1).
 *
 * Use these where CSS variables are not available (charts, map layers,
 * canvas). Keep both files in sync.
 */
export const colors = {
  forest: {
    50: "#eef4f0",
    100: "#dce8e2",
    200: "#b9d1c5",
    300: "#8db3a2",
    400: "#5e907b",
    500: "#3c735f",
    600: "#2e6555",
    700: "#1b4a3e",
    800: "#103d32",
    900: "#082b24",
    950: "#051d18",
  },
  lime: {
    50: "#f4fae6",
    100: "#eef7d9",
    200: "#dcefb2",
    300: "#c9ea78",
    400: "#b5e33d",
    500: "#9ccb27",
    600: "#7fa61e",
    700: "#5f7f14",
    800: "#3a5a0e",
    900: "#2c4409",
  },
  neutral: {
    50: "#f6f8f5",
    100: "#eef1ef",
    200: "#e3eae5",
    300: "#d6dfd9",
    400: "#9aa59f",
    500: "#7b8983",
    600: "#5e6b65",
    700: "#4f5b56",
    800: "#333d39",
    900: "#202a27",
    950: "#141b19",
  },
  /** Dot/indicator shades; text uses the semantic dark shades below. */
  status: {
    active: "#103d32",
    activeRing: "#b5e33d",
    stale: "#e8a23a",
    critical: "#d9534f",
    inactive: "#9aa59f",
  },
  semantic: {
    background: "#f6f8f5",
    surface: "#ffffff",
    text: "#202a27",
    textMuted: "#5e6b65",
    border: "#e3eae5",
    primary: "#103d32",
    accent: "#b5e33d",
    gps: "#b5e33d",
    success: "#3a5a0e",
    warning: "#7a4e08",
    danger: "#a3302c",
    info: "#24507a",
  },
} as const;

export type ColorScale = keyof typeof colors;
