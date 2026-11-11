import { describe, expect, it } from "vitest";
import { queriesState, type QueryLike } from "./queries";

const pending: QueryLike<number> = { isPending: true, error: null };
const ok = <T>(data: T): QueryLike<T> => ({ data, isPending: false, error: null });
const failed = (error: unknown): QueryLike<number> => ({ isPending: false, error });

describe("queriesState", () => {
  it("is ready with every data in order", () => {
    expect(queriesState([ok(1), ok("a")])).toEqual({ state: "ready", data: [1, "a"] });
  });

  it("waits while any query is pending, even when another failed", () => {
    expect(queriesState([ok(1), pending])).toEqual({ state: "loading" });
    expect(queriesState([failed("boom"), pending])).toEqual({ state: "loading" });
  });

  it("reports the first error in order", () => {
    expect(queriesState([ok(1), failed("first"), failed("second")])).toEqual({
      state: "error",
      error: "first",
    });
  });

  it("treats settled queries without data (disabled) as loading", () => {
    expect(queriesState([ok(1), { isPending: false, error: null }])).toEqual({ state: "loading" });
  });
});
