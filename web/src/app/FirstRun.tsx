/**
 * First-run experience. A fresh install has no data, so instead of sixteen empty dashboards
 * the shell shows a welcome screen with the Garmin sign-in, then the progress of the first
 * sync, and switches to the dashboards as soon as the first day of data is in the database.
 */
import { useQueryClient } from "@tanstack/react-query";
import { Link, useRouterState } from "@tanstack/react-router";
import { Loader2, RefreshCw, X } from "lucide-react";
import { useEffect, useRef, useState, type ReactNode } from "react";
import { api, type Schemas } from "@/api/client";
import { ConnectForm } from "@/components/ConnectForm";
import { Card, ErrorState, PageHeader, Skeleton } from "@/components/ui";
import { firstRunStage, historyLoading } from "@/lib/firstRun";
import { fmtDate, fmtNumber } from "@/lib/format";

type Status = Schemas["SyncStatus"];

const STEPS: { title: string; text: string }[] = [
  {
    title: "Connect",
    text: "Sign in once with your Garmin account. Two-factor codes are supported.",
  },
  {
    title: "First sync",
    text: "The last days are fetched first, so your dashboards appear within minutes.",
  },
  {
    title: "Full history",
    text: "Older years load in the background over a few hours. Nothing to wait for.",
  },
];

function Welcome({ mfaPending }: { mfaPending: boolean }) {
  return (
    <div data-testid="first-run" data-stage="welcome" className="mx-auto max-w-4xl">
      <PageHeader
        title="Welcome to Garminizer"
        description="Connect your Garmin account and Garminizer copies your activities, sleep and health data into the database on this computer, then keeps it up to date."
      />
      <div className="grid gap-5 lg:grid-cols-2">
        <Card
          title="Connect your Garmin account"
          subtitle="One-time sign-in; supports two-factor authentication"
        >
          <ConnectForm mfaPending={mfaPending} />
        </Card>
        <Card title="What happens next">
          <ol className="flex flex-col gap-4">
            {STEPS.map((step, i) => (
              <li key={step.title} className="flex gap-3">
                <span
                  aria-hidden
                  className="flex h-6 w-6 shrink-0 items-center justify-center rounded-chip bg-surface-2 text-xs font-semibold text-ink tabular"
                >
                  {i + 1}
                </span>
                <span className="text-sm text-ink-2">
                  <span className="block font-medium text-ink">{step.title}</span>
                  {step.text}
                </span>
              </li>
            ))}
          </ol>
        </Card>
      </div>
      <p className="mt-5 text-xs text-ink-3">
        Just looking around? The demo with a synthetic athlete needs no Garmin account:{" "}
        <code className="font-mono text-ink-2">docker compose -f compose.demo.yml up -d</code>
      </p>
    </div>
  );
}

function FirstSync({ s }: { s: Status }) {
  const qc = useQueryClient();
  const run = api.useMutation("post", "/api/sync/run");
  const last = s.last_runs[0];
  const problem = s.recent_errors[0];
  return (
    <div data-testid="first-run" data-stage="first-sync" className="mx-auto max-w-4xl">
      <PageHeader
        title={s.running ? "Your first sync is running" : "Connected to Garmin"}
        description="The last days are fetched first. This page switches to your dashboards as soon as the first data is in, usually within a few minutes."
      />
      <Card>
        <div className="flex items-start gap-3" role="status">
          {s.running && (
            <Loader2 size={20} className="mt-0.5 shrink-0 animate-spin text-accent" aria-hidden />
          )}
          <div className="min-w-0 text-sm text-ink-2">
            <p className="font-medium text-ink">
              {s.running ? "Fetching your data from Garmin" : "Waiting for the first sync to start"}
            </p>
            <p className="mt-1 tabular">
              {s.running && last
                ? `${fmtNumber(last.requests)} requests · ${fmtNumber(last.items_written)} items stored so far`
                : "The background worker starts one automatically; you can also start it now."}
            </p>
          </div>
        </div>
        {!s.running && (
          <button
            type="button"
            disabled={run.isPending}
            onClick={() =>
              run.mutate(
                { body: { kind: "incremental" } },
                { onSuccess: () => qc.invalidateQueries() },
              )
            }
            className="mt-4 inline-flex items-center gap-2 rounded-control bg-action px-4 py-2 text-sm font-semibold text-on-action transition-colors hover:bg-action-hover disabled:opacity-60"
          >
            <RefreshCw size={16} aria-hidden /> Sync now
          </button>
        )}
        {run.error && <ErrorState error={run.error} />}
        {!s.running && problem && (
          <p className="mt-3 text-xs text-ink-3">
            Last problem: {problem.error}. Garminizer retries automatically.
          </p>
        )}
        <p className="mt-4 border-t border-line pt-3 text-xs text-ink-3">
          Every request, dataset and error is listed on{" "}
          <Link to="/sync" className="font-medium text-ink underline underline-offset-2">
            Sync &amp; settings
          </Link>
          .
        </p>
      </Card>
    </div>
  );
}

/** Wraps the page outlet: welcome and first-sync screens until there is data to show. */
export function FirstRunGate({ children }: { children: ReactNode }) {
  const qc = useQueryClient();
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const status = api.useQuery(
    "get",
    "/api/sync/status",
    {},
    {
      refetchInterval: (q) =>
        q.state.data && firstRunStage(q.state.data) === "first-sync" ? 5000 : false,
    },
  );
  const stage = status.data ? firstRunStage(status.data) : null;
  const previous = useRef(stage);
  useEffect(() => {
    // The first data just arrived: drop what was cached while the database was empty.
    if (stage === "ready" && previous.current === "first-sync") void qc.invalidateQueries();
    previous.current = stage;
  }, [stage, qc]);

  if (status.isPending) return <Skeleton height={240} />;
  if (!status.data) return <>{children}</>;
  if (stage === "welcome") return <Welcome mfaPending={status.data.mfa_pending} />;
  if (stage === "first-sync" && pathname !== "/sync") return <FirstSync s={status.data} />;
  return <>{children}</>;
}

const BANNER_KEY = "gz.historyBanner";

function bannerHidden(): boolean {
  try {
    return window.localStorage.getItem(BANNER_KEY) === "hidden";
  } catch {
    return false;
  }
}

/** Slim note while older history is still loading, so short charts are not mistaken for bugs. */
export function HistoryBanner() {
  const status = api.useQuery("get", "/api/sync/status");
  const [hidden, setHidden] = useState(bannerHidden);
  if (hidden || !status.data || !historyLoading(status.data)) return null;
  const hide = () => {
    setHidden(true);
    try {
      window.localStorage.setItem(BANNER_KEY, "hidden");
    } catch {
      /* private mode etc.: the banner just comes back on reload */
    }
  };
  return (
    <div
      className="flex items-center justify-center gap-3 border-b border-line bg-accent-soft px-4 py-2 text-xs text-ink-2"
      data-testid="history-banner"
    >
      <p>
        Older history is still loading in the background; data reaches back to{" "}
        <strong className="font-semibold text-ink">{fmtDate(status.data.first_day)}</strong> so far.{" "}
        <Link to="/sync" className="font-semibold text-ink underline underline-offset-2">
          Progress
        </Link>
      </p>
      <button
        type="button"
        onClick={hide}
        aria-label="Hide this note"
        className="shrink-0 rounded-control p-1 text-ink-2 hover:bg-hover hover:text-ink active:bg-pressed"
      >
        <X size={14} aria-hidden />
      </button>
    </div>
  );
}
