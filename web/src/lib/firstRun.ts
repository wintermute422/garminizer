/** What a fresh install shows before there is any data: welcome → first sync → dashboards. */
import type { Schemas } from "@/api/client";

type Status = Pick<Schemas["SyncStatus"], "is_demo" | "connected" | "first_day" | "cursors">;

export type FirstRunStage = "welcome" | "first-sync" | "ready";

/**
 * `welcome` until a Garmin account is connected, `first-sync` until the first day of data is
 * in the database, `ready` from then on (and always for the demo or any database with data).
 */
export function firstRunStage(s: Status): FirstRunStage {
  if (s.is_demo || s.first_day) return "ready";
  return s.connected ? "first-sync" : "welcome";
}

/** Dashboards are usable, but the worker is still walking back through older history. */
export function historyLoading(s: Status): boolean {
  return (
    firstRunStage(s) === "ready" && !s.is_demo && s.connected && s.cursors.some((c) => !c.complete)
  );
}
