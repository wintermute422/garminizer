/** Routes. Every page lives in src/pages/<name>/index.tsx and is code-split. */
import {
  createRootRoute,
  createRoute,
  createRouter,
  lazyRouteComponent,
} from "@tanstack/react-router";
import { validateGlobalSearch } from "@/lib/range";
import { Layout } from "./Layout";

const rootRoute = createRootRoute({
  component: Layout,
  validateSearch: validateGlobalSearch,
});

const page = <P extends string>(
  path: P,
  load: () => Promise<{ default: () => React.ReactElement }>,
) => createRoute({ getParentRoute: () => rootRoute, path, component: lazyRouteComponent(load) });

export const activityRoute = createRoute({
  getParentRoute: () => rootRoute,
  path: "/activities/$activityId",
  component: lazyRouteComponent(() => import("@/pages/activity")),
});

const routeTree = rootRoute.addChildren([
  page("/", () => import("@/pages/overview")),
  page("/activities", () => import("@/pages/activities")),
  activityRoute,
  page("/training", () => import("@/pages/training")),
  page("/performance", () => import("@/pages/performance")),
  page("/records", () => import("@/pages/records")),
  page("/health", () => import("@/pages/health")),
  page("/sleep", () => import("@/pages/sleep")),
  page("/body", () => import("@/pages/body")),
  page("/calendar", () => import("@/pages/calendar")),
  page("/map", () => import("@/pages/map")),
  page("/insights", () => import("@/pages/insights")),
  page("/gear", () => import("@/pages/gear")),
  page("/year", () => import("@/pages/year")),
  page("/sync", () => import("@/pages/sync")),
]);

export const router = createRouter({
  routeTree,
  defaultPreload: "intent",
  scrollRestoration: true,
});

declare module "@tanstack/react-router" {
  interface Register {
    router: typeof router;
  }
}
