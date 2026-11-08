import { clsx } from "clsx";
import {
  Activity,
  ArrowDownRight,
  ArrowRight,
  ArrowUpRight,
  Brain,
  CalendarCheck,
  CalendarDays,
  CircleAlert,
  CircleCheck,
  Flame,
  Gauge,
  HeartPulse,
  Lightbulb,
  Minus,
  Moon,
  TrendingUp,
  Trophy,
  type LucideIcon,
} from "lucide-react";
import { createElement } from "react";
import type { Schemas } from "@/api/client";
import { EmptyState } from "@/components/ui";
import { fmtHours, fmtNumber, signed } from "@/lib/format";
import { fmtR, linkText } from "./metrics";

type InsightCard = Schemas["InsightCard"];
export interface Pair {
  x: string;
  y: string;
  lag: number;
}

const ICON: Record<string, LucideIcon> = {
  resting_hr_change: HeartPulse,
  hrv_after_hard_days: Activity,
  fitness_change: TrendingUp,
  vo2max_change: Gauge,
  sleep_readiness: Moon,
  stress_sleep: Brain,
  weekend_sleep: Moon,
  training_weekday: CalendarDays,
  streak: Flame,
  most_active_month: Trophy,
  consistency: CalendarCheck,
};

/** Cards whose finding is a relationship between two daily metrics (x on d, y on d + lag). */
const PAIRS: Record<string, Pair> = {
  sleep_readiness: { x: "sleep_score", y: "readiness", lag: 0 },
  stress_sleep: { x: "avg_stress", y: "sleep_score", lag: 1 },
  hrv_after_hard_days: { x: "load", y: "hrv_ms", lag: 1 },
};

const DIGITS: Record<string, number> = { load: 1, "ml/kg/min": 1 };
const SINGULAR: Record<string, string> = { days: "day", activities: "activity" };

function valueParts(c: InsightCard): { value: string; unit: string; words?: boolean } {
  if (c.value === null) return { value: "–", unit: "" };
  switch (c.unit) {
    case "s":
      return { value: fmtHours(c.value), unit: "" };
    case "r":
      // Lead with the meaning; r is the supporting number.
      return { value: linkText(c.value), unit: `r ${fmtR(c.value)}`, words: true };
    case "load":
      return { value: fmtNumber(c.value, 1), unit: c.metric === "ctl" ? "CTL" : "load" };
    default: {
      const unit = c.unit ?? "";
      return {
        value: fmtNumber(c.value, DIGITS[unit] ?? 0),
        unit: c.value === 1 ? (SINGULAR[unit] ?? unit) : unit,
      };
    }
  }
}

function deltaText(c: InsightCard): string | null {
  if (c.delta === null || Math.abs(c.delta) < 1e-9) return null;
  if (c.unit === "s") return `${c.delta > 0 ? "+" : "−"}${fmtHours(Math.abs(c.delta))}`;
  const u = c.unit === "load" ? "" : c.unit ? ` ${c.unit}` : "";
  return signed(c.delta, DIGITS[c.unit ?? ""] ?? 1, u);
}

type Tone = "good" | "bad" | "neutral";

function trendChip(c: InsightCard): { icon: LucideIcon; text: string; tone: Tone } | null {
  const tone: Tone = c.sentiment;
  if (c.unit === "r") return null; // the hero already says it in words
  const delta = deltaText(c);
  if (c.trend !== "flat") {
    return {
      icon: c.trend === "up" ? ArrowUpRight : ArrowDownRight,
      text: delta ?? (c.trend === "up" ? "rising" : "falling"),
      tone,
    };
  }
  if (c.metric) return { icon: Minus, text: "no real change", tone: "neutral" };
  if (delta && c.delta !== null)
    return {
      icon: c.delta > 0 ? ArrowUpRight : ArrowDownRight,
      text: `${delta} vs. average`,
      tone,
    };
  return null;
}

const TONE_TEXT: Record<Tone, string> = {
  good: "text-good-text",
  bad: "text-critical-text",
  neutral: "text-ink-3",
};

function Sentiment({ sentiment }: { sentiment: InsightCard["sentiment"] }) {
  if (sentiment === "neutral") return null;
  const good = sentiment === "good";
  return (
    <span
      className={clsx(
        "inline-flex shrink-0 items-center gap-1 text-xs font-medium",
        good ? "text-good-text" : "text-critical-text",
      )}
    >
      {createElement(good ? CircleCheck : CircleAlert, { size: 14, "aria-hidden": true })}
      {good ? "Good sign" : "Worth a look"}
    </span>
  );
}

function Finding({
  c,
  onExplore,
  className,
}: {
  c: InsightCard;
  onExplore: (p: Pair) => void;
  className?: string;
}) {
  const { value, unit, words } = valueParts(c);
  const chip = trendChip(c);
  const pair = PAIRS[c.id];
  return (
    <article
      className={clsx(
        "flex min-w-0 flex-col gap-3 rounded-2xl border border-line bg-surface p-4 shadow-card",
        className,
      )}
    >
      <header className="flex items-center justify-between gap-2">
        <h3 className="flex min-w-0 items-center gap-2 text-sm font-medium text-ink-2">
          <span className="inline-flex size-7 shrink-0 items-center justify-center rounded-lg bg-surface-2 text-ink-2">
            {createElement(ICON[c.id] ?? Lightbulb, { size: 15, "aria-hidden": true })}
          </span>
          <span className="truncate">{c.title}</span>
        </h3>
        <Sentiment sentiment={c.sentiment} />
      </header>
      <div className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
        <span
          className={clsx(
            "leading-none font-semibold tracking-tight text-ink",
            words ? "text-[22px]" : "text-[30px]",
          )}
        >
          {value}
        </span>
        {unit && <span className="text-sm text-ink-3 tabular">{unit}</span>}
        {chip && (
          <span
            className={clsx(
              "ml-1 inline-flex items-center gap-0.5 text-xs font-medium tabular",
              TONE_TEXT[chip.tone],
            )}
          >
            {createElement(chip.icon, { size: 14, "aria-hidden": true })}
            {chip.text}
          </span>
        )}
      </div>
      <p className="text-sm leading-relaxed text-ink-2">{c.text}</p>
      {pair && (
        <button
          type="button"
          onClick={() => onExplore(pair)}
          className="mt-auto inline-flex items-center gap-1 self-start rounded-lg border border-line px-2.5 py-1 text-xs font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
        >
          Explore this link <ArrowRight size={13} aria-hidden className="text-accent" />
        </button>
      )}
    </article>
  );
}

/** The last card stretches over the empty cells of the last row (2 and 3 columns). */
function lastSpan(n: number): string {
  const sm = n % 2 === 1 ? "sm:col-span-2" : "";
  const xl = n % 3 === 2 ? "xl:col-span-2" : n % 3 === 1 ? "xl:col-span-3" : "xl:col-span-1";
  return clsx(sm, xl);
}

export function InsightCards({
  cards,
  onExplore,
}: {
  cards: InsightCard[];
  onExplore: (p: Pair) => void;
}) {
  if (!cards.length)
    return (
      <EmptyState title="Not enough data for findings yet">
        Findings appear once a few weeks of daily data are in this range.
      </EmptyState>
    );
  return (
    <section aria-labelledby="findings-heading">
      <h2 id="findings-heading" className="sr-only">
        Findings
      </h2>
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-3">
        {cards.map((c, i) => (
          <Finding
            key={c.id}
            c={c}
            onExplore={onExplore}
            className={i === cards.length - 1 ? lastSpan(cards.length) : undefined}
          />
        ))}
      </div>
    </section>
  );
}
