/**
 * Chart palette (validated with the dataviz validator for both modes):
 * - categorical slots in a fixed order (never cycled); sports map to fixed slots
 * - sequential = one hue (blue) light→dark; HR zones use it as an ordinal ramp
 * - diverging = blue ↔ red with a gray midpoint
 * - status colours are reserved and always paired with an icon + label
 */
export type Mode = "light" | "dark";

export const CATEGORICAL: Record<Mode, readonly string[]> = {
  light: ["#2a78d6", "#eb6834", "#1baf7a", "#eda100", "#e87ba4", "#008300", "#6250d6", "#e34948"],
  dark: ["#3987e5", "#d95926", "#199e70", "#c98500", "#d55181", "#008300", "#9085e9", "#e66767"],
};

export const NEUTRAL: Record<Mode, string> = { light: "#898781", dark: "#898781" };

export const BLUE: Record<number, string> = {
  100: "#cde2fb",
  150: "#b7d3f6",
  200: "#9ec5f4",
  250: "#86b6ef",
  300: "#6da7ec",
  350: "#5598e7",
  400: "#3987e5",
  450: "#2a78d6",
  500: "#256abf",
  550: "#1c5cab",
  600: "#184f95",
  650: "#104281",
  700: "#0d366b",
};

/** Ordinal ramp for 5 HR zones (zone 1 → 5); every step clears 3:1 against its card. */
export const ZONE_RAMP: Record<Mode, readonly string[]> = {
  light: [BLUE[400]!, BLUE[500]!, BLUE[550]!, BLUE[650]!, BLUE[700]!],
  dark: [BLUE[500]!, BLUE[400]!, BLUE[300]!, BLUE[200]!, BLUE[100]!],
};

/**
 * Three intensity bands (easy Z1–2, moderate Z3, hard Z4–5) for stacked time-in-zone charts:
 * five blue steps are not tellable apart in thin stacks, three are (validated: adjacent
 * ΔE ≥ 17 normal and CVD, every step ≥ 3:1 on the card).
 */
export const INTENSITY_BANDS: Record<Mode, readonly [string, string, string]> = {
  light: ["#3987e5", "#184f95", "#0a2547"],
  dark: ["#256abf", "#6da7ec", "#cde2fb"],
};

/**
 * Garmin stress levels: rest in blue, low → high in a warm ramp (Garmin's own convention;
 * validated: adjacent ΔE ≥ 15.6 normal and CVD, every step ≥ 3:1 on the card).
 */
export const STRESS_LEVELS: Record<Mode, readonly [string, string, string, string]> = {
  light: ["#3987e5", "#e0702a", "#a8400f", "#5e1f05"],
  dark: ["#3987e5", "#b35217", "#ec8a44", "#fcd2ad"],
};

/**
 * One fixed colour per measure across all pages (metric charts, not sports). Measures that
 * share a chart never share a colour; text still uses ink tokens.
 */
export const MEASURE_COLORS: Record<
  Mode,
  Record<
    | "fitness"
    | "fatigue"
    | "hr"
    | "pace"
    | "power"
    | "cadence"
    | "elevation"
    | "hrv"
    | "stress"
    | "bodyBattery"
    | "sleep"
    | "spo2"
    | "respiration"
    | "weight"
    | "steps"
    | "intake"
    | "burn"
    | "protein"
    | "carbs"
    | "fat",
    string
  >
> = {
  light: {
    fitness: "#2a78d6",
    fatigue: "#e87ba4",
    hr: "#e34948",
    pace: "#2a78d6",
    power: "#eb6834",
    cadence: "#6250d6",
    elevation: "#898781",
    hrv: "#1baf7a",
    stress: "#eda100",
    bodyBattery: "#2a78d6",
    sleep: "#6250d6",
    spo2: "#1baf7a",
    respiration: "#6250d6",
    weight: "#2a78d6",
    steps: "#1baf7a",
    // Nutrition page (validated together: burn, intake, protein, carbs, fat)
    intake: "#eb6834",
    burn: "#2a78d6",
    protein: "#6250d6",
    carbs: "#eda100",
    fat: "#e87ba4",
  },
  dark: {
    fitness: "#3987e5",
    fatigue: "#d55181",
    hr: "#e66767",
    pace: "#3987e5",
    power: "#d95926",
    cadence: "#9085e9",
    elevation: "#9a9890",
    hrv: "#199e70",
    stress: "#c98500",
    bodyBattery: "#3987e5",
    sleep: "#9085e9",
    spo2: "#199e70",
    respiration: "#9085e9",
    weight: "#3987e5",
    steps: "#199e70",
    intake: "#d95926",
    burn: "#3987e5",
    protein: "#9085e9",
    carbs: "#c98500",
    fat: "#d55181",
  },
};

/** Continuous sequential ramp (heatmaps), low → high. */
export const SEQUENTIAL: Record<Mode, readonly string[]> = {
  light: [BLUE[100]!, BLUE[250]!, BLUE[400]!, BLUE[550]!, BLUE[700]!],
  dark: ["#1f2a38", BLUE[650]!, BLUE[500]!, BLUE[350]!, BLUE[150]!],
};

export const DIVERGING: Record<Mode, { negative: string; mid: string; positive: string }> = {
  light: { negative: "#2a78d6", mid: "#f0efec", positive: "#e34948" },
  dark: { negative: "#3987e5", mid: "#383835", positive: "#e66767" },
};

export const STATUS = {
  good: "#0ca30c",
  warning: "#fab219",
  serious: "#ec835a",
  critical: "#d03b3b",
} as const;
export type Status = keyof typeof STATUS;

export const SLEEP_STAGES: Record<Mode, Record<"deep" | "light" | "rem" | "awake", string>> = {
  light: { deep: "#256abf", light: "#1baf7a", rem: "#6250d6", awake: "#e87ba4" },
  dark: { deep: "#256abf", light: "#199e70", rem: "#9085e9", awake: "#d55181" },
};

export const CHROME: Record<
  Mode,
  { surface: string; text: string; text2: string; muted: string; grid: string; axis: string }
> = {
  light: {
    surface: "#fcfcfb",
    text: "#0b0b0b",
    text2: "#52514e",
    muted: "#6f6d68",
    grid: "#e1e0d9",
    axis: "#c3c2b7",
  },
  dark: {
    surface: "#1a1a19",
    text: "#f0efec",
    text2: "#c3c2b7",
    muted: "#9a9890",
    grid: "#2c2c2a",
    axis: "#383835",
  },
};

/** Area fills: the series hue as a ~10 % wash. */
export function wash(hex: string, alpha = 0.1): string {
  const n = Number.parseInt(hex.slice(1), 16);
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, ${alpha})`;
}
