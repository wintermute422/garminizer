import { ChevronRight } from "lucide-react";
import { useMemo, useState } from "react";
import type { Schemas } from "@/api/client";
import { EmptyState } from "@/components/ui";
import { fmtNumber } from "@/lib/format";
import { useMode } from "@/lib/preferences";
import { DIVERGING } from "@/lib/tokens";
import type { Pair } from "./InsightCards";
import { correlationPairs, fmtR, lagText, linkText, phrase } from "./metrics";

type Correlations = Schemas["InsightCorrelations"];

const MIN_DAYS = 14;
const PAGE = 8;

/** r as a bar from the centre: right = move together (red), left = move opposite (blue). */
function MiniBar({ r }: { r: number }) {
  const mode = useMode();
  const w = Math.min(Math.abs(r), 1) * 50;
  return (
    <span aria-hidden className="relative block h-2 w-16 shrink-0 rounded-full bg-surface-3">
      <span className="absolute inset-y-[-2px] left-1/2 w-px bg-line-strong" />
      <span
        className="absolute inset-y-0 rounded-full"
        style={{
          left: r >= 0 ? "50%" : `${50 - w}%`,
          width: `${w}%`,
          background: r >= 0 ? DIVERGING[mode].positive : DIVERGING[mode].negative,
        }}
      />
    </span>
  );
}

/** Phones: the strongest links as a ranked list instead of an unreadable 19 × 19 matrix. */
export function StrongestLinks({
  data,
  labelOf,
  onSelect,
}: {
  data: Correlations;
  labelOf: (key: string) => string;
  onSelect: (p: Pair) => void;
}) {
  const [limit, setLimit] = useState(PAGE);
  const ranked = useMemo(
    () =>
      correlationPairs(data)
        .filter((p): p is typeof p & { r: number } => !p.derived && p.r !== null && p.n >= MIN_DAYS)
        .sort((p, q) => Math.abs(q.r) - Math.abs(p.r) || p.a - q.a || p.b - q.b),
    [data],
  );
  if (!ranked.length) return <EmptyState title="Not enough days to compare metrics" />;
  return (
    <div>
      <ol className="-mx-2 flex flex-col">
        {ranked.slice(0, limit).map((p) => (
          <li key={`${p.x}-${p.y}`}>
            <button
              type="button"
              onClick={() => onSelect({ x: p.x, y: p.y, lag: p.lag })}
              className="flex w-full items-center gap-3 rounded-xl px-2 py-2.5 text-left hover:bg-surface-2"
            >
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-medium text-ink">
                  {labelOf(p.x)} {p.lag ? "→" : "&"} {phrase(labelOf(p.y))}
                  {p.lag ? ` ${lagText(p.lag)}` : ""}
                </span>
                <span className="block text-xs text-ink-3">
                  {linkText(p.r)} · r {fmtR(p.r)} · {fmtNumber(p.n)} days
                </span>
              </span>
              <MiniBar r={p.r} />
              <ChevronRight size={16} aria-hidden className="shrink-0 text-ink-3" />
            </button>
          </li>
        ))}
      </ol>
      {limit < ranked.length && (
        <button
          type="button"
          onClick={() => setLimit((l) => l + PAGE)}
          className="mt-2 w-full rounded-xl border border-line px-3 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2 hover:text-ink"
        >
          Show more links
        </button>
      )}
    </div>
  );
}
