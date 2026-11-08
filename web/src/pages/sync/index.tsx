import { useQueryClient } from "@tanstack/react-query";
import {
  Check,
  CheckCircle2,
  Copy,
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
import { DASH, fmtDate, fmtMonth, fmtNumber, fmtWeight, titleCase } from "@/lib/format";
import { useMode, useUnits } from "@/lib/preferences";

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

function CopyCommand({ command }: { command: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <div className="mt-3 flex items-center gap-2 rounded-xl border border-line bg-surface-2 py-1.5 pr-1.5 pl-3">
      <code className="min-w-0 flex-1 truncate font-mono text-xs text-ink">{command}</code>
      <button
        type="button"
        onClick={() => {
          void navigator.clipboard?.writeText(command).then(() => {
            setCopied(true);
            window.setTimeout(() => setCopied(false), 1500);
          });
        }}
        className="inline-flex shrink-0 items-center gap-1.5 rounded-lg px-2 py-1 text-xs font-medium text-ink-2 hover:bg-surface hover:text-ink"
      >
        {copied ? <Check size={14} aria-hidden /> : <Copy size={14} aria-hidden />}
        {copied ? "Copied" : "Copy"}
      </button>
    </div>
  );
}

function Connection({ s }: { s: Status }) {
  const qc = useQueryClient();
  const run = api.useMutation("post", "/api/sync/run");
  const disconnect = api.useMutation("post", "/api/sync/disconnect");
  const refresh = () => qc.invalidateQueries();

  if (s.is_demo) {
    return (
      <Card title="Garmin connection" actions={<StatusPill status={null} label="Demo data" />}>
        <div className="flex items-start gap-3">
          <Database size={20} className="mt-0.5 shrink-0 text-ink-3" aria-hidden />
          <div className="text-sm text-ink-2">
            <p className="font-medium text-ink">This database holds the synthetic demo athlete.</p>
            <p className="mt-1">
              Real Garmin data is never mixed into it. Start the main stack from the project folder,
              open <span className="font-medium text-ink">localhost:8420</span> and connect your
              account there:
            </p>
          </div>
        </div>
        <CopyCommand command="docker compose up -d" />
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
    <Card
      title="Garmin connection"
      actions={
        <StatusPill
          status={s.running ? null : "good"}
          label={s.running ? "Syncing…" : "Connected"}
        />
      }
    >
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
        Data from {fmtDate(s.first_day)} to {fmtDate(s.last_day)}. The background worker syncs every
        few hours and keeps loading older history until it reaches your first Garmin day.
      </p>
    </Card>
  );
}

function RunStatus({ status }: { status: string }) {
  if (status === "ok")
    return (
      <span className="inline-flex items-center gap-1 text-ink-2">
        <CheckCircle2 size={14} color="var(--good)" aria-hidden /> Done
      </span>
    );
  if (status === "running")
    return (
      <span className="inline-flex items-center gap-1 text-ink-2">
        <Loader2 size={14} className="animate-spin text-accent" aria-hidden /> Running
      </span>
    );
  return (
    <span className="inline-flex items-center gap-1 text-ink-2">
      <TriangleAlert size={14} color="var(--critical)" aria-hidden /> {titleCase(status)}
    </span>
  );
}

function Runs({ runs }: { runs: Status["last_runs"] }) {
  if (runs.length === 0) return <EmptyState title="No sync runs yet" />;
  return (
    <>
      <ul className="divide-y divide-line text-sm tabular sm:hidden">
        {runs.map((r) => (
          <li key={r.id} className="flex items-center justify-between gap-3 py-2">
            <span className="min-w-0">
              <span className="block text-ink">
                {titleCase(r.kind)} · {fmtDateTime(r.started_at)}
              </span>
              <span className="block text-xs text-ink-3">
                {duration(r.started_at, r.finished_at)} · {fmtNumber(r.requests)} requests ·{" "}
                {fmtNumber(r.items_written)} items
              </span>
            </span>
            <span className="shrink-0 text-xs">
              <RunStatus status={r.status} />
            </span>
          </li>
        ))}
      </ul>
      <ScrollArea label="Recent sync runs" className="hidden max-h-80 overflow-auto sm:block">
        <table className="w-full text-sm tabular">
          <thead className="sticky top-0 bg-surface text-xs text-ink-3">
            <tr>
              {["Started", "Kind", "Duration", "Requests", "Items", "Status"].map((h) => (
                <th key={h} scope="col" className="py-1.5 pr-3 text-left font-medium last:pr-0">
                  {h}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {runs.map((r) => (
              <tr key={r.id} className="border-t border-line">
                <td className="py-1.5 pr-3 whitespace-nowrap text-ink-2">
                  {fmtDateTime(r.started_at)}
                </td>
                <td className="py-1.5 pr-3 text-ink">{titleCase(r.kind)}</td>
                <td className="py-1.5 pr-3 text-ink-2">{duration(r.started_at, r.finished_at)}</td>
                <td className="py-1.5 pr-3 text-ink-2">{fmtNumber(r.requests)}</td>
                <td className="py-1.5 pr-3 text-ink-2">{fmtNumber(r.items_written)}</td>
                <td className="py-1.5 text-xs whitespace-nowrap">
                  <RunStatus status={r.status} />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </ScrollArea>
    </>
  );
}

/** Per-dataset backfill cursor: how far back each dataset has been loaded. */
function Progress({ cursors }: { cursors: Status["cursors"] }) {
  if (cursors.length === 0) return null;
  const done = cursors.filter((c) => c.complete).length;
  return (
    <Card
      title="History loaded per dataset"
      subtitle={`${done} of ${cursors.length} datasets reach your first Garmin day`}
    >
      <ul className="grid gap-x-6 text-sm sm:grid-cols-2">
        {cursors.map((c) => (
          <li
            key={c.dataset}
            className="flex items-center justify-between gap-3 border-t border-line py-1.5"
          >
            <span className="min-w-0 truncate text-ink">{titleCase(c.dataset)}</span>
            <span className="flex shrink-0 items-center gap-2 text-xs text-ink-2 tabular">
              {c.oldest_day ? `${fmtDate(c.oldest_day)} – ${fmtDate(c.newest_day)}` : "not yet"}
              {c.complete ? (
                <CheckCircle2 size={14} color="var(--good)" aria-label="complete" />
              ) : (
                <Loader2 size={14} className="text-ink-3" aria-label="loading older days" />
              )}
            </span>
          </li>
        ))}
      </ul>
    </Card>
  );
}

function Profile() {
  const meta = api.useQuery("get", "/api/meta");
  const units = useUnits();
  const a = meta.data?.athlete;
  if (meta.isPending) return <Skeleton height={220} />;
  if (!a) return null;
  const zones = a.hr_zones?.slice(0, 5) ?? [];
  const items: [string, string][] = [
    ["Max heart rate", a.max_hr ? `${a.max_hr} bpm` : DASH],
    ["Resting heart rate", a.resting_hr ? `${a.resting_hr} bpm` : DASH],
    ["Lactate threshold", a.lactate_threshold_hr ? `${a.lactate_threshold_hr} bpm` : DASH],
    ["Functional threshold power", a.ftp_w ? `${a.ftp_w} W` : DASH],
    ["Weight", fmtWeight(a.weight_kg, units)],
    ["Time zone", a.time_zone ?? DASH],
  ];
  return (
    <Card
      title="Profile used for the analysis"
      subtitle="Read from Garmin Connect; change them there and the next sync picks them up"
    >
      <dl className="grid gap-x-6 text-sm sm:grid-cols-2">
        {items.map(([k, v]) => (
          <div key={k} className="flex justify-between gap-3 border-t border-line py-1.5">
            <dt className="text-ink-2">{k}</dt>
            <dd className="text-ink tabular">{v}</dd>
          </div>
        ))}
      </dl>
      {zones.length === 5 && (
        <div className="mt-3">
          <p className="mb-1.5 text-xs text-ink-3">Heart-rate zones (lower limit, bpm)</p>
          <ol className="grid grid-cols-5 gap-1 text-center text-xs tabular">
            {zones.map((z, i) => (
              <li key={i} className="rounded-lg bg-surface-2 py-1.5">
                <span className="block text-ink-3">Z{i + 1}</span>
                <span className="block font-medium text-ink">{fmtNumber(z)}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
    </Card>
  );
}

function Coverage({ isDemo }: { isDemo: boolean }) {
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
          return `${titleCase(datasets[v[1]])}<br/>${fmtMonth(`${months[v[0]]}-01`)}: <b>${v[2]}</b> days with data`;
        },
      },
      xAxis: {
        type: "category",
        data: months.map((m) => fmtMonth(`${m}-01`)),
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
  const months = new Set(q.data.months.map((r) => r.month)).size;
  return (
    <Card title="History coverage" subtitle="Days with data per dataset and month">
      {option ? (
        <ScrollArea label="History coverage" className="overflow-x-auto">
          <div style={{ minWidth: Math.max(480, 160 + months * 44) }}>
            <Chart
              option={option}
              height={Math.max(220, 26 * new Set(q.data.months.map((r) => r.dataset)).size + 80)}
              ariaLabel="Synced days per dataset and month"
            />
          </div>
        </ScrollArea>
      ) : isDemo ? (
        <EmptyState title="Not tracked for the demo athlete">
          The demo data is generated straight into the database, so there is no download history to
          chart. With your own account this shows which months have been loaded.
        </EmptyState>
      ) : (
        <EmptyState title="Nothing downloaded yet">
          The first sync fills this in; it starts automatically after you connect.
        </EmptyState>
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
            <Runs runs={status.data.last_runs} />
          </Card>
          <div className="lg:col-span-2">
            <Coverage isDemo={status.data.is_demo} />
          </div>
          {!status.data.is_demo && <Progress cursors={status.data.cursors} />}
          <Profile />
          {status.data.recent_errors.length > 0 && (
            <Card
              title="Recent problems"
              subtitle="Data that could not be read; usually retried automatically"
              className="lg:col-span-2"
            >
              <ul className="flex flex-col gap-2 text-sm">
                {status.data.recent_errors.slice(0, 10).map((e) => (
                  <li key={e.id} className="flex gap-2 text-ink-2">
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
