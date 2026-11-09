import { useQueryClient } from "@tanstack/react-query";
import { useState, type FormEvent, type ReactNode } from "react";
import { api } from "@/api/client";
import { Skeleton } from "@/components/ui";

/** Shows a login form when the server runs with APP_PASSWORD and no session exists. */
export function AuthGate({ children }: { children: ReactNode }) {
  const status = api.useQuery("get", "/api/auth/status");
  const login = api.useMutation("post", "/api/auth/login");
  const qc = useQueryClient();
  const [password, setPassword] = useState("");

  if (status.isPending) return <Skeleton height={240} className="m-8" />;
  if (!status.data?.required || status.data.authenticated) return <>{children}</>;

  const submit = (e: FormEvent) => {
    e.preventDefault();
    login.mutate({ body: { password } }, { onSuccess: () => qc.invalidateQueries() });
  };

  return (
    <main className="flex min-h-screen items-center justify-center bg-page px-4">
      <form
        onSubmit={submit}
        className="w-full max-w-sm rounded-card border border-line border-t-2 border-t-rule bg-surface p-6 shadow-card"
      >
        <h1 className="text-xl font-semibold tracking-tight text-ink">Garminizer</h1>
        <p className="mt-1 text-sm text-ink-2">This dashboard is password protected.</p>
        <label htmlFor="password" className="mt-5 block text-eyebrow text-ink-2 uppercase">
          Password
        </label>
        <input
          id="password"
          type="password"
          autoComplete="current-password"
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          className="mt-1 w-full rounded-control border border-line-strong bg-surface px-3 py-2 text-sm text-ink"
          required
        />
        {login.error && (
          <p role="alert" className="mt-2 text-xs text-critical-text">
            {(login.error as { detail?: string }).detail ?? "Login failed"}
          </p>
        )}
        <button
          type="submit"
          disabled={login.isPending}
          className="mt-4 w-full rounded-control bg-action px-3 py-2.5 text-sm font-semibold text-on-action transition-colors hover:bg-action-hover disabled:opacity-60"
        >
          Sign in
        </button>
      </form>
    </main>
  );
}
