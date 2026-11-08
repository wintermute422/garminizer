/** Theme and unit preferences (per browser; stored in localStorage when available). */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import type { UnitSystem } from "./format";
import type { Mode } from "./tokens";

export type ThemeChoice = "system" | "light" | "dark";

interface Preferences {
  theme: ThemeChoice;
  mode: Mode;
  setTheme: (t: ThemeChoice) => void;
  units: UnitSystem;
  setUnits: (u: UnitSystem) => void;
}

const Ctx = createContext<Preferences | null>(null);

function read(key: string): string | null {
  try {
    return window.localStorage.getItem(key);
  } catch {
    return null;
  }
}

function write(key: string, value: string): void {
  try {
    window.localStorage.setItem(key, value);
  } catch {
    /* private mode etc. — preference just isn't remembered */
  }
}

function systemMode(): Mode {
  return window.matchMedia?.("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

export function PreferencesProvider({
  children,
  defaultUnits = "metric",
}: {
  children: ReactNode;
  defaultUnits?: UnitSystem;
}) {
  const [theme, setThemeState] = useState<ThemeChoice>(
    () => (read("gz.theme") as ThemeChoice | null) ?? "dark",
  );
  const [system, setSystem] = useState<Mode>(systemMode);
  const [units, setUnitsState] = useState<UnitSystem | null>(
    () => read("gz.units") as UnitSystem | null,
  );

  useEffect(() => {
    const mq = window.matchMedia?.("(prefers-color-scheme: dark)");
    if (!mq) return;
    const onChange = () => setSystem(mq.matches ? "dark" : "light");
    mq.addEventListener("change", onChange);
    return () => mq.removeEventListener("change", onChange);
  }, []);

  const mode: Mode = theme === "system" ? system : theme;
  useEffect(() => {
    document.documentElement.dataset.theme = mode;
  }, [mode]);

  const setTheme = useCallback((t: ThemeChoice) => {
    setThemeState(t);
    write("gz.theme", t);
  }, []);
  const setUnits = useCallback((u: UnitSystem) => {
    setUnitsState(u);
    write("gz.units", u);
  }, []);

  const value = useMemo(
    () => ({ theme, mode, setTheme, units: units ?? defaultUnits, setUnits }),
    [theme, mode, setTheme, units, defaultUnits, setUnits],
  );
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function usePreferences(): Preferences {
  const ctx = useContext(Ctx);
  if (!ctx) throw new Error("usePreferences outside PreferencesProvider");
  return ctx;
}

export const useMode = (): Mode => usePreferences().mode;
export const useUnits = (): UnitSystem => usePreferences().units;
