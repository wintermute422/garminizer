/** Page-local helpers for gear: names, types, wear levels and fixed colour slots. */
import { Bike, Footprints, Package, type LucideIcon } from "lucide-react";
import type { Schemas } from "@/api/client";
import { niceScale, niceStep } from "@/lib/charts";
import { titleCase } from "@/lib/format";
import { CATEGORICAL, NEUTRAL, type Mode, type Status } from "@/lib/tokens";

export type Gear = Schemas["GearItem"];

export function gearName(g: Gear): string {
  return g.display_name ?? ([g.make, g.model].filter(Boolean).join(" ") || "Unnamed gear");
}

/** Make/model line under the name, without repeating the name. */
export function gearMakeModel(g: Gear): string {
  const name = gearName(g);
  if (g.model && name.includes(g.model)) return g.make ?? "";
  return [g.make, g.model].filter(Boolean).join(" ");
}

export function isRetired(g: Gear): boolean {
  return g.status === "retired";
}

const TYPE_ORDER = ["shoes", "bike"];

export function sortTypes(types: string[]): string[] {
  const rank = (t: string) => (TYPE_ORDER.includes(t) ? TYPE_ORDER.indexOf(t) : 99);
  return [...new Set(types)].sort((a, b) => rank(a) - rank(b) || a.localeCompare(b));
}

export function typeLabel(type: string, plural = true): string {
  if (type === "shoes") return plural ? "Shoes" : "Shoe";
  if (type === "bike") return plural ? "Bikes" : "Bike";
  return titleCase(type);
}

export function gearIcon(type: string): LucideIcon {
  return type === "shoes" ? Footprints : type === "bike" ? Bike : Package;
}

export type WearLevel = Extract<Status, "good" | "warning" | "critical">;

export function wearLevel(pct: number): WearLevel {
  return pct < 75 ? "good" : pct <= 100 ? "warning" : "critical";
}

export const WEAR_LABEL: Record<WearLevel, string> = {
  good: "In good shape",
  warning: "Nearing its limit",
  critical: "Past its limit",
};

/**
 * Fixed categorical slot per gear item (colour follows the item, never its rank): items are
 * ordered by first use. With more than 8 items the 7 with the most distance keep a slot and
 * the rest fold into "Other" (null).
 */
export function gearSlots(items: Gear[]): Map<string, number | null> {
  const byFirstUse = [...items].sort(
    (a, b) =>
      (a.date_begin ?? a.usage[0]?.month ?? "9999").localeCompare(
        b.date_begin ?? b.usage[0]?.month ?? "9999",
      ) || a.uuid.localeCompare(b.uuid),
  );
  const keep =
    items.length <= 8
      ? new Set(items.map((g) => g.uuid))
      : new Set(
          [...items]
            .sort((a, b) => b.distance_m - a.distance_m)
            .slice(0, 7)
            .map((g) => g.uuid),
        );
  const slots = new Map<string, number | null>();
  let next = 0;
  for (const g of byFirstUse) slots.set(g.uuid, keep.has(g.uuid) ? next++ : null);
  return slots;
}

export function slotColor(slot: number | null | undefined, mode: Mode): string {
  return slot === null || slot === undefined ? NEUTRAL[mode] : CATEGORICAL[mode][slot]!;
}

/** Axis maximum and tick interval with about `ticks` round steps covering `v`. */
export function niceAxis(v: number, ticks = 4): { max: number; interval: number } {
  if (!(v > 0)) return { max: 1, interval: 0.25 };
  const { max, interval } = niceScale(0, v, { steps: niceStep, ticks });
  return { max, interval };
}
