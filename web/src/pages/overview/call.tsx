/** "Today's call": one honest, rule-based line at the top of the overview. */
import { AlertTriangle, CircleAlert, CircleCheck } from "lucide-react";
import { createElement } from "react";
import { STATUS } from "@/lib/tokens";
import type { TodaysCall } from "@/lib/status";

const ICON = { go: CircleCheck, steady: AlertTriangle, easy: CircleAlert } as const;

export function TodayCall({ call }: { call: TodaysCall }) {
  return (
    <section
      aria-label="Today's call"
      className="mb-5 flex flex-col gap-1 rounded-2xl border border-line bg-surface px-4 py-3 shadow-card sm:px-5 lg:flex-row lg:items-center lg:gap-4"
    >
      <p className="flex min-w-0 items-start gap-2.5 text-sm lg:flex-1">
        {createElement(ICON[call.tone], {
          size: 18,
          color: STATUS[call.status],
          "aria-hidden": true,
          className: "mt-px shrink-0",
        })}
        <span>
          <strong className="font-semibold text-ink">{call.headline}</strong>
          <span className="text-ink-2"> — {call.reasons.join(", ")}</span>
        </span>
      </p>
      <p className="pl-7 text-xs text-ink-3 lg:shrink-0 lg:pl-0">
        Rule of thumb from readiness, HRV, sleep and load
      </p>
    </section>
  );
}
