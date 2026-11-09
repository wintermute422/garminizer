import { QueryClientProvider } from "@tanstack/react-query";
import { RouterProvider } from "@tanstack/react-router";
import { StrictMode, type ReactNode } from "react";
import { createRoot } from "react-dom/client";
import { api, queryClient } from "@/api/client";
import { AuthGate } from "@/app/AuthGate";
import { router } from "@/app/router";
import { PreferencesProvider } from "@/lib/preferences";
import "@fontsource-variable/inter";
import "./styles.css";

/** The athlete's Garmin unit setting is the default until the viewer picks one. */
function WithPreferences({ children }: { children: ReactNode }) {
  const meta = api.useQuery("get", "/api/meta");
  const units = meta.data?.athlete?.unit_system === "statute" ? "imperial" : "metric";
  return <PreferencesProvider defaultUnits={units}>{children}</PreferencesProvider>;
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <AuthGate>
        <WithPreferences>
          <RouterProvider router={router} />
        </WithPreferences>
      </AuthGate>
    </QueryClientProvider>
  </StrictMode>,
);
