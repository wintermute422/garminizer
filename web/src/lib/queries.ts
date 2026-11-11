/** Loading / error / ready state of one or several query results (rendered by `QueryState`). */

/** The slice of a query result that loading / error / content rendering needs. */
export interface QueryLike<T> {
  data?: T;
  isPending: boolean;
  error: unknown;
}

/** Data of each query in a tuple of queries. */
export type QueryData<Qs extends readonly QueryLike<unknown>[]> = {
  [K in keyof Qs]: Exclude<Qs[K]["data"], undefined>;
};

export type QueriesState<Qs extends readonly QueryLike<unknown>[]> =
  | { state: "loading" }
  | { state: "error"; error: unknown }
  | { state: "ready"; data: QueryData<Qs> };

/**
 * Where a set of queries stands: "loading" while any is pending, then "error" with the first
 * error in order, "loading" again while any still has no data, else "ready" with every data.
 */
export function queriesState<Qs extends readonly QueryLike<unknown>[]>(
  queries: readonly [...Qs],
): QueriesState<Qs> {
  if (queries.some((q) => q.isPending)) return { state: "loading" };
  const failed = queries.find((q) => q.error);
  if (failed) return { state: "error", error: failed.error };
  if (queries.some((q) => q.data === undefined)) return { state: "loading" };
  return { state: "ready", data: queries.map((q) => q.data) as QueryData<Qs> };
}
