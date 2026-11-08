/**
 * Typed API access. `schema.d.ts` is generated from the backend's OpenAPI schema by
 * scripts/gen_api_types.sh — never edit it by hand.
 *
 *   const { data } = api.useQuery("get", "/api/meta");
 *   const { data } = api.useQuery("get", "/api/activities/{activity_id}", {
 *     params: { path: { activity_id: id } },
 *   });
 */
import { QueryClient } from "@tanstack/react-query";
import createFetchClient from "openapi-fetch";
import createClient from "openapi-react-query";
import type { components, paths } from "./schema";

export type Schemas = components["schemas"];

export const fetchClient = createFetchClient<paths>({
  baseUrl: "",
  headers: { "X-Requested-With": "garminizer" },
  credentials: "same-origin",
});

export const api = createClient(fetchClient);

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 60_000,
      gcTime: 10 * 60_000,
      refetchOnWindowFocus: false,
      retry: (count, error) => {
        const status = (error as { status?: number } | null)?.status;
        return status !== 401 && status !== 404 && count < 2;
      },
    },
  },
});
