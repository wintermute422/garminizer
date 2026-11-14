import { useQueryClient } from "@tanstack/react-query";
import { api, type Schemas } from "@/api/client";
import { ScrollArea, StatusPill } from "@/components/ui";
import { fmtDate, fmtNumber } from "@/lib/format";
import { checkpointState, formErrors } from "./goal";

type Checkpoint = Schemas["GoalCheckpoint"];

/** Checkpoints with their state; past ones that were not reached can be counted by hand. */
export function CheckpointList({ checkpoints }: { checkpoints: Checkpoint[] }) {
  const qc = useQueryClient();
  const put = api.useMutation("put", "/api/goal/checkpoints/{day}");
  const pending = put.isPending ? put.variables?.params.path.day : null;
  const error = put.error ? formErrors(put.error).general.join(" ") : null;
  return (
    <>
      <ScrollArea label="Checkpoints" className="-mx-1 overflow-x-auto px-1">
        <table className="w-full text-sm tabular">
          <thead className="text-xs text-ink-3">
            <tr>
              <th scope="col" className="py-1.5 pr-3 text-left font-medium">
                Checkpoint
              </th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium whitespace-nowrap">
                Target
              </th>
              <th scope="col" className="py-1.5 pr-3 text-right font-medium whitespace-nowrap">
                Trend
              </th>
              <th scope="col" className="py-1.5 text-left font-medium">
                Status
              </th>
            </tr>
          </thead>
          <tbody>
            {checkpoints.map((c) => {
              const s = checkpointState(c);
              return (
                <tr key={c.day} className="border-t border-line">
                  <td className="py-2 pr-3 whitespace-nowrap text-ink">
                    {fmtDate(c.day, { day: "numeric", month: "short" })}
                  </td>
                  <td className="py-2 pr-3 text-right whitespace-nowrap text-ink">
                    {fmtNumber(c.target_kg, 2)}
                  </td>
                  <td className="py-2 pr-3 text-right whitespace-nowrap text-ink-2">
                    {fmtNumber(c.trend_kg, 2)}
                  </td>
                  <td className="py-2">
                    <div className="flex flex-wrap items-center justify-between gap-2">
                      <StatusPill status={s.status} label={s.label} />
                      {s.action && (
                        <button
                          type="button"
                          disabled={pending != null}
                          aria-label={`${s.action.label}: checkpoint ${fmtDate(c.day)}`}
                          onClick={() =>
                            put.mutate(
                              {
                                params: { path: { day: c.day } },
                                body: { accepted: s.action!.accepted },
                              },
                              { onSuccess: () => void qc.invalidateQueries() },
                            )
                          }
                          className="rounded-control border border-line px-2 py-1 text-xs font-medium whitespace-nowrap text-ink-2 transition-colors hover:bg-hover hover:text-ink active:bg-pressed disabled:opacity-60"
                        >
                          {pending === c.day ? "Saving…" : s.action.label}
                        </button>
                      )}
                    </div>
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </ScrollArea>
      {error && (
        <p role="alert" className="mt-2 text-xs text-critical-text">
          {error}
        </p>
      )}
      <p className="mt-3 text-xs text-ink-3">
        A checkpoint is reached when the trend is below its target; the target line then restarts
        from that trend. Counting a missed checkpoint as reached never lifts the line.
      </p>
    </>
  );
}
