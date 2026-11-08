import {
  Activity,
  Bike,
  Dumbbell,
  Footprints,
  HeartPulse,
  Mountain,
  Sailboat,
  Snowflake,
  WavesLadder,
  Zap,
  type LucideIcon,
} from "lucide-react";
import { CATEGORICAL, NEUTRAL, type Mode } from "./tokens";

export const SPORT_GROUPS = [
  "run",
  "ride",
  "swim",
  "walk",
  "cardio",
  "hike",
  "strength",
  "winter",
  "water",
  "other",
] as const;
export type SportGroup = (typeof SPORT_GROUPS)[number];

/** Fixed categorical slot per sport (colour follows the entity, never its rank). */
const SLOT: Record<SportGroup, number | null> = {
  run: 0,
  ride: 1,
  swim: 2,
  walk: 3,
  cardio: 4,
  hike: 5,
  strength: 6,
  winter: 7,
  water: null,
  other: null,
};

export const SPORT_LABEL: Record<SportGroup, string> = {
  run: "Running",
  ride: "Cycling",
  swim: "Swimming",
  walk: "Walking",
  cardio: "Cardio",
  hike: "Hiking",
  strength: "Strength",
  winter: "Winter sports",
  water: "Water sports",
  other: "Other",
};

export const SPORT_ICON: Record<SportGroup, LucideIcon> = {
  run: Zap,
  ride: Bike,
  swim: WavesLadder,
  walk: Footprints,
  cardio: HeartPulse,
  hike: Mountain,
  strength: Dumbbell,
  winter: Snowflake,
  water: Sailboat,
  other: Activity,
};

export function isSportGroup(value: string): value is SportGroup {
  return (SPORT_GROUPS as readonly string[]).includes(value);
}

export function sportColor(group: string, mode: Mode): string {
  const slot = isSportGroup(group) ? SLOT[group] : null;
  return slot === null ? NEUTRAL[mode] : CATEGORICAL[mode][slot]!;
}

export function sportLabel(group: string): string {
  return isSportGroup(group) ? SPORT_LABEL[group] : group;
}

export function sportIcon(group: string): LucideIcon {
  return isSportGroup(group) ? SPORT_ICON[group] : Activity;
}

/** Sort sport groups in their fixed slot order (stack order = validated adjacency order). */
export function bySlot(a: string, b: string): number {
  const ia = SPORT_GROUPS.indexOf(a as SportGroup);
  const ib = SPORT_GROUPS.indexOf(b as SportGroup);
  return (ia < 0 ? 99 : ia) - (ib < 0 ? 99 : ib);
}

/** Pace is the natural speed unit for these groups; the rest show km/h or mph. */
export function usesPace(group: string): boolean {
  return group === "run" || group === "walk" || group === "hike" || group === "swim";
}
