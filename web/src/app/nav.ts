import type { PresetKey } from "@/lib/range";
import {
  Award,
  CalendarDays,
  Gauge,
  HeartPulse,
  LayoutDashboard,
  Lightbulb,
  ListOrdered,
  Map,
  Moon,
  Package,
  RefreshCw,
  Scale,
  TrendingUp,
  Trophy,
  Utensils,
  type LucideIcon,
} from "lucide-react";

export interface NavItem {
  to: string;
  label: string;
  icon: LucideIcon;
  /** Pages that react to the global date range / sport filter show the filter bar. */
  filters?: "range" | "range+sport" | "sport";
  /** Default range preset when the URL has none (must match the page's useRange fallback). */
  defaultPreset?: PresetKey;
  /** The page always shows one sport (no "All sports"); this one when none is chosen. */
  defaultSport?: string;
}

export const NAV: { section: string; items: NavItem[] }[] = [
  {
    section: "Today",
    items: [{ to: "/", label: "Today", icon: LayoutDashboard }],
  },
  {
    section: "Training",
    items: [
      { to: "/activities", label: "Activities", icon: ListOrdered, filters: "range+sport" },
      { to: "/training", label: "Training load", icon: TrendingUp, filters: "range+sport" },
      { to: "/performance", label: "Performance", icon: Gauge, filters: "range" },
      { to: "/records", label: "Records", icon: Trophy, filters: "sport", defaultSport: "run" },
      {
        to: "/calendar",
        label: "Calendar",
        icon: CalendarDays,
        filters: "range+sport",
        defaultPreset: "365d",
      },
      { to: "/map", label: "Map", icon: Map, filters: "range+sport" },
      { to: "/gear", label: "Gear", icon: Package },
    ],
  },
  {
    section: "Health",
    items: [
      { to: "/health", label: "Health & recovery", icon: HeartPulse, filters: "range" },
      { to: "/sleep", label: "Sleep", icon: Moon, filters: "range" },
      { to: "/body", label: "Body", icon: Scale, filters: "range", defaultPreset: "365d" },
      { to: "/nutrition", label: "Nutrition", icon: Utensils, filters: "range" },
    ],
  },
  {
    section: "Discover",
    items: [
      { to: "/insights", label: "Insights", icon: Lightbulb, filters: "range" },
      { to: "/year", label: "Year in review", icon: Award },
    ],
  },
  {
    section: "System",
    items: [{ to: "/sync", label: "Sync & settings", icon: RefreshCw }],
  },
];

export const ALL_NAV: NavItem[] = NAV.flatMap((s) => s.items);

/** Detail pages (one activity) show no global filters. */
export function isDetailPage(pathname: string): boolean {
  return /^\/activities\/[^/]+/.test(pathname);
}

export function navItemFor(pathname: string): NavItem | undefined {
  if (pathname === "/") return ALL_NAV[0];
  return ALL_NAV.filter((i) => i.to !== "/").find((i) => pathname.startsWith(i.to));
}
