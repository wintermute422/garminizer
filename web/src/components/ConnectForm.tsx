import { useQueryClient } from "@tanstack/react-query";
import { Loader2, ShieldCheck } from "lucide-react";
import { useState, type FormEvent } from "react";
import { api } from "@/api/client";

/** Garmin sign-in (e-mail + password, then the MFA code when Garmin asks for one). */
export function ConnectForm({ mfaPending }: { mfaPending: boolean }) {
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
            className="rounded-control border border-line bg-surface-2 px-3 py-2 text-sm text-ink"
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
            className="rounded-control border border-line bg-surface-2 px-3 py-2 text-sm text-ink"
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
            className="rounded-control border border-line bg-surface-2 px-3 py-2 text-sm tracking-widest text-ink"
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
        className="inline-flex items-center justify-center gap-2 rounded-control bg-action px-4 py-2 text-sm font-semibold text-on-action transition-colors hover:bg-action-hover disabled:opacity-60"
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
