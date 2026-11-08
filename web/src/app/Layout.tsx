import { Link, Outlet, useRouterState } from "@tanstack/react-router";
import { clsx } from "clsx";
import { Menu, Monitor, Moon, Sun, X } from "lucide-react";
import { useEffect, useState } from "react";
import { api } from "@/api/client";
import { usePreferences, type ThemeChoice } from "@/lib/preferences";
import { FilterBar } from "./FilterBar";
import { NAV, navItemFor } from "./nav";

function Logo() {
  return (
    <Link to="/" className="flex items-center gap-2.5 px-2" aria-label="Garminizer home">
      <svg width="28" height="28" viewBox="0 0 32 32" aria-hidden>
        <rect width="32" height="32" rx="9" fill="var(--accent)" />
        <path
          d="M7 20l5-7 4 5 3-4 6 8"
          fill="none"
          stroke="#fff"
          strokeWidth="2.4"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <span className="text-[15px] font-semibold tracking-tight text-ink">Garminizer</span>
    </Link>
  );
}

function Nav({ onNavigate }: { onNavigate?: () => void }) {
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const active = navItemFor(pathname);
  return (
    <nav aria-label="Main" className="flex flex-col gap-5">
      {NAV.map((section) => (
        <div key={section.section}>
          <p className="mb-1 px-3 text-[11px] font-semibold tracking-wide text-ink-3 uppercase">
            {section.section}
          </p>
          <ul className="flex flex-col gap-0.5">
            {section.items.map((item) => {
              const Icon = item.icon;
              const isActive = active?.to === item.to;
              return (
                <li key={item.to}>
                  <Link
                    to={item.to}
                    search={(prev: Record<string, unknown>) => prev}
                    onClick={onNavigate}
                    aria-current={isActive ? "page" : undefined}
                    className={clsx(
                      "flex items-center gap-3 rounded-xl px-3 py-2 text-sm font-medium transition-colors",
                      isActive
                        ? "bg-accent-soft text-ink"
                        : "text-ink-2 hover:bg-surface-2 hover:text-ink",
                    )}
                  >
                    <Icon size={18} aria-hidden className={isActive ? "text-accent" : undefined} />
                    {item.label}
                  </Link>
                </li>
              );
            })}
          </ul>
        </div>
      ))}
    </nav>
  );
}

function Preferences() {
  const { theme, setTheme, units, setUnits } = usePreferences();
  const themes: { value: ThemeChoice; icon: typeof Sun; label: string }[] = [
    { value: "light", icon: Sun, label: "Light theme" },
    { value: "dark", icon: Moon, label: "Dark theme" },
    { value: "system", icon: Monitor, label: "System theme" },
  ];
  return (
    <div className="flex items-center gap-2">
      <div
        role="radiogroup"
        aria-label="Theme"
        className="inline-flex rounded-xl border border-line bg-surface-2 p-0.5"
      >
        {themes.map((t) => (
          <button
            key={t.value}
            type="button"
            role="radio"
            aria-checked={theme === t.value}
            aria-label={t.label}
            title={t.label}
            onClick={() => setTheme(t.value)}
            className={clsx(
              "rounded-[10px] p-1.5",
              theme === t.value ? "bg-surface text-ink shadow-card" : "text-ink-3 hover:text-ink",
            )}
          >
            <t.icon size={15} aria-hidden />
          </button>
        ))}
      </div>
      <div
        role="radiogroup"
        aria-label="Units"
        className="inline-flex rounded-xl border border-line bg-surface-2 p-0.5"
      >
        {(["metric", "imperial"] as const).map((u) => (
          <button
            key={u}
            type="button"
            role="radio"
            aria-checked={units === u}
            onClick={() => setUnits(u)}
            className={clsx(
              "rounded-[10px] px-2 py-1 text-xs font-medium",
              units === u ? "bg-surface text-ink shadow-card" : "text-ink-3 hover:text-ink",
            )}
          >
            {u === "metric" ? "km" : "mi"}
          </button>
        ))}
      </div>
    </div>
  );
}

function DemoBanner() {
  const meta = api.useQuery("get", "/api/meta");
  if (!meta.data?.athlete?.is_demo) return null;
  return (
    <div
      className="border-b border-line bg-accent-soft px-4 py-2 text-center text-xs text-ink-2"
      data-testid="demo-banner"
    >
      You are looking at <strong className="font-semibold text-ink">synthetic demo data</strong>.{" "}
      <Link to="/sync" className="font-semibold text-ink underline underline-offset-2">
        Connect your Garmin account
      </Link>{" "}
      to see your own.
    </div>
  );
}

export function Layout() {
  const [open, setOpen] = useState(false);
  const pathname = useRouterState({ select: (s) => s.location.pathname });
  const item = navItemFor(pathname);
  useEffect(() => {
    document.title = item ? `${item.label} · Garminizer` : "Garminizer";
  }, [item]);

  return (
    <div className="min-h-screen bg-page">
      <DemoBanner />
      <div className="mx-auto flex max-w-[1680px]">
        <aside className="sticky top-0 hidden h-screen w-60 shrink-0 flex-col gap-6 overflow-y-auto border-r border-line px-3 py-5 lg:flex">
          <Logo />
          <Nav />
        </aside>
        {open && (
          <div
            className="fixed inset-0 z-40 lg:hidden"
            role="dialog"
            aria-modal="true"
            aria-label="Navigation"
          >
            <button
              type="button"
              aria-label="Close navigation"
              className="absolute inset-0 bg-black/40"
              onClick={() => setOpen(false)}
            />
            <div className="absolute inset-y-0 left-0 flex w-72 flex-col gap-6 overflow-y-auto bg-surface px-3 py-5 shadow-card">
              <div className="flex items-center justify-between">
                <Logo />
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  aria-label="Close navigation"
                  className="rounded-lg p-2 text-ink-2 hover:bg-surface-2"
                >
                  <X size={18} />
                </button>
              </div>
              <Nav onNavigate={() => setOpen(false)} />
            </div>
          </div>
        )}
        <div className="flex min-w-0 flex-1 flex-col">
          <header className="sticky top-0 z-30 flex flex-wrap items-center gap-3 border-b border-line bg-page/85 px-4 py-3 backdrop-blur sm:px-6">
            <button
              type="button"
              onClick={() => setOpen(true)}
              aria-label="Open navigation"
              className="rounded-lg p-2 text-ink-2 hover:bg-surface-2 lg:hidden"
            >
              <Menu size={18} />
            </button>
            <div className="min-w-0 flex-1">
              {item?.filters ? (
                <FilterBar withSport={item.filters === "range+sport"} />
              ) : (
                <span className="text-sm font-medium text-ink-2 lg:hidden">Garminizer</span>
              )}
            </div>
            <Preferences />
          </header>
          <main className="min-w-0 flex-1 px-4 py-6 sm:px-6 lg:px-8">
            <Outlet />
          </main>
        </div>
      </div>
    </div>
  );
}
