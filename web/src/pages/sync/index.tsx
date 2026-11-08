import { useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  Database,
  KeyRound,
  Link2Off,
  Loader2,
  RefreshCw,
  ShieldCheck,
  TriangleAlert,
} from "lucide-react";
import { useMemo, useState, type FormEvent } from "react";
import { api, type Schemas } from "@/api/client";
import { Chart, type ChartOption } from "@/components/Chart";
import {
  Card,
  EmptyState,
  ErrorState,
  PageHeader,
  ScrollArea,
  Skeleton,
  StatusPill,
} from "@/components/ui";
import { CHROME, SEQUENTIAL } from "@/lib/tokens";
import { DASH, fmtDate, fmtNumber, titleCase } from "@/lib/format";
import { useMode } from "@/lib/preferences";

type Status = Schemas["SyncStatus"];

function fmtDateTime(iso: string | null | undefined): string {
  if (!iso) return DASH;
  return new Date(iso).toLocaleString(undefined, {
    day: "numeric",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function duration(a: string | null | undefined, b: string | null | undefined): string {
  if (!a || !b) return DASH;
  const s = Math.max(0, (new Date(b).getTime() - new Date(a).getTime()) / 1000);
  return s < 90 ? `${Math.round(s)} s` : `${Math.round(s / 60)} min`;
}

function ConnectForm({ mfaPending }: { mfaPending: boolean }) {
  const qc = useQueryClient();
  const connect = api.useMutation("post", "/api/sync/connect");
  const mfa = api.useMutation("post", "/api/sync/mfa");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [code, setCode] = useState("");
  const [needsMfa, setNeedsMfa] = useState(mfaPending);
  const done = () => qc.invalidateQueries();

  const submit = (e: FormEvent) => {
    e.preventDefault();
    if (needsMfa) {
      mfa.mutate({ body: { code } }, { onSuccess: done });
      return;
    }
    connect.mutate(
      { body: { email, password } },
      {
        onSuccess: (r) => {
          setPassword("");
          if (r.status === "needs_mfa") setNeedsMfa(true);
          else void done();
        },
      },
    );
  };
  const error = (connect.error ?? mfa.error) as { detail?: string } | null;

  return (
    <form onSubmit={submit} className="flex max-w-md flex-col gap-3">
      {!needsMfa ? (
        <>
          <label className="text-xs font-medium text-ink-2" htmlFor="garmin-email">
            Garmin e-mail
          </label>
          <input
            id="garmin-email"
            type="email"
            autoComplete="username"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink"
          />
          <label className="text-xs font-medium text-ink-2" htmlFor="garmin-password">
            Garmin password
          </label>
          <input
            id="garmin-password"
            type="password"
            autoComplete="current-password"
            required
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm text-ink"
          />
        </>
      ) : (
        <>
          <p className="text-sm text-ink-2">
            Garmin sent you a verification code. Enter it to finish signing in.
          </p>
          <label className="text-xs font-medium text-ink-2" htmlFor="garmin-mfa">
            Verification code
          </label>
          <input
            id="garmin-mfa"
            inputMode="numeric"
            autoComplete="one-time-code"
            required
            value={code}
            onChange={(e) => setCode(e.target.value)}
            className="rounded-xl border border-line bg-surface-2 px-3 py-2 text-sm tracking-widest text-ink"
          />
        </>
      )}
      {error && (
        <p role="alert" className="text-xs text-critical-text">
          {error.detail ?? "Sign-in failed."}
        </p>
      )}
      <button
        type="submit"
        disabled={connect.isPending || mfa.isPending}
        className="inline-flex items-center justify-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
      >
        {(connect.isPending || mfa.isPending) && (
          <Loader2 size={16} className="animate-spin" aria-hidden />
        )}
        {needsMfa ? "Verify" : "Connect Garmin"}
      </button>
      <p className="flex items-start gap-2 text-xs text-ink-3">
        <ShieldCheck size={14} className="mt-0.5 shrink-0" aria-hidden />
        Your password goes straight to Garmin and is not stored. Garminizer keeps only Garmin's
        login tokens on this computer and only ever reads data.
      </p>
    </form>
  );
}

function Connection({ s }: { s: Status }) {
  const qc = useQueryClient();
  const run = api.useMutation("post", "/api/sync/run");
  const disconnect = api.useMutation("post", "/api/sync/disconnect");
  const refresh = () => qc.invalidateQueries();

  if (s.is_demo) {
    return (
      <Card title="Garmin connection">
        <div className="flex items-start gap-3">
          <Database size={20} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />
          <div className="text-sm text-ink-2">
            <p className="font-medium text-ink">This database holds the synthetic demo athlete.</p>
            <p className="mt-1">
              Real Garmin data is never mixed into it. Start the main stack (
              <code className="rounded bg-surface-2 px-1">docker compose up -d</code>, port 8420)
              and connect your account there.
            </p>
          </div>
        </div>
      </Card>
    );
  }
  if (!s.connected) {
    return (
      <Card
        title="Connect your Garmin account"
        subtitle="One-time sign-in; supports two-factor authentication"
      >
        <ConnectForm mfaPending={s.mfa_pending} />
      </Card>
    );
  }
  return (
    <Card title="Garmin connection" actions={<StatusPill status="good" label="Connected" />}>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          disabled={s.running || run.isPending}
          onClick={() => run.mutate({ body: { kind: "incremental" } }, { onSuccess: refresh })}
          className="inline-flex items-center gap-2 rounded-xl bg-accent px-4 py-2 text-sm font-semibold text-white disabled:opacity-60"
        >
          <RefreshCw size={16} className={s.running ? "animate-spin" : undefined} aria-hidden />
          {s.running ? "Syncing…" : "Sync now"}
        </button>
        <button
          type="button"
          disabled={s.running || run.isPending}
          onClick={() => run.mutate({ body: { kind: "backfill" } }, { onSuccess: refresh })}
          className="rounded-xl border border-line px-4 py-2 text-sm font-medium text-ink-2 hover:bg-surface-2 hover:text-ink disabled:opacity-60"
        >
          Load older history
        </button>
        <button
          type="button"
          onClick={() => disconnect.mutate({}, { onSuccess: refresh })}
          className="ml-auto inline-flex items-center gap-2 rounded-xl px-3 py-2 text-sm text-ink-3 hover:bg-surface-2 hover:text-ink"
        >
          <Link2Off size={16} aria-hidden /> Disconnect
        </button>
      </div>
      {run.error && <ErrorState error={run.error} />}
      <p className="mt-3 text-xs text-ink-3">
        Data from {fmtDate(s.first_day)} to {fmtDate(s.last_day)}. The background worker syncs
        automatically and keeps loading older history until it reaches your first Garmin day.
      </p>
    </Card>
  );
}

function Coverage() {
  const mode = useMode();
  const q = api.useQuery("get", "/api/sync/coverage");
  const option = useMemo<ChartOption | null>(() => {
    const rows = q.data?.months ?? [];
    if (!rows.length) return null;
    const datasets = [...new Set(rows.map((r) => r.dataset))].sort();
    const months = [...new Set(rows.map((r) => r.month))].sort();
    return {
      grid: { left: 4, right: 12, top: 8, bottom: 56 },
      tooltip: {
        trigger: "item",
        formatter: (p: unknown) => {
          const v = (p as { value: [number, number, number] }).value;
          return `${datasets[v[1]]}<br/>${months[v[0]]}: <b>${v[2]}</b> days`;
        },
      },
      xAxis: {
        type: "category",
        data: months.map((m) => m.slice(0, 7)),
        axisLabel: { color: CHROME[mode].muted },
      },
      yAxis: { type: "category", data: datasets.map(titleCase) },
      visualMap: {
        min: 0,
        max: 31,
        orient: "horizontal",
        left: "center",
        bottom: 0,
        itemHeight: 120,
        inRange: { color: [...SEQUENTIAL[mode]] },
        text: ["31 days", "0"],
      },
      series: [
        {
          type: "heatmap",
          data: rows.map((r) => [
            months.indexOf(r.month),
            datasets.indexOf(r.dataset),
            r.days_with_data,
          ]),
          itemStyle: { borderColor: CHROME[mode].surface, borderWidth: 2, borderRadius: 3 },
        },
      ],
    };
  }, [q.data, mode]);
  if (q.isPending) return <Skeleton height={260} />;
  if (q.isError) return <ErrorState error={q.error as unknown} />;
  return (
    <Card title="History coverage" subtitle="Days with data per dataset and month">
      {option ? (
        <Chart
          option={option}
          height={Math.max(220, 26 * (q.data?.datasets.length ?? 0) + 80)}
          ariaLabel="Synced days per dataset and month"
        />
      ) : (
        <EmptyState title="Nothing synced yet" />
      )}
    </Card>
  );
}

export default function SyncPage() {
  const status = api.useQuery(
    "get",
    "/api/sync/status",
    {},
    { refetchInterval: (q) => (q.state.data?.running ? 5000 : false) },
  );
  return (
    <>
      <PageHeader
        title="Sync & settings"
        description="Connect Garmin, watch the sync and see how much of your history is in the database."
      />
      {status.isPending ? (
        <Skeleton height={240} />
      ) : status.isError ? (
        <ErrorState error={status.error as unknown} />
      ) : (
        <div className="grid gap-5 lg:grid-cols-2">
          <Connection s={status.data} />
          <Card title="Recent sync runs">
            {status.data.last_runs.length === 0 ? (
              <EmptyState title="No sync runs yet" />
            ) : (
              <ScrollArea label="Recent sync runs" className="max-h-80 overflow-auto">
                <table className="w-full text-sm tabular">
                  <thead className="sticky top-0 bg-surface text-xs text-ink-3">
                    <tr>
                      {["Started", "Kind", "Duration", "Requests", "Items", "Status"].map((h) => (
                        <th
                          key={h}
                          scope="col"
                          className="py-1.5 pr-3 text-left font-medium last:pr-0"
                        >
                          {h}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {status.data.last_runs.map((r) => (
                      <tr key={r.id} className="border-t border-line">
                        <td className="py-1.5 pr-3 whitespace-nowrap text-ink-2">
                          {fmtDateTime(r.started_at)}
                        </td>
                        <td className="py-1.5 pr-3 text-ink">{titleCase(r.kind)}</td>
                        <td className="py-1.5 pr-3 text-ink-2">
                          {duration(r.started_at, r.finished_at)}
                        </td>
                        <td className="py-1.5 pr-3 text-ink-2">{fmtNumber(r.requests)}</td>
                        <td className="py-1.5 pr-3 text-ink-2">{fmtNumber(r.items_written)}</td>
                        <td className="py-1.5">
                          {r.status === "ok" ? (
                            <CheckCircle2 size={16} color="var(--good)" aria-label="ok" />
                          ) : r.status === "running" ? (
                            <Loader2
                              size={16}
                              className="animate-spin text-accent"
                              aria-label="running"
                            />
                          ) : (
                            <TriangleAlert size={16} color="var(--critical)" aria-label="error" />
                          )}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </ScrollArea>
            )}
          </Card>
          <div className="lg:col-span-2">
            <Coverage />
          </div>
          {status.data.recent_errors.length > 0 && (
            <Card
              title="Recent problems"
              subtitle="Data that could not be read; usually retried automatically"
              className="lg:col-span-2"
            >
              <ul className="flex flex-col gap-2 text-sm">
                {status.data.recent_errors.slice(0, 10).map((e, i) => (
                  <li key={i} className="flex gap-2 text-ink-2">
                    <KeyRound size={14} className="mt-1 shrink-0 text-ink-3" aria-hidden />
                    <span>
                      <span className="font-medium text-ink">{titleCase(e.dataset)}</span>{" "}
                      {e.key ?? ""} — {e.error}
                    </span>
                  </li>
                ))}
              </ul>
            </Card>
          )}
        </div>
      )}
    </>
  );
}
